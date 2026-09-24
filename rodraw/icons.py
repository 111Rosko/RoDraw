"""Toolbar glyphs drawn with QPainter.

Drawing them in code keeps the build to a single binary with no image files
to lose, and lets every glyph re-render crisply at whatever size and tint the
toolbar asks for.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QGuiApplication, QIcon, QPainter, QPainterPath,
                         QPen, QPixmap)

_CACHE: dict[tuple[str, int, str, float, float], QIcon] = {}


def target_ratio() -> float:
    """How many real pixels one logical pixel is worth, at the sharpest
    screen attached.

    A glyph drawn at its logical size is a quarter of the pixels it needs on
    a display scaled to 200% -- a 4K classroom board, typically -- and Windows
    stretches it to fit, which is what makes the toolbar look smeared. Drawing
    at the real pixel count and labelling the result keeps it crisp, and the
    highest ratio is used so it stays crisp after the window is dragged onto
    a sharper screen.
    """
    if QGuiApplication.instance() is None:
        return 1.0
    return max((s.devicePixelRatio() for s in QGuiApplication.screens()),
               default=1.0)


# How much to thicken every stroke for the glyph being drawn. A classroom
# board is glossy and lit from above, and the reflection eats hairlines long
# before it touches a solid shape.
_WEIGHT = 1.0


def _pen(painter: QPainter, color: QColor, width: float = 2.0) -> None:
    painter.setPen(QPen(color, width * _WEIGHT, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _draw(name: str, painter: QPainter, color: QColor, s: float) -> None:
    """Each glyph is drawn inside a 0..s box with a small inset."""
    m = s * 0.18          # margin
    a, b = m, s - m       # usable span

    if name == "select":
        # arrow cursor
        arrow = QPainterPath(QPointF(a, a))
        arrow.lineTo(QPointF(a, b))
        arrow.lineTo(QPointF(a + s * 0.17, b - s * 0.18))
        arrow.lineTo(QPointF(a + s * 0.30, b + s * 0.03))
        arrow.lineTo(QPointF(a + s * 0.40, b - s * 0.02))
        arrow.lineTo(QPointF(a + s * 0.27, b - s * 0.26))
        arrow.lineTo(QPointF(a + s * 0.46, b - s * 0.28))
        arrow.closeSubpath()
        painter.fillPath(arrow, color)

    elif name == "screens":
        _pen(painter, color, s * 0.08)
        painter.drawRoundedRect(QRectF(a, a + s * 0.02, (b - a) * 0.64,
                                       (b - a) * 0.52), s * 0.04, s * 0.04)
        painter.drawRoundedRect(QRectF(a + (b - a) * 0.36, a + s * 0.26,
                                       (b - a) * 0.64, (b - a) * 0.52),
                                s * 0.04, s * 0.04)

    elif name == "pen":
        _pen(painter, color, s * 0.09)
        painter.drawLine(QPointF(a, b), QPointF(a + s * 0.12, b - s * 0.12))
        path = QPainterPath(QPointF(a + s * 0.10, b - s * 0.14))
        path.lineTo(QPointF(b - s * 0.12, a + s * 0.02))
        path.lineTo(QPointF(b, a + s * 0.14))
        path.lineTo(QPointF(a + s * 0.22, b - s * 0.02))
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "highlighter":
        # Chisel-tip marker leaning right, over the wide band it lays down.
        painter.save()
        painter.translate(s * 0.52, s * 0.44)
        painter.rotate(38)
        _pen(painter, color, s * 0.08)
        body_w, body_h = s * 0.26, s * 0.34
        painter.drawRect(QRectF(-body_w / 2, -body_h, body_w, body_h))
        tip = QPainterPath(QPointF(-body_w / 2, 0))
        tip.lineTo(QPointF(body_w / 2, 0))
        tip.lineTo(QPointF(body_w * 0.32, s * 0.20))
        tip.lineTo(QPointF(-body_w * 0.32, s * 0.20))
        tip.closeSubpath()
        painter.fillPath(tip, color)
        painter.restore()
        band = QColor(color)
        band.setAlpha(120)
        painter.fillRect(QRectF(a - s * 0.04, b - s * 0.10,
                                (b - a) + s * 0.08, s * 0.13), band)

    elif name == "eraser":
        # Angled block with the worn-down lower face picked out.
        painter.save()
        painter.translate(s * 0.5, s * 0.52)
        painter.rotate(-35)
        _pen(painter, color, s * 0.08)
        w, h = s * 0.56, s * 0.40
        painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), s * 0.06, s * 0.06)
        painter.drawLine(QPointF(-w / 2, h * 0.12), QPointF(w / 2, h * 0.12))
        smudge = QColor(color)
        smudge.setAlpha(90)
        painter.fillRect(QRectF(-w / 2 + s * 0.02, h * 0.14,
                                w - s * 0.04, h * 0.36 - s * 0.02), smudge)
        painter.restore()

    elif name == "line":
        _pen(painter, color, s * 0.10)
        painter.drawLine(QPointF(a, b), QPointF(b, a))

    elif name == "arrow":
        _pen(painter, color, s * 0.10)
        painter.drawLine(QPointF(a, b), QPointF(b - s * 0.08, a + s * 0.08))
        head = QPainterPath(QPointF(b, a))
        head.lineTo(QPointF(b - s * 0.30, a + s * 0.04))
        head.lineTo(QPointF(b - s * 0.04, a + s * 0.30))
        head.closeSubpath()
        painter.fillPath(head, color)

    elif name == "rect":
        _pen(painter, color, s * 0.10)
        painter.drawRect(QRectF(a, a + s * 0.06, b - a, (b - a) - s * 0.12))

    elif name == "ellipse":
        _pen(painter, color, s * 0.10)
        painter.drawEllipse(QRectF(a, a + s * 0.04, b - a, (b - a) - s * 0.08))

    elif name == "text":
        _pen(painter, color, s * 0.10)
        painter.drawLine(QPointF(a + s * 0.02, a + s * 0.04), QPointF(b - s * 0.02, a + s * 0.04))
        painter.drawLine(QPointF(s / 2, a + s * 0.04), QPointF(s / 2, b))
        painter.drawLine(QPointF(s / 2 - s * 0.16, b), QPointF(s / 2 + s * 0.16, b))

    elif name == "laser":
        painter.setPen(Qt.PenStyle.NoPen)
        faded = QColor(color)
        faded.setAlpha(80)
        painter.setBrush(faded)
        painter.drawEllipse(QPointF(s / 2, s / 2), s * 0.32, s * 0.32)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(s / 2, s / 2), s * 0.15, s * 0.15)

    elif name == "spotlight":
        _pen(painter, color, s * 0.09)
        painter.drawEllipse(QPointF(s / 2, s / 2), s * 0.24, s * 0.24)
        for i in range(8):
            ang = math.radians(i * 45)
            inner = QPointF(s / 2 + math.cos(ang) * s * 0.32,
                            s / 2 + math.sin(ang) * s * 0.32)
            outer = QPointF(s / 2 + math.cos(ang) * s * 0.42,
                            s / 2 + math.sin(ang) * s * 0.42)
            painter.drawLine(inner, outer)

    elif name == "zoom":
        _pen(painter, color, s * 0.10)
        r = s * 0.26
        c = QPointF(s * 0.44, s * 0.44)
        painter.drawEllipse(c, r, r)
        painter.drawLine(QPointF(c.x() + r * 0.72, c.y() + r * 0.72), QPointF(b, b))
        painter.drawLine(QPointF(c.x() - r * 0.5, c.y()), QPointF(c.x() + r * 0.5, c.y()))
        painter.drawLine(QPointF(c.x(), c.y() - r * 0.5), QPointF(c.x(), c.y() + r * 0.5))

    elif name in ("undo", "redo"):
        _pen(painter, color, s * 0.10)
        if name == "redo":
            painter.translate(s, 0)
            painter.scale(-1, 1)
        path = QPainterPath(QPointF(b, b - s * 0.06))
        path.cubicTo(QPointF(b, a + s * 0.10), QPointF(a + s * 0.24, a),
                     QPointF(a + s * 0.06, a + s * 0.20))
        painter.drawPath(path)
        head = QPainterPath(QPointF(a, a + s * 0.12))
        head.lineTo(QPointF(a + s * 0.30, a + s * 0.10))
        head.lineTo(QPointF(a + s * 0.10, a + s * 0.38))
        head.closeSubpath()
        painter.fillPath(head, color)

    elif name == "clear":
        _pen(painter, color, s * 0.10)
        painter.drawLine(QPointF(a + s * 0.04, a + s * 0.10), QPointF(b - s * 0.04, a + s * 0.10))
        painter.drawLine(QPointF(a + s * 0.16, a + s * 0.10), QPointF(a + s * 0.22, b))
        painter.drawLine(QPointF(b - s * 0.16, a + s * 0.10), QPointF(b - s * 0.22, b))
        painter.drawLine(QPointF(a + s * 0.22, b), QPointF(b - s * 0.22, b))

    elif name == "save":
        _pen(painter, color, s * 0.09)
        painter.drawRect(QRectF(a, a, b - a, b - a))
        painter.drawRect(QRectF(a + s * 0.14, a, (b - a) - s * 0.28, s * 0.22))
        painter.drawRect(QRectF(a + s * 0.10, b - s * 0.28, (b - a) - s * 0.20, s * 0.28))

    elif name == "settings":
        # A real cogwheel: flat-topped teeth around a solid ring with a hole.
        # The old radial-spokes version read as a lamp or a sun.
        # Tuned at 19 px, not at 256: long thin teeth blur into a starburst
        # at toolbar size, which is why the first attempt read as a sun.
        # Short wide teeth on a fat body with a big hole survive the shrink.
        teeth = 8
        r_out, r_in, r_hole = s * 0.47, s * 0.355, s * 0.185
        step = math.tau / teeth
        tooth, gap = step * 0.30, step * 0.38
        gear = QPainterPath()
        for i in range(teeth):
            base = i * step
            for radius, angle in ((r_out, base - tooth), (r_out, base + tooth),
                                  (r_in, base + gap), (r_in, base + step - gap)):
                point = QPointF(s / 2 + math.cos(angle) * radius,
                                s / 2 + math.sin(angle) * radius)
                if i == 0 and radius == r_out and angle == base - tooth:
                    gear.moveTo(point)
                else:
                    gear.lineTo(point)
        gear.closeSubpath()
        hole = QPainterPath()
        hole.addEllipse(QPointF(s / 2, s / 2), r_hole, r_hole)
        painter.fillPath(gear.subtracted(hole), color)

    elif name == "sleep":
        # crescent moon
        outer = QPainterPath()
        outer.addEllipse(QPointF(s * 0.52, s * 0.48), s * 0.30, s * 0.30)
        inner = QPainterPath()
        inner.addEllipse(QPointF(s * 0.66, s * 0.38), s * 0.26, s * 0.26)
        painter.fillPath(outer.subtracted(inner), color)

    elif name == "wake":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(s / 2, s / 2), s * 0.16, s * 0.16)
        _pen(painter, color, s * 0.09)
        for i in range(8):
            ang = math.radians(i * 45)
            painter.drawLine(
                QPointF(s / 2 + math.cos(ang) * s * 0.24, s / 2 + math.sin(ang) * s * 0.24),
                QPointF(s / 2 + math.cos(ang) * s * 0.38, s / 2 + math.sin(ang) * s * 0.38))

    elif name == "close":
        _pen(painter, color, s * 0.11)
        painter.drawLine(QPointF(a, a), QPointF(b, b))
        painter.drawLine(QPointF(b, a), QPointF(a, b))

    elif name == "board":
        _pen(painter, color, s * 0.09)
        painter.drawRect(QRectF(a, a + s * 0.04, b - a, (b - a) - s * 0.16))
        painter.drawLine(QPointF(s / 2, b - s * 0.12), QPointF(s / 2, b))

    elif name == "escape":
        # An arrow leaving a bracket: the universal "get me out of this".
        _pen(painter, color, s * 0.09)
        painter.drawArc(QRectF(s * 0.30, a, (b - a) * 0.92, b - a),
                        -70 * 16, 140 * 16)
        painter.drawLine(QPointF(a + s * 0.02, s / 2), QPointF(s * 0.56, s / 2))
        head = QPainterPath(QPointF(a - s * 0.02, s / 2))
        head.lineTo(QPointF(a + s * 0.22, s / 2 - s * 0.16))
        head.lineTo(QPointF(a + s * 0.22, s / 2 + s * 0.16))
        head.closeSubpath()
        painter.fillPath(head, color)

    elif name in ("plus", "minus"):
        _pen(painter, color, s * 0.12)
        painter.drawLine(QPointF(a, s / 2), QPointF(b, s / 2))
        if name == "plus":
            painter.drawLine(QPointF(s / 2, a), QPointF(s / 2, b))

    elif name == "hand":
        # Open palm, the sign every map app uses for "drag the view".
        _pen(painter, color, s * 0.075)
        palm = QPainterPath(QPointF(s * 0.28, s * 0.44))
        palm.lineTo(QPointF(s * 0.28, s * 0.66))
        palm.cubicTo(QPointF(s * 0.28, s * 0.86), QPointF(s * 0.44, s * 0.92),
                     QPointF(s * 0.58, s * 0.92))
        palm.cubicTo(QPointF(s * 0.74, s * 0.92), QPointF(s * 0.80, s * 0.80),
                     QPointF(s * 0.80, s * 0.62))
        palm.lineTo(QPointF(s * 0.80, s * 0.40))
        painter.drawPath(palm)
        for x, top in ((0.40, 0.30), (0.53, 0.24), (0.66, 0.28)):
            painter.drawLine(QPointF(s * x, s * top), QPointF(s * x, s * 0.60))
        # the thumb, tucked across the heel
        painter.drawLine(QPointF(s * 0.28, s * 0.52), QPointF(s * 0.16, s * 0.62))

    elif name == "grip":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for row in range(3):
            for col in range(2):
                painter.drawEllipse(
                    QPointF(s * 0.38 + col * s * 0.24, s * 0.28 + row * s * 0.22),
                    s * 0.05, s * 0.05)


def icon(name: str, size: int = 22, color: str = "#E8ECF1",
         weight: float = 1.0) -> QIcon:
    global _WEIGHT
    ratio = target_ratio()
    key = (name, size, color, ratio, weight)
    if key in _CACHE:
        return _CACHE[key]

    pixmap = QPixmap(int(round(size * ratio)), int(round(size * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # The painter works in logical units, so the drawing code is unchanged.
    _WEIGHT = weight
    try:
        _draw(name, painter, QColor(color), float(size))
    finally:
        _WEIGHT = 1.0
    painter.end()

    result = QIcon(pixmap)
    _CACHE[key] = result
    return result


def swatch(color: str, size: int = 22, selected: bool = False) -> QIcon:
    ratio = target_ratio()
    pixmap = QPixmap(int(round(size * ratio)), int(round(size * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    inset = 3.0 if selected else 2.0
    rect = QRectF(inset, inset, size - inset * 2, size - inset * 2)
    painter.setBrush(QColor(color))
    painter.setPen(QPen(QColor("#12161B"), 1.2))
    painter.drawEllipse(rect)
    if selected:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#FFFFFF"), 2.0))
        painter.drawEllipse(QRectF(0.9, 0.9, size - 1.8, size - 1.8))
    painter.end()
    return QIcon(pixmap)
