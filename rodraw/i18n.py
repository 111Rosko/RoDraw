"""Interface translations.

`tr(key)` returns the string for the chosen language, falling back to English
for anything a translation has not filled in, so a partial translation shows
English in the gaps rather than a raw key.

English is the default. Bulgarian sits directly after it in the language list
because this is where RoDraw is used.

Adding a language means adding a code to LANGUAGES and a dict to STRINGS --
every key it omits simply reads in English.
"""
from __future__ import annotations

# Every language RoDraw knows a name for. English first, Bulgarian second --
# the rest alphabetically by their own name. A code only reaches the settings
# list once a translation for it actually exists, so nothing is offered that
# would silently show English.
NAMES: dict[str, str] = {
    "en": "English",
    "bg": "Български (Bulgarian)",
    "de": "Deutsch (German)",
    "es": "Español (Spanish)",
    "fr": "Français (French)",
    "it": "Italiano (Italian)",
    "pt": "Português do Brasil (Portuguese)",
    "ru": "Русский (Russian)",
    "tr": "Türkçe (Turkish)",
    "uk": "Українська (Ukrainian)",
}

ORDER = ["en"] + ['bg', 'de', 'es', 'fr', 'it', 'pt', 'ru', 'tr', 'uk']

_current = "en"


def set_language(code: str) -> None:
    global _current
    _current = code if code in STRINGS else "en"


def current() -> str:
    return _current


def language_name(code: str) -> str:
    return NAMES.get(code, code)


def available() -> list[tuple[str, str]]:
    """(code, name) for every language that really has a translation."""
    return [(code, NAMES.get(code, code)) for code in ORDER if code in STRINGS]


def tr(key: str, /, **fmt) -> str:
    """Look the key up in the active language, then English, then give back
    the key itself so a missing string is obvious rather than silent.

    `key` is positional-only on purpose: several strings interpolate a
    keyboard shortcut named `{key}`, and without the marker `tr("msg.ready",
    key="F8")` collides with this parameter instead of filling the
    placeholder.
    """
    table = STRINGS.get(_current, {})
    text = table.get(key) or STRINGS["en"].get(key) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text


