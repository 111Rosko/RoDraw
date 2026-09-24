"""Annotation document: the shapes on screen, plus undo/redo.

Coordinates are always stored in *canvas space* -- pixels relative to the
top-left of the virtual desktop, independent of any zoom transform. That way
zooming in, drawing, and zooming back out leaves strokes exactly where the
user put them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QTransform, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

HIGHLIGHTER_OPACITY = 0.35
UNDO_LIMIT = 300


@dataclass(eq=False)     # identity, not value, equality
class Shape:
    kind: str                       # path | line | arrow | rect | ellipse | text
    color: str = "#FF3B30"
    width: float = 4.0
    opacity: float = 1.0
    points: list[tuple[float, float]] = field(default_factory=list)
    text: str = ""
    font_size: int = 28
    fill: bool = False
    # Degrees clockwise about the middle of the shape. The points themselves
    # stay unturned, so every existing calculation keeps working in the
    # shape's own frame and only the ends have to know about the angle.
    angle: float = 0.0

    # ---------------------------------------------------------- geometry
    def _qpoints(self) -> list[QPointF]:
        return [QPointF(x, y) for x, y in self.points]

    def rect(self) -> QRectF:
        """Normalised rect from the first and last point (shapes only)."""
        if len(self.points) < 2:
            return QRectF()
        (x1, y1), (x2, y2) = self.points[0], self.points[-1]
        return QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized()

    def translate(self, dx: float, dy: float) -> None:
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def centre(self) -> QPointF:
        return self.raw_bounds().center()

    def transform(self) -> QTransform:
        """Maps the shape's own frame onto the screen."""
        if not self.angle:
            return QTransform()
        c = self.raw_bounds().center()
        return (QTransform().translate(c.x(), c.y())
                .rotate(self.angle).translate(-c.x(), -c.y()))

    def bounds(self) -> QRectF:
        """Where the shape lies on screen, turned as it is."""
        raw = self.raw_bounds()
        if not self.angle or raw.isNull():
            return raw
        return self.transform().mapRect(raw)

    def content_bounds(self) -> QRectF:
        """The geometry alone, without the room left for the stroke.

        raw_bounds() stands clear of the drawing by half the pen width so
        nothing is clipped. That margin is the same whatever the size, so
        resizing has to be worked out on this rectangle instead, or the far
        corner creeps away as the near one is pulled.
        """
        if not self.points:
            return QRectF()
        if self.kind == "text":
            return self.raw_bounds().adjusted(4, 4, -4, -4)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def raw_bounds(self) -> QRectF:
        """The same, before it was turned -- the frame the points live in."""
        if not self.points:
            return QRectF()
        if self.kind == "text":
            x, y = self.points[0]
            metrics = QFontMetricsF(self.font())
            lines = self.text.split("\n") or [""]
            width = max([metrics.horizontalAdvance(line) for line in lines] + [1.0])
            height = metrics.height() * max(1, len(lines))
            return QRectF(x, y, width, height).adjusted(-4, -4, 4, 4)

        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        pad = self.width / 2 + 2
        if self.kind == "arrow":
            pad += self.width * 3
        return QRectF(min(xs) - pad, min(ys) - pad,
                      max(xs) - min(xs) + pad * 2, max(ys) - min(ys) + pad * 2)

    def font(self) -> QFont:
        f = QFont("Segoe UI", self.font_size)
        f.setBold(True)
        return f

    # ------------------------------------------------------- hit testing
    def hits(self, point: QPointF, radius: float) -> bool:
        """True if an eraser of `radius` at `point` touches this shape."""
        if not self.points:
            return False
        tolerance = radius + self.width / 2

        if self.angle:
            # Ask the question in the shape's own frame rather than turning
            # every one of its points to answer it.
            inverse, ok = self.transform().inverted()
            if ok:
                point = inverse.map(point)

        if self.kind == "text":
            return self.raw_bounds().adjusted(-radius, -radius,
                                              radius, radius).contains(point)

        if self.kind in ("path", "line", "arrow"):
            pts = self._qpoints()
            if len(pts) == 1:
                return QLineF(pts[0], point).length() <= tolerance
            if self.kind in ("line", "arrow"):
                pts = [pts[0], pts[-1]]
            return any(
                _dist_to_segment(point, pts[i], pts[i + 1]) <= tolerance
                for i in range(len(pts) - 1)
            )

        rect = self.rect()
        if self.fill:
            return rect.adjusted(-tolerance, -tolerance, tolerance, tolerance).contains(point)

        outer = rect.adjusted(-tolerance, -tolerance, tolerance, tolerance)
        inner = rect.adjusted(tolerance, tolerance, -tolerance, -tolerance)
        if not outer.contains(point):
            return False
        if inner.isValid() and inner.contains(point):
            return False  # inside a hollow shape, not on its outline
        return True

    # ----------------------------------------------------------- drawing
    def paint(self, painter: QPainter) -> None:
        if not self.points:
            return

        color = QColor(self.color)
        painter.save()
        painter.setOpacity(self.opacity)
        if self.angle:
            c = self.raw_bounds().center()
            painter.translate(c)
            painter.rotate(self.angle)
            painter.translate(-c)

        if self.kind == "text":
            painter.setPen(QPen(color))
            painter.setFont(self.font())
            x, y = self.points[0]
            metrics = QFontMetricsF(self.font())
            for i, line in enumerate(self.text.split("\n")):
                painter.drawText(QPointF(x, y + metrics.ascent() + i * metrics.height()), line)
            painter.restore()
            return

        pen = QPen(color, self.width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(color if self.fill else Qt.BrushStyle.NoBrush)

        if self.kind == "path":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(smooth_path(self._qpoints()))
        elif self.kind == "line":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(*self.points[0]), QPointF(*self.points[-1]))
        elif self.kind == "arrow":
            self._paint_arrow(painter, color)
        elif self.kind == "rect":
            painter.drawRect(self.rect())
        elif self.kind == "ellipse":
            painter.drawEllipse(self.rect())

        painter.restore()

    def _paint_arrow(self, painter: QPainter, color: QColor) -> None:
        start = QPointF(*self.points[0])
        end = QPointF(*self.points[-1])
        line = QLineF(start, end)
        if line.length() < 1:
            return

        head = max(self.width * 3.2, 12.0)
        # Stop the shaft short so the stroke does not poke past the tip.
        shaft = QLineF(start, end)
        shaft.setLength(max(0.0, line.length() - head * 0.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(shaft)

        angle = math.radians(line.angle())
        spread = math.radians(26)
        p1 = QPointF(end.x() - head * math.cos(angle - spread),
                     end.y() + head * math.sin(angle - spread))
        p2 = QPointF(end.x() - head * math.cos(angle + spread),
                     end.y() + head * math.sin(angle + spread))
        head_path = QPainterPath(end)
        head_path.lineTo(p1)
        head_path.lineTo(p2)
        head_path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(head_path, color)


# ------------------------------------------------------------- helpers

def _dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(p.x() - ax, p.y() - ay)
    t = ((p.x() - ax) * dx + (p.y() - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p.x() - (ax + t * dx), p.y() - (ay + t * dy))


def _split_path(points: list[tuple[float, float]], centre: QPointF,
                reach: float) -> list[list[tuple[float, float]]]:
    """Break a freehand stroke into the runs the eraser did not touch.

    Samples inside the eraser are dropped, and a run is also cut when the
    segment joining two kept samples passes through it -- on a fast stroke
    the samples can straddle the eraser without either landing inside it.
    """
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    previous: tuple[float, float] | None = None
    cx, cy = centre.x(), centre.y()

    def flush():
        nonlocal current
        if len(current) >= 2:
            runs.append(current)
        current = []

    for x, y in points:
        if math.hypot(x - cx, y - cy) <= reach:
            flush()
            previous = None
            continue
        if previous is not None and _dist_to_segment(
                centre, QPointF(*previous), QPointF(x, y)) <= reach:
            flush()
        current.append((x, y))
        previous = (x, y)

    flush()
    return runs


def smooth_path(pts: list[QPointF]) -> QPainterPath:
    """Quadratic curve through segment midpoints -- removes the polygonal
    look of raw mouse samples without displacing the stroke."""
    path = QPainterPath()
    if not pts:
        return path
    if len(pts) == 1:
        # A single click should still leave a visible dot.
        path.addEllipse(pts[0], 0.1, 0.1)
        return path

    path.moveTo(pts[0])
    if len(pts) == 2:
        path.lineTo(pts[1])
        return path

    for i in range(1, len(pts) - 1):
        mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2.0,
                      (pts[i].y() + pts[i + 1].y()) / 2.0)
        path.quadTo(pts[i], mid)
    path.lineTo(pts[-1])
    return path


# ------------------------------------------------------------ document

class Document:
    """Ordered shape list with snapshot-based undo.

    Snapshots only copy the list of references (shapes are immutable once
    committed), so they are cheap enough to take on every edit.
    """

    def __init__(self):
        self.shapes: list[Shape] = []
        self._undo: list[list[Shape]] = []
        self._redo: list[list[Shape]] = []

    # -- history ---------------------------------------------------------
    def _snapshot(self) -> None:
        self._undo.append(list(self.shapes))
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(list(self.shapes))
        self.shapes = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(list(self.shapes))
        self.shapes = self._redo.pop()
        return True

    # -- edits -----------------------------------------------------------
    def begin_change(self) -> None:
        """Open one undo step before mutating a shape in place (a drag)."""
        self._snapshot()

    def swap(self, old: Shape, new: Shape) -> bool:
        """Put `new` where `old` sits, without touching history.

        Undo snapshots keep references, so editing a shape in place would
        silently rewrite the history that was supposed to remember it. The
        caller opens an undo step, swaps in a copy, and edits the copy.
        """
        for index, shape in enumerate(self.shapes):
            if shape is old:
                self.shapes[index] = new
                return True
        return False

    def add(self, shape: Shape) -> None:
        self._snapshot()
        self.shapes.append(shape)

    def erase_at(self, point: QPointF, radius: float, snapshot: bool = True,
                 whole_stroke: bool = False) -> QRectF | None:
        """Rub out at `point`. Returns the area that changed, or None.

        Freehand strokes are cut where the eraser passes, leaving the rest of
        the line behind -- deleting a whole stroke because its far end was
        touched is not what anyone means by an eraser. Geometry and text
        cannot be partially rubbed out, so those still go whole; set
        `whole_stroke` to get that behaviour for everything.

        `snapshot` is passed True only for the first change of a drag, so the
        whole gesture collapses into one undo step -- and a drag that erased
        nothing leaves no empty step behind.
        """
        dirty = QRectF()
        changed = False
        survivors: list[Shape] = []

        for shape in self.shapes:
            if not shape.hits(point, radius):
                survivors.append(shape)
                continue

            if not changed:
                # self.shapes is still untouched here, so this snapshots the
                # state from before the whole gesture.
                if snapshot:
                    self._snapshot()
                changed = True
            bounds = shape.bounds()
            dirty = bounds if dirty.isNull() else dirty.united(bounds)

            if whole_stroke or shape.kind != "path":
                continue      # dropped entirely

            reach = radius + shape.width / 2.0
            for run in _split_path(shape.points, point, reach):
                survivors.append(replace(shape, points=run))

        if not changed:
            return None
        self.shapes = survivors
        return dirty

    def shape_at(self, point: QPointF, tolerance: float = 7.0) -> Shape | None:
        """Topmost shape under `point`, for picking things up with the
        select tool. Later shapes are drawn on top, so search backwards."""
        for shape in reversed(self.shapes):
            if shape.hits(point, tolerance):
                return shape
        return None

    def move(self, shape: Shape, dx: float, dy: float) -> None:
        shape.translate(dx, dy)

    def remove(self, shape: Shape) -> bool:
        for index, existing in enumerate(self.shapes):
            if existing is shape:
                self._snapshot()
                del self.shapes[index]
                return True
        return False

    def clear(self) -> bool:
        if not self.shapes:
            return False
        self._snapshot()
        self.shapes = []
        return True

    def is_empty(self) -> bool:
        return not self.shapes
