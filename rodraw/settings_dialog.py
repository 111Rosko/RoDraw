"""Settings window: General, Drawing, Keybinds, About.

Edits are staged in a working copy and only pushed into the live config when
the user saves, so cancelling really does cancel.
"""
from __future__ import annotations

import copy

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                             QDialogButtonBox,
                             QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                             QKeySequenceEdit, QLabel, QMessageBox, QPushButton,
                             QScrollArea, QSpinBox, QTabWidget, QToolButton,
                             QVBoxLayout, QWidget)

from . import icons
from .assets import resource_path
from .config import DEFAULT_KEYBINDS, KEYBIND_GROUPS
from .i18n import available, set_language, tr
from .hotkeys import parse_hotkey

DIALOG_STYLE = """
QDialog, QWidget { background: #1B1F24; color: #E8ECF1; }
QGroupBox {
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px; margin-top: 14px; padding-top: 10px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9AA4AF; }
QLabel { color: #E8ECF1; }
QLabel#hint { color: #9AA4AF; font-size: 11px; }
QLabel#warn { color: #FF9F0A; font-size: 11px; }
QTabWidget::pane { border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; }
QTabBar::tab {
    background: transparent; color: #9AA4AF;
    padding: 7px 16px; border-radius: 6px; margin: 3px;
}
QTabBar::tab:selected { background: rgba(50,173,230,0.24); color: #FFFFFF; }
QSpinBox, QKeySequenceEdit, QLineEdit {
    background: rgba(255,255,255,0.07); color: #E8ECF1;
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 5px; padding: 4px 6px; min-height: 18px;
}
QPushButton {
    background: rgba(255,255,255,0.09); color: #E8ECF1;
    border: 1px solid rgba(255,255,255,0.16);
    border-radius: 6px; padding: 6px 14px;
}
QPushButton:hover { background: rgba(255,255,255,0.15); }
QPushButton:default { background: rgba(50,173,230,0.34); border-color: #32ADE6; }
QScrollArea { border: none; }
QCheckBox { spacing: 8px; }
"""


def _row_label(action: str, label_key: str) -> str:
    """Keybind row label; colour slots interpolate their number."""
    slot = action.rsplit(".", 1)[-1] if action.startswith("color.") else ""
    return tr(label_key, index=slot)


def seq_to_text(edit: QKeySequenceEdit) -> str:
    seq = edit.keySequence()
    return seq.toString(QKeySequence.SequenceFormat.PortableText) if not seq.isEmpty() else ""


