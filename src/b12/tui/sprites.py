"""Registered cybercat atlas and bounded terminal graphics, independent of the agent."""

import json
import os
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from itertools import islice
from pathlib import Path

from PIL import Image
from textual_image._terminal import get_cell_size, prepare_terminal_sequence
from textual_image.renderable import Image as AutoImage
from textual_image.renderable.halfcell import Image as HalfcellImage
from textual_image.renderable.tgp import Image as TGPImage

ASSETS = Path(__file__).with_name("assets")
BG = "#0b1020"
TAIL_BOX = (0, 168, 112, 324)  # registered native-pixel tail layer in the 362px cells
SKIN_PHASES = frozenset(
    {
        "idle",
        "typing",
        "thinking",
        "speaking",
        "working",
        "approval",
        "success",
        "error",
        "cancelled",
    }
)
SKIN_REACTIONS = frozenset({"purr", "look_left", "look_right", "look_up", "look_down"})
MAX_MANIFEST_BYTES = 65_536
MAX_ATLAS_BYTES = 32 * 1024 * 1024
MAX_ATLAS_SIDE = 4096
MAX_ATLAS_PIXELS = 16_777_216
ANIMATION_TICK_MS = 120
_SKIN_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")


def _text(value, name, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"invalid skin {name}")
    if not value.isprintable() or "[" in value or "]" in value:
        raise ValueError(f"invalid skin {name}")
    return value.strip()


def _integer(value, name, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"invalid skin {name}")
    return value


def _open_atlas(path):
    with path.open("rb") as stream:
        encoded = stream.read(MAX_ATLAS_BYTES + 1)
    if len(encoded) > MAX_ATLAS_BYTES:
        raise ValueError("skin atlas too large")
    return Image.open(BytesIO(encoded))


@dataclass(frozen=True)
class SkinManifest:
    """Versioned local data only; a pack never supplies executable renderer code."""

    path: Path
    id: str
    display_name: str
    atlas_path: Path
    frame_width: int
    frame_height: int
    columns: int
    rows: int
    frame_duration_ms: int
    phases: dict[str, tuple[int, ...]]
    provenance: dict[str, str]

    @classmethod
    def load(cls, path: Path | str):
        candidate = Path(path).expanduser()
        if candidate.is_dir():
            candidate /= "manifest.json"
        root = candidate.parent.resolve(strict=True)
        manifest_path = candidate.resolve(strict=True)
        if manifest_path.parent != root or not manifest_path.is_file():
            raise ValueError("skin manifest escapes pack")
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("skin manifest too large")
        with manifest_path.open("rb") as stream:
            encoded = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise ValueError("skin manifest too large")
        data = json.loads(encoded)
        if (
            not isinstance(data, dict)
            or type(data.get("version")) is not int
            or data["version"] != 1
        ):
            raise ValueError("unsupported skin manifest")
        skin_id = data.get("id")
        if not isinstance(skin_id, str) or not _SKIN_ID.fullmatch(skin_id) or skin_id == "cybercat":
            raise ValueError("invalid skin id")
        display_name = _text(data.get("display_name"), "display_name", 64)
        atlas_name = _text(data.get("atlas"), "atlas", 256)
        relative = Path(atlas_name)
        # Reject Windows paths too, even when loading on POSIX. Resolving a local
        # symlink is allowed only when its target remains inside this pack.
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in atlas_name
            or ":" in atlas_name
        ):
            raise ValueError("invalid skin atlas path")
        atlas_path = (root / relative).resolve(strict=True)
        if not atlas_path.is_relative_to(root) or not atlas_path.is_file():
            raise ValueError("skin atlas escapes pack")
        if atlas_path.stat().st_size > MAX_ATLAS_BYTES:
            raise ValueError("skin atlas too large")
        width = _integer(data.get("frame_width"), "frame_width", 1, 512)
        height = _integer(data.get("frame_height"), "frame_height", 1, 512)
        columns = _integer(data.get("columns"), "columns", 1, 32)
        rows = _integer(data.get("rows"), "rows", 1, 32)
        if columns * rows > 256:
            raise ValueError("too many skin frames")
        duration = _integer(data.get("frame_duration_ms"), "frame_duration_ms", 120, 5000)
        phases = data.get("phases")
        if not isinstance(phases, dict) or "idle" not in phases:
            raise ValueError("skin requires idle frames")
        phase_frames = {}
        for phase, frames in phases.items():
            if phase not in SKIN_PHASES | SKIN_REACTIONS or not isinstance(frames, list):
                raise ValueError("invalid skin phase")
            if not 1 <= len(frames) <= 256:
                raise ValueError("invalid skin animation length")
            phase_frames[phase] = tuple(
                _integer(frame, "frame index", 0, columns * rows - 1) for frame in frames
            )
        provenance = data.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError("skin requires provenance")
        provenance = {
            name: _text(provenance.get(name), name, 1024)
            for name in ("source", "license", "attribution")
        }
        manifest = cls(
            manifest_path,
            skin_id,
            display_name,
            atlas_path,
            width,
            height,
            columns,
            rows,
            duration,
            phase_frames,
            provenance,
        )
        with _open_atlas(atlas_path) as source:
            manifest.validate_image(source)
            source.verify()
        return manifest

    def validate_image(self, source):
        width, height = source.size
        if (
            source.format != "PNG"
            or source.mode != "RGBA"
            or width > MAX_ATLAS_SIDE
            or height > MAX_ATLAS_SIDE
            or width * height > MAX_ATLAS_PIXELS
            or source.size != (self.frame_width * self.columns, self.frame_height * self.rows)
        ):
            raise ValueError("skin atlas must be a bounded RGBA PNG matching the grid")


