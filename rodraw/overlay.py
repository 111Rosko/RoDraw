"""The annotation surface -- one translucent window per monitor.

Originally this was a single window stretched across the whole virtual
desktop, which meant zooming into something on one screen magnified the other
one too, and there was no way to leave a second monitor alone while
annotating the first. Each monitor now gets its own overlay with its own zoom
and its own board, and can be switched off independently.

All the windows share one Document, so undo is a single global history and a
label drawn on one screen is still one Ctrl+Z away no matter where the mouse
is.

Three coordinate spaces are in play:

  widget space  -- pixels inside this window (0,0 = this monitor's top-left)
  local space   -- this monitor's pixels, before zoom
  canvas space  -- virtual-desktop pixels; what the Document stores

`to_canvas` / `to_widget` convert between widget and canvas, so zooming and
panning never move a stroke relative to the thing it points at.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QPainter,
                         QPainterPath, QPen,
                         QTransform,
                         QPixmap)
from PyQt6.QtWidgets import QLineEdit, QWidget

from . import capture, tools as T, winutil
from .i18n import tr
from dataclasses import replace

from .model import HIGHLIGHTER_OPACITY, Document, Shape

MIN_ZOOM = 1.0
MAX_ZOOM = 16.0
SLEEP_ANNOTATION_OPACITY = 0.45
MIN_BRUSH = 1
MAX_BRUSH = 120
CURSOR_POLL_MS = 16
# How far one wheel notch slides a magnified view, in screen pixels.
# Measured on screen rather than in canvas units, so the view moves the
# same visible distance whatever the magnification.
PAN_STEP = 120

# Selection handles, in screen pixels: how big they are drawn, how close a
# press has to be to count as grabbing one, and how far above the box the
# turn handle floats.
HANDLE = 9.0
HANDLE_GRAB = 15.0
TURN_GAP = 28.0
MIN_SPAN = 8.0          # a shape may not be squeezed smaller than this

# One step of alpha: invisible on screen, but enough that Windows treats the
# overlay as a real hit target instead of letting clicks fall through it.
HIT_TEST_VEIL = QColor(0, 0, 0, 1)


class Overlay(QWidget):
    tool_changed = pyqtSignal(str)
    selection_changed = pyqtSignal()
    color_changed = pyqtSignal(str)
    sleep_changed = pyqtSignal(bool)
    history_changed = pyqtSignal()
    zoom_changed = pyqtSignal(float)
    status = pyqtSignal(str)
    close_requested = pyqtSignal()

    def __init__(self, config, screen, document: Document):
        super().__init__(None)
        self.cfg = config
        self.doc = document
        self.screen_obj = screen

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool          # keeps it out of the taskbar/alt-tab
        )
        # Titled even though it is frameless: it makes the running app
        # findable from outside, which the build smoke test relies on.
        self.setWindowTitle("RoDraw")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # -- state
        self.tool = T.PEN
        self.color = self.cfg.get("drawing.color", "#FF3B30")
        self.asleep = False
        self.active = True                # does this monitor take the mouse?
        self.board = None                 # None | "white" | "black"

        self._drawing = False
        self._erasing = False
        self._erase_started = False
        self._erase_last: QPointF | None = None
        self._live: Shape | None = None
        self._cursor_pos: QPointF | None = None
        self._suppress_paint = False      # true only while capturing

        # -- select / move
        self._selected: Shape | None = None
        self._hover: Shape | None = None      # what select would pick up
        self._drag_from: QPointF | None = None
        self._moved = False
        # Mirrors the WS_EX_TRANSPARENT bit so it is only poked on a change.
        self._passthrough: bool | None = None

        # Other always-on-top windows of ours (toolbar, toast). They sit above
        # the desktop, so they must step aside for a screen grab or they end up
        # baked into zoomed views and saved screenshots.
        self.companions: list[QWidget] = []
        self._hidden_for_capture: list[QWidget] = []

        # -- zoom (per monitor)
        self.zoom_scale = 1.0
        self.zoom_origin = QPointF(0.0, 0.0)
        self._zoom_pixmap: QPixmap | None = None
        self._zoom_rect_start: QPointF | None = None
        self._zoom_rect_end: QPointF | None = None
        self._panning = False
        self._pan_anchor = QPointF()
        self._pan_origin = QPointF()
        # Drag-to-move-the-view, for screens with no wheel and no middle
        # button. Off unless the toolbar's hand button is pressed, because
        # while it is on a drag moves the view instead of drawing.
        self.pan_mode = False
        self._toolbar_rect = None
        # Dragging a handle: which one, and what the shape looked like when
        # it was grabbed.
        self._grab: dict | None = None

        # -- inline text editor
        self._editor: QLineEdit | None = None
        self._editor_pos: QPointF | None = None

        # While a pointing tool is active the window stops receiving mouse
        # events, so the cursor has to be polled instead.
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._poll_cursor)

        self.refresh_geometry()

    # ------------------------------------------------------------ geometry
    @property
    def origin(self) -> QPoint:
        """This monitor's top-left in canvas space."""
        return self.screen_obj.geometry().topLeft()

    def refresh_geometry(self) -> None:
        self.setGeometry(self.screen_obj.geometry())

    def to_canvas(self, p: QPointF) -> QPointF:
        o = self.origin
        return QPointF(p.x() / self.zoom_scale + self.zoom_origin.x() + o.x(),
                       p.y() / self.zoom_scale + self.zoom_origin.y() + o.y())

    def to_widget(self, p: QPointF) -> QPointF:
        o = self.origin
        return QPointF((p.x() - o.x() - self.zoom_origin.x()) * self.zoom_scale,
                       (p.y() - o.y() - self.zoom_origin.y()) * self.zoom_scale)

    def set_toolbar_hole(self, global_rect) -> None:   # noqa: D401
        """Keep the toolbar clickable by removing its area from this window.

        Window regions are measured in real device pixels, while Qt reports
        everything in logical ones. The two are the same only at 100% display
        scaling; on a 4K classroom board at 200% a region built from logical
        sizes covers a quarter of the window, and Windows discards the rest --
        the overlay stops accepting input anywhere outside the top-left
        corner. Everything here is therefore converted before it is handed
        over.
        """
        # Remembered so a press that lands here can be refused even in the
        # instant between the bar changing size and the cut being remade.
        self._toolbar_rect = global_rect

        hwnd = int(self.winId())
        ratio = self.devicePixelRatioF()
        width = int(round(self.width() * ratio))
        height = int(round(self.height() * ratio))

        geo = self.screen_obj.geometry()
        if global_rect is None or not geo.intersects(global_rect):
            winutil.set_window_hole(hwnd, width, height, None)
            return

        local = global_rect.translated(-geo.x(), -geo.y())
        winutil.set_window_hole(hwnd, width, height, (
            int(local.left() * ratio), int(local.top() * ratio),
            int((local.right() + 1) * ratio), int((local.bottom() + 1) * ratio)))

    def covers(self, canvas_point: QPointF) -> bool:
        return QRectF(self.screen_obj.geometry()).contains(canvas_point)

    def _update_canvas_rect(self, rect: QRectF) -> None:
        """Repaint just the affected area, in widget coords."""
        if rect.isNull():
            self.update()
            return
        top_left = self.to_widget(rect.topLeft())
        bottom_right = self.to_widget(rect.bottomRight())
        self.update(QRectF(top_left, bottom_right).normalized()
                    .adjusted(-6, -6, 6, 6).toRect())

    # --------------------------------------------------------------- state
    def set_tool(self, tool_id: str) -> None:
        if tool_id not in T.BY_ID:
            return
        self._commit_editor()
        if tool_id != T.SELECT:
            self._set_selected(None)
        self.tool = tool_id
        self._apply_cursor()
        self._refresh_input_mode()
        self.tool_changed.emit(tool_id)
        self.update()

    def set_active(self, active: bool) -> None:
        """Whether this monitor takes the mouse at all."""
        if active == self.active:
            return
        self.active = active
        if not active:
            self._cancel_live()
            self._commit_editor()
            self.reset_zoom()
            self.board = None
        self._refresh_input_mode()
        self.update()

    def set_color(self, color: str) -> None:
        self.color = color
        self.cfg.set("drawing.color", color)
        self.color_changed.emit(color)

    @property
    def spotlight_radius(self) -> float:
        return float(self.cfg.get("drawing.spotlight_radius", 150))

    def brush_width(self, tool_id: str | None = None) -> int:
        tool = tool_id or self.tool
        low, high = T.width_range(tool)
        return max(low, min(high, int(self.cfg.get(T.width_key(tool), 4))))

    def set_brush_width(self, value: int) -> None:
        low, high = T.width_range(self.tool)
        self.cfg.set(T.width_key(self.tool), max(low, min(high, int(value))))
        # The wheel and the keyboard come through here rather than through
        # the toolbar, and a text box already open has to follow them too --
        # otherwise the size changes, the message says so, and the box on
        # screen stays the size it was when it opened.
        self.restyle_editor()
        self.update()

    def nudge_brush(self, delta: int) -> None:
        """One step bigger or smaller, in this tool's own units."""
        step = T.width_step(self.tool)
        self.set_brush_width(self.brush_width() + (step if delta > 0 else -step))
        self.status.emit(tr("msg.size", tool=T.BY_ID[self.tool].label,
                            size=self.brush_width()))

    def set_pan_mode(self, on: bool) -> None:
        """Turn drag-to-move-the-view on or off for this monitor."""
        if self.pan_mode == on:
            return
        self.pan_mode = on
        if not on and self._panning:
            self._panning = False
        self._apply_cursor()

    def _apply_cursor(self) -> None:
        if self.asleep:
            return
        if self.pan_mode and self.zoomed:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self.tool == T.TEXT:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif self.tool == T.SELECT:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    # -------------------------------------------------------- input mode
    def _set_passthrough(self, passthrough: bool) -> None:
        """Flip click-through only when it actually changes -- the select tool
        re-evaluates this sixty times a second."""
        if passthrough == self._passthrough:
            return
        self._passthrough = passthrough
        winutil.set_click_through(int(self.winId()), passthrough)

    def _refresh_input_mode(self) -> None:
        """Decide whether the mouse reaches us or the apps underneath.

        Three cases:

        * Drawing tools take the mouse outright.
        * The laser and the spotlight are for pointing at something live, so
          they never block it -- the window stays click-through and the cursor
          is polled instead of delivered.
        * Select behaves like an ordinary cursor until it is over something of
          ours. Windows decides hit-testing per window, not per click, so this
          has to be settled before the button goes down: the cursor is polled
          and the window is made solid only while it is over an annotation.
        """
        pointing = self.tool in T.PASSTHROUGH_TOOLS
        hybrid = self.tool == T.SELECT
        forced = self.asleep or not self.active

        if forced or pointing:
            self._set_passthrough(True)
        elif hybrid:
            over_handle = (self._handle_at(self._cursor_pos) is not None
                           if self._cursor_pos is not None else False)
            self._set_passthrough(self._hover is None and not over_handle)
        else:
            self._set_passthrough(False)

        if (pointing or hybrid) and not forced:
            if not self._cursor_timer.isActive():
                self._cursor_timer.start(CURSOR_POLL_MS)
        else:
            self._cursor_timer.stop()
            if self._hover is not None:
                self._hover = None
                self.update()

    def _poll_cursor(self) -> None:
        inside = self.mapFromGlobal(QCursor.pos())
        was = self._cursor_pos
        self._cursor_pos = QPointF(inside) if self.rect().contains(inside) else None

        if self.tool == T.SELECT:
            self._poll_select_hover()
            return

        if was is None and self._cursor_pos is None:
            return
        if self.tool == T.SPOTLIGHT:
            self._repaint_spotlight(was, self._cursor_pos)
        else:
            self._repaint_cursor(was, self._cursor_pos)

    def nudge_spotlight(self, steps: int) -> None:
        """Resize the spotlight from the low-level wheel hook.

        While the spotlight is active the window is click-through, so no wheel
        event is ever delivered to it -- the hook is the only way the scroll
        can reach us.
        """
        step = T.width_step(T.SPOTLIGHT)
        low, high = T.width_range(T.SPOTLIGHT)
        value = int(self.spotlight_radius) + steps * step
        self.cfg.set("drawing.spotlight_radius", max(low, min(high, value)))
        self.update()

    def _poll_select_hover(self) -> None:
        """Work out whether the select tool is over one of our annotations.

        While it is, the window takes the mouse so the thing can be picked up
        and dragged; the rest of the time it is click-through, and the cursor
        behaves exactly as it would if RoDraw were not running.
        """
        if self._drag_from is not None:
            return                          # never let go mid-drag

        previous = self._hover
        if self._cursor_pos is None:
            self._hover = None
        else:
            canvas = self.to_canvas(self._cursor_pos)
            self._hover = self.doc.shape_at(canvas, max(7.0, 9.0 / self.zoom_scale))

        # The handles stand outside the shape, and the turn handle floats
        # clear above it. Without this the window would hand the mouse back
        # to whatever is underneath exactly where they are.
        handle = self._handle_at(self._cursor_pos) if self._cursor_pos else None
        self._set_passthrough(self._hover is None and handle is None)
        if handle is not None:
            self.setCursor(self._HANDLE_CURSORS.get(handle, Qt.CursorShape.ArrowCursor))
        elif self._hover is not None:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self._apply_cursor()

        if previous is not self._hover:
            dirty = QRectF()
            for shape in (previous, self._hover):
                if shape is not None:
                    bounds = self.painted_bounds(shape)
                    dirty = bounds if dirty.isNull() else dirty.united(bounds)
            self._update_canvas_rect(dirty)

    # --------------------------------------------------------------- sleep
    def set_asleep(self, asleep: bool) -> None:
        if asleep == self.asleep:
            return
        self.asleep = asleep
        self._commit_editor()
        self._cancel_live()

        if asleep:
            # Both of these paint an opaque layer. Leaving one up while clicks
            # pass through would hide the very thing being clicked -- and a
            # zoomed view would put annotations nowhere near the real pixels
            # underneath. Sleep means get out of the way, so drop them.
            self.reset_zoom()
            self.board = None
            self._set_selected(None)
            self.unsetCursor()

        self._refresh_input_mode()
        if not asleep:
            winutil.raise_topmost(int(self.winId()), activate=self.active)
            if self.active:
                self.activateWindow()
            self.raise_()
            self._apply_cursor()

        self.sleep_changed.emit(asleep)
        self.update()

    def toggle_sleep(self) -> None:
        self.set_asleep(not self.asleep)

    # ---------------------------------------------------------------- board
    def set_board(self, mode: str | None) -> None:
        self.board = None if self.board == mode else mode
        self.update()

    # ----------------------------------------------------------------- zoom
    @property
    def zoomed(self) -> bool:
        return self.zoom_scale > 1.0001

    def _blank_for_capture(self) -> None:
        self._suppress_paint = True
        self._hidden_for_capture = [w for w in self.companions if w.isVisible()]
        for widget in self._hidden_for_capture:
            widget.hide()
        self.repaint()

    def _restore_after_capture(self) -> None:
        self._suppress_paint = False
        for widget in self._hidden_for_capture:
            if getattr(widget, "restore_after_capture", True):
                widget.show()
                widget.raise_()
        self._hidden_for_capture = []
        self.repaint()

    def _ensure_zoom_pixmap(self) -> None:
        # Only this monitor is grabbed, so the magnified view can never leak
        # content from another screen.
        self._zoom_pixmap = capture.grab_screen_clean(
            self.screen_obj, self._blank_for_capture, self._restore_after_capture)

    def zoom_to_rect(self, rect: QRectF) -> None:
        """Magnify a canvas-space rectangle to fill this monitor."""
        if rect.width() < 8 or rect.height() < 8:
            self.status.emit("Zoom region too small")
            return
        if not self.zoomed:
            self._ensure_zoom_pixmap()

        scale = min(self.width() / rect.width(), self.height() / rect.height())
        self.zoom_scale = max(MIN_ZOOM, min(MAX_ZOOM, scale))
        self._center_on(rect.center())
        self.zoom_changed.emit(self.zoom_scale)
        self.update()

    def _center_on(self, canvas_point: QPointF) -> None:
        o = self.origin
        self.zoom_origin = QPointF(
            canvas_point.x() - o.x() - self.width() / (2 * self.zoom_scale),
            canvas_point.y() - o.y() - self.height() / (2 * self.zoom_scale),
        )
        self._clamp_origin()

    def _clamp_origin(self) -> None:
        """Keep the magnified view inside this monitor's captured image."""
        max_x = max(0.0, self.width() - self.width() / self.zoom_scale)
        max_y = max(0.0, self.height() - self.height() / self.zoom_scale)
        self.zoom_origin = QPointF(
            min(max(0.0, self.zoom_origin.x()), max_x),
            min(max(0.0, self.zoom_origin.y()), max_y),
        )

    def pan_by(self, dx: float, dy: float) -> None:
        """Slide a magnified view by a distance measured in screen pixels."""
        if not self.zoomed:
            return
        before = QPointF(self.zoom_origin)
        self.zoom_origin = QPointF(self.zoom_origin.x() + dx / self.zoom_scale,
                                   self.zoom_origin.y() + dy / self.zoom_scale)
        self._clamp_origin()
        if self.zoom_origin != before:
            self.update()

    def wheel_navigate(self, steps: int, ctrl: bool, shift: bool,
                       anchor: QPointF | None = None) -> bool:
        """What one wheel notch does over a magnified view.

        Scrolling moves the view, which is what the wheel does everywhere
        else; magnification is on Ctrl, where the rest of the world puts it.
        Shared by the widget's own wheel events and the global hook, so every
        tool behaves the same -- including the ones that make the window
        click-through and never see a wheel event at all.
        """
        if not self.zoomed:
            return False
        if ctrl:
            self.zoom_by(1.15 ** steps, anchor)
        elif shift:
            self.pan_by(-PAN_STEP * steps, 0)
        else:
            self.pan_by(0, -PAN_STEP * steps)
        return True

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        """Scale around `anchor` (widget coords) so the point under the cursor
        stays put."""
        new_scale = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom_scale * factor))
        if abs(new_scale - self.zoom_scale) < 1e-6:
            return
        if not self.zoomed and new_scale > 1.0:
            self._ensure_zoom_pixmap()

        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        canvas_anchor = self.to_canvas(anchor)
        o = self.origin
        self.zoom_scale = new_scale
        # Solve for the origin that keeps canvas_anchor under the same pixel.
        self.zoom_origin = QPointF(
            canvas_anchor.x() - o.x() - anchor.x() / new_scale,
            canvas_anchor.y() - o.y() - anchor.y() / new_scale)
        self._clamp_origin()

        if not self.zoomed:
            self.reset_zoom()
        else:
            self.zoom_changed.emit(self.zoom_scale)
            self.update()

    def reset_zoom(self) -> None:
        was = self.zoomed
        self.zoom_scale = 1.0
        self.zoom_origin = QPointF(0.0, 0.0)
        self._zoom_pixmap = None
        self._zoom_rect_start = self._zoom_rect_end = None
        if was:
            self.zoom_changed.emit(1.0)
        self.update()

    def refresh_zoom_capture(self) -> None:
        """Re-grab this monitor so the magnified view shows current content."""
        if self.zoomed:
            self._ensure_zoom_pixmap()
            self.status.emit("Zoom view refreshed")
            self.update()

    # ------------------------------------------------------------ document
    def undo(self) -> None:
        if self.doc.undo():
            self._set_selected(None)
            self.history_changed.emit()

    def redo(self) -> None:
        if self.doc.redo():
            self._set_selected(None)
            self.history_changed.emit()

    def clear(self) -> None:
        self._commit_editor()
        if self.doc.clear():
            self._set_selected(None)
            self.history_changed.emit()
            self.status.emit("Cleared")

    def forget_hover(self) -> None:
        """Drop the hover after the document changes underneath it."""
        if self._hover is not None:
            self._hover = None
            self._refresh_input_mode()

    def delete_selection(self) -> bool:
        if self._selected is None:
            return False
        bounds = self.painted_bounds(self._selected)
        if self.doc.remove(self._selected):
            self._set_selected(None)
            self._hover = None
            self.history_changed.emit()
            self._update_canvas_rect(bounds)
            return True
        return False

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:
        if self._suppress_paint:
            return

        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing
                               | QPainter.RenderHint.SmoothPixmapTransform
                               | QPainter.RenderHint.TextAntialiasing)

        # Windows hit-tests a layered window by its alpha channel: a pixel at
        # alpha 0 is not just see-through, it is click-through. A fully
        # transparent overlay therefore receives no mouse input at all, and
        # drawing only works once something opaque (a board) is painted.
        # One step of alpha is invisible and makes the window solid to input.
        painter.fillRect(self.rect(), HIT_TEST_VEIL)

        hide_annotations = self.asleep and not self.cfg.get(
            "general.keep_annotations_when_asleep", True)

        # 1. background: board colour, or this monitor's frozen image
        if self.board:
            painter.fillRect(self.rect(),
                             QColor("#FFFFFF") if self.board == "white" else QColor("#101418"))
        elif self.zoomed and self._zoom_pixmap is not None:
            painter.save()
            painter.scale(self.zoom_scale, self.zoom_scale)
            painter.translate(-self.zoom_origin)
            painter.drawPixmap(QPointF(0, 0), self._zoom_pixmap)
            painter.restore()

        if hide_annotations:
            painter.end()
            return

        # 2. shapes, in canvas coordinates under this monitor's transform
        painter.save()
        self._apply_canvas_transform(painter)
        if self.asleep and self.cfg.get("general.dim_annotations_when_asleep", True):
            painter.setOpacity(SLEEP_ANNOTATION_OPACITY)
        for shape in self.doc.shapes:
            shape.paint(painter)
        if self._live is not None:
            self._live.paint(painter)
        if self._hover is not None and self._hover is not self._selected:
            self._paint_hover(painter)
        if self._selected is not None and not self.asleep:
            self._paint_selection(painter)
        painter.restore()

        if self.asleep:
            painter.end()
            return

        # 3. transient overlays, drawn in widget space
        if self.tool == T.SPOTLIGHT and self._cursor_pos is not None:
            self._paint_spotlight(painter)
        if self._zoom_rect_start is not None and self._zoom_rect_end is not None:
            self._paint_zoom_marquee(painter)
        if self.cfg.get("general.show_brush_cursor", True):
            self._paint_brush_cursor(painter)

        painter.end()

    def _apply_canvas_transform(self, painter: QPainter) -> None:
        painter.scale(self.zoom_scale, self.zoom_scale)
        painter.translate(-self.zoom_origin)
        painter.translate(-QPointF(self.origin))

    # ------------------------------------------------- selection handles
    def painted_bounds(self, shape) -> QRectF:
        """Everything drawn for this shape, decorations and all.

        The dashed frame stands clear of the drawing, the handles straddle
        that frame, and the turn handle floats well beyond it. Repainting
        only the shape's own bounds left all of that behind as a trail every
        time something was dragged.
        """
        box = shape.bounds()
        if box.isNull():
            return box
        scale = max(0.2, self.zoom_scale)
        if shape is self._selected:
            # The turn handle sits above the top edge in the shape's own
            # frame, so once it is turned it can be on any side of the box.
            reach = (TURN_GAP + HANDLE) / scale + 6.0
        else:
            reach = 8.0 / scale + 4.0          # the hover outline
        return box.adjusted(-reach, -reach, reach, reach)

    def _handle_frame(self, shape) -> QRectF:
        """The box the handles sit on, in the shape's own unturned frame."""
        return shape.raw_bounds().adjusted(-3, -3, 3, 3)

    def _local_handles(self, frame: QRectF) -> dict:
        """Handle centres on that box: corners, edge middles, and the turn
        handle floating above the top edge."""
        cx, cy = frame.center().x(), frame.center().y()
        gap = TURN_GAP / max(0.2, self.zoom_scale)
        return {
            "nw": QPointF(frame.left(), frame.top()),
            "n": QPointF(cx, frame.top()),
            "ne": QPointF(frame.right(), frame.top()),
            "e": QPointF(frame.right(), cy),
            "se": QPointF(frame.right(), frame.bottom()),
            "s": QPointF(cx, frame.bottom()),
            "sw": QPointF(frame.left(), frame.bottom()),
            "w": QPointF(frame.left(), cy),
            "turn": QPointF(cx, frame.top() - gap),
        }

    def _handle_positions(self, shape) -> dict:
        """The same handles in canvas coordinates, turned with the shape."""
        frame = self._handle_frame(shape)
        if frame.width() < 2 or frame.height() < 2:
            return {}
        local = self._local_handles(frame)
        if not shape.angle:
            return local
        turn = shape.transform()
        return {name: turn.map(point) for name, point in local.items()}

    def _handle_at(self, widget_pos: QPointF) -> str | None:
        """Which handle a press at this point has hold of, if any."""
        if self._selected is None or self.tool != T.SELECT:
            return None
        best, best_distance = None, HANDLE_GRAB
        for name, point in self._handle_positions(self._selected).items():
            here = self.to_widget(point)
            distance = math.hypot(here.x() - widget_pos.x(), here.y() - widget_pos.y())
            if distance <= best_distance:
                best, best_distance = name, distance
        return best

    _HANDLE_CURSORS = {
        "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
        "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
        "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
        "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
        "turn": Qt.CursorShape.CrossCursor,
    }

    def _paint_selection(self, painter: QPainter) -> None:
        shape = self._selected
        frame = self._handle_frame(shape)
        scale = max(0.2, self.zoom_scale)
        accent = QColor("#32ADE6")

        painter.save()
        painter.setOpacity(1.0)
        if shape.angle:
            centre = shape.raw_bounds().center()
            painter.translate(centre)
            painter.rotate(shape.angle)
            painter.translate(-centre)

        painter.setPen(QPen(accent, max(1.0, 1.6 / scale), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(frame)

        if frame.width() >= 2 and frame.height() >= 2:
            handles = self._local_handles(frame)
            solid = QPen(accent, max(1.0, 1.4 / scale))
            painter.setPen(solid)
            painter.drawLine(QPointF(frame.center().x(), frame.top()),
                             handles["turn"])
            size = HANDLE / scale
            painter.setBrush(QColor("#FFFFFF"))
            for name, point in handles.items():
                if name == "turn":
                    continue
                painter.drawRect(QRectF(point.x() - size / 2, point.y() - size / 2,
                                        size, size))
            self._paint_turn_handle(painter, handles["turn"], size * 0.95, accent)
        painter.restore()

    def _paint_turn_handle(self, painter: QPainter, centre: QPointF,
                           radius: float, accent: QColor) -> None:
        """A round button with an arrow curling round it."""
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(accent, max(1.0, radius * 0.18)))
        painter.drawEllipse(centre, radius, radius)

        arc = QRectF(centre.x() - radius * 0.5, centre.y() - radius * 0.5,
                     radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(accent, max(1.0, radius * 0.22),
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(arc, 40 * 16, 260 * 16)
        tip = QPointF(centre.x() + radius * 0.38, centre.y() - radius * 0.32)
        head = QPainterPath(tip)
        head.lineTo(QPointF(tip.x() - radius * 0.1, tip.y() - radius * 0.44))
        head.lineTo(QPointF(tip.x() + radius * 0.44, tip.y() - radius * 0.16))
        head.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(head, accent)

    def _paint_hover(self, painter: QPainter) -> None:
        """Faint outline under the select tool, so it is clear that clicking
        here grabs an annotation rather than the app behind it."""
        rect = self._hover.bounds().adjusted(-3, -3, 3, 3)
        painter.setPen(QPen(QColor(50, 173, 230, 150),
                            max(1.0, 1.4 / self.zoom_scale), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(1.0)
        painter.drawRect(rect)

    def _paint_spotlight(self, painter: QPainter) -> None:
        """Dim everything except one circle.

        This used to subtract the circle from a path the size of the whole
        display and fill the remainder, for every pixel of mouse movement.
        The cost of that grows with the pixel count, which is why it was
        smooth on a desk and like treacle on a 4K board. The dim is four
        plain rectangles around the circle now, and the only path arithmetic
        happens inside the circle's own bounding box.
        """
        dim = QColor(0, 0, 0, 165)
        radius = float(self.spotlight_radius)
        centre = self._cursor_pos
        # Snapped to whole pixels: the dim is half transparent, so four
        # rectangles meeting on fractional edges leave a faint seam where the
        # antialiasing of each one is laid over the other.
        box = QRectF(QRectF(centre.x() - radius, centre.y() - radius,
                            radius * 2, radius * 2).toAlignedRect())
        screen = QRectF(self.rect())

        above = max(0.0, box.top() - screen.top())
        below = max(0.0, screen.bottom() - box.bottom())
        left = max(0.0, box.left() - screen.left())
        right = max(0.0, screen.right() - box.right())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(QRectF(screen.left(), screen.top(), screen.width(), above), dim)
        painter.fillRect(QRectF(screen.left(), box.bottom(), screen.width(), below), dim)
        painter.fillRect(QRectF(screen.left(), box.top(), left, box.height()), dim)
        painter.fillRect(QRectF(box.right(), box.top(), right, box.height()), dim)
        painter.restore()

        corners = QPainterPath()
        corners.addRect(box)
        circle = QPainterPath()
        circle.addEllipse(centre, radius, radius)
        painter.fillPath(corners.subtracted(circle), dim)

        painter.setPen(QPen(QColor(255, 255, 255, 90), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(centre, radius, radius)

    def _spotlight_band(self, pos: QPointF | None) -> QRectF:
        if pos is None:
            return QRectF()
        radius = float(self.spotlight_radius) + 4      # room for the outline
        return QRectF(pos.x() - radius, pos.y() - radius, radius * 2, radius * 2)

    def _repaint_spotlight(self, old: QPointF | None, new: QPointF | None) -> None:
        """Repaint only where the circle was and where it now is.

        Everything outside those two discs is dim before the move and dim
        after it, so asking for the whole screen -- sixty times a second, on
        a translucent window covering eight million pixels -- was the lag.
        """
        if old is None or new is None:
            self.update()          # the dim layer is appearing or going away
            return
        band = self._spotlight_band(old).united(self._spotlight_band(new))
        self.update(band.toRect().adjusted(-1, -1, 1, 1))

    def _paint_zoom_marquee(self, painter: QPainter) -> None:
        rect = QRectF(self._zoom_rect_start, self._zoom_rect_end).normalized()
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        inner = QPainterPath()
        inner.addRect(rect)
        painter.fillPath(shade.subtracted(inner), QColor(0, 0, 0, 110))
        painter.setPen(QPen(QColor("#32ADE6"), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

    def text_caret_size(self) -> tuple[float, float]:
        """How tall and wide the text cursor stands, in canvas units."""
        font = QFont("Segoe UI", int(self.cfg.get("drawing.font_size", 28)))
        font.setBold(True)
        height = QFontMetricsF(font).height()
        return height, max(6.0, height * 0.28)

    def _paint_text_caret(self, painter: QPainter) -> None:
        """Stand an I-beam the height of the lettering under the cursor.

        The size box is a number, and a number is no help at the front of a
        classroom in judging whether the back row will be able to read it.
        This shows the height before a word is typed.
        """
        if self._cursor_pos is None:
            return
        height, width = self.text_caret_size()
        # Painted in window coordinates, like the brush ring, so a magnified
        # view has to be accounted for by hand.
        height *= self.zoom_scale
        width = max(6.0, width * self.zoom_scale)
        x, y = self._cursor_pos.x(), self._cursor_pos.y()
        bottom = y + height          # lettering is laid downward from here
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for pen in (QPen(QColor(0, 0, 0, 150), 3.4),
                    QPen(QColor(self.color), 1.6)):
            painter.setPen(pen)
            painter.drawLine(QPointF(x, y), QPointF(x, bottom))
            painter.drawLine(QPointF(x - width / 2, y), QPointF(x + width / 2, y))
            painter.drawLine(QPointF(x - width / 2, bottom),
                             QPointF(x + width / 2, bottom))

    def _paint_brush_cursor(self, painter: QPainter) -> None:
        if self.tool == T.TEXT:
            if self._editor is None:
                self._paint_text_caret(painter)
            return
        if (self._cursor_pos is None
                or self.tool in (T.ZOOM, T.SPOTLIGHT, T.SELECT)):
            return
        radius = max(3.0, self.brush_width() * self.zoom_scale / 2.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 140), 3))
        painter.drawEllipse(self._cursor_pos, radius, radius)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.4))
        painter.drawEllipse(self._cursor_pos, radius, radius)

    # -------------------------------------------------------------- input
    def mousePressEvent(self, event) -> None:
        if self.asleep or not self.active:
            return
        pos = QPointF(event.position())

        # The toolbar's rectangle is cut out of this window, so a press there
        # should never arrive. It can for an instant after the bar changes
        # size, and drawing a stray mark across a lesson is a far worse
        # outcome than a tap that has to be repeated.
        if self._toolbar_rect is not None:
            here = self.mapToGlobal(pos.toPoint())
            if self._toolbar_rect.contains(here):
                event.ignore()
                return

        canvas = self.to_canvas(pos)

        # Middle button pans a magnified view regardless of active tool.
        if event.button() == Qt.MouseButton.MiddleButton and self.zoomed:
            self._panning = True
            self._pan_anchor = pos
            self._pan_origin = QPointF(self.zoom_origin)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # With the hand button pressed a plain drag moves the view, so a
        # finger on a board does what the wheel does on a desk.
        if self.pan_mode and self.zoomed:
            self._panning = True
            self._pan_anchor = pos
            self._pan_origin = QPointF(self.zoom_origin)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        self._commit_editor()

        if self.tool == T.SELECT:
            handle = self._handle_at(pos)
            if handle is not None and self._begin_grab(handle, canvas):
                return
            self._begin_select(canvas)
            return

        if self.tool == T.ZOOM:
            self._zoom_rect_start = pos
            self._zoom_rect_end = pos
            self.update()
            return

        if self.tool in T.PASSTHROUGH_TOOLS:
            return

        if self.tool == T.TEXT:
            self._open_editor(canvas)
            return

        if self.tool == T.ERASER:
            self._erasing = True
            self._erase_started = False
            self._erase_last = None      # a fresh gesture starts from here
            self._erase(canvas)
            return

        self._drawing = True
        self._live = self._new_shape(canvas)
        self._update_canvas_rect(self._live.bounds())

    def _cursor_band(self, pos: QPointF | None) -> QRectF:
        """The patch of screen the cursor ring, or the text I-beam, covers."""
        if pos is None:
            return QRectF()
        if self.tool == T.TEXT:
            # The I-beam hangs below the cursor rather than round it.
            height, width = self.text_caret_size()
            height *= self.zoom_scale
            width = max(width * self.zoom_scale, 8.0)
            return QRectF(pos.x() - width / 2 - 4, pos.y() - 4,
                          width + 8, height + 8)
        radius = max(4.0, self.brush_width() * self.zoom_scale / 2.0) + 4
        return QRectF(pos.x() - radius, pos.y() - radius, radius * 2, radius * 2)

    def _repaint_cursor(self, old: QPointF | None, new: QPointF | None) -> None:
        """Clear the ring's old position as well as painting the new one.

        While erasing, the only repaint was the area the eraser removed, so
        the ring itself smeared a trail of leftover arcs across the screen.
        """
        band = self._cursor_band(old).united(self._cursor_band(new))
        if not band.isNull():
            self.update(band.toRect())

    def mouseMoveEvent(self, event) -> None:
        pos = QPointF(event.position())
        previous = self._cursor_pos
        self._cursor_pos = pos
        canvas = self.to_canvas(pos)

        if self.asleep or not self.active:
            return

        # Whatever the tool does below, the ring has moved and both the old
        # and the new position need repainting.
        if self.tool == T.SPOTLIGHT:
            self._repaint_spotlight(previous, pos)
        else:
            self._repaint_cursor(previous, pos)

        if self._panning:
            delta = pos - self._pan_anchor
            self.zoom_origin = QPointF(
                self._pan_origin.x() - delta.x() / self.zoom_scale,
                self._pan_origin.y() - delta.y() / self.zoom_scale)
            self._clamp_origin()
            self.update()
            return

        if self._grab is not None:
            self._drag_grab(canvas)
            return

        if self._drag_from is not None and self._selected is not None:
            self._drag_selection(canvas)
            return

        if self._zoom_rect_start is not None:
            self._zoom_rect_end = pos
            self.update()
            return

        if self._erasing:
            self._erase(canvas)
            return

        if self._drawing and self._live is not None:
            old = self._live.bounds()
            if self._live.kind == "path":
                self._live.points.append((canvas.x(), canvas.y()))
            else:
                end = canvas
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    end = self._constrain(QPointF(*self._live.points[0]), canvas)
                self._live.points = [self._live.points[0], (end.x(), end.y())]
            self._update_canvas_rect(old.united(self._live.bounds()))
            return

        # Idle movement is already covered by the cursor repaint above.

    def mouseReleaseEvent(self, event) -> None:
        if self._panning and event.button() in (Qt.MouseButton.MiddleButton,
                                                Qt.MouseButton.LeftButton):
            self._panning = False
            self._apply_cursor()
            return

        if self.asleep or event.button() != Qt.MouseButton.LeftButton:
            return

        if self._grab is not None:
            self._end_grab()
            self._refresh_input_mode()
            return

        if self._drag_from is not None:
            self._drag_from = None
            if self._moved:
                self.history_changed.emit()
            self._moved = False
            self._refresh_input_mode()   # may be over empty space now
            return

        if self._zoom_rect_start is not None:
            start, end = self._zoom_rect_start, self._zoom_rect_end
            self._zoom_rect_start = self._zoom_rect_end = None
            if start is not None and end is not None:
                rect = QRectF(self.to_canvas(start), self.to_canvas(end)).normalized()
                self.zoom_to_rect(rect)
            self.update()
            return

        if self._erasing:
            self._erasing = False
            self._erase_last = None
            return

        if self._drawing and self._live is not None:
            self._drawing = False
            shape = self._live
            self._live = None
            # A click with a drag tool produces a degenerate shape; drop it.
            if shape.kind in ("line", "arrow", "rect", "ellipse"):
                rect = shape.rect()
                if rect.width() < 3 and rect.height() < 3:
                    self.update()
                    return
            self.doc.add(shape)
            self.history_changed.emit()
            self._update_canvas_rect(shape.bounds())

    def wheelEvent(self, event) -> None:
        if self.asleep or not self.active:
            return
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            return

        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if self.wheel_navigate(int(steps), ctrl, shift, QPointF(event.position())):
            return
        if self.tool == T.ZOOM:
            self.zoom_by(1.15 ** steps, QPointF(event.position()))
        else:
            self.nudge_brush(1 if steps > 0 else -1)

    def escape(self) -> bool:
        """Back out of whatever this monitor is doing. True if it did.

        Anything half-finished is abandoned first -- one press should not
        throw away a zoom when all you wanted was to cancel the shape you
        were dragging. Past that, a single press clears every state that has
        taken the screen over, rather than making you press it once per
        layer.
        """
        if self._editor is not None:
            self._cancel_editor()
            return True
        if self._drawing or self._erasing or self._zoom_rect_start is not None \
                or self._drag_from is not None or self._grab is not None:
            self._cancel_live()
            return True

        did = False
        if self.zoomed:
            self.reset_zoom()
            did = True
        if self.board is not None:
            self.board = None
            self.update()
            did = True
        if self._selected is not None:
            self._set_selected(None)
            self.update()
            did = True
        return did

    def can_escape(self) -> bool:
        """Would pressing Back do anything on this monitor?

        The same conditions escape() itself tests. The app refreshes the
        button whenever the tool, the history or a zoom changes, which covers
        every state that actually traps someone -- a zoom, a board, a pointing
        tool. A selection made since the last of those can leave the button
        dark for a moment although it would still clear it.
        """
        return bool(self._editor is not None or self._drawing or self._erasing
                    or self._zoom_rect_start is not None
                    or self._drag_from is not None or self._grab is not None
                    or self.zoomed or self.board is not None
                    or self._selected is not None)

    def presenting(self) -> bool:
        """Is this monitor covered by something the user needs a way out of?"""
        return self.zoomed or self.board is not None

    # ------------------------------------------------------- select tool
    def _begin_select(self, canvas: QPointF) -> None:
        tolerance = max(7.0, 9.0 / self.zoom_scale)
        shape = self.doc.shape_at(canvas, tolerance)
        previous = self._selected
        self._set_selected(shape)
        self._moved = False

        if shape is None:
            # The cursor moved off the annotation between the poll and the
            # click. Give the mouse back at once so the next one lands on the
            # app underneath instead of being swallowed again.
            self._drag_from = None
            self._hover = None
            self._set_passthrough(True)
            if previous is not None:
                self.update()
            return

        # One undo step per drag, opened before anything moves. The shape is
        # then swapped for a copy: the snapshot just taken holds references,
        # so moving the original in place would drag history along with it.
        self.doc.begin_change()
        clone = replace(shape, points=list(shape.points))
        if self.doc.swap(shape, clone):
            shape = clone
            self._set_selected(clone)
        self._drag_from = canvas
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    # ------------------------------------------------ resizing, turning
    def _open_edit_step(self):
        """Start one undo step and hand back a copy safe to change.

        The snapshot just taken holds references, so editing the original in
        place would rewrite the history that was meant to remember it.
        """
        shape = self._selected
        self.doc.begin_change()
        clone = replace(shape, points=list(shape.points))
        if self.doc.swap(shape, clone):
            self._set_selected(clone)
            return clone
        return shape

    def _to_local(self, canvas: QPointF, centre: QPointF, angle: float) -> QPointF:
        """A canvas point expressed in the shape's own unturned frame."""
        if not angle:
            return QPointF(canvas)
        turn = (QTransform().translate(centre.x(), centre.y())
                .rotate(angle).translate(-centre.x(), -centre.y()))
        inverse, ok = turn.inverted()
        return inverse.map(canvas) if ok else QPointF(canvas)

    def _begin_grab(self, name: str, canvas: QPointF) -> bool:
        frame = self._handle_frame(self._selected)
        if frame.width() < 2 or frame.height() < 2:
            return False
        shape = self._open_edit_step()
        centre = shape.raw_bounds().center()
        self._grab = {
            "handle": name,
            "frame": QRectF(frame),
            # The visible box stands clear of the drawing by a fixed margin
            # that does not grow with it, so the sums are done on the
            # geometry itself.
            "raw": QRectF(shape.content_bounds()),
            "points": list(shape.points),
            "font": int(shape.font_size),
            "angle": float(shape.angle),
            "centre": centre,
        }
        if name == "turn":
            self._grab["from"] = math.degrees(math.atan2(canvas.y() - centre.y(),
                                                         canvas.x() - centre.x()))
        self._moved = False
        self.setCursor(self._HANDLE_CURSORS.get(name, Qt.CursorShape.ArrowCursor))
        return True

    def _drag_grab(self, canvas: QPointF) -> None:
        if self._grab["handle"] == "turn":
            self._turn_to(canvas)
        else:
            self._resize_to(canvas)

    def _turn_to(self, canvas: QPointF) -> None:
        state = self._grab
        centre = state["centre"]
        now = math.degrees(math.atan2(canvas.y() - centre.y(),
                                      canvas.x() - centre.x()))
        angle = state["angle"] + (now - state["from"])
        if winutil.modifier_state()[1]:          # Shift: quarter-hour steps
            angle = round(angle / 15.0) * 15.0
        shape = self._selected
        if abs(angle - shape.angle) < 0.05:
            return
        before = self.painted_bounds(shape)
        shape.angle = angle % 360.0
        self._moved = True
        self._update_canvas_rect(before.united(self.painted_bounds(shape)))

    def _resize_to(self, canvas: QPointF) -> None:
        """Drag one handle, keeping the opposite edge or corner still.

        Corners keep the proportions, because a photograph of handwriting
        stretched in one direction looks wrong; the edge handles are there
        for when stretching is what you want.
        """
        state = self._grab
        name = state["handle"]
        frame = state["frame"]
        local = self._to_local(canvas, state["centre"], state["angle"])

        left, top = frame.left(), frame.top()
        right, bottom = frame.right(), frame.bottom()
        if "w" in name:
            left = min(local.x(), right - MIN_SPAN)
        if "e" in name:
            right = max(local.x(), left + MIN_SPAN)
        if "n" in name:
            top = min(local.y(), bottom - MIN_SPAN)
        if "s" in name:
            bottom = max(local.y(), top + MIN_SPAN)

        raw = state["raw"]
        pad_x = max(0.0, (frame.width() - raw.width()) / 2.0)
        pad_y = max(0.0, (frame.height() - raw.height()) / 2.0)
        inner_w = max(1.0, (right - left) - pad_x * 2.0)
        inner_h = max(1.0, (bottom - top) - pad_y * 2.0)
        sx = inner_w / max(1.0, raw.width())
        sy = inner_h / max(1.0, raw.height())
        shape = self._selected
        corner = name in ("nw", "ne", "se", "sw")
        if corner or shape.kind == "text":
            # One factor for both axes; lettering has no other meaning.
            sx = sy = sx if abs(sx - 1.0) > abs(sy - 1.0) else sy
            sx = sy = max(0.02, sx)

        anchor_x = raw.right() if "w" in name else raw.left()
        anchor_y = raw.bottom() if "n" in name else raw.top()
        if name in ("n", "s") and shape.kind == "text":
            anchor_x = raw.center().x()
        if name in ("e", "w") and shape.kind == "text":
            anchor_y = raw.center().y()

        before = self.painted_bounds(shape)
        shape.points = [(anchor_x + (x - anchor_x) * sx,
                         anchor_y + (y - anchor_y) * sy)
                        for x, y in state["points"]]
        if shape.kind == "text":
            shape.font_size = max(8, min(200, int(round(state["font"] * sy))))

        # The shape's middle has moved, and it is turned about its middle, so
        # without this the grabbed corner would swing away from the finger.
        if state["angle"]:
            drift = state["centre"] - shape.raw_bounds().center()
            spun = QTransform().rotate(state["angle"]).map(drift)
            shape.translate(drift.x() - spun.x(), drift.y() - spun.y())

        self._moved = True
        self._update_canvas_rect(before.united(self.painted_bounds(shape)))

    def _end_grab(self) -> None:
        self._grab = None
        if self._moved:
            self.history_changed.emit()
        self._moved = False
        self._apply_cursor()
        self.update()

    def _drag_selection(self, canvas: QPointF) -> None:
        dx = canvas.x() - self._drag_from.x()
        dy = canvas.y() - self._drag_from.y()
        if dx == 0 and dy == 0:
            return
        before = self.painted_bounds(self._selected)
        self._selected.translate(dx, dy)
        self._drag_from = canvas
        self._moved = True
        self._update_canvas_rect(before.united(self.painted_bounds(self._selected)))

    # -------------------------------------------------------- eraser
    def _erase(self, canvas: QPointF) -> None:
        """Rub out everything between the last eraser position and this one.

        The mouse is only sampled every so often, so erasing just at the
        reported points leaves untouched gaps between them -- a trail of
        leftover fragments along a quick stroke. Walking the gap in steps of
        half a radius makes the eraser continuous.
        """
        radius = max(2.0, self.brush_width() / 2.0)
        whole = bool(self.cfg.get("drawing.eraser_whole_stroke", False))

        points = [canvas]
        previous = self._erase_last
        if previous is not None:
            span = math.hypot(canvas.x() - previous.x(), canvas.y() - previous.y())
            steps = int(span / max(1.0, radius * 0.5))
            if steps > 1:
                points = [
                    QPointF(previous.x() + (canvas.x() - previous.x()) * i / steps,
                            previous.y() + (canvas.y() - previous.y()) * i / steps)
                    for i in range(1, steps + 1)
                ]
        self._erase_last = QPointF(canvas)

        dirty = QRectF()
        for point in points:
            hit = self.doc.erase_at(point, radius,
                                    snapshot=not self._erase_started,
                                    whole_stroke=whole)
            if hit is None:
                continue
            self._erase_started = True
            dirty = hit if dirty.isNull() else dirty.united(hit)

        if dirty.isNull():
            return
        self.history_changed.emit()
        # Repainting the whole monitor on every sample made the app crawl.
        self._update_canvas_rect(dirty)

    def _constrain(self, start: QPointF, end: QPointF) -> QPointF:
        """Shift-snap: 45 degree angles for lines, square for boxes."""
        dx, dy = end.x() - start.x(), end.y() - start.y()
        if self.tool in (T.RECT, T.ELLIPSE):
            size = max(abs(dx), abs(dy))
            return QPointF(start.x() + math.copysign(size, dx or 1),
                           start.y() + math.copysign(size, dy or 1))
        angle = math.atan2(dy, dx)
        step = math.pi / 4
        snapped = round(angle / step) * step
        length = math.hypot(dx, dy)
        return QPointF(start.x() + length * math.cos(snapped),
                       start.y() + length * math.sin(snapped))

    def _new_shape(self, canvas: QPointF) -> Shape:
        tool = T.BY_ID[self.tool]
        kind = tool.shape_kind or "path"
        opacity = HIGHLIGHTER_OPACITY if self.tool == T.HIGHLIGHTER else 1.0
        return Shape(
            kind=kind,
            color=self.color,
            width=self.brush_width(),
            opacity=opacity,
            points=[(canvas.x(), canvas.y())],
            fill=bool(self.cfg.get("drawing.fill_shapes", False))
            and kind in ("rect", "ellipse"),
        )

    def _cancel_live(self) -> None:
        if self._grab is not None and self._selected is not None:
            # Put the shape back as it was grabbed, so Escape means "forget
            # this" rather than "stop halfway".
            state, shape = self._grab, self._selected
            shape.points = list(state["points"])
            shape.font_size = state["font"]
            shape.angle = state["angle"]
            self._grab = None
            self._apply_cursor()
        self._drawing = False
        self._erasing = False
        self._erase_started = False
        self._erase_last = None
        self._drag_from = None
        self._moved = False
        self._live = None
        self._zoom_rect_start = self._zoom_rect_end = None
        self.update()

    # ---------------------------------------------------------- text tool
    def _open_editor(self, canvas: QPointF) -> None:
        self._commit_editor()
        widget_pos = self.to_widget(canvas)

        editor = QLineEdit(self)
        editor.setFont(self._editor_font())
        editor.setStyleSheet(self._editor_style())
        editor.setMinimumWidth(240)
        editor.move(widget_pos.toPoint())
        editor.returnPressed.connect(self._commit_editor)
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)

        self._editor = editor
        self._editor_pos = canvas

    def _set_selected(self, shape) -> None:
        """Record what is picked up, and say so.

        The size box shows the selected thing's own size rather than the
        tool's, so it has to be told; there are nine places that change the
        selection and this is the one that announces it.
        """
        if self._selected is shape:
            return
        self._selected = shape
        self.selection_changed.emit()

    def selected_size(self) -> int | None:
        """The size the box should show: lettering height, or stroke width."""
        shape = self._selected
        if shape is None:
            return None
        return int(shape.font_size if shape.kind == "text" else shape.width)

    def resize_selected(self, value: int) -> bool:
        """Change the size of the annotation that is picked up.

        Asked for after a lesson where the lettering came out too small to
        read from the back and the only way to fix it was to delete it and
        type it again.
        """
        shape = self._selected
        if shape is None:
            return False
        value = int(value)
        if shape.kind == "text":
            if int(shape.font_size) == value:
                return False
            new = replace(shape, font_size=value, points=list(shape.points))
        else:
            if int(shape.width) == value:
                return False
            new = replace(shape, width=float(value), points=list(shape.points))

        before = self.painted_bounds(shape)
        self.doc.begin_change()
        if not self.doc.swap(shape, new):
            return False
        self._set_selected(new)
        self.history_changed.emit()
        self._update_canvas_rect(before.united(self.painted_bounds(new)))
        return True

    def _editor_font(self) -> QFont:
        """The font the text box types in.

        The very same one the finished caption is drawn with. It used to be
        set in pixels through a stylesheet while the caption itself was set
        in points, so the box showed the lettering a third smaller than it
        came out -- there was no way to judge the size until it was placed.
        """
        font = QFont("Segoe UI", int(self.cfg.get("drawing.font_size", 28)))
        font.setBold(True)
        if self.zoom_scale != 1.0:
            font.setPointSizeF(max(1.0, font.pointSizeF() * self.zoom_scale))
        return font

    def _editor_style(self) -> str:
        return (f"QLineEdit {{ background: rgba(0,0,0,170); color: {self.color};"
                f" border: 1px solid {self.color}; padding: 2px 6px; }}")

    def restyle_editor(self) -> None:
        """Re-dress an open text box after the size or colour changes.

        Turning the size box while typing used to do nothing at all: the
        editor was dressed once, when it opened.
        """
        if self._editor is None:
            return
        self._editor.setFont(self._editor_font())
        self._editor.setStyleSheet(self._editor_style())
        self._editor.adjustSize()
        if self._editor.width() < 240:
            self._editor.resize(240, self._editor.height())

    def editing_text(self) -> bool:
        return self._editor is not None

    def _commit_editor(self) -> None:
        if self._editor is None:
            return
        text = self._editor.text().strip()
        pos = self._editor_pos
        self._editor.deleteLater()
        self._editor = None
        self._editor_pos = None
        if text and pos is not None:
            self.doc.add(Shape(kind="text", color=self.color, text=text,
                               font_size=int(self.cfg.get("drawing.font_size", 28)),
                               points=[(pos.x(), pos.y())]))
            self.history_changed.emit()
        self.setFocus()
        self.update()

    def _cancel_editor(self) -> None:
        if self._editor is None:
            return
        self._editor.deleteLater()
        self._editor = None
        self._editor_pos = None
        self.setFocus()
        self.update()

    def closeEvent(self, event) -> None:
        """A close request (the taskbar, taskkill without /F, shutdown) should
        end the session properly -- otherwise the tray icon is orphaned and
        Windows leaves a dead copy of it sitting in the notification area."""
        event.accept()
        self.close_requested.emit()

    def leaveEvent(self, event) -> None:
        if not self._cursor_timer.isActive():
            self._cursor_pos = None
            self.update()
        super().leaveEvent(event)
