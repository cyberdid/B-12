"""Validated local companion skin manifests shared by desktop and terminal UIs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from itertools import islice
from pathlib import Path

from PIL import Image

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
    configured = (
        capri_dir
        if capri_dir is not None
        else os.environ.get("B12_CAPRI_DIR") or os.environ.get("B12_TUI_CAPRI_DIR")
    )
    options = []
    if configured:
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
                candidates = []
            for candidate in candidates:
                try:
                    manifest = SkinManifest.load(candidate)
                except Exception:
                    continue
                if manifest.id not in {option.id for option in options}:
                    options.append(SkinOption(manifest.id, manifest.display_name, manifest.path))
        except Exception:
            pass
    # Put the explicitly installed appearance first; keep the built-in cat as an option.
    options.append(SkinOption("cybercat", "КІБЕРКІТ"))
    return tuple(options)
