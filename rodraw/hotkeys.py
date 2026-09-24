"""System-wide hotkey registration (Windows).

Sleep mode is only useful if the wake key still works while another
application has focus, so the toggle cannot be an ordinary Qt shortcut. This
wraps Win32 RegisterHotKey and surfaces presses through a Qt native event
filter, which keeps everything on the GUI thread.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter, QElapsedTimer, QObject, pyqtSignal

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {
    "CTRL": MOD_CONTROL,
    "CONTROL": MOD_CONTROL,
    "ALT": MOD_ALT,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN,
    "META": MOD_WIN,
}

# Named keys that are sensible choices for a global toggle.
_NAMED_VK = {
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
    "ENTER": 0x0D, "RETURN": 0x0D, "BACKSPACE": 0x08,
    "INS": 0x2D, "INSERT": 0x2D, "DEL": 0x2E, "DELETE": 0x2E,
    "HOME": 0x24, "END": 0x23, "PGUP": 0x21, "PAGEUP": 0x21,
    "PGDOWN": 0x22, "PAGEDOWN": 0x22,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "PAUSE": 0x13, "SCROLLLOCK": 0x91, "NUMLOCK": 0x90,
    "CAPSLOCK": 0x14, "PRINTSCREEN": 0x2C, "PRTSC": 0x2C,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
for _n in range(1, 25):
    _NAMED_VK[f"F{_n}"] = 0x6F + _n


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """Turn "Ctrl+Alt+S" into (modifiers, virtual-key). None if unparseable."""
    if not text:
        return None
    parts = [p.strip() for p in str(text).split("+") if p.strip()]
    if not parts:
        return None

    # A trailing literal "+" (e.g. "Ctrl++") splits into an empty tail, so the
    # key is whatever survived last; handle the bare "+" case explicitly.
    if text.strip().endswith("+") and len(parts) >= 1:
        parts.append("+")

    mods = 0
    key = None
    for part in parts:
        upper = part.upper()
        if upper in _MODS:
            mods |= _MODS[upper]
        else:
            key = part

    if key is None:
        return None

    upper = key.upper()
    if upper in _NAMED_VK:
        vk = _NAMED_VK[upper]
    elif upper == "+":
        vk = 0xBB  # VK_OEM_PLUS
    elif len(upper) == 1 and (upper.isalpha() or upper.isdigit()):
        vk = ord(upper)
    else:
        return None

    return mods | MOD_NOREPEAT, vk


class _Filter(QAbstractNativeEventFilter):
    """Watches the Qt event loop for WM_HOTKEY messages."""

    def __init__(self, owner: "HotkeyManager"):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            except (TypeError, ValueError):
                return False, 0
            if msg.message == WM_HOTKEY:
                self.owner._fire(int(msg.wParam))
                return True, 0
        return False, 0


class HotkeyManager(QObject):
    """Registers global hotkeys and emits `triggered(name)` when pressed."""

    triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._next_id = 1
        self._by_id: dict[int, str] = {}
        self._by_name: dict[str, int] = {}
        self._filter = _Filter(self)
        self._installed = False
        # Depending on whether the message arrives thread- or window-bound,
        # Windows can deliver the same press twice. For a toggle that would
        # cancel itself out, so collapse bursts.
        self._since_last = QElapsedTimer()
        self._last_fired: str | None = None

    def install(self, app) -> None:
        if not self._installed:
            app.installNativeEventFilter(self._filter)
            self._installed = True

    DEBOUNCE_MS = 250

    def _fire(self, hotkey_id: int) -> None:
        name = self._by_id.get(hotkey_id)
        if not name:
            return
        if (self._last_fired == name and self._since_last.isValid()
                and self._since_last.elapsed() < self.DEBOUNCE_MS):
            return
        self._last_fired = name
        self._since_last.restart()
        self.triggered.emit(name)

    def register(self, name: str, sequence: str) -> bool:
        """(Re)bind `name` to `sequence`. Returns False if Windows refused it,
        which usually means another application already owns that combo."""
        self.unregister(name)
        parsed = parse_hotkey(sequence)
        if parsed is None:
            return False
        mods, vk = parsed
        hotkey_id = self._next_id
        self._next_id += 1
        # hwnd 0 posts to this thread's queue, which Qt's dispatcher pumps.
        if not user32.RegisterHotKey(None, hotkey_id, mods, vk):
            return False
        self._by_id[hotkey_id] = name
        self._by_name[name] = hotkey_id
        return True

    def unregister(self, name: str) -> None:
        hotkey_id = self._by_name.pop(name, None)
        if hotkey_id is not None:
            user32.UnregisterHotKey(None, hotkey_id)
            self._by_id.pop(hotkey_id, None)

    def unregister_all(self) -> None:
        for name in list(self._by_name):
            self.unregister(name)
