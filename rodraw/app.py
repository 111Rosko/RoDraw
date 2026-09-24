"""Application wiring: overlays, shortcuts, tray icon, sleep toggle, export.

There is one Overlay per monitor, all sharing a single Document. That keeps
undo global while letting each screen have its own zoom, its own board, and
its own on/off switch -- so magnifying a diagram for the class does not drag
the second monitor along with it.
"""
from __future__ import annotations

import datetime
import sys

from PyQt6.QtCore import QObject, QPoint, QPointF, QTimer, Qt
from PyQt6.QtGui import (QAction, QCursor, QGuiApplication, QIcon, QKeySequence,
                         QPainter, QPixmap, QShortcut)
from PyQt6.QtWidgets import (QApplication, QLabel, QMenu, QMessageBox,
                             QSystemTrayIcon, QWidget)

from . import capture, icons, tools as T, winutil
from .assets import resource_path
from .colordialog import ColorDialog
from .config import (Config, DEFAULT_PALETTE,
                     shots_dir)
from .hotkeys import HotkeyManager
from .i18n import set_language, tr
from .model import Document
from .overlay import Overlay
from .settings_dialog import SettingsDialog
from .toolbar import Toolbar

APP_ICON_NAME = "rodraw.ico"
TOAST_MS = 1600


def app_icon() -> QIcon:
    """The bundled brush mark, falling back to a drawn glyph."""
    path = resource_path(APP_ICON_NAME)
    return QIcon(str(path)) if path else icons.icon("pen", 64)


def screen_label(screen, index: int) -> str:
    geo = screen.geometry()
    tag = tr("screen.main") if screen == QGuiApplication.primaryScreen() else ""
    return tr("screen.label", index=index + 1,
              width=geo.width(), height=geo.height()) + tag