@dataclass(frozen=True)
class SkinOption:
    id: str
    display_name: str
    manifest_path: Path | None = None


def available_skins(capri_dir: Path | str | None = None) -> tuple[SkinOption, ...]:
    """Discover at most 32 local packs; bad files are ignored, never downloaded."""
    options = [SkinOption("cybercat", "КІБЕРКІТ")]
    configured = capri_dir if capri_dir is not None else os.environ.get("B12_TUI_CAPRI_DIR")
    if not configured:
        return tuple(options)
    try:
        location = Path(configured).expanduser()
        if location.is_file() or (location / "manifest.json").is_file():
            candidates = [location]
        elif location.is_dir():
            root = location.resolve(strict=True)
            candidates = [
                child
                for child in sorted(islice(location.iterdir(), 32))
                if child.is_dir() and child.resolve().is_relative_to(root)
            ]
        else:
            return tuple(options)
        for candidate in candidates:
            try:
                manifest = SkinManifest.load(candidate)
            except Exception:
                # Optional pack schema/decoder failures never terminate the TUI.
                continue
            if manifest.id not in {option.id for option in options}:
                options.append(SkinOption(manifest.id, manifest.display_name, manifest.path))
    except Exception:
        pass
    return tuple(options)


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

    def close(self):
        self.frames.clear()
        self.sheet.close()


class PackAtlas:
    """Generic atlas animation; missing phases use the pack's required idle frames."""

    def __init__(self, manifest: SkinManifest):
        self.manifest = manifest
        with _open_atlas(manifest.atlas_path) as source:
            manifest.validate_image(source)
            self.sheet = source.convert("RGBA")
        self.frames = OrderedDict()

    def key(self, *, phase, frame, look_x=0, look_y=0, purring=False, motion=True):
        phases = self.manifest.phases
        reaction = ""
        if purring and "purr" in phases:
            reaction = "purr"
        elif phase in ("idle", "typing"):
            if look_x:
                reaction = "look_left" if look_x < 0 else "look_right"
            elif look_y:
                reaction = "look_up" if look_y < 0 else "look_down"
        sequence = phases.get(reaction) or phases.get(phase) or phases["idle"]
        position = frame * ANIMATION_TICK_MS // self.manifest.frame_duration_ms if motion else 0
        return sequence[position % len(sequence)]

    def image(self, **state):
        index = self.key(**state)
        if index in self.frames:
            self.frames.move_to_end(index)
            return self.frames[index]
        manifest = self.manifest
        x = index % manifest.columns * manifest.frame_width
        y = index // manifest.columns * manifest.frame_height
        sprite = self.sheet.crop((x, y, x + manifest.frame_width, y + manifest.frame_height))
        canvas = Image.new("RGB", sprite.size, BG)
        canvas.paste(sprite, (0, 0), sprite)
        if len(self.frames) >= 48:
            self.frames.popitem(last=False)
        self.frames[index] = canvas
        return canvas

    def close(self):
        self.frames.clear()
        self.sheet.close()


