"""Post-build check: does the built exe actually come up?

Written after a shipped build failed at import and this test's predecessor
passed anyway. It had only asked "is the process still alive?" -- and
PyInstaller's crash dialog keeps the process alive indefinitely, so a total
startup failure looked identical to success.

So this inspects the windows the process actually puts on screen:

  * any window whose title looks like a crash dialog  -> fail
  * no window titled "RoDraw" within the timeout      -> fail

    python tools/smoke_test.py [path-to-exe]

Exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

import win32gui
import win32process

TIMEOUT_S = 25
EXPECTED_TITLE = "RoDraw"

# PyInstaller, Python faulthandler and Windows error dialogs all announce
# themselves in the title bar.
CRASH_MARKERS = (
    "unhandled exception",
    "failed to execute script",
    "fatal error",
    "has stopped working",
    "application error",
    "traceback",
    "python error",
)


def windows_for_pid(pid: int) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []

    def callback(hwnd, _):
        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        if wpid == pid:
            found.append((hwnd, win32gui.GetWindowText(hwnd),
                          win32gui.GetClassName(hwnd)))
        return True

    win32gui.EnumWindows(callback, None)
    return found


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def overlay_accepts_clicks(pid: int) -> bool:
    """Is a click in the middle of the primary screen delivered to RoDraw?

    Being visible is not the same as being drawable: Windows hit-tests a
    layered window by its alpha channel, so a fully transparent overlay looks
    perfect and silently passes every click to whatever is underneath.
    """
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = [_POINT]

    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    # Away from the toolbar, which sits near the top centre.
    hwnd = user32.WindowFromPoint(_POINT(width // 2, int(height * 0.6)))
    if not hwnd:
        return False
    try:
        _, owner = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return False
    return owner == pid


def already_running() -> list[int]:
    """PIDs of RoDraw instances already up.

    One holds the single-instance mutex, so a fresh launch only shows an
    "already running" message box -- whose title is also "RoDraw". Without
    this check that box looks exactly like a healthy start.
    """
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq RoDraw.exe", "/NH", "/FO", "CSV"],
        capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower().startswith("rodraw"):
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def check(exe: Path) -> int:
    stale = already_running()
    if stale:
        print(f"FAIL: RoDraw is already running (pid {', '.join(map(str, stale))}).")
        print("       It holds the single-instance mutex, so this launch would")
        print("       only produce an 'already running' dialog. Close it first.")
        return 1

    print(f"launching {exe}")
    proc = subprocess.Popen([str(exe)])
    crash: tuple[int, str, str] | None = None
    started = False
    deadline = time.time() + TIMEOUT_S

    try:
        while time.time() < deadline:
            time.sleep(0.5)

            if proc.poll() is not None:
                print(f"FAIL: process exited early with code {proc.returncode}")
                return 1

            visible = [w for w in windows_for_pid(proc.pid) if w[1]]
            for hwnd, title, cls in visible:
                if any(m in title.lower() for m in CRASH_MARKERS):
                    crash = (hwnd, title, cls)
                    break
            if crash:
                break

            # Require a window that is actually overlay-sized. A message box
            # or the toast carries the same title but is tiny.
            min_width = ctypes.windll.user32.GetSystemMetrics(0) * 0.8
            for hwnd, title, _ in visible:
                if title != EXPECTED_TITLE:
                    continue
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                if (right - left) >= min_width and win32gui.IsWindowVisible(hwnd):
                    started = True
                    break
            if started:
                break

        if crash:
            hwnd, title, cls = crash
            print(f"FAIL: crash dialog on screen -- {title!r} (class {cls})")
            # The message body lives in a child control; pull it out so the
            # failure is actionable without a screenshot.
            def dump(child, _):
                text = win32gui.GetWindowText(child)
                if text and len(text) > 20:
                    print("       " + text.replace("\r\n", "\n       ")[:600])
                return True
            win32gui.EnumChildWindows(hwnd, dump, None)
            return 1

        if not started:
            titles = [t for _, t, _ in windows_for_pid(proc.pid) if t]
            print(f"FAIL: no window titled {EXPECTED_TITLE!r} after {TIMEOUT_S}s")
            print(f"       windows seen: {titles or 'none'}")
            return 1

        time.sleep(1.5)
        if not overlay_accepts_clicks(proc.pid):
            print("FAIL: the overlay is on screen but does not accept mouse input")
            print("       Windows hit-tests layered windows by alpha, so a fully")
            print("       transparent overlay is click-through and cannot draw.")
            return 1

        print(f"PASS: {EXPECTED_TITLE} window is up, accepts clicks, no crash dialog")
        return 0

    finally:
        # Ask nicely first: RoDraw quits on a close request and takes its
        # tray icon with it. Force-killing orphans the icon, and Windows
        # leaves the dead copy in the notification area until it is hovered.
        subprocess.run(["taskkill", "/T", "/PID", str(proc.pid)],
                       capture_output=True)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)


if __name__ == "__main__":
    default = Path(__file__).resolve().parents[1] / "dist" / "RoDraw" / "RoDraw.exe"
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not target.exists():
        print(f"FAIL: {target} does not exist")
        sys.exit(1)
    sys.exit(check(target))
