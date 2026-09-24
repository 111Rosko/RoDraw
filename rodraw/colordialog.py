"""Custom colour picker.

Gives what Qt's stock dialog does not put together in one place: a live
saturation/value gradient with a hue bar, a hex box, the colours recently
used, and a way back to the eight defaults without losing that history.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QToolButton,
                             QVBoxLayout, QWidget)

from . import icons
from .i18n import tr

HISTORY_LIMIT = 18


class _SatVal(QWidget):
    """Saturation across, value down, for the current hue."""

    picked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 170)
        self._hue = 0.0
        self._sat = 1.0
        self._val = 1.0

    def set_hue(self, hue: float) -> None:
        self._hue = hue
        self.update()

    def set_sv(self, sat: float, val: float) -> None:
        self._sat, self._val = sat, val
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())

        across = QLinearGradient(rect.topLeft(), rect.topRight())
        across.setColorAt(0.0, QColor("#FFFFFF"))
        across.setColorAt(1.0, QColor.fromHsvF(self._hue, 1.0, 1.0))
        painter.fillRect(rect, across)

        down = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        down.setColorAt(0.0, QColor(0, 0, 0, 0))
        down.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, down)

        x = rect.left() + self._sat * rect.width()
        y = rect.top() + (1.0 - self._val) * rect.height()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 180), 3))
        painter.drawEllipse(QPoint(int(x), int(y)), 7, 7)
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.6))
        painter.drawEllipse(QPoint(int(x), int(y)), 7, 7)

    def _emit(self, pos) -> None:
        sat = min(1.0, max(0.0, pos.x() / max(1, self.width())))
        val = 1.0 - min(1.0, max(0.0, pos.y() / max(1, self.height())))
        self._sat, self._val = sat, val
        self.update()
        self.picked.emit(sat, val)

    def mousePressEvent(self, event):
        self._emit(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._emit(event.position())


class _HueBar(QWidget):
    picked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(22)
        self.setMinimumHeight(170)
        self._hue = 0.0

    def set_hue(self, hue: float) -> None:
        self._hue = hue
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = QRectF(self.rect())
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        for i in range(7):
            gradient.setColorAt(i / 6.0, QColor.fromHsvF(i / 6.0 % 1.0, 1.0, 1.0))
        painter.fillRect(rect, gradient)

        y = rect.top() + self._hue * rect.height()
        painter.setPen(QPen(QColor(0, 0, 0, 200), 3))
        painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.4))
        painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))

    def _emit(self, pos) -> None:
        hue = min(0.9999, max(0.0, pos.y() / max(1, self.height())))
        self._hue = hue
        self.update()
        self.picked.emit(hue)

    def mousePressEvent(self, event):
        self._emit(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._emit(event.position())


class ColorDialog(QDialog):
    """Pick a colour for one palette slot."""

    def __init__(self, config, slot: int, current: str, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.slot = slot
        self._color = QColor(current)
        self.reset_requested = False

        self.setWindowTitle(tr("colour.title", index=slot + 1))
        self.setWindowIcon(icons.icon("settings", 32))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self)

        # -- gradient + hue
        row = QHBoxLayout()
        self.square = _SatVal(self)
        self.bar = _HueBar(self)
        row.addWidget(self.square, 1)
        row.addWidget(self.bar)
        outer.addLayout(row)

        # -- hex box and preview
        line = QHBoxLayout()
        line.addWidget(QLabel(tr("colour.hex"), self))
        self.hex_edit = QLineEdit(self)
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setFixedWidth(110)
        line.addWidget(self.hex_edit)
        self.preview = QLabel(self)
        self.preview.setFixedSize(58, 26)
        line.addWidget(self.preview)
        line.addStretch(1)
        outer.addLayout(line)

        # -- history
        outer.addWidget(QLabel(tr("colour.recent"), self))
        self.history_row = QGridLayout()
        self.history_row.setSpacing(4)
        holder = QWidget(self)
        holder.setLayout(self.history_row)
        outer.addWidget(holder)
        self._build_history()

        # -- reset
        self.reset_button = QPushButton(tr("colour.reset"), self)
        self.reset_button.setToolTip(tr("colour.reset.hint"))
        self.reset_button.clicked.connect(self._reset_palette)
        outer.addWidget(self.reset_button, alignment=Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("colour.ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("set.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.square.picked.connect(self._sv_picked)
        self.bar.picked.connect(self._hue_picked)
        self.hex_edit.textEdited.connect(self._hex_typed)

        self._apply(self._color, update_hex=True)

    # ------------------------------------------------------------ colour
    def color(self) -> str:
        return self._color.name().upper()

    def _apply(self, color: QColor, update_hex: bool) -> None:
        self._color = color
        hue, sat, val, _ = color.getHsvF()
        if hue < 0:
            hue = 0.0                    # greys report -1
        self.bar.set_hue(hue)
        self.square.set_hue(hue)
        self.square.set_sv(sat, val)
        self.preview.setStyleSheet(
            f"background: {color.name()}; border: 1px solid rgba(255,255,255,0.3);"
            f" border-radius: 4px;")
        if update_hex:
            self.hex_edit.setText(color.name().upper())

    def _sv_picked(self, sat: float, val: float) -> None:
        hue, _, _, _ = self._color.getHsvF()
        self._apply(QColor.fromHsvF(max(0.0, hue), sat, val), update_hex=True)

    def _hue_picked(self, hue: float) -> None:
        _, sat, val, _ = self._color.getHsvF()
        self._apply(QColor.fromHsvF(hue, sat, val), update_hex=True)

    def _hex_typed(self, text: str) -> None:
        text = text.strip()
        if not text.startswith("#"):
            text = "#" + text
        color = QColor(text)
        if color.isValid() and len(text) in (4, 7):
            self._apply(color, update_hex=False)

    # ----------------------------------------------------------- history
    def _build_history(self) -> None:
        while self.history_row.count():
            item = self.history_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        history = list(self.cfg.get("drawing.color_history") or [])
        if not history:
            empty = QLabel(tr("colour.recent.none"), self)
            empty.setObjectName("hint")
            self.history_row.addWidget(empty, 0, 0)
            return

        for index, value in enumerate(history[:HISTORY_LIMIT]):
            button = QToolButton(self)
            button.setFixedSize(26, 26)
            button.setIcon(icons.swatch(value, 18))
            button.setToolTip(value)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _, v=value: self._apply(QColor(v), update_hex=True))
            self.history_row.addWidget(button, index // 9, index % 9)

        # Keep the swatches packed to the left instead of spread across.
        self.history_row.setColumnStretch(9, 1)

    def _reset_palette(self) -> None:
        """Put the eight defaults back. The history is untouched, so anything
        mixed by hand can still be picked out of it afterwards."""
        self.reset_requested = True
        self.accept()


STYLE = """
QDialog, QWidget { background: #1B1F24; color: #E8ECF1; }
QLabel { color: #E8ECF1; }
QLabel#hint { color: #9AA4AF; font-size: 11px; }
QLineEdit {
    background: rgba(255,255,255,0.07); color: #E8ECF1;
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 5px; padding: 4px 6px;
}
QPushButton {
    background: rgba(255,255,255,0.09); color: #E8ECF1;
    border: 1px solid rgba(255,255,255,0.16);
    border-radius: 6px; padding: 6px 14px;
}
QPushButton:hover { background: rgba(255,255,255,0.15); }
QPushButton:default { background: rgba(50,173,230,0.34); border-color: #32ADE6; }
QToolButton { background: transparent; border: none; border-radius: 4px; }
QToolButton:hover { background: rgba(255,255,255,0.14); }
"""
