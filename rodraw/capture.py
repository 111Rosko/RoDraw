"""Desktop capture, used by the zoom tool and by save/copy.

The overlay is translucent, so a naive grab would include whatever is already
drawn on it. Callers hand us a `blank` callback that hides the annotation
layer for a frame; we wait for the compositor to catch up, grab, then let the
caller restore. That keeps zoomed screenshots free of doubled strokes.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

# How long to let DWM present a frame after we hide the annotation layer.
COMPOSITOR_SETTLE_S = 0.06


def virtual_geometry() -> QRect:
    """Bounding rect of every monitor, in logical pixels.

    The origin is often negative on multi-monitor setups (a screen placed to
    the left of the primary), so never assume it starts at 0,0.
    """
    screens = QGuiApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    rect = screens[0].geometry()
    for screen in screens[1:]:
        rect = rect.united(screen.geometry())
    return rect


def grab_desktop() -> QPixmap:
    """Composite every monitor into one pixmap in virtual-desktop space."""
    screens = QGuiApplication.screens()
    virt = virtual_geometry()
    dpr = max((s.devicePixelRatio() for s in screens), default=1.0)

    result = QPixmap(int(virt.width() * dpr), int(virt.height() * dpr))
    result.setDevicePixelRatio(dpr)
    result.fill(Qt.GlobalColor.black)

    painter = QPainter(result)
    for screen in screens:
        shot = screen.grabWindow(0)
        if shot.isNull():
            continue
        geo = screen.geometry()
        target = QRectF(geo.x() - virt.x(), geo.y() - virt.y(), geo.width(), geo.height())
        painter.drawPixmap(target, shot, QRectF(shot.rect()))
    painter.end()
    return result


def grab_screen(screen) -> QPixmap:
    """Grab one monitor only, so a magnified view on one screen can never
    show content pulled in from another."""
    shot = screen.grabWindow(0)
    return shot


def grab_screen_clean(screen, blank, restore) -> QPixmap:
    try:
        blank()
        QApplication.processEvents()
        time.sleep(COMPOSITOR_SETTLE_S)
        QApplication.processEvents()
        return grab_screen(screen)
    finally:
        restore()
        QApplication.processEvents()


def grab_desktop_clean(blank, restore) -> QPixmap:
    """Grab the desktop with the annotation layer temporarily suppressed.

    `blank` should make the overlay draw nothing; `restore` puts it back. Both
    run on the GUI thread, and `restore` is guaranteed to run even if the grab
    raises -- otherwise a failed capture would leave the screen blank.
    """
    try:
        blank()
        QApplication.processEvents()
        time.sleep(COMPOSITOR_SETTLE_S)
        QApplication.processEvents()
        return grab_desktop()
    finally:
        restore()
        QApplication.processEvents()
