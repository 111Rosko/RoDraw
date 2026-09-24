"""Floating tool palette.

A separate always-on-top window rather than a strip inside the overlay, so it
can be dragged anywhere and never eats part of the drawing surface. It is
deliberately focus-proof: clicking a button must not pull keyboard focus away
from the overlay, or the single-key shortcuts would stop working.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                             QSizePolicy, QSpinBox, QToolButton, QVBoxLayout,
                             QWidget)

from . import icons, tools as T
from .i18n import tr


def tip(label: str, key: str, hint: str = "") -> str:
    """Bold name, the key that picks it, then what it does."""
    head = f"<b>{label}</b>" + (f" &nbsp;({key})" if key else "")
    return f"{head}<br><span style='color:#9AA4AF'>{hint}</span>" if hint else head


BUTTON = 32
ICON = 21
# How far a finger or a mouse must travel before it counts as dragging the
# bar rather than pressing what is under it. A finger never lands perfectly
# still, so without this the bar wanders every time someone taps near a gap
# between two buttons.
DRAG_SLOP = 6
# A fingertip needs about 9mm of target. The ordinary 32px button is under
# that on an unscaled 1080p board, so a touch screen gets its own sizes.
TOUCH_BUTTON = 46
TOUCH_ICON = 30
ACCENT = "#32ADE6"

STYLE = f"""
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
}}
QToolButton:hover   {{ background: rgba(255,255,255,0.10); }}
QToolButton:pressed {{ background: rgba(255,255,255,0.18); }}
QToolButton:checked {{
    background: rgba(50,173,230,0.28);
    border: 1px solid {ACCENT};
}}
QLabel {{ color: #9AA4AF; font-size: 11px; }}
QLabel#colourHint {{ color: #32ADE6; font-size: 11px; padding: 1px 0 2px 0; }}
QSpinBox {{
    background: rgba(255,255,255,0.08);
    color: #E8ECF1;
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 5px;
    padding: 2px 4px;
    min-width: 42px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 12px; }}
"""

# The size box is the only control with parts too small to hit with a finger.
TOUCH_STYLE = """
QSpinBox { min-width: 64px; }
QSpinBox::up-button, QSpinBox::down-button { width: 26px; }
QLabel { font-size: 13px; }
"""


def scale_of(config) -> float:
    """The size multiplier the person has chosen, as a fraction."""
    try:
        percent = int(config.get("general.toolbar_scale") or 100)
    except (TypeError, ValueError):
        percent = 100
    return max(60, min(220, percent)) / 100.0


def compact_wanted(config) -> bool:
    """Whether to stack the bar into a block rather than a long strip.

    A strip across the top of a board is out of reach for a short pupil, and
    dropped to their height it lies across the work. A block can sit in a
    corner, where it is reachable and out of the way.
    """
    return str(config.get("general.toolbar_layout") or "bar").lower() == "compact"


def touch_wanted(config) -> bool:
    """Whether to lay the bar out for fingers rather than a mouse.

    Left on "auto" this follows what Windows reports about the hardware, which
    is right for a teacher who plugs the same laptop into an interactive board
    and into a projector on alternate days.
    """
    mode = str(config.get("general.touch_mode") or "auto").lower()
    if mode == "on":
        return True
    if mode == "off":
        return False
    from . import winutil
    return winutil.has_touch_screen()


class Bubble(QWidget):
    """Our own tooltip.

    Qt only pops its tooltips for widgets in the *active* window, and this
    toolbar deliberately never activates -- taking focus would break the
    single-key shortcuts. That is why hints appeared for some tools and not
    others. Drawing the bubble ourselves makes every button behave the same.
    """

    DELAY_MS = 350

    def __init__(self, parent=None):
        # Parented on purpose: as a top-level widget with no owner it could
        # outlive the QApplication at shutdown and take the process down with
        # it. The window flags keep it a separate window regardless.
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.label = QLabel("", self)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setStyleSheet(
            "QLabel { background: rgba(18,22,28,246); color: #E8ECF1;"
            " border: 1px solid rgba(255,255,255,0.20); border-radius: 8px;"
            " padding: 7px 11px; font-size: 12px; }")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reveal)
        self._pending: tuple[str, QPoint] | None = None

    def request(self, text: str, anchor_below: QPoint) -> None:
        self._pending = (text, anchor_below)
        self._timer.start(self.DELAY_MS)

    def cancel(self) -> None:
        self._timer.stop()
        self._pending = None
        self.hide()

    def _reveal(self) -> None:
        if self._pending is None:
            return
        text, anchor = self._pending
        self.label.setText(text)
        self.label.adjustSize()
        self.resize(self.label.size())

        x = anchor.x() - self.width() // 2
        y = anchor.y()
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen:                       # keep it on the same monitor
            area = screen.availableGeometry()
            x = max(area.left() + 4, min(x, area.right() - self.width() - 4))
            if y + self.height() > area.bottom():
                y = anchor.y() - self.height() - 46
        self.move(x, y)
        self.show()
        self.raise_()


class _Swatch(QToolButton):
    """A palette slot. A single click selects it, a double-click edits it."""

    edit_requested = pyqtSignal(int)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self.index)
        event.accept()


class _Flow:
    """Gathers the bar's controls so they can be dealt out across rows.

    The bar was one long row, which is fine on a desk. A 4K board at 300%
    reports 1280 logical pixels across and the touch layout wants 1631, so
    the right-hand buttons would hang off the screen -- the same trap as the
    zoom, in a different costume. Collecting first and placing afterwards
    means the number of rows can follow the narrowest screen attached.
    """

    def __init__(self):
        self.items: list[QWidget] = []

    def addWidget(self, widget) -> None:
        self.items.append(widget)


class _Separator(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(1)
        self.setFixedHeight(22)
        self.setStyleSheet("background: rgba(255,255,255,0.14);")


class Toolbar(QWidget):
    tool_picked = pyqtSignal(str)
    color_picked = pyqtSignal(str)
    width_changed = pyqtSignal(int)
    action_triggered = pyqtSignal(str)   # undo | redo | clear | save | settings | sleep | quit | board
    color_edit_requested = pyqtSignal(int)   # double-clicked slot index
    placement_changed = pyqtSignal()     # moved, shown or hidden
    pan_mode_changed = pyqtSignal(bool)  # drag-to-move-the-view toggled

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.cfg = config

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowTitle("RoDraw Toolbar")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Never steal focus -- the overlay needs it for single-key shortcuts.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(STYLE)

        self.touch = touch_wanted(config)
        self.compact = compact_wanted(config)
        scale = scale_of(config)
        self.btn_size = int(round((TOUCH_BUTTON if self.touch else BUTTON) * scale))
        self.icon_size = int(round((TOUCH_ICON if self.touch else ICON) * scale))
        # Heavier lines for a board, which is read from the back of a room
        # and usually has a window reflected in it.
        self.icon_weight = 1.35 if self.touch else 1.0
        if self.touch:
            self.setStyleSheet(STYLE + TOUCH_STYLE)

        self._asleep = False
        self._bubble = Bubble(self)
        self._hints: dict[QWidget, str] = {}
        self._drag_offset: QPoint | None = None
        self._press_at: QPoint | None = None
        self._dragging = False
        self._tool_buttons: dict[str, QToolButton] = {}
        self._swatches: list[QToolButton] = []

        self._build()
        self._restore_position()

    # ------------------------------------------------------------- build
    def _button(self, icon_name: str, tooltip: str, checkable=False) -> QToolButton:
        btn = QToolButton(self)
        btn.setIcon(icons.icon(icon_name, self.icon_size, weight=self.icon_weight))
        btn.setIconSize(QSize(self.icon_size, self.icon_size))
        btn.setFixedSize(self.btn_size, self.btn_size)
        btn.setCheckable(checkable)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.set_hint(btn, tooltip)
        return btn

    def set_hint(self, widget: QWidget, text: str) -> None:
        """Attach a hint and make sure the widget reports hover to us."""
        self._hints[widget] = text
        widget.setToolTip("")            # ours replaces Qt's
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            text = self._hints.get(obj)
            if text:
                below = obj.mapToGlobal(QPoint(obj.width() // 2, obj.height() + 8))
                self._bubble.request(text, below)
            if obj in getattr(self, "_swatch_widgets", ()):
                self._show_colour_hint(True)
        elif kind in (QEvent.Type.Leave, QEvent.Type.HoverLeave,
                      QEvent.Type.MouseButtonPress, QEvent.Type.Hide):
            self._bubble.cancel()
            if obj in getattr(self, "_swatch_widgets", ()):
                self._show_colour_hint(False)
        return super().eventFilter(obj, event)

    def _build(self) -> None:
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 7, 10, 5)
        column.setSpacing(2)

        row = _Flow()

        self.colour_hint = QLabel(tr("bar.colour.doubleclick"), self)
        self.colour_hint.setObjectName("colourHint")
        self.colour_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.colour_hint.hide()
        column.addWidget(self.colour_hint)

        column.addWidget(self._build_zoom_row())

        grip = QLabel(self)
        grip.setPixmap(icons.icon("grip", 18, "#6B7681").pixmap(
            QSize(18, 18), icons.target_ratio()))
        grip.setFixedWidth(16)
        grip.setCursor(Qt.CursorShape.SizeAllCursor)
        self.set_hint(grip, tip(tr("bar.move.name"), "", tr("bar.move.hint")))
        row.addWidget(grip)

        # -- tools
        group = QButtonGroup(self)
        group.setExclusive(True)
        for tool in T.TOOLS:
            btn = self._button(tool.id,
                               tip(tool.label, self.cfg.key(tool.action), tool.hint),
                               checkable=True)
            btn.clicked.connect(lambda _, tid=tool.id: self.tool_picked.emit(tid))
            group.addButton(btn)
            self._tool_buttons[tool.id] = btn
            row.addWidget(btn)

        row.addWidget(_Separator())

        # -- colours
        for index, color in enumerate(self.cfg.palette):
            btn = _Swatch(index, self)
            btn.setFixedSize(self.btn_size - 4, self.btn_size - 4)
            btn.setIconSize(QSize(self.icon_size, self.icon_size))
            btn.setIcon(icons.swatch(color, self.icon_size))
            self.set_hint(btn, tip(tr("bar.colour.name", colour=color),
                                   self.cfg.key(f"color.{index + 1}"),
                                   tr("bar.colour.hint")))
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, i=index: self._swatch_clicked(i))
            btn.edit_requested.connect(self.color_edit_requested.emit)
            self._swatches.append(btn)
            row.addWidget(btn)

        row.addWidget(_Separator())

        # -- size
        self.size_label = QLabel(tr("bar.size.name"), self)
        row.addWidget(self.size_label)
        self.size_spin = QSpinBox(self)
        self.size_spin.setRange(1, 120)
        self.size_spin.setFixedHeight(self.btn_size - 6)
        self.size_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.size_spin.valueChanged.connect(self.width_changed.emit)
        self.set_hint(self.size_spin, tip(
            tr("bar.size.name"),
            f"{self.cfg.key('brush.smaller')} / {self.cfg.key('brush.bigger')}",
            tr("bar.size.hint")))
        row.addWidget(self.size_spin)

        row.addWidget(_Separator())

        # -- actions
        # First of them on purpose: with no keyboard on a touch board this is
        # the only way out of a zoom, a spotlight or a whiteboard, so it has
        # to be the easiest button on the bar to find.
        self.btn_escape = self._button("escape", self._escape_tip())
        self.btn_escape.setEnabled(False)
        self.btn_escape.clicked.connect(
            lambda: self.action_triggered.emit("escape"))
        row.addWidget(self.btn_escape)

        for name, icon_name, text in self._action_tips():
            btn = self._button(icon_name, text)
            btn.clicked.connect(lambda _, n=name: self.action_triggered.emit(n))
            setattr(self, f"btn_{name}", btn)
            row.addWidget(btn)

        self.btn_sleep = self._button("sleep", tip(
            tr("bar.sleep.name"), str(self.cfg.get("general.sleep_hotkey")),
            tr("bar.sleep.hint")))
        self.btn_sleep.clicked.connect(lambda: self.action_triggered.emit("sleep"))
        row.addWidget(self.btn_sleep)

        btn_quit = self._button("close", tip(tr("bar.quit.name"), self.cfg.key("app.quit")))
        btn_quit.clicked.connect(lambda: self.action_triggered.emit("quit"))
        row.addWidget(btn_quit)

        self._place(column, row.items)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.adjustSize()
        self._swatch_widgets = set(self._swatches)

    def _row_budget(self) -> int:
        """How wide one row may be: the narrowest screen, less the margins.

        The narrowest rather than the current one, because the bar can be
        dragged from a laptop panel onto a board mid-lesson and must not need
        rebuilding when it lands.
        """
        widths = [s.availableGeometry().width() for s in QGuiApplication.screens()]
        return max(360, (min(widths) if widths else 1280) - 48)

    def _place(self, column, items) -> None:
        rows = self._block_rows(items) if self.compact else self._strip_rows(items)
        spacing = 3
        for index, widgets in enumerate(rows):
            # A rule at the very start or end of a row separates nothing.
            while widgets and isinstance(widgets[0], _Separator):
                widgets.pop(0).deleteLater()
            while widgets and isinstance(widgets[-1], _Separator):
                widgets.pop().deleteLater()
            holder = QWidget(self)
            lay = QHBoxLayout(holder)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(spacing)
            if len(rows) > 1:
                lay.addStretch(1)          # centre each row under the others
            for widget in widgets:
                lay.addWidget(widget)
            if len(rows) > 1:
                lay.addStretch(1)
            column.insertWidget(index, holder)

    def _block_rows(self, items) -> list[list]:
        """A roughly square block, a fixed number of buttons to a row.

        Each group starts a fresh row, so the tools, the colours and the
        actions stay recognisably apart without any rules between them. A
        square is only the starting point: turned up to 220% on a board that
        reports 720 pixels of height the block would run off the bottom, so
        it is widened until it fits, with the zoom row's height allowed for.
        """
        buttons = sum(1 for i in items if not isinstance(i, _Separator))
        columns = max(5, min(8, int(math.ceil(math.sqrt(buttons)))))
        budget = self._height_budget()
        rows = self._pack_block(items, columns)
        while columns < 14 and self._block_height(len(rows)) > budget:
            columns += 1
            rows = self._pack_block(items, columns)

        for item in items:
            if isinstance(item, _Separator):
                item.deleteLater()
        return rows

    def _pack_block(self, items, columns: int) -> list[list]:
        rows, current = [], []
        for item in items:
            if isinstance(item, _Separator):
                if current:
                    rows.append(current)
                    current = []
                continue
            if len(current) >= columns:
                rows.append(current)
                current = []
            current.append(item)
        if current:
            rows.append(current)
        return rows

    def _block_height(self, rows: int) -> int:
        """Roughly how tall the block will stand, zoom row included."""
        return rows * (self.btn_size + 3) + self.btn_size + 32

    def _height_budget(self) -> int:
        widths = [s.availableGeometry().height() for s in QGuiApplication.screens()]
        return max(300, (min(widths) if widths else 720) - 40)

    def _strip_rows(self, items) -> list[list]:
        """As few long rows as the narrowest screen will take."""
        budget, spacing = self._row_budget(), 3
        rows, current, used = [], [], 0
        for item in items:
            # setFixedSize does not move sizeHint, which still reports the
            # style's natural width -- 35 for a button actually 46 across.
            # Measuring by the hint alone under-counts every button and the
            # bar comes out wider than the screen it was packed for.
            width = max(item.sizeHint().width(), item.minimumWidth())
            if current and used + spacing + width > budget:
                rows.append(current)
                current, used = [], 0
            current.append(item)
            used += width + (spacing if len(current) > 1 else 0)
        if current:
            rows.append(current)
        return rows

    def _build_zoom_row(self) -> QWidget:
        """Everything a magnified view needs, for a screen with no keyboard.

        The wheel moves the view and Ctrl+wheel changes the magnification,
        but an interactive whiteboard has no wheel and no Esc key, so a zoom
        there was a trap you could not get out of. This row appears by itself
        whenever a zoom is live and disappears with it.

        Icons carry it rather than words: there is no hover on a touch screen,
        so the tooltips never appear and each button has to read on its own.
        """
        holder = QWidget(self)
        holder.hide()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(3)
        lay.addStretch(1)

        self.btn_zoom_out = self._button("minus", tip(tr("bar.zoomout.name"), "Ctrl+-"))
        self.btn_zoom_out.clicked.connect(
            lambda: self.action_triggered.emit("zoom_out"))
        lay.addWidget(self.btn_zoom_out)

        self.zoom_label = QLabel("", holder)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(46)
        lay.addWidget(self.zoom_label)

        self.btn_zoom_in = self._button("plus", tip(tr("bar.zoomin.name"), "Ctrl++"))
        self.btn_zoom_in.clicked.connect(
            lambda: self.action_triggered.emit("zoom_in"))
        lay.addWidget(self.btn_zoom_in)

        lay.addWidget(_Separator())

        self.btn_zoom_pan = self._button(
            "hand", tip(tr("bar.zoompan.name"), "", tr("bar.zoompan.hint")),
            checkable=True)
        self.btn_zoom_pan.toggled.connect(self.pan_mode_changed.emit)
        lay.addWidget(self.btn_zoom_pan)

        self.btn_zoom_exit = self._button("escape", tip(tr("bar.zoomexit.name"),
                                                        self.cfg.key("app.escape")))
        self.btn_zoom_exit.clicked.connect(
            lambda: self.action_triggered.emit("escape"))
        lay.addWidget(self.btn_zoom_exit)

        lay.addStretch(1)
        self.zoom_row = holder
        return holder

    def _escape_tip(self) -> str:
        return tip(tr("bar.escape.name"), self.cfg.key("app.escape"),
                   tr("bar.escape.hint"))

    def set_can_escape(self, can: bool) -> None:
        """Light the Back button only when there is something to back out of."""
        if self.btn_escape.isEnabled() != can:
            self.btn_escape.setEnabled(can)

    def set_zoomed(self, zoomed: bool, scale: float = 1.0) -> None:
        """Show or hide the zoom row and keep the magnification readout true."""
        if zoomed:
            self.zoom_label.setText(f"×{scale:.1f}")
        if self.zoom_row.isVisible() == zoomed:
            return
        if not zoomed and self.btn_zoom_pan.isChecked():
            self.btn_zoom_pan.setChecked(False)   # also clears it on the overlays
        self.zoom_row.setVisible(zoomed)
        self.adjustSize()
        # The bar just changed height, so the hole cut in the overlay for it
        # has to be recut or the new row would not be clickable.
        self.placement_changed.emit()

    def _swatch_clicked(self, index: int) -> None:
        palette = self.cfg.palette
        if 0 <= index < len(palette):
            self.color_picked.emit(palette[index])

    def refresh_palette(self) -> None:
        """Redraw the swatches after the palette changes."""
        for index, button in enumerate(self._swatches):
            color = self.cfg.palette[index]
            button.setIcon(icons.swatch(color, self.icon_size))
            self.set_hint(button, tip(tr("bar.colour.name", colour=color),
                                      self.cfg.key(f"color.{index + 1}"),
                                      tr("bar.colour.hint")))

    def _show_colour_hint(self, showing: bool) -> None:
        """Grow the bar by one line under the colours.

        Double-clicking a swatch to edit it is not discoverable on its own, so
        the bar says so while the mouse is down there.
        """
        if self.colour_hint.isVisible() == showing:
            return
        if showing and self._swatches:
            # Sit it under the swatches rather than under the whole bar, so it
            # clearly belongs to the colours.
            first = self._swatches[0]
            last = self._swatches[-1]
            centre = (first.mapTo(self, QPoint(0, 0)).x()
                      + last.mapTo(self, QPoint(last.width(), 0)).x()) // 2
            offset = max(0, centre - self.colour_hint.sizeHint().width() // 2)
            self.colour_hint.setContentsMargins(offset, 0, 0, 0)
            self.colour_hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.colour_hint.setVisible(showing)
        self.adjustSize()
        self.placement_changed.emit()

    def _action_tips(self):
        return [
            ("undo", "undo", tip(tr("bar.undo.name"), self.cfg.key("edit.undo"),
                                 tr("bar.undo.hint"))),
            ("redo", "redo", tip(tr("bar.redo.name"), self.cfg.key("edit.redo"),
                                 tr("bar.redo.hint"))),
            ("clear", "clear", tip(tr("bar.clear.name"), self.cfg.key("edit.clear"),
                                   tr("bar.clear.hint"))),
            ("screens", "screens", tip(tr("bar.screens.name"), "",
                                       tr("bar.screens.hint"))),
            ("board", "board", tip(tr("bar.board.name"), self.cfg.key("view.whiteboard"),
                                   tr("bar.board.hint",
                                      key=self.cfg.key("view.blackboard")))),
            ("save", "save", tip(tr("bar.save.name"), self.cfg.key("edit.save"),
                                 tr("bar.save.hint"))),
            ("settings", "settings", tip(tr("bar.settings.name"),
                                         self.cfg.key("app.settings"),
                                         tr("bar.settings.hint"))),
        ]

    # ------------------------------------------------------------- state
    def set_tool(self, tool_id: str) -> None:
        btn = self._tool_buttons.get(tool_id)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def set_color(self, color: str) -> None:
        for btn, swatch_color in zip(self._swatches, self.cfg.palette):
            btn.setIcon(icons.swatch(swatch_color, self.icon_size,
                                     selected=swatch_color.lower() == color.lower()))

    def set_width(self, value: int) -> None:
        if self.size_spin.value() != value:
            self.size_spin.blockSignals(True)
            self.size_spin.setValue(value)
            self.size_spin.blockSignals(False)

    def set_size_for_tool(self, tool_id: str, value: int) -> None:
        """Point the size box at this tool, with its own range and step.

        The spotlight is measured in radius rather than stroke width, so it
        needs a far wider range than a pen ever would.
        """
        low, high = T.width_range(tool_id)
        self.size_spin.blockSignals(True)
        self.size_spin.setRange(low, high)
        self.size_spin.setSingleStep(T.width_step(tool_id))
        self.size_spin.setValue(max(low, min(high, value)))
        self.size_spin.blockSignals(False)

    def set_history(self, can_undo: bool, can_redo: bool) -> None:
        self.btn_undo.setEnabled(can_undo)
        self.btn_redo.setEnabled(can_redo)

    def set_asleep(self, asleep: bool) -> None:
        self._asleep = asleep
        self.btn_sleep.setIcon(icons.icon("wake" if asleep else "sleep",
                                          self.icon_size, weight=self.icon_weight))
        self.set_hint(self.btn_sleep, tip(
            tr("bar.wake.name") if asleep else tr("bar.sleep.name"),
            str(self.cfg.get("general.sleep_hotkey")), tr("bar.sleep.hint")))

    def refresh_tooltips(self) -> None:
        """Called after keybinds change so the hints stay truthful.

        Built from the same helpers as the buttons themselves, so a rebind can
        never leave a tooltip advertising the old key.
        """
        for tool in T.TOOLS:
            button = self._tool_buttons.get(tool.id)
            if button is not None:
                self.set_hint(button, tip(tool.label, self.cfg.key(tool.action), tool.hint))

        for index, button in enumerate(self._swatches):
            self.set_hint(button, tip(tr("bar.colour.name", colour=self.cfg.palette[index]),
                                      self.cfg.key(f"color.{index + 1}"),
                                      tr("bar.colour.hint")))

        for name, _icon, text in self._action_tips():
            button = getattr(self, f"btn_{name}", None)
            if button is not None:
                self.set_hint(button, text)

        self.size_label.setText(tr("bar.size.name"))
        self.set_hint(self.btn_escape, self._escape_tip())
        self.set_hint(self.btn_zoom_out, tip(tr("bar.zoomout.name"), "Ctrl+-"))
        self.set_hint(self.btn_zoom_in, tip(tr("bar.zoomin.name"), "Ctrl++"))
        self.set_hint(self.btn_zoom_pan, tip(tr("bar.zoompan.name"), "",
                                             tr("bar.zoompan.hint")))
        self.set_hint(self.btn_zoom_exit, tip(tr("bar.zoomexit.name"),
                                              self.cfg.key("app.escape")))
        self.set_hint(self.btn_sleep, tip(
            tr("bar.wake.name") if self._asleep else tr("bar.sleep.name"),
            str(self.cfg.get("general.sleep_hotkey")), tr("bar.sleep.hint")))

    # ----------------------------------------------------------- position
    def _restore_position(self) -> None:
        saved = self.cfg.get("general.toolbar_pos")
        if saved and isinstance(saved, (list, tuple)) and len(saved) == 2:
            self.move(QPoint(int(saved[0]), int(saved[1])))
            if self._on_screen():
                return
        self._center_top()

    def _on_screen(self) -> bool:
        from .capture import virtual_geometry
        # Require a decent overlap so a toolbar left on a now-absent monitor
        # does not come back off-screen.
        return virtual_geometry().intersected(self.frameGeometry()).width() > 80

    def _center_top(self) -> None:
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        self.adjustSize()
        if area:
            self.move(area.center().x() - self.width() // 2, area.y() + 24)

    def save_position(self) -> None:
        self.cfg.set("general.toolbar_pos", [self.x(), self.y()])

    # -------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        # Solid, with a dark rim under a light edge. On a classroom board,
        # lit from above and glossy, a nearly-transparent dark bar with
        # hairline icons washes out into whatever is behind it; the two-tone
        # edge keeps it separate against both a white window and a dark
        # desktop.
        rim = QPainterPath()
        rim.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 13, 13)
        painter.strokePath(rim, QColor(0, 0, 0, 150))
        path.addRoundedRect(QRectF(self.rect()).adjusted(2.0, 2.0, -2.0, -2.0), 12, 12)
        painter.fillPath(path, QColor(22, 26, 32))
        painter.strokePath(path, QColor(255, 255, 255, 110))

    # --------------------------------------------------------- dragging
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_at = event.globalPosition().toPoint()
            self._drag_offset = self._press_at - self.frameGeometry().topLeft()
            self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None or self._press_at is None:
            return
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        here = event.globalPosition().toPoint()
        if not self._dragging:
            travelled = abs(here.x() - self._press_at.x()) + abs(here.y() - self._press_at.y())
            if travelled < DRAG_SLOP:
                return
            self._dragging = True
        self.move(here - self._drag_offset)
        self.placement_changed.emit()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is None:
            return
        self._drag_offset = None
        self._press_at = None
        if self._dragging:
            self._dragging = False
            self.keep_on_screen()
            self.save_position()
            self.placement_changed.emit()

    def keep_on_screen(self) -> None:
        """Pull the bar back inside the monitor it is mostly on.

        A bar dragged over the edge takes its buttons with it, and on a board
        with no keyboard there is then no way to reach them again -- not even
        to quit.
        """
        frame = self.frameGeometry()
        screen = (QGuiApplication.screenAt(frame.center())
                  or QGuiApplication.screenAt(frame.topLeft())
                  or QGuiApplication.primaryScreen())
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(frame.x(), area.left()),
                max(area.left(), area.right() - frame.width() + 1))
        y = min(max(frame.y(), area.top()),
                max(area.top(), area.bottom() - frame.height() + 1))
        if (x, y) != (frame.x(), frame.y()):
            self.move(x, y)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.placement_changed.emit()

    def hideEvent(self, event) -> None:
        self._bubble.cancel()
        super().hideEvent(event)
        self.placement_changed.emit()

    def moveEvent(self, event) -> None:
        # Every move and every resize has to be announced, however it was
        # caused: the overlay cuts this rectangle out of itself, and a hole
        # left where the bar used to be means the buttons stop responding.
        super().moveEvent(event)
        self.placement_changed.emit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.placement_changed.emit()