class SettingsDialog(QDialog):
    applied = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.working = copy.deepcopy(config.data)

        self.setWindowTitle(tr("set.title"))
        self.setWindowIcon(icons.icon("settings", 32))
        self.setStyleSheet(DIALOG_STYLE)
        self.setMinimumSize(620, 600)
        # Stay above the always-on-top overlay, or it would be unreachable.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._key_edits: dict[str, QKeySequenceEdit] = {}
        self.language_changed = False

        layout = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._general_tab(), tr("set.tab.general"))
        tabs.addTab(self._drawing_tab(), tr("set.tab.drawing"))
        tabs.addTab(self._keybinds_tab(), tr("set.tab.keys"))
        tabs.addTab(self._about_tab(), tr("set.tab.about"))
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("set.save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("set.cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ----------------------------------------------------------- General
    def _general_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)

        lang_box = QGroupBox(tr("set.lang.group"))
        lang_form = QFormLayout(lang_box)
        self.lang_combo = QComboBox(self)
        for code, name in available():
            self.lang_combo.addItem(name, code)
        current = str(self.working["general"].get("language", "en"))
        index = self.lang_combo.findData(current)
        self.lang_combo.setCurrentIndex(index if index >= 0 else 0)
        lang_form.addRow(tr("set.lang.label"), self.lang_combo)
        lang_hint = QLabel(tr("set.lang.hint"), self)
        lang_hint.setObjectName("hint")
        lang_hint.setWordWrap(True)
        lang_form.addRow(lang_hint)

        outer.addWidget(lang_box)

        sleep_box = QGroupBox(tr("set.sleep.group"))
        form = QFormLayout(sleep_box)

        self.sleep_edit = QKeySequenceEdit(self)
        self.sleep_edit.setKeySequence(QKeySequence(self.working["general"]["sleep_hotkey"]))
        self.sleep_edit.setMaximumSequenceLength(1)
        self.sleep_edit.keySequenceChanged.connect(self._validate_sleep_key)
        form.addRow(tr("set.sleep.button"), self.sleep_edit)

        self.sleep_warning = QLabel("", self)
        self.sleep_warning.setObjectName("warn")
        self.sleep_warning.setWordWrap(True)
        form.addRow("", self.sleep_warning)

        hint = QLabel(tr("set.sleep.hint"), self)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)

        self.chk_keep = QCheckBox(tr("set.sleep.keep"), self)
        self.chk_keep.setChecked(self.working["general"]["keep_annotations_when_asleep"])
        self.chk_dim = QCheckBox(tr("set.sleep.fade"), self)
        self.chk_dim.setChecked(self.working["general"]["dim_annotations_when_asleep"])
        self.chk_start_asleep = QCheckBox(tr("set.sleep.start"), self)
        self.chk_start_asleep.setChecked(self.working["general"]["start_asleep"])
        for box in (self.chk_keep, self.chk_dim, self.chk_start_asleep):
            form.addRow(box)
        self.chk_keep.toggled.connect(self.chk_dim.setEnabled)
        self.chk_dim.setEnabled(self.chk_keep.isChecked())

        outer.addWidget(sleep_box)

        iface = QGroupBox(tr("set.ui.group"))
        iform = QFormLayout(iface)
        self.chk_toolbar = QCheckBox(tr("set.ui.toolbar"), self)
        self.chk_toolbar.setChecked(self.working["general"]["show_toolbar"])
        self.chk_cursor = QCheckBox(tr("set.ui.cursor"), self)
        self.chk_cursor.setChecked(self.working["general"]["show_brush_cursor"])
        self.chk_startup = QCheckBox(tr("set.ui.startup"), self)
        self.chk_startup.setChecked(self.working["general"]["run_at_startup"])
        for box in (self.chk_toolbar, self.chk_cursor, self.chk_startup):
            iform.addRow(box)

        self.layout_combo = QComboBox(self)
        for value, key in (("bar", "set.layout.bar"),
                           ("compact", "set.layout.compact")):
            self.layout_combo.addItem(tr(key), value)
        shape = str(self.working["general"].get("toolbar_layout", "bar"))
        found = self.layout_combo.findData(shape)
        self.layout_combo.setCurrentIndex(found if found >= 0 else 0)
        iform.addRow(tr("set.general.barlayout"), self.layout_combo)
        layout_hint = QLabel(tr("set.general.barlayout.hint"), self)
        layout_hint.setObjectName("hint")
        layout_hint.setWordWrap(True)
        iform.addRow(layout_hint)

        self.scale_spin = QSpinBox(self)
        self.scale_spin.setRange(60, 220)
        self.scale_spin.setSingleStep(10)
        self.scale_spin.setSuffix(" %")
        try:
            self.scale_spin.setValue(int(self.working["general"].get("toolbar_scale", 100)))
        except (TypeError, ValueError):
            self.scale_spin.setValue(100)
        iform.addRow(tr("set.general.barscale"), self.scale_spin)
        scale_hint = QLabel(tr("set.general.barscale.hint"), self)
        scale_hint.setObjectName("hint")
        scale_hint.setWordWrap(True)
        iform.addRow(scale_hint)

        self.touch_combo = QComboBox(self)
        for value, key in (("auto", "set.touch.auto"), ("on", "set.touch.on"),
                           ("off", "set.touch.off")):
            self.touch_combo.addItem(tr(key), value)
        mode = str(self.working["general"].get("touch_mode", "auto"))
        found = self.touch_combo.findData(mode)
        self.touch_combo.setCurrentIndex(found if found >= 0 else 0)
        iform.addRow(tr("set.general.touch"), self.touch_combo)
        touch_hint = QLabel(tr("set.general.touch.hint"), self)
        touch_hint.setObjectName("hint")
        touch_hint.setWordWrap(True)
        iform.addRow(touch_hint)

        outer.addWidget(iface)

        outer.addStretch(1)
        return page

    def _validate_sleep_key(self) -> None:
        text = seq_to_text(self.sleep_edit)
        if not text:
            self.sleep_warning.setText("")
            return
        if parse_hotkey(text) is None:
            self.sleep_warning.setText(tr("set.sleep.bad_key", key=text))
        elif "+" not in text and len(text) == 1:
            self.sleep_warning.setText(tr("set.sleep.plain_key", key=text))
        else:
            self.sleep_warning.setText("")

    # ----------------------------------------------------------- Drawing
    def _drawing_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)

        sizes = QGroupBox(tr("set.sizes.group"))
        form = QFormLayout(sizes)
        self.spins: dict[str, QSpinBox] = {}
        for key, label_key, lo, hi in [
            ("pen_width", "set.sizes.pen", 1, 60),
            ("highlighter_width", "set.sizes.highlighter", 4, 120),
            ("eraser_width", "set.sizes.eraser", 4, 120),
            ("shape_width", "set.sizes.shape", 1, 60),
            ("font_size", "set.sizes.font", 8, 120),
        ]:
            spin = QSpinBox(self)
            spin.setRange(lo, hi)
            spin.setValue(int(self.working["drawing"][key]))
            form.addRow(tr(label_key), spin)
            self.spins[key] = spin
        self.chk_fill = QCheckBox(tr("set.fill"), self)
        self.chk_fill.setChecked(self.working["drawing"]["fill_shapes"])
        form.addRow(self.chk_fill)

        self.chk_whole = QCheckBox(tr("set.eraser_whole"), self)
        self.chk_whole.setChecked(self.working["drawing"].get("eraser_whole_stroke", False))
        form.addRow(self.chk_whole)
        outer.addWidget(sizes)

        palette_box = QGroupBox(tr("set.palette.group"))
        grid = QGridLayout(palette_box)
        self._palette_buttons: list[QToolButton] = []
        for index, color in enumerate(self.working["drawing"]["palette"]):
            btn = QToolButton(self)
            btn.setFixedSize(40, 32)
            btn.setIcon(icons.swatch(color, 22))
            btn.setToolTip(tr("set.palette.tip", index=index + 1))
            btn.clicked.connect(lambda _, i=index: self._pick_color(i))
            grid.addWidget(QLabel(str(index + 1), self), 0, index, Qt.AlignmentFlag.AlignHCenter)
            grid.addWidget(btn, 1, index)
            self._palette_buttons.append(btn)
        hint = QLabel(tr("set.palette.hint"), self)
        hint.setObjectName("hint")
        grid.addWidget(hint, 2, 0, 1, len(self._palette_buttons))
        outer.addWidget(palette_box)

        outer.addStretch(1)
        return page

    def _pick_color(self, index: int) -> None:
        current = QColor(self.working["drawing"]["palette"][index])
        chosen = QColorDialog.getColor(current, self,
                                       tr("set.palette.pick", index=index + 1))
        if chosen.isValid():
            value = chosen.name().upper()
            self.working["drawing"]["palette"][index] = value
            self._palette_buttons[index].setIcon(icons.swatch(value, 22))

    # ---------------------------------------------------------- Keybinds
    def _keybinds_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)

        intro = QLabel(tr("set.keys.intro"), self)
        intro.setObjectName("hint")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        inner = QWidget()
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(4, 4, 12, 4)

        for group_key, entries in KEYBIND_GROUPS:
            box = QGroupBox(tr(group_key))
            form = QFormLayout(box)
            for action, label_key in entries:
                edit = QKeySequenceEdit(self)
                edit.setMaximumSequenceLength(1)
                edit.setKeySequence(QKeySequence(self.working["keybinds"].get(action, "")))
                edit.keySequenceChanged.connect(self._check_conflicts)
                self._key_edits[action] = edit

                clear = QToolButton(self)
                clear.setText("x")
                clear.setToolTip(tr("set.keys.unassign"))
                clear.setFixedWidth(26)
                clear.clicked.connect(lambda _, e=edit: e.clear())

                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(edit, 1)
                row.addWidget(clear)
                holder = QWidget()
                holder.setLayout(row)
                form.addRow(_row_label(action, label_key) + ":", holder)
            vbox.addWidget(box)
        vbox.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, 1)

        self.conflict_label = QLabel("", self)
        self.conflict_label.setObjectName("warn")
        self.conflict_label.setWordWrap(True)
        outer.addWidget(self.conflict_label)

        restore = QPushButton(tr("set.keys.restore"), self)
        restore.clicked.connect(self._restore_keybinds)
        outer.addWidget(restore, alignment=Qt.AlignmentFlag.AlignLeft)

        self._check_conflicts()
        return page

    def _restore_keybinds(self) -> None:
        for action, edit in self._key_edits.items():
            edit.setKeySequence(QKeySequence(DEFAULT_KEYBINDS.get(action, "")))
        self._check_conflicts()

    def _current_keybinds(self) -> dict[str, str]:
        return {action: seq_to_text(edit) for action, edit in self._key_edits.items()}

    def _check_conflicts(self) -> None:
        seen: dict[str, list[str]] = {}
        labels = {action: _row_label(action, label_key)
                  for _, entries in KEYBIND_GROUPS for action, label_key in entries}
        for action, text in self._current_keybinds().items():
            if text:
                seen.setdefault(text.lower(), []).append(labels.get(action, action))

        clashes = [f"{key.upper()} -> {' + '.join(names)}"
                   for key, names in seen.items() if len(names) > 1]
        if clashes:
            self.conflict_label.setText(
                tr("set.keys.clash", list="; ".join(clashes)))
        else:
            self.conflict_label.setText("")

    # ------------------------------------------------------------- About
    def _about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        logo_path = resource_path("logo.png")
        if logo_path is not None:
            logo = QLabel(self)
            # Scale to the real pixel count, then label it, or the mark is
            # soft on a display running above 100%.
            ratio = icons.target_ratio()
            mark = QPixmap(str(logo_path)).scaled(
                int(72 * ratio), int(72 * ratio), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            mark.setDevicePixelRatio(ratio)
            logo.setPixmap(mark)
            layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignLeft)

        text = QLabel(tr("set.about.body"), self)
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(text)
        layout.addStretch(1)
        return page

    # -------------------------------------------------------------- save
    def _save(self) -> None:
        sleep_key = seq_to_text(self.sleep_edit)
        if not sleep_key:
            QMessageBox.warning(self, "RoDraw", tr("set.sleep.need_key"))
            return
        if parse_hotkey(sleep_key) is None:
            QMessageBox.warning(self, "RoDraw",
                                tr("set.sleep.refused", key=sleep_key))
            return

        general = self.working["general"]
        general["sleep_hotkey"] = sleep_key
        general["keep_annotations_when_asleep"] = self.chk_keep.isChecked()
        general["dim_annotations_when_asleep"] = self.chk_dim.isChecked()
        general["start_asleep"] = self.chk_start_asleep.isChecked()
        general["show_toolbar"] = self.chk_toolbar.isChecked()
        general["show_brush_cursor"] = self.chk_cursor.isChecked()
        general["run_at_startup"] = self.chk_startup.isChecked()

        chosen = self.lang_combo.currentData() or "en"
        language_changed = chosen != str(self.cfg.get("general.language", "en"))
        general["language"] = chosen

        touch = self.touch_combo.currentData() or "auto"
        shape = self.layout_combo.currentData() or "bar"
        scale = int(self.scale_spin.value())
        # Any of the three means the bar has to be built again: the button
        # sizes are fixed when each widget is made.
        touch_changed = (touch != str(self.cfg.get("general.touch_mode", "auto"))
                         or shape != str(self.cfg.get("general.toolbar_layout", "bar"))
                         or scale != int(self.cfg.get("general.toolbar_scale", 100) or 100))
        general["touch_mode"] = touch
        general["toolbar_layout"] = shape
        general["toolbar_scale"] = scale

        drawing = self.working["drawing"]
        for key, spin in self.spins.items():
            drawing[key] = spin.value()
        drawing["fill_shapes"] = self.chk_fill.isChecked()
        drawing["eraser_whole_stroke"] = self.chk_whole.isChecked()

        self.working["keybinds"] = self._current_keybinds()

        self.cfg.data = self.working
        self.cfg.save()
        # Take effect at once so the toolbar and menus change with it; this
        # dialog keeps the old wording until it is reopened.
        set_language(chosen)
        self.language_changed = language_changed
        self.touch_changed = touch_changed
        self.applied.emit()
        self.accept()
