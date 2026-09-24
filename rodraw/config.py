r"""Persistent configuration for RoDraw.

Settings live in %APPDATA%\RoDraw\settings.json. Anything missing from the
file falls back to DEFAULTS, so upgrading RoDraw never invalidates an old
config -- new keys simply appear with their default value.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

APP_NAME = "RoDraw"

# ---------------------------------------------------------------- locations

def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "settings.json"


def shots_dir() -> Path:
    d = Path.home() / "Pictures" / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


# ----------------------------------------------------------------- defaults

# Eight slots, reachable with the 1-8 number keys. Chosen to stay legible on
# both bright slides and dark IDE/terminal backgrounds.
DEFAULT_PALETTE = [
    "#FF3B30",  # red
    "#FF9500",  # orange
    "#FFD60A",  # yellow
    "#34C759",  # green
    "#32ADE6",  # cyan
    "#0A84FF",  # blue
    "#BF5AF2",  # purple
    "#FFFFFF",  # white
]

# action id -> default key sequence. Single letters are tool switches; the
# combos follow the conventions people already know from other editors.
DEFAULT_KEYBINDS = {
    "tool.select": "V",
    "tool.pen": "P",
    "tool.highlighter": "H",
    "tool.eraser": "E",
    "tool.line": "L",
    "tool.arrow": "A",
    "tool.rect": "R",
    "tool.ellipse": "O",
    "tool.text": "T",
    "tool.spotlight": "X",
    "tool.zoom": "Z",

    "edit.undo": "Ctrl+Z",
    "edit.redo": "Ctrl+Y",
    "edit.redo_alt": "Ctrl+Shift+Z",
    "edit.clear": "Ctrl+D",
    "edit.delete": "Del",
    "edit.save": "Ctrl+S",
    "edit.copy": "Ctrl+C",

    "view.zoom_in": "+",
    "view.zoom_out": "-",
    "view.zoom_reset": "0",
    "view.refresh_capture": "F5",
    "view.whiteboard": "W",
    "view.blackboard": "B",

    "brush.bigger": "]",
    "brush.smaller": "[",

    "app.escape": "Esc",
    "app.toggle_toolbar": "Tab",
    "app.settings": "Ctrl+,",
    "app.quit": "Ctrl+Q",
}

# Colour slots are generated rather than typed out, so the palette length and
# the keybind list can never drift apart.
for _i in range(len(DEFAULT_PALETTE)):
    DEFAULT_KEYBINDS[f"color.{_i + 1}"] = str(_i + 1)

# Keybind rows for the settings tab: (group key, [(action, label key)]).
# Only keys are stored; the text is translated when the tab is drawn.
KEYBIND_GROUPS = [
    ("keys.group.tools", [
        ("tool.select", "tool.select.name"),
        ("tool.pen", "tool.pen.name"),
        ("tool.highlighter", "tool.highlighter.name"),
        ("tool.eraser", "tool.eraser.name"),
        ("tool.line", "tool.line.name"),
        ("tool.arrow", "tool.arrow.name"),
        ("tool.rect", "tool.rect.name"),
        ("tool.ellipse", "tool.ellipse.name"),
        ("tool.text", "tool.text.name"),
        ("tool.spotlight", "tool.spotlight.name"),
        ("tool.zoom", "tool.zoom.name"),
    ]),
    ("keys.group.edit", [
        ("edit.undo", "keys.edit.undo"),
        ("edit.redo", "keys.edit.redo"),
        ("edit.redo_alt", "keys.edit.redo_alt"),
        ("edit.clear", "keys.edit.clear"),
        ("edit.delete", "keys.edit.delete"),
        ("edit.save", "keys.edit.save"),
        ("edit.copy", "keys.edit.copy"),
    ]),
    ("keys.group.view", [
        ("view.zoom_in", "keys.view.zoom_in"),
        ("view.zoom_out", "keys.view.zoom_out"),
        ("view.zoom_reset", "keys.view.zoom_reset"),
        ("view.refresh_capture", "keys.view.refresh"),
        ("view.whiteboard", "keys.view.whiteboard"),
        ("view.blackboard", "keys.view.blackboard"),
    ]),
    ("keys.group.brush", [
        ("brush.bigger", "keys.brush.bigger"),
        ("brush.smaller", "keys.brush.smaller"),
    ]),
    ("keys.group.colours",
     [(f"color.{i + 1}", "keys.colour.slot") for i in range(len(DEFAULT_PALETTE))]),
    ("keys.group.app", [
        ("app.escape", "keys.app.escape"),
        ("app.toggle_toolbar", "keys.app.toolbar"),
        ("app.settings", "keys.app.settings"),
        ("app.quit", "keys.app.quit"),
    ]),
]

DEFAULTS = {
    "version": 1,
    "general": {
        # Interface language; English unless the user picks otherwise.
        "language": "en",
        # Global hotkey -- works even while RoDraw is asleep and another app
        # has focus, which is the whole point of sleep mode.
        "sleep_hotkey": "F8",
        "start_asleep": False,
        "show_toolbar": True,
        "keep_annotations_when_asleep": True,
        "dim_annotations_when_asleep": True,
        "toolbar_pos": None,
        "run_at_startup": False,
        "show_brush_cursor": True,
        # "auto" follows what Windows reports about the hardware; "on" and
        # "off" override it for a board whose driver lies either way.
        "touch_mode": "auto",
        # "bar" is one long strip; "compact" stacks it into a block that can
        # sit in a corner, within reach of a pupil who cannot get to the top
        # of a board.
        "toolbar_layout": "bar",
        # Percent. For a board whose buttons come out too small, or a laptop
        # where they come out too big.
        "toolbar_scale": 100,
    },
    "drawing": {
        "color": DEFAULT_PALETTE[0],
        "pen_width": 4,
        "highlighter_width": 26,
        "eraser_width": 34,
        "shape_width": 4,
        "spotlight_radius": 150,
        "font_size": 28,
        "fill_shapes": False,
        # False = rub out only what the eraser passes over; True = remove a
        # whole stroke the moment the eraser touches any part of it.
        "eraser_whole_stroke": False,
        "palette": list(DEFAULT_PALETTE),
        # Colours mixed by hand, newest first. Survives a palette reset so a
        # favourite is never lost by swapping a slot.
        "color_history": [],
    },
    "keybinds": dict(DEFAULT_KEYBINDS),
}


# ------------------------------------------------------------------- loader

def _deep_merge(base: dict, override: dict) -> dict:
    """Overlay `override` onto a copy of `base`, recursing into dicts."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Dict-backed settings with dotted-path access and atomic saves."""

    def __init__(self, data: dict | None = None):
        self.data = _deep_merge(DEFAULTS, data or {})
        # A config written by a future/corrupt build could drop keybinds we
        # rely on; backfill so lookups never KeyError.
        for action, seq in DEFAULT_KEYBINDS.items():
            self.data["keybinds"].setdefault(action, seq)

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls(json.load(fh))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            # A damaged file should not stop the app from starting.
            return cls()

    def save(self) -> None:
        path = config_path()
        tmp = path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass

    # dotted access -------------------------------------------------------
    def get(self, path: str, default=None):
        node = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, path: str, value) -> None:
        parts = path.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    # keybinds ------------------------------------------------------------
    def key(self, action: str) -> str:
        return self.data["keybinds"].get(action, DEFAULT_KEYBINDS.get(action, ""))

    def reset_keybinds(self) -> None:
        self.data["keybinds"] = dict(DEFAULT_KEYBINDS)

    @property
    def palette(self) -> list[str]:
        pal = self.get("drawing.palette") or []
        if len(pal) < len(DEFAULT_PALETTE):
            pal = list(pal) + DEFAULT_PALETTE[len(pal):]
        return pal[:len(DEFAULT_PALETTE)]
