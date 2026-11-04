"""The companion must change visible sprites, keep proportions and release graphics."""

import importlib

import pytest
from PIL import ImageChops


def sprites():
    assert importlib.util.find_spec("b12.tui.sprites"), "raster companion is not implemented"
    return importlib.import_module("b12.tui.sprites")


def test_mouse_gaze_blink_and_pet_reaction_change_the_actual_image():
    atlas = sprites().CatAtlas()
    neutral = atlas.image(phase="idle", frame=8, motion=False)
    left = atlas.image(phase="idle", frame=8, look_x=-1, motion=False)
    right = atlas.image(phase="idle", frame=8, look_x=1, motion=False)
    happy = atlas.image(phase="idle", frame=8, purring=True, motion=False)
    for other in (left, right, happy):
        assert ImageChops.difference(neutral, other).getbbox() is not None
    assert ImageChops.difference(left, right).getbbox() is not None
    # Idle time must produce visible changes even with no mouse or model events.
    states = {atlas.image(phase="idle", frame=f).tobytes() for f in range(60)}
    assert len(states) >= 5


def test_motion_pause_freezes_ambient_animation_but_keeps_chat_reactions():
    atlas = sprites().CatAtlas()
    still = atlas.image(phase="idle", frame=8, motion=False)
    assert all(
        atlas.image(phase="idle", frame=f, motion=False).tobytes() == still.tobytes()
        for f in range(60)
    )
    talking = atlas.image(phase="speaking", frame=8, motion=False)
    assert ImageChops.difference(still, talking).getbbox() is not None


def test_tail_keeps_moving_while_the_cat_looks_at_the_mouse():
    atlas = sprites().CatAtlas()
    outward = atlas.image(phase="typing", frame=10, look_x=-1)
    inward = atlas.image(phase="typing", frame=30, look_x=-1)
    # These two times have the same breathing offset. The tail must change on its own.
    tail = (0, 168, 112, 324)
    assert ImageChops.difference(outward.crop(tail), inward.crop(tail)).getbbox() is not None


@pytest.mark.parametrize("cells,available", [((10, 20), (30, 17)), ((9, 22), (23, 5))])
def test_portrait_contains_the_whole_sprite_without_stretching(cells, available):
    fit = sprites().fit_portrait(*available, *cells)
    columns, rows = fit
    assert 0 < columns <= available[0] and 0 < rows <= available[1]
    assert abs(columns * cells[0] - rows * cells[1]) <= max(cells)


def test_render_cache_is_bounded_and_released_on_resize_and_exit():
    module = sprites()
    portrait = module.PortraitRenderer()
    for frame in range(80):
        portrait.render(phase="idle", frame=frame, width=30, height=17)
    assert 1 < len(portrait.cache) <= 36
    previous = list(portrait.cache.values())
    portrait.render(phase="idle", frame=8, width=22, height=8)
    assert len(portrait.cache) == 1
    assert all(item not in portrait.cache.values() for item in previous)
    portrait.close()
    assert not portrait.cache


def test_graphics_cleanup_deletes_only_the_owned_image_and_its_data(monkeypatch):
    import io
    import sys

    from PIL import Image

    module = sprites()
    output = io.StringIO()
    monkeypatch.setattr(sys, "__stdout__", output)
    image = module.OwnedTGPImage(Image.new("RGB", (2, 2)))
    image.terminal_image_id = 123
    image.cleanup()
    assert output.getvalue() == "\x1b_Ga=d,d=I,i=123,q=2\x1b\\"
    image.cleanup()
    assert output.getvalue().count("a=d") == 1


@pytest.mark.parametrize("terminal,no_color", [("sixel", None), ("kitty", ""), ("kitty", "1")])
def test_unsupported_or_no_color_terminal_uses_visible_textual_fallback(
    monkeypatch, terminal, no_color
):
    import io
    import sys

    from rich.console import Console
    from textual_image.renderable.sixel import Image as SixelImage

    module = sprites()
    if no_color is None:
        monkeypatch.delenv("NO_COLOR", raising=False)
    else:
        monkeypatch.setenv("NO_COLOR", no_color)
    monkeypatch.setattr(module, "AutoImage", SixelImage if terminal == "sixel" else module.TGPImage)
    # Capture protocol output too: this probe must never send graphics to a real terminal.
    monkeypatch.setattr(sys, "__stdout__", io.StringIO())
    portrait = module.PortraitRenderer()
    art = portrait.render(phase="idle", frame=8, width=24, height=12)
    console = Console(width=24, file=io.StringIO(), force_terminal=True, no_color=False)
    assert any(segment.text == "▀" for segment in console.render(art))
    portrait.close()


def test_eviction_and_resize_free_every_uploaded_image_once(monkeypatch):
    import io
    import re
    import sys

    module = sprites()
    output = io.StringIO()
    monkeypatch.setattr(sys, "__stdout__", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(module, "AutoImage", module.TGPImage)
    portrait = module.PortraitRenderer()
    next_id = 100
    # Exercise real cache/cleanup. IDs stand for the terminal's upload boundary;
    # no PNG or escape sequence is sent to a real terminal during this test.
    for phase in ("idle", "thinking", "speaking", "success", "idle"):
        for x, y in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            for frame in range(280):
                art = portrait.render(
                    phase=phase, frame=frame, look_x=x, look_y=y, width=30, height=17
                )
                if art.terminal_image_id is None:
                    art.terminal_image_id = next_id
                    next_id += 1
                if next_id == 160:
                    break
            if next_id == 160:
                break
        if next_id == 160:
            break
    assert next_id == 160
    assert len(portrait.cache) == 48
    assert output.getvalue().count("a=d,d=I") == 12
    portrait.render(phase="idle", frame=8, width=22, height=8)
    deleted = re.findall(r"a=d,d=I,i=(\d+),q=2", output.getvalue())
    assert sorted(map(int, deleted)) == list(range(100, 160))
    portrait.close()
    portrait.close()
    assert not portrait.cache
    assert output.getvalue().count("a=d,d=I") == 60
