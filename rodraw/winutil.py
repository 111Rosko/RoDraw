"""Thin Win32 helpers for overlay behaviour.

Sleep mode needs the overlay to stop receiving mouse input while staying
visible. Qt can do that with WindowTransparentForInput, but changing that flag
forces the window to be recreated (visible flicker, lost z-order). Toggling
WS_EX_TRANSPARENT directly takes effect immediately instead.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# 64-bit safe accessors; the *Ptr variants only exist on 64-bit builds.
if hasattr(user32, "GetWindowLongPtrW"):
    _get_long = user32.GetWindowLongPtrW
    _set_long = user32.SetWindowLongPtrW
    _get_long.restype = ctypes.c_longlong
    _set_long.restype = ctypes.c_longlong
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
else:  # pragma: no cover - 32-bit fallback
    _get_long = user32.GetWindowLongW
    _set_long = user32.SetWindowLongW


def set_click_through(hwnd: int, enabled: bool) -> None:
    """Let mouse input pass straight through the window to whatever is below."""
    if not hwnd:
        return
    handle = wintypes.HWND(hwnd)
    style = _get_long(handle, GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    else:
        style &= ~WS_EX_TRANSPARENT
    _set_long(handle, GWL_EXSTYLE, style)


def raise_topmost(hwnd: int, activate: bool = False) -> None:
    """Re-assert always-on-top without stealing focus unless asked."""
    if not hwnd:
        return
    flags = SWP_NOMOVE | SWP_NOSIZE
    if not activate:
        flags |= SWP_NOACTIVATE
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST),
                        0, 0, 0, 0, flags)


# ---------------------------------------------------------------- startup

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "RoDraw"


def set_run_at_startup(enabled: bool, command: str) -> bool:
    """Add or remove RoDraw from the current user's sign-in programs.

    Per-user (HKCU) only -- never machine-wide, so it needs no elevation and
    cannot affect anyone else who uses the PC.
    """
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# --------------------------------------------------------- single instance

ERROR_ALREADY_EXISTS = 183


def has_touch_screen() -> bool:
    """Whether Windows reports a usable touch digitiser.

    SM_DIGITIZER carries capability bits; NID_READY (0x80) means a digitiser
    is attached and switched on, which is the one that matters -- a machine
    can report touch support in the abstract and have nothing plugged in.
    The touch-point count is checked too, because some interactive-board
    drivers set the ready bit while reporting no contacts.
    """
    try:
        user32 = ctypes.windll.user32
        SM_DIGITIZER, SM_MAXIMUMTOUCHES = 94, 95
        NID_READY = 0x80
        flags = user32.GetSystemMetrics(SM_DIGITIZER)
        return bool(flags & NID_READY) and user32.GetSystemMetrics(SM_MAXIMUMTOUCHES) > 0
    except Exception:
        return False


def claim_single_instance(name: str = "RoDraw.SingleInstance.Mutex"):
    """Return the mutex handle, or None if another copy is already running.

    The handle must be kept alive for the process lifetime; dropping it
    releases the claim.
    """
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True  # cannot tell -- fail open rather than refuse to start
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        ctypes.windll.kernel32.CloseHandle(handle)
        return None
    return handle


# ------------------------------------------------------------ window shape

gdi32 = ctypes.windll.gdi32
RGN_DIFF = 4


def set_window_hole(hwnd: int, width: int, height: int,
                    hole: tuple[int, int, int, int] | None) -> None:
    """Cut `hole` (window-local left, top, right, bottom) out of the window.

    Used to keep the toolbar clickable. Drawing activates the overlay, which
    lifts it above the toolbar inside the always-on-top band, and from then on
    the overlay swallows every click and hover meant for the buttons. Fighting
    that with z-order is a race; removing the area from the window entirely is
    not -- input there goes straight to whatever is behind.
    """
    if not hwnd:
        return
    handle = wintypes.HWND(hwnd)
    if hole is None:
        user32.SetWindowRgn(handle, None, True)
        return

    full = gdi32.CreateRectRgn(0, 0, width, height)
    cut = gdi32.CreateRectRgn(*hole)
    gdi32.CombineRgn(full, full, cut, RGN_DIFF)
    gdi32.DeleteObject(cut)
    # The window takes ownership of `full`; it must not be deleted here.
    user32.SetWindowRgn(handle, full, True)


# ---------------------------------------------------------- wheel hook

WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int,
                               wintypes.WPARAM, wintypes.LPARAM)

# Without these, ctypes assumes a 32-bit int return and truncates the hook
# handle on a 64-bit build -- SetWindowsHookExW then looks like it failed.
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC,
                                     wintypes.HINSTANCE, wintypes.DWORD]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.CallNextHookEx.restype = ctypes.c_longlong
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM]
ctypes.windll.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
ctypes.windll.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class WheelHook:
    """Watch the scroll wheel system-wide, for as long as it is installed.

    The spotlight makes the overlay click-through so the class can still be
    shown a live page, which also means no wheel event is ever delivered to
    it. This is the only way the scroll can reach the spotlight. It is
    installed only while that tool is active and removed the moment it is
    not, and the callback does nothing but arithmetic -- a slow low-level
    hook gets dropped by Windows and would make the whole mouse stutter.
    """

    def __init__(self, on_wheel):
        # on_wheel(steps, x, y) -> True to swallow the scroll
        self._on_wheel = on_wheel
        self._handle = None
        self._proc = _HOOKPROC(self._callback)

    def _callback(self, code, wparam, lparam):
        if code == 0 and wparam == WM_MOUSEWHEEL:
            try:
                data = ctypes.cast(lparam,
                                   ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                delta = ctypes.c_short((data.mouseData >> 16) & 0xFFFF).value
                steps = delta // 120 or (1 if delta > 0 else -1)
                if self._on_wheel(steps, data.pt.x, data.pt.y):
                    return 1              # consumed; nothing else scrolls
            except Exception:
                pass                      # never break the mouse over a bug
        return user32.CallNextHookEx(None, code, wparam, lparam)

    @property
    def installed(self) -> bool:
        return self._handle is not None

    def install(self) -> bool:
        if self._handle is not None:
            return True
        module = ctypes.windll.kernel32.GetModuleHandleW(None)
        self._handle = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc,
                                                module, 0) or None
        return self._handle is not None

    def remove(self) -> None:
        if self._handle is not None:
            user32.UnhookWindowsHookEx(self._handle)
            self._handle = None


def modifier_state() -> tuple[bool, bool]:
    """(ctrl, shift) right now.

    The low-level wheel hook is handed raw mouse data with no modifier flags,
    so the keyboard has to be asked directly.
    """
    down = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)
    return down(0x11), down(0x10)      # VK_CONTROL, VK_SHIFT
