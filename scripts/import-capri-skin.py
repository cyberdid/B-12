#!/usr/bin/env python3
"""Build a private, local-only B-12 Capri atlas from a pinned asset checkout."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

PINNED_REVISION = "7752959e7a708bac5b540d5380321c33694f6fb6"
FRAME_WIDTH = 249
FRAME_HEIGHT = 380
COLUMNS = 8
ROWS = 8


def contain(source: Image.Image) -> Image.Image:
    image = source.convert("RGBA")
    image.thumbnail((FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0))
    frame.alpha_composite(
        image,
        ((FRAME_WIDTH - image.width) // 2, (FRAME_HEIGHT - image.height) // 2),
    )
    return frame


def git_revision(source: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build(source: Path, destination: Path, *, replace: bool) -> None:
    source = source.expanduser().resolve(strict=True)
    if git_revision(source) != PINNED_REVISION:
        raise ValueError(f"source revision must be exactly {PINNED_REVISION}")
    asset_root = source / "assets"
    animation = sorted((asset_root / "anim" / "capri").glob("*.png"))
    poses = (
        asset_root / "poses" / "capri.png",
        asset_root / "poses" / "capri_roam.png",
        asset_root / "poses" / "каприии.png",
    )
    if len(animation) != 60 or not all(path.is_file() for path in poses):
        raise ValueError("pinned source is missing the reviewed Capri image set")

    destination = destination.expanduser().absolute()
    if destination.exists() and not replace:
        raise FileExistsError(f"destination exists; pass --replace to update: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".b12-capri-", dir=destination.parent))
    staging = temp_root / "capri"
    staging.mkdir()
    try:
        frames = []
        for path in animation:
            with Image.open(path) as image:
                if image.size != (FRAME_WIDTH, FRAME_HEIGHT) or image.mode != "RGBA":
                    raise ValueError(f"unexpected animation frame format: {path.name}")
                frames.append(image.copy())
        for path in poses:
            with Image.open(path) as image:
                frames.append(contain(image))

        atlas = Image.new("RGBA", (FRAME_WIDTH * COLUMNS, FRAME_HEIGHT * ROWS), (0, 0, 0, 0))
        for index, frame in enumerate(frames):
            atlas.alpha_composite(
                frame,
                ((index % COLUMNS) * FRAME_WIDTH, (index // COLUMNS) * FRAME_HEIGHT),
            )
        atlas.save(staging / "atlas.png", optimize=True)

        motion = list(range(60))
        manifest = {
            "version": 1,
            "id": "capri",
            "display_name": "CAPRI",
            "atlas": "atlas.png",
            "frame_width": FRAME_WIDTH,
            "frame_height": FRAME_HEIGHT,
            "columns": COLUMNS,
            "rows": ROWS,
            "frame_duration_ms": 120,
            "phases": {
                "idle": motion,
                "typing": motion,
                "thinking": [61],
                "working": [61],
                "speaking": motion,
                "approval": [62],
                "success": [60],
                "error": [62],
                "cancelled": [61],
                "purr": [60],
            },
            "provenance": {
                "source": (
                    "https://github.com/nic0dvornikov/capricorn-linux/tree/"
                    f"{PINNED_REVISION} (assets/poses and assets/anim/capri)"
                ),
                "license": (
                    "Repository MIT license covers code only and explicitly excludes "
                    "Capri character/Cyberpunk IP; local preview copy, no redistribution rights"
                ),
                "attribution": (
                    "Capri character artwork from nic0dvornikov/capricorn-linux, "
                    f"revision {PINNED_REVISION}; private local B-12 preview"
                ),
            },
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        license_path = source / "LICENSE"
        if license_path.is_file():
            shutil.copyfile(license_path, staging / "UPSTREAM-LICENSE.txt")
        (staging / "README.txt").write_text(
            "Private local B-12 visual preview asset pack.\n"
            f"Source: nic0dvornikov/capricorn-linux @ {PINNED_REVISION}\n"
            "The upstream MIT license covers code only and excludes Capri character art.\n"
            "This pack stays outside the B-12 repository; do not redistribute it.\n",
            encoding="utf-8",
        )
        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="pinned source checkout")
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path.home() / ".local/share/b12/skins/capri",
        help="local data directory (default: ~/.local/share/b12/skins/capri)",
    )
    parser.add_argument("--replace", action="store_true", help="replace an existing destination")
    args = parser.parse_args(argv)
    try:
        build(args.source, args.dest, replace=args.replace)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1
    print(args.dest.expanduser().absolute())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