class Toast(QWidget):
    """Brief centred message -- feedback that is readable from the back row."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.label = QLabel("", self)
        self.label.setStyleSheet(
            "QLabel { background: rgba(20,24,30,235); color: #FFFFFF;"
            " border: 1px solid rgba(255,255,255,0.18); border-radius: 10px;"
            " padding: 10px 20px; font-size: 16px; font-weight: 600; }")

        # A screen grab hides us mid-message; do not pop back afterwards, or
        # an already-expired toast would stick around.
        self.restore_after_capture = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, ms: int = TOAST_MS) -> None:
        self.label.setText(text)
        self.label.adjustSize()
        self.resize(self.label.size())

        # Appear on whichever monitor the teacher is working on.
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen:
            area = screen.geometry()
            self.move(area.center().x() - self.width() // 2, area.y() + 70)
        self.show()
        self.raise_()
        self._timer.start(ms)


class RoDrawApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = Config.load()
        set_language(str(self.cfg.get("general.language", "en")))
        self.doc = Document()

        self.toolbar = Toolbar(self.cfg)
        self.toast = Toast()
        self.overlays: list[Overlay] = []
        self._hidden_for_capture: list[QWidget] = []
        self._tool = T.PEN
        self._asleep = False
        self._quitting = False
        self._escape_hotkey = False

        # Only live while the spotlight is the current tool.
        self._wheel_hook = winutil.WheelHook(self._on_global_wheel)

        self.hotkeys = HotkeyManager(self)
        self.hotkeys.install(app)
        self._shortcuts: list[QShortcut] = []
        self._settings_dialog: SettingsDialog | None = None

        self._build_tray()
        self._connect_toolbar()
        # Not in _connect_toolbar: that runs again when the bar is rebuilt,
        # and a second connection here would fire every hotkey twice.
        self.hotkeys.triggered.connect(self._on_global_hotkey)
        self.rebuild_overlays()

        self.toolbar.set_tool(T.PEN)
        self.toolbar.set_color(self.cfg.get("drawing.color"))
        self.toolbar.set_size_for_tool(T.PEN, int(self.cfg.get("drawing.pen_width", 4)))
        self._sync_toolbar_visibility()

        self.rebuild_shortcuts()
        self.apply_sleep_hotkey()
        self._apply_startup_setting()

        if self.cfg.get("general.start_asleep", False):
            self.set_asleep(True)

        QTimer.singleShot(400, self._greet)

        # Monitors can be plugged in mid-lesson; rebuild so each still has one.
        app.screenAdded.connect(lambda _: self.rebuild_overlays())
        app.screenRemoved.connect(lambda _: self.rebuild_overlays())
        app.primaryScreenChanged.connect(lambda _: self.rebuild_overlays())

    # ---------------------------------------------------------- overlays
    def rebuild_overlays(self) -> None:
        """One overlay per monitor, all sharing the document."""
        for overlay in self.overlays:
            # Disconnect first: hiding/destroying during a rebuild is not a
            # request to quit the application.
            try:
                overlay.close_requested.disconnect()
            except TypeError:
                pass
            overlay.hide()
            overlay.deleteLater()
        self.overlays = []

        for screen in QGuiApplication.screens():
            overlay = Overlay(self.cfg, screen, self.doc)
            overlay.companions = [self.toolbar, self.toast]
            overlay.tool_changed.connect(self.toolbar.set_tool)
            overlay.history_changed.connect(self._sync_history)
            overlay.status.connect(self.toast.show_message)
            overlay.zoom_changed.connect(self._on_zoom_changed)
            overlay.selection_changed.connect(self._on_selection_changed)
            overlay.close_requested.connect(self._closed_externally)
            overlay.set_active(self.screen_enabled(screen))
            overlay.set_tool(self._tool)
            overlay.set_color(self.cfg.get("drawing.color"))
            overlay.show()
            if self._asleep:
                overlay.set_asleep(True)
            self.overlays.append(overlay)

        # The bar is laid out for the narrowest screen that was attached
        # when it was built. Losing a monitor can leave it too wide for what
        # remains, and no amount of nudging will bring its right-hand end
        # back onto the glass -- it has to be laid out again.
        if self.toolbar.width() > self.toolbar._row_budget():
            self.rebuild_toolbar()

        # A monitor may have just been unplugged from under the bar.
        if not self.toolbar._on_screen():
            self.toolbar._center_top()
        else:
            self.toolbar.keep_on_screen()
        self.sync_toolbar_hole()
        self._sync_history()

    def _closed_externally(self) -> None:
        """Something asked a window to close; shut down tidily so the tray
        icon goes with us instead of being left behind as a ghost."""
        if not self._quitting:
            self.quit()

    def focused(self) -> Overlay:
        """The overlay the mouse is on -- what a zoom or a board applies to."""
        pos = QCursor.pos()
        for overlay in self.overlays:
            if overlay.active and overlay.screen_obj.geometry().contains(pos):
                return overlay
        for overlay in self.overlays:
            if overlay.active:
                return overlay
        return self.overlays[0]

    def sync_toolbar_hole(self) -> None:
        """Cut the toolbar's rectangle out of every overlay it sits over."""
        rect = self.toolbar.frameGeometry() if self.toolbar.isVisible() else None
        for overlay in self.overlays:
            overlay.set_toolbar_hole(rect)

    def for_each(self, fn) -> None:
        for overlay in self.overlays:
            fn(overlay)

    def _repaint_all(self) -> None:
        for overlay in self.overlays:
            overlay.update()

    # ------------------------------------------------------ active screens
    def screen_enabled(self, screen) -> bool:
        disabled = self.cfg.get("general.disabled_screens") or []
        return screen.name() not in disabled

    def set_screen_enabled(self, screen, enabled: bool) -> None:
        disabled = list(self.cfg.get("general.disabled_screens") or [])
        name = screen.name()
        if enabled:
            if name in disabled:
                disabled.remove(name)
        else:
            if sum(1 for o in self.overlays if o.active) <= 1:
                self.toast.show_message(tr("msg.screen_last"))
                return
            if name not in disabled:
                disabled.append(name)

        self.cfg.set("general.disabled_screens", disabled)
        self.cfg.save()
        for overlay in self.overlays:
            overlay.set_active(self.screen_enabled(overlay.screen_obj))

        screens = QGuiApplication.screens()
        index = screens.index(screen) if screen in screens else 0
        self.toast.show_message(
            tr("msg.screen_on" if enabled else "msg.screen_off",
               screen=screen_label(screen, index)))

    def show_screens_menu(self) -> None:
        menu = QMenu()
        header = QAction(tr("screen.menu"), menu)
        header.setEnabled(False)
        menu.addAction(header)
        menu.addSeparator()
        for index, screen in enumerate(QGuiApplication.screens()):
            action = QAction(screen_label(screen, index), menu)
            action.setCheckable(True)
            action.setChecked(self.screen_enabled(screen))
            action.toggled.connect(
                lambda checked, s=screen: self.set_screen_enabled(s, checked))
            menu.addAction(action)
        menu.exec(QCursor.pos())

    # ------------------------------------------------------------- wiring
    def _connect_toolbar(self) -> None:
        self.toolbar.tool_picked.connect(self.set_tool)
        self.toolbar.color_picked.connect(self.set_color)
        self.toolbar.width_changed.connect(self.set_brush_width)
        self.toolbar.action_triggered.connect(self._toolbar_action)
        self.toolbar.color_edit_requested.connect(self.edit_color_slot)
        self.toolbar.placement_changed.connect(self.sync_toolbar_hole)
        self.toolbar.pan_mode_changed.connect(self.set_pan_mode)

    def rebuild_toolbar(self) -> None:
        """Build the bar again after its layout mode changes.

        Button sizes are fixed when each widget is created, so switching the
        touch layout on or off needs a new bar rather than a resize.
        """
        old = self.toolbar
        old.save_position()
        self.toolbar = Toolbar(self.cfg)
        self._connect_toolbar()
        self.toolbar.set_tool(self._tool)
        self.toolbar.set_color(str(self.cfg.get("drawing.color")))
        self.toolbar.set_size_for_tool(
            self._tool, int(self.cfg.get(T.width_key(self._tool), 4)))
        self.toolbar.set_asleep(self._asleep)
        # The overlays hide their companions to take a clean screenshot, so a
        # stale bar left in that list would be a deleted widget by then.
        for overlay in self.overlays:
            overlay.companions = [self.toolbar, self.toast]
        old.hide()
        old.deleteLater()
        self._sync_history()
        self._sync_toolbar_visibility()
        self.sync_toolbar_hole()

    def set_tool(self, tool_id: str) -> None:
        # Reaching for a tool means you want to draw, not to keep shoving the
        # view about. Leaving the hand pressed made it look as though the pen
        # had stopped working: every stroke just slid the magnified picture.
        if self.toolbar.btn_zoom_pan.isChecked():
            self.toolbar.btn_zoom_pan.setChecked(False)

        self._tool = tool_id
        self.for_each(lambda o: o.set_tool(tool_id))
        self.toolbar.set_tool(tool_id)
        self.toolbar.set_size_for_tool(tool_id, int(self.cfg.get(
            T.width_key(tool_id), 4)))
        self._sync_wheel_hook()
        self._sync_escape_hotkey()   # also relights the Back button

    def _sync_size_box(self) -> None:
        """Point the size box at whatever it is currently editing.

        That is the picked-up annotation's own size when there is one, and
        the current tool's otherwise, so the wheel and the keyboard never
        leave a stale number showing.
        """
        holder = self.selected_overlay()
        if holder is not None:
            shape = holder._selected
            kind = T.TEXT if shape.kind == "text" else self._tool
            self.toolbar.set_size_for_tool(kind, holder.selected_size())
            return
        self.toolbar.set_size_for_tool(
            self._tool, int(self.cfg.get(T.width_key(self._tool), 4)))

    def _sync_wheel_hook(self) -> None:
        """Watch the wheel globally when an event alone would not reach us.

        The spotlight and the select tool make the window click-through, so no
        wheel event is ever delivered; and a magnified view has to scroll
        whichever tool happens to be in hand. The hook goes away as soon as
        neither is true.
        """
        wanted = not self._asleep and (
            self._tool == T.SPOTLIGHT
            or any(o.zoomed for o in self.overlays))
        if wanted:
            self._wheel_hook.install()
        else:
            self._wheel_hook.remove()

    def _on_global_wheel(self, steps: int, x: int, y: int) -> bool:
        if self._asleep:
            return False
        for overlay in self.overlays:
            if not (overlay.active and overlay.screen_obj.geometry().contains(x, y)):
                continue

            # Scrolling a magnified view comes first: while it is up the screen
            # is covered anyway, so nothing underneath wants the scroll.
            if overlay.zoomed:
                ctrl, shift = winutil.modifier_state()
                anchor = overlay.mapFromGlobal(QPoint(x, y))
                overlay.wheel_navigate(steps, ctrl, shift, QPointF(anchor))
                return True

            if self._tool == T.SPOTLIGHT:
                overlay.nudge_spotlight(steps)
                self._sync_size_box()
                return True     # swallow it, so the page underneath sits still
        return False

    def set_color(self, color: str) -> None:
        self.for_each(lambda o: o.set_color(color))
        self.toolbar.set_color(color)

    def remember_color(self, color: str) -> None:
        """Keep a hand-mixed colour, newest first and without duplicates, so
        swapping a slot never loses it for good."""
        history = [c for c in (self.cfg.get("drawing.color_history") or [])
                   if c.upper() != color.upper()]
        history.insert(0, color.upper())
        self.cfg.set("drawing.color_history", history[:24])

    def edit_color_slot(self, index: int) -> None:
        """Double-clicking a swatch opens the picker for that slot."""
        palette = list(self.cfg.palette)
        if not 0 <= index < len(palette):
            return

        # The overlays swallow the mouse; step aside while the dialog is up.
        was_asleep = self._asleep
        self.set_asleep(True)
        try:
            dialog = ColorDialog(self.cfg, index, palette[index], None)
            accepted = dialog.exec()
        finally:
            self.set_asleep(was_asleep)

        if not accepted:
            return

        if dialog.reset_requested:
            self.cfg.set("drawing.palette", list(DEFAULT_PALETTE))
            self.cfg.save()
            self.toolbar.refresh_palette()
            self.set_color(DEFAULT_PALETTE[0])
            self.rebuild_shortcuts()       # the number keys follow the palette
            self.toast.show_message(tr("msg.palette_reset"), 2600)
            return

        chosen = dialog.color()
        palette[index] = chosen
        self.cfg.set("drawing.palette", palette)
        self.remember_color(chosen)
        self.cfg.save()
        self.toolbar.refresh_palette()
        self.set_color(chosen)
        self.rebuild_shortcuts()
        self.toast.show_message(tr("msg.colour_changed", index=index + 1,
                                   colour=chosen), 2200)

    def selected_overlay(self):
        """The monitor holding the annotation that is picked up, if any."""
        here = self.focused()
        if here.selected_size() is not None:
            return here
        for overlay in self.overlays:
            if overlay.selected_size() is not None:
                return overlay
        return None

    def set_brush_width(self, value: int) -> None:
        """What the size box does, which depends on what is in hand.

        With an annotation picked up it resizes that annotation -- lettering
        that came out too small to read from the back used to have to be
        deleted and typed again. Otherwise it sets the size the current tool
        will draw at next.
        """
        value = int(value)
        holder = self.selected_overlay()
        if holder is not None:
            holder.resize_selected(value)
            return

        low, high = T.width_range(self._tool)
        self.cfg.set(T.width_key(self._tool), max(low, min(high, value)))
        # A text box that is open at this moment should change with it.
        self.for_each(lambda o: o.restyle_editor())
        self._repaint_all()

    def _on_selection_changed(self) -> None:
        self._sync_size_box()
        self._sync_escape_hotkey()

    def zoomed_overlay(self):
        """The monitor a zoom is live on, preferring the one under the cursor.

        The toolbar can be dragged onto a different screen from the zoom, so
        its buttons must not go looking for the zoom where the mouse is.
        """
        here = self.focused()
        if here.zoomed:
            return here
        for overlay in self.overlays:
            if overlay.zoomed:
                return overlay
        return here

    def set_pan_mode(self, on: bool) -> None:
        self.for_each(lambda o: o.set_pan_mode(on))

    def _on_zoom_changed(self, scale: float) -> None:
        self._sync_escape_hotkey()
        self._sync_wheel_hook()
        live = [o for o in self.overlays if o.zoomed]
        # Report the magnification of a screen that is still zoomed, not the
        # one that just went back to 1:1, or the readout contradicts itself
        # while the other monitor is plainly still magnified.
        self.toolbar.set_zoomed(bool(live),
                                live[0].zoom_scale if live else scale)
        self.toast.show_message(
            tr("msg.zoom_on", scale=f"{scale:.1f}") if scale > 1.001
            else tr("msg.zoom_off"))

    def _greet(self) -> None:
        key = self.cfg.get("general.sleep_hotkey", "F8")
        self.toast.show_message(
            tr("msg.start_asleep" if self._asleep else "msg.ready", key=key), 2600)

    # -------------------------------------------------------------- tray
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(tr("tray.ready"))

        menu = QMenu()
        self.act_sleep = QAction(tr("tray.sleep"), menu)
        self.act_sleep.triggered.connect(self.toggle_sleep)
        menu.addAction(self.act_sleep)
        menu.addSeparator()

        self.act_screens = act_screens = QAction(tr("tray.screens"), menu)
        act_screens.triggered.connect(self.show_screens_menu)
        menu.addAction(act_screens)

        self.act_clear = act_clear = QAction(tr("tray.clear"), menu)
        act_clear.triggered.connect(self.clear)
        menu.addAction(act_clear)

        self.act_settings = act_settings = QAction(tr("tray.settings"), menu)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)
        menu.addSeparator()

        self.act_quit = act_quit = QAction(tr("tray.quit"), menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)

        self._tray_menu = menu          # keep a reference or it is collected
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def retranslate(self) -> None:
        """Re-label everything that is already on screen after a language
        change, so only the settings window itself needs reopening."""
        self.act_sleep.setText(tr("tray.wake") if self._asleep else tr("tray.sleep"))
        self.act_screens.setText(tr("tray.screens"))
        self.act_clear.setText(tr("tray.clear"))
        self.act_settings.setText(tr("tray.settings"))
        self.act_quit.setText(tr("tray.quit"))
        self.tray.setToolTip(tr("tray.asleep") if self._asleep else tr("tray.ready"))
        self.toolbar.refresh_tooltips()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_sleep()

    # --------------------------------------------------------- shortcuts
    def _actions(self) -> dict:
        table = {
            "edit.undo": self.undo,
            "edit.redo": self.redo,
            "edit.redo_alt": self.redo,
            "edit.clear": self.clear,
            "edit.delete": lambda: self.focused().delete_selection(),
            "edit.save": self.save_screenshot,
            "edit.copy": self.copy_screenshot,

            "view.zoom_in": lambda: self.focused().zoom_by(1.25),
            "view.zoom_out": lambda: self.focused().zoom_by(1 / 1.25),
            "view.zoom_reset": lambda: self.focused().reset_zoom(),
            "view.refresh_capture": lambda: self.focused().refresh_zoom_capture(),
            "view.whiteboard": lambda: self._set_board("white"),
            "view.blackboard": lambda: self._set_board("black"),

            "brush.bigger": lambda: self._nudge_size(1),
            "brush.smaller": lambda: self._nudge_size(-1),

            "app.escape": self.escape,
            "app.toggle_toolbar": self.toggle_toolbar,
            "app.settings": self.open_settings,
            "app.quit": self.quit,
        }
        for tool in T.TOOLS:
            table[tool.action] = (lambda tid=tool.id: self.set_tool(tid))
        for index, color in enumerate(self.cfg.palette):
            table[f"color.{index + 1}"] = (lambda c=color: self._pick_color(c))
        return table

    def _set_board(self, mode: str) -> None:
        self.focused().set_board(mode)
        self._sync_escape_hotkey()

    def _nudge_size(self, direction: int) -> None:
        self.focused().nudge_brush(direction)
        # The nudge lands on the monitor the cursor is over, but the setting
        # is shared, so a text box open on another screen has to follow too.
        self.for_each(lambda o: o.restyle_editor())
        self._sync_size_box()

    def _pick_color(self, color: str) -> None:
        self.set_color(color)
        self.toast.show_message(tr("msg.colour", colour=color))

    def rebuild_shortcuts(self) -> None:
        """Recreate every QShortcut from the current keybinds."""
        for shortcut in self._shortcuts:
            shortcut.setParent(None)
            shortcut.deleteLater()
        self._shortcuts.clear()

        claimed: set[str] = set()
        for action, handler in self._actions().items():
            text = self.cfg.key(action)
            if not text:
                continue
            # First binding wins; the settings dialog warns about duplicates.
            if text.lower() in claimed:
                continue
            claimed.add(text.lower())

            # Parented to the toolbar, which outlives any single overlay --
            # overlays are thrown away and rebuilt when monitors change.
            shortcut = QShortcut(QKeySequence(text), self.toolbar)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

        self.toolbar.refresh_tooltips()

    def apply_sleep_hotkey(self) -> None:
        key = self.cfg.get("general.sleep_hotkey", "F8")
        if not self.hotkeys.register("sleep", key):
            self.toast.show_message(tr("msg.hotkey_failed", key=key), 5000)

    def _on_global_hotkey(self, name: str) -> None:
        if name == "sleep":
            self.toggle_sleep()
        elif name == "escape":
            self.escape()

    def escape(self) -> None:
        """One press out of zoom, a board, or a pointing tool.

        The overlay the mouse is on goes first, then any other monitor that is
        still zoomed or on a board -- otherwise a zoom left on the second
        screen would need the mouse moved over there to clear it.
        """
        did = self.focused().escape()
        for overlay in self.overlays:
            if overlay.presenting():
                did = overlay.escape() or did

        # Pointing tools take over the screen too; drop back to the pen.
        if self._tool in (T.SPOTLIGHT, T.LASER, T.ZOOM):
            self.set_tool(T.PEN)
            did = True

        self._sync_escape_hotkey()
        if did:
            self.toast.show_message(tr("msg.escaped"))

    def _sync_escape_hotkey(self) -> None:
        """Claim Escape system-wide only while a screen is actually covered.

        While zoomed or on a board the overlay is opaque, so no other program
        can be in use and taking Escape from them costs nothing. The rest of
        the time it stays an ordinary key that RoDraw only sees when one of
        its own windows is active.
        """
        self.toolbar.set_can_escape(
            not self._asleep
            and (any(o.can_escape() for o in self.overlays)
                 or self._tool in (T.SPOTLIGHT, T.LASER, T.ZOOM)))

        wanted = (not self._asleep
                  and any(o.presenting() for o in self.overlays))
        if wanted == self._escape_hotkey:
            return
        self._escape_hotkey = wanted
        if wanted:
            self.hotkeys.register("escape", "Esc")
        else:
            self.hotkeys.unregister("escape")

    # ----------------------------------------------------------- editing
    def _clear_selections(self) -> None:
        # Undo, redo and clear can delete the very shape the select tool is
        # hovering; drop both so it does not point at something gone.
        for overlay in self.overlays:
            overlay._selected = None
            overlay.forget_hover()

    def undo(self) -> None:
        if self.doc.undo():
            self._clear_selections()
            self._sync_history()
            self._repaint_all()

    def redo(self) -> None:
        if self.doc.redo():
            self._clear_selections()
            self._sync_history()
            self._repaint_all()

    def clear(self) -> None:
        self.for_each(lambda o: o._commit_editor())
        if self.doc.clear():
            self._clear_selections()
            self._sync_history()
            self._repaint_all()
            self.toast.show_message(tr("msg.cleared"))

    def _toolbar_action(self, name: str) -> None:
        if name == "undo":
            self.undo()
        elif name == "redo":
            self.redo()
        elif name == "clear":
            self.clear()
        elif name == "save":
            self.save_screenshot()
        elif name == "settings":
            self.open_settings()
        elif name == "sleep":
            self.toggle_sleep()
        elif name == "screens":
            self.show_screens_menu()
        elif name == "escape":
            self.escape()
        elif name == "zoom_in":
            self.zoomed_overlay().zoom_by(1.25)
        elif name == "zoom_out":
            self.zoomed_overlay().zoom_by(1 / 1.25)
        elif name == "board":
            overlay = self.focused()
            overlay.set_board("white" if overlay.board != "white" else None)
            self._sync_escape_hotkey()
        elif name == "quit":
            self.quit()

    # -------------------------------------------------------------- sleep
    def set_asleep(self, asleep: bool) -> None:
        self._asleep = asleep
        self.for_each(lambda o: o.set_asleep(asleep))
        self.toolbar.set_asleep(asleep)
        self.act_sleep.setText(tr("tray.wake") if asleep else tr("tray.sleep"))
        self.tray.setToolTip(tr("tray.asleep") if asleep else tr("tray.ready"))
        self._sync_toolbar_visibility()
        self._sync_wheel_hook()
        self._sync_escape_hotkey()
        key = self.cfg.get("general.sleep_hotkey", "F8")
        self.toast.show_message(
            tr("msg.asleep", key=key) if asleep else tr("msg.awake"))

    def toggle_sleep(self) -> None:
        self.set_asleep(not self._asleep)

    def _sync_toolbar_visibility(self) -> None:
        # The toolbar would be a click target in the way, so it goes with sleep.
        visible = self.cfg.get("general.show_toolbar", True) and not self._asleep
        self.toolbar.setVisible(visible)
        if visible:
            self.toolbar.raise_()
        self.sync_toolbar_hole()

    def _sync_history(self) -> None:
        self.toolbar.set_history(self.doc.can_undo(), self.doc.can_redo())
        self._sync_escape_hotkey()   # a finished stroke may have cleared a selection

    def toggle_toolbar(self) -> None:
        self.cfg.set("general.show_toolbar", not self.cfg.get("general.show_toolbar", True))
        self._sync_toolbar_visibility()

    # ------------------------------------------------------------ export
    def _blank_everything(self) -> None:
        self._hidden_for_capture = [w for w in (self.toolbar, self.toast) if w.isVisible()]
        for widget in self._hidden_for_capture:
            widget.hide()
        for overlay in self.overlays:
            overlay._suppress_paint = True
            overlay.repaint()

    def _restore_everything(self) -> None:
        for overlay in self.overlays:
            overlay._suppress_paint = False
            overlay.repaint()
        for widget in self._hidden_for_capture:
            if getattr(widget, "restore_after_capture", True):
                widget.show()
                widget.raise_()
        self._hidden_for_capture = []

    def render_composite(self) -> QPixmap:
        """The whole desktop with every annotation burned in, at 1:1."""
        pixmap = capture.grab_desktop_clean(self._blank_everything,
                                            self._restore_everything)
        virt = capture.virtual_geometry()
        painter = QPainter(pixmap)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing
                               | QPainter.RenderHint.TextAntialiasing)
        painter.translate(-virt.x(), -virt.y())   # canvas -> pixmap coords
        for shape in self.doc.shapes:
            shape.paint(painter)
        painter.end()
        return pixmap

    def save_screenshot(self) -> None:
        pixmap = self.render_composite()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        path = shots_dir() / f"RoDraw {stamp}.png"
        if pixmap.save(str(path), "PNG"):
            self.toast.show_message(tr("msg.saved", name=path.name), 2600)
        else:
            self.toast.show_message(tr("msg.save_failed"), 2600)

    def copy_screenshot(self) -> None:
        QApplication.clipboard().setPixmap(self.render_composite())
        self.toast.show_message(tr("msg.copied"))

    # ---------------------------------------------------------- settings
    def open_settings(self) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        # Sleep while the dialog is up, otherwise stray clicks would draw on
        # the overlays that cover the rest of the screen.
        was_asleep = self._asleep
        self.set_asleep(True)

        dialog = SettingsDialog(self.cfg, None)
        dialog.setWindowIcon(app_icon())
        self._settings_dialog = dialog
        dialog.applied.connect(self._settings_applied)
        dialog.finished.connect(lambda _: self._settings_closed(was_asleep))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _settings_applied(self) -> None:
        changed_language = bool(getattr(self._settings_dialog, "language_changed", False))
        if bool(getattr(self._settings_dialog, "touch_changed", False)):
            self.rebuild_toolbar()
        if changed_language:
            self.retranslate()
        self.rebuild_shortcuts()
        self.apply_sleep_hotkey()
        self._apply_startup_setting()
        self.set_color(self.cfg.get("drawing.color"))
        self.toolbar.set_size_for_tool(self._tool,
                                       int(self.cfg.get(T.width_key(self._tool), 4)))
        self._repaint_all()
        self.toast.show_message(
            tr("msg.lang_changed") if changed_language else tr("msg.settings_saved"),
            2600 if changed_language else 1600)

    def _settings_closed(self, was_asleep: bool) -> None:
        self._settings_dialog = None
        self.set_asleep(was_asleep)
        self._sync_toolbar_visibility()

    def _apply_startup_setting(self) -> None:
        wanted = bool(self.cfg.get("general.run_at_startup", False))
        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}"'
        else:
            command = f'"{sys.executable}" -m rodraw'
        winutil.set_run_at_startup(wanted, command)

    # -------------------------------------------------------------- quit
    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._wheel_hook.remove()
        # The toast has no parent -- it has to survive the toolbar being
        # hidden -- so close it by hand rather than leaving a top-level
        # widget to be collected after the QApplication has gone.
        self.toast.hide()
        self.toast.deleteLater()
        self.toolbar.save_position()
        self.cfg.save()
        self.hotkeys.unregister_all()
        self.tray.hide()
        self.app.quit()


def main() -> int:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv)
    app.setApplicationName("RoDraw")
    app.setOrganizationName("RoDraw")
    app.setWindowIcon(app_icon())
    # Closing the settings dialog must not end the session.
    app.setQuitOnLastWindowClosed(False)

    guard = winutil.claim_single_instance()
    if guard is None:
        # Read the language before this message, since it is shown before
        # RoDrawApp (and its config load) ever runs.
        set_language(str(Config.load().get("general.language", "en")))
        QMessageBox.information(None, "RoDraw", tr("app.running"))
        return 0

    rodraw = RoDrawApp(app)
    app._rodraw = rodraw       # keep alive for the whole session
    app._guard = guard
    return app.exec()
