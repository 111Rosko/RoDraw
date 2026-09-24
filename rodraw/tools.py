"""Tool catalogue.

One table drives the toolbar buttons, the keybind defaults and the settings
UI, so adding a tool never means editing three files that can drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass

from .i18n import tr

SELECT = "select"
PEN = "pen"
HIGHLIGHTER = "highlighter"
ERASER = "eraser"
LINE = "line"
ARROW = "arrow"
RECT = "rect"
ELLIPSE = "ellipse"
TEXT = "text"
# Kept so an old settings file naming it does not break anything. The
# laser is no longer offered: it followed the mouse cursor, and on a touch
# board there is no cursor except while a finger is down.
LASER = "laser"
SPOTLIGHT = "spotlight"
ZOOM = "zoom"


@dataclass(frozen=True)
class ToolDef:
    id: str
    action: str              # keybind action id
    shape_kind: str | None   # what it commits to the document, if anything

    # Name and description are looked up when they are shown, not when the
    # table is built, so switching language does not need a restart.
    @property
    def label(self) -> str:
        return tr(f"tool.{self.id}.name")

    @property
    def hint(self) -> str:
        return tr(f"tool.{self.id}.hint")


TOOLS: list[ToolDef] = [
    ToolDef(SELECT, "tool.select", None),
    ToolDef(PEN, "tool.pen", "path"),
    ToolDef(HIGHLIGHTER, "tool.highlighter", "path"),
    ToolDef(ERASER, "tool.eraser", None),
    ToolDef(LINE, "tool.line", "line"),
    ToolDef(ARROW, "tool.arrow", "arrow"),
    ToolDef(RECT, "tool.rect", "rect"),
    ToolDef(ELLIPSE, "tool.ellipse", "ellipse"),
    ToolDef(TEXT, "tool.text", "text"),
    ToolDef(SPOTLIGHT, "tool.spotlight", None),
    ToolDef(ZOOM, "tool.zoom", None),
]

BY_ID = {t.id: t for t in TOOLS}

# Tools that commit a shape by dragging from press to release.
DRAG_SHAPE_TOOLS = {LINE, ARROW, RECT, ELLIPSE}

# Tools that only affect presentation and never touch the document.
TRANSIENT_TOOLS = {SPOTLIGHT, ZOOM}

# Pointing aids rather than drawing tools. While one of these is active the
# overlay stops swallowing the mouse, so the class can still be shown a live
# page -- scrolled, clicked -- with the pointer riding on top of it.
PASSTHROUGH_TOOLS = {SPOTLIGHT}


def width_key(tool_id: str) -> str:
    """Which config value the size box edits for this tool."""
    if tool_id == HIGHLIGHTER:
        return "drawing.highlighter_width"
    if tool_id == ERASER:
        return "drawing.eraser_width"
    if tool_id == PEN:
        return "drawing.pen_width"
    if tool_id == SPOTLIGHT:
        # Not a stroke width, but the same control edits it: the size box and
        # the wheel both resize the spotlight circle.
        return "drawing.spotlight_radius"
    if tool_id == TEXT:
        # Nor is this one. The size box used to point at the shape outline
        # width while the text tool was in hand, so turning it did nothing
        # visible and the lettering stayed one size for ever.
        return "drawing.font_size"
    return "drawing.shape_width"


def width_range(tool_id: str) -> tuple[int, int]:
    """Lowest and highest useful size for this tool."""
    if tool_id == SPOTLIGHT:
        return 40, 700
    if tool_id == TEXT:
        return 8, 200
    if tool_id in (HIGHLIGHTER, ERASER):
        return 4, 120
    return 1, 120


def width_step(tool_id: str) -> int:
    """How much one wheel notch or key press changes the size."""
    if tool_id == SPOTLIGHT:
        return 20
    return 4 if tool_id == TEXT else 2
