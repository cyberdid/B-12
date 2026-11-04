"""Registered cybercat atlas and bounded terminal graphics, independent of the agent."""

import os
import sys
from collections import OrderedDict
from pathlib import Path

from PIL import Image
from textual_image._terminal import get_cell_size, prepare_terminal_sequence
from textual_image.renderable import Image as AutoImage
from textual_image.renderable.halfcell import Image as HalfcellImage
from textual_image.renderable.tgp import Image as TGPImage

ASSETS = Path(__file__).with_name("assets")
BG = "#0b1020"
TAIL_BOX = (0, 168, 112, 324)  # registered native-pixel tail layer in the 362px cells


class CatAtlas:
    """Read generated frames without rewriting the original PNG or its transparency."""

    def __init__(self):
        with Image.open(ASSETS / "cybercat-atlas.png") as source:
            self.sheet = source.convert("RGBA")
        self.side = self.sheet.width // 4
        self.frames = OrderedDict()
        if self.sheet.size != (self.side * 4, self.side * 3):
            raise ValueError("cybercat atlas must have twelve square cells")

    def key(self, *, phase, frame, look_x=0, look_y=0, purring=False, motion=True):
        if purring or phase == "success":
            pose = 7
        elif motion and frame % 56 in (51, 52, 53, 54):
            pose = 5 if frame % 56 in (51, 54) else 6
        elif phase == "speaking":
            pose = 8 if not motion or frame % 4 < 2 else 0
        elif phase in ("thinking", "working"):
            pose = 9
        elif phase == "approval":
            pose = 3
        elif phase in ("error", "cancelled"):
            pose = 5
        elif look_x:
            pose = 1 if look_x < 0 else 2
        elif look_y:
            pose = 3 if look_y < 0 else 4
        else:
            pose = 0
        tail = (0, 10, 0, 11)[frame % 40 // 10] if motion else 0
        # Two native-pixel positions: subtle breathing, without stretching the drawing.
        bob = 2 if motion and frame % 28 >= 14 else 0
        return pose, tail, bob

    def image(self, **state):
        return self._cell(*self.key(**state))

    def _cell(self, pose, tail, bob):
        key = pose, tail, bob
        if key in self.frames:
            self.frames.move_to_end(key)
            return self.frames[key]
        x, y = pose % 4 * self.side, pose // 4 * self.side
        sprite = self.sheet.crop((x, y, x + self.side, y + self.side))
        # Tail and face animate independently. Draw registered parts of the generated
        # sheet at runtime; neither source image is modified or written back.
        tx, ty = tail % 4 * self.side, tail // 4 * self.side
        left, top, right, bottom = TAIL_BOX
        tail_layer = self.sheet.crop((tx + left, ty + top, tx + right, ty + bottom))
        sprite.paste(tail_layer, (left, top))
        # Composite at render time so ANSI fallback has the same indigo background.
        canvas = Image.new("RGB", (self.side, self.side), BG)
        canvas.paste(sprite, (0, bob), sprite)
        if len(self.frames) >= 48:
            self.frames.popitem(last=False)
        self.frames[key] = canvas
        return canvas


def fit_portrait(width, height, cell_width, cell_height):
    """Contain a square in the available physical pixels, not the terminal cell ratio."""
    side = min(max(1, width) * cell_width, max(1, height) * cell_height)
    return max(1, side // cell_width), max(1, side // cell_height)


class OwnedTGPImage(TGPImage):
    """Delete only our image id and its data; upstream 0.14.2 uses a broad delete."""

    def cleanup(self):
        if self.terminal_image_id is not None:
            if sys.__stdout__ and not sys.__stdout__.closed:
                sequence = f"\x1b_Ga=d,d=I,i={self.terminal_image_id},q=2\x1b\\"
                sys.__stdout__.write(prepare_terminal_sequence(sequence))
                sys.__stdout__.flush()
            self.terminal_image_id = None


class PortraitRenderer:
    """Keep a finite set of image placements; release them on resize and unmount."""

    def __init__(self):
        self.atlas = CatAtlas()
        self.cache = OrderedDict()
        self.size = None
        # Capability probing happens on import, before Textual owns stdin.
        if AutoImage is TGPImage and "NO_COLOR" not in os.environ:
            self.renderable = OwnedTGPImage
        else:
            # Rich Sixel renderables cannot be embedded directly in Textual. Keep
            # a visible ANSI fallback for non-TGP and all NO_COLOR environments.
            self.renderable = HalfcellImage

    def render(self, *, width, height, **state):
        cells = get_cell_size()
        size = fit_portrait(width, height, cells.width, cells.height)
        if size != self.size:
            self.close()
            self.size = size
        key = self.atlas.key(**state)
        if key not in self.cache:
            if len(self.cache) >= 48:
                _, oldest = self.cache.popitem(last=False)
                oldest.cleanup()
            self.cache[key] = self.renderable(self.atlas.image(**state), *size)
        self.cache.move_to_end(key)
        return self.cache[key]

    def close(self):
        for image in self.cache.values():
            image.cleanup()
        self.cache.clear()