def fit_portrait(width, height, cell_width, cell_height):
    """Contain a square in the available physical pixels, not the terminal cell ratio."""
    side = min(max(1, width) * cell_width, max(1, height) * cell_height)
    return max(1, side // cell_width), max(1, side // cell_height)


def fit_frame(width, height, cell_width, cell_height, frame_width, frame_height):
    """Contain a rectangular pack frame without stretching its physical proportions."""
    scale = min(
        max(1, width) * cell_width / frame_width,
        max(1, height) * cell_height / frame_height,
    )
    return (
        max(1, int(frame_width * scale / cell_width)),
        max(1, int(frame_height * scale / cell_height)),
    )


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

    def __init__(self, capri_dir: Path | str | None = None):
        self.atlas = CatAtlas()
        self.cache = OrderedDict()
        self.size = None
        self.capri_dir = capri_dir
        self.skin_id = "cybercat"
        self.skin_name = "КІБЕРКІТ"
        self.skin_error = ""
        self.skin_options = self.refresh_skins()
        # Capability probing happens on import, before Textual owns stdin.
        if AutoImage is TGPImage and "NO_COLOR" not in os.environ:
            self.renderable = OwnedTGPImage
        else:
            # Rich Sixel renderables cannot be embedded directly in Textual. Keep
            # a visible ANSI fallback for non-TGP and all NO_COLOR environments.
            self.renderable = HalfcellImage

    def refresh_skins(self) -> tuple[SkinOption, ...]:
        self.skin_options = available_skins(self.capri_dir)
        configured = (
            self.capri_dir if self.capri_dir is not None else os.environ.get("B12_TUI_CAPRI_DIR")
        )
        self.skin_error = "skin_pack_invalid" if configured and len(self.skin_options) == 1 else ""
        return self.skin_options

    def set_skin(self, skin_id: str) -> bool:
        """Switch only after loading a pack; failed requests reset to the built-in cat."""
        options = {option.id: option for option in self.refresh_skins()}
        option = options.get(skin_id) if isinstance(skin_id, str) else None
        selected_id, selected_name, error = "cybercat", "КІБЕРКІТ", ""
        if option is None:
            atlas = CatAtlas()
            error = "skin_unavailable"
        elif option.manifest_path is None:
            atlas = CatAtlas()
        else:
            try:
                manifest = SkinManifest.load(option.manifest_path)
                if manifest.id != skin_id:
                    raise ValueError("skin manifest changed")
                atlas = PackAtlas(manifest)
                selected_id, selected_name = manifest.id, manifest.display_name
            except Exception:
                atlas = CatAtlas()
                error = "skin_pack_invalid"
        # Release only terminal placements owned by this renderer before changing
        # the source atlas. The old decoded image is then no longer referenced.
        self.close()
        self.atlas.close()
        self.atlas = atlas
        self.size = None
        self.skin_id, self.skin_name, self.skin_error = selected_id, selected_name, error
        return not error

    def render(self, *, width, height, **state):
        cells = get_cell_size()
        if isinstance(self.atlas, PackAtlas):
            manifest = self.atlas.manifest
            size = fit_frame(
                width,
                height,
                cells.width,
                cells.height,
                manifest.frame_width,
                manifest.frame_height,
            )
        else:
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