EN = {
    # ---------------------------------------------------------- tools
    "tool.select.name": "Select / move",
    "tool.select.hint": "Pick up a label or shape and drag it; Delete removes it",
    "tool.pen.name": "Pen",
    "tool.pen.hint": "Freehand drawing",
    "tool.highlighter.name": "Highlighter",
    "tool.highlighter.hint": "Translucent wide stroke",
    "tool.eraser.name": "Eraser",
    "tool.eraser.hint": "Rubs out the part you pass over",
    "tool.line.name": "Line",
    "tool.line.hint": "Straight line; hold Shift to snap to 45 degrees",
    "tool.arrow.name": "Arrow",
    "tool.arrow.hint": "Points students at the thing that matters",
    "tool.rect.name": "Rectangle",
    "tool.rect.hint": "Box a region; hold Shift for a square",
    "tool.ellipse.name": "Ellipse",
    "tool.ellipse.hint": "Circle a region; hold Shift for a circle",
    "tool.text.name": "Text",
    "tool.text.hint": "Click, then type a label",
    "tool.laser.name": "Laser pointer",
    "tool.laser.hint": "A dot that follows the cursor; clicks still reach your apps",
    "tool.spotlight.name": "Spotlight",
    "tool.spotlight.hint": "Dims all but a circle; clicks still reach your apps",
    "tool.zoom.name": "Zoom to region",
    "tool.zoom.hint": 'Drag a box to magnify it; then scroll to move it, Ctrl+scroll to zoom',

    # -------------------------------------------------------- toolbar
    "bar.move.name": "Move the toolbar",
    "bar.move.hint": "Drag me anywhere",
    "bar.colour.name": "Colour {colour}",
    "bar.colour.hint": "Pen, shapes and text use this colour",
    "bar.size.name": "Size",
    "bar.size.hint": "How thick the current tool draws; the scroll wheel works too",
    "bar.undo.name": "Undo",
    "bar.undo.hint": "Take back the last thing you drew",
    "bar.redo.name": "Redo",
    "bar.redo.hint": "Put it back",
    "bar.clear.name": "Clear all",
    "bar.clear.hint": "Wipe every annotation from every screen",
    "bar.screens.name": "Screens",
    "bar.screens.hint": "Pick which monitors RoDraw draws on",
    "bar.board.name": "Whiteboard",
    "bar.board.hint": "A plain background on this screen; {key} for black",
    "bar.save.name": "Save screenshot",
    "bar.save.hint": "Writes a PNG into your Pictures folder",
    "bar.settings.name": "Settings",
    "bar.settings.hint": "Sleep button, sizes, colours, keybinds",
    "bar.sleep.name": "Sleep",
    "bar.wake.name": "Wake up",
    "bar.sleep.hint": "Lets every click through to your apps; drawings stay on screen",
    "bar.quit.name": "Quit RoDraw",

    # -- touch boards: on-screen replacements for the wheel and Esc
    "bar.escape.name": "Back",
    "bar.escape.hint": "Leaves zoom, spotlight or whiteboard — the same as Esc",
    "bar.zoomout.name": "Zoom out",
    "bar.zoomin.name": "Zoom in",
    "bar.zoompan.name": "Move the view",
    "bar.zoompan.hint": "Drag anywhere on the screen to move the magnified view",
    "bar.zoomexit.name": "Close the zoom",
    "set.general.touch": "Touch screen mode",
    "set.general.touch.hint": "Bigger buttons, sized for a finger",
    "set.touch.auto": "Automatic",
    "set.touch.on": "Always on",
    "set.touch.off": "Off",

    # -- the shape and size of the bar itself
    "set.general.barlayout": "Toolbar shape",
    "set.layout.bar": "One long bar",
    "set.layout.compact": "Compact block",
    "set.general.barlayout.hint": "A block sits in a corner, within reach of a pupil who cannot get to the top of a board",
    "set.general.barscale": "Toolbar size",
    "set.general.barscale.hint": "Per cent of the normal size, if the buttons come out too small or too large",

    # ----------------------------------------------------------- tray
    "tray.sleep": "Sleep",
    "tray.wake": "Wake up",
    "tray.screens": "Screens...",
    "tray.clear": "Clear annotations",
    "tray.settings": "Settings...",
    "tray.quit": "Quit RoDraw",
    "tray.ready": "RoDraw -- ready",
    "tray.asleep": "RoDraw -- asleep",

    # --------------------------------------------------------- toasts
    "msg.ready": "RoDraw is ready -- press {key} to sleep",
    "msg.start_asleep": "RoDraw is asleep -- press {key} to draw",
    "msg.asleep": "Asleep -- clicks go through. {key} to wake up",
    "msg.awake": "Awake -- ready to draw",
    "msg.cleared": "Cleared",
    "msg.zoom_on": 'Zoom {scale}x -- scroll to move, Esc to exit',
    "msg.zoom_off": "Zoom off",
    "msg.escaped": "Back to normal",
    "msg.zoom_small": "Zoom region too small",
    "msg.zoom_refreshed": "Zoom view refreshed",
    "msg.colour": "Colour {colour}",
    "msg.size": "{tool} size {size}",
    "msg.saved": "Saved to Pictures\\RoDraw\\{name}",
    "msg.save_failed": "Could not save the screenshot",
    "msg.copied": "Screenshot copied to clipboard",
    "msg.settings_saved": "Settings saved",
    "msg.hotkey_failed": "Windows would not give RoDraw the {key} button -- "
                         "another program may already use it. Pick another in Settings.",
    "msg.screen_on": "Drawing on {screen}",
    "msg.screen_off": "Leaving alone: {screen}",
    "msg.screen_last": "At least one screen has to stay on",
    "msg.lang_changed": "Language changed -- reopen Settings to see it there too",

    # -------------------------------------------------------- screens
    "screen.label": "Screen {index}: {width}x{height}",
    "screen.main": " (main)",
    "screen.menu": "Draw on which screens?",

    # ------------------------------------------------------- settings
    "set.title": "RoDraw Settings",
    "set.tab.general": "General",
    "set.tab.drawing": "Drawing",
    "set.tab.keys": "Keybinds",
    "set.tab.about": "About",
    "set.save": "Save",
    "set.cancel": "Cancel",

    "set.lang.group": "Language",
    "set.lang.label": "Interface language:",
    "set.lang.hint": "Applies to the toolbar, the menus and the messages on screen.",

    "set.sleep.group": "Sleep mode",
    "set.sleep.button": "Sleep / wake button:",
    "set.sleep.hint": "This one is registered system-wide, so it still works while "
                      "RoDraw is asleep and another program has focus. Function keys "
                      "(F8, F9...) and combos like Ctrl+Alt+D are the safest choices "
                      "-- a plain letter would be taken away from every other program.",
    "set.sleep.keep": "Keep annotations on screen while asleep",
    "set.sleep.fade": "Fade annotations while asleep",
    "set.sleep.start": "Start RoDraw asleep",
    "set.sleep.bad_key": "Windows cannot register '{key}' as a global button. "
                         "Try a function key or a combination with Ctrl / Alt.",
    "set.sleep.plain_key": "'{key}' will be captured from every program while RoDraw runs.",
    "set.sleep.need_key": "Sleep mode needs a button. Pick one before saving.",
    "set.sleep.refused": "Windows cannot register '{key}' as a system-wide button.\n\n"
                         "Try a function key such as F8, or a combination like Ctrl+Alt+D.",

    "set.ui.group": "Interface",
    "set.ui.toolbar": "Show the floating toolbar",
    "set.ui.cursor": "Show a ring around the cursor at brush size",
    "set.ui.startup": "Start RoDraw when I sign in to Windows",

    "set.sizes.group": "Default sizes",
    "set.sizes.pen": "Pen:",
    "set.sizes.highlighter": "Highlighter:",
    "set.sizes.eraser": "Eraser:",
    "set.sizes.shape": "Lines, arrows and shapes:",
    "set.sizes.font": "Text size:",
    "set.fill": "Fill rectangles and ellipses",
    "set.eraser_whole": "Eraser removes a whole stroke instead of rubbing part of it out",

    "set.palette.group": "Colour palette",
    "set.palette.hint": "Click a swatch to change it. The number above is its shortcut.",
    "set.palette.pick": "Colour slot {index}",
    "set.palette.tip": "Colour slot {index} -- press {index} while drawing",

    "set.keys.intro": "Click a box and press the keys you want. Single letters work "
                      "as plain presses while RoDraw is awake.",
    "set.keys.restore": "Restore default keybinds",
    "set.keys.unassign": "Unassign",
    "set.keys.clash": "Duplicate shortcuts (only the first will fire): {list}",

    "set.about.body":
        "<h2>RoDraw</h2>"
        "<p>Draw straight onto the screen so a class can see exactly where to look.</p>"
        "<p><b>Sleep mode</b> makes RoDraw click-through: your annotations stay on "
        "screen but every click goes to the program underneath. Press the sleep "
        "button again to carry on drawing.</p>"
        "<p><b>Zoom to region</b> freezes the screen, then blows up the box you "
        "drag. Scroll to change the magnification, middle-drag to pan, Esc to "
        "come back out.</p>"
        "<p style='color:#9AA4AF'>Settings are stored in "
        "<code>%APPDATA%\\RoDraw\\settings.json</code>.</p>",

    # -------------------------------------------------------- keybinds
    "keys.group.tools": "Tools",
    "keys.group.edit": "Edit",
    "keys.group.view": "View",
    "keys.group.brush": "Brush",
    "keys.group.colours": "Colours",
    "keys.group.app": "Application",

    "keys.edit.undo": "Undo",
    "keys.edit.redo": "Redo",
    "keys.edit.redo_alt": "Redo (alternate)",
    "keys.edit.clear": "Clear all annotations",
    "keys.edit.delete": "Delete the selected item",
    "keys.edit.save": "Save screenshot to Pictures",
    "keys.edit.copy": "Copy screenshot to clipboard",
    "keys.view.zoom_in": "Zoom in",
    "keys.view.zoom_out": "Zoom out",
    "keys.view.zoom_reset": "Reset zoom",
    "keys.view.refresh": "Refresh the frozen zoom image",
    "keys.view.whiteboard": "Whiteboard background",
    "keys.view.blackboard": "Blackboard background",
    "keys.brush.bigger": "Increase size",
    "keys.brush.smaller": "Decrease size",
    "keys.colour.slot": "Colour slot {index}",
    "keys.app.escape": "Get out of zoom, spotlight or a board",
    "keys.app.toolbar": "Show / hide toolbar",
    "keys.app.settings": "Open settings",
    "keys.app.quit": "Quit RoDraw",

    # -------------------------------------------------- colour picker
    "colour.title": "Colour slot {index}",
    "colour.hex": "Hex:",
    "colour.recent": "Recently used",
    "colour.recent.none": "Nothing yet -- colours you mix will collect here.",
    "colour.reset": "Reset the eight colours to their defaults",
    "colour.reset.hint": "Your recently used colours are kept",
    "colour.ok": "Use this colour",
    "msg.colour_changed": "Colour slot {index} is now {colour}",
    "msg.palette_reset": "Palette reset -- your recent colours are still there",
    "bar.colour.doubleclick": "Double-click a colour to mix your own",

    # ----------------------------------------------------------- misc
    "app.running": "RoDraw is already running.\n\nLook for its icon in the "
                   "notification area, next to the clock.",
}

STRINGS: dict[str, dict[str, str]] = {"en": EN}

# Pull in whatever translation modules are present.
try:
    from .lang import load as _load_translations

    STRINGS.update(_load_translations())
except ImportError:      # pragma: no cover - source tree without translations
    pass
