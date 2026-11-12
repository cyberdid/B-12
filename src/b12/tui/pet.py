"""Animated raster cybercat. Reactions are local presentation state only."""

import time

from rich.align import Align
from rich.console import Group
from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widgets import Static

from b12.tui.sprites import PortraitRenderer

CYAN = "#69f4df"
PINK = "#ff79c8"
PHASES = {
    "idle": ("ПОРУЧ ІЗ ТОБОЮ", "Я тут. Я слухаю.", CYAN),
    "typing": ("УВАЖНО СЛУХАЮ", "Що ти задумав?", CYAN),
    "thinking": ("ОБМІРКОВУЮ", "Ловлю нитку думки…", "#b6a0ff"),
    "speaking": ("ВІДПОВІДАЮ", "Ділюся тим, що знайшов.", CYAN),
    "working": ("ПРАЦЮЮ", "Перевіряю, а не вгадую.", "#ffd58a"),
    "approval": ("ЧЕКАЮ НА ТЕБЕ", "Цю дію вирішуєш ти.", "#ffd58a"),
    "success": ("ГОТОВО", "Ще одну пригоду?", CYAN),
    "error": ("ЗВ’ЯЗОК ПЕРЕРВАНО", "Я тут. Спробуємо ще раз.", "#ff8193"),
    "cancelled": ("ЗУПИНИВСЯ", "Можемо змінити напрям.", "#b6a0ff"),
}


class CyberCat(Static):
    """Approved pixel-art companion, using terminal graphics or an ANSI fallback."""

    frame = reactive(8)
    phase = reactive("idle")
    look_x = reactive(0)
    look_y = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.portrait = PortraitRenderer()
        self.motion = True
        self.detail = ""
        self._reaction_until = 0.0
        self._phase_until = 0.0

    def on_mount(self):
        self.set_interval(0.12, self._tick)

    def on_unmount(self):
        self.portrait.close()

    @property
    def skin_id(self) -> str:
        return self.portrait.skin_id

    @property
    def skin_name(self) -> str:
        return self.portrait.skin_name

    @property
    def skin_error(self) -> str:
        return self.portrait.skin_error

    def available_skins(self):
        return self.portrait.refresh_skins()

    def set_skin(self, skin_id: str) -> bool:
        selected = self.portrait.set_skin(skin_id)
        self.refresh()
        return selected

    def _tick(self):
        now = time.monotonic()
        if self._phase_until and now >= self._phase_until:
            self.set_phase("idle")
        if self._reaction_until and now >= self._reaction_until:
            self._reaction_until = 0
            self.refresh()
        if self.motion:
            self.frame += 1

    def set_phase(self, phase: str, detail: str = ""):
        if phase not in PHASES:
            raise ValueError("unknown companion phase")
        self.phase = phase
        self.detail = detail
        self._phase_until = (
            time.monotonic() + 3 if phase in ("success", "error", "cancelled") else 0
        )
        self.refresh()

    def pat(self):
        self._reaction_until = time.monotonic() + 2
        self.refresh()

    def track_pointer(self, screen_x: float, screen_y: float):
        region = self.region
        x = (screen_x - region.x) / max(1, region.width) - 0.5
        y = (screen_y - region.y) / max(1, region.height) - 0.5
        # A central dead zone lets the cat look up/down without horizontal jitter.
        self.look_x = (-1 if x < 0 else 1) if abs(x) > 0.18 else 0
        self.look_y = (-1 if y < 0 else 1) if abs(y) > 0.18 else 0

    def on_mouse_move(self, event: events.MouseMove):
        self.track_pointer(event.screen_x, event.screen_y)

    def on_click(self, event: events.Click):
        self.pat()
        event.stop()

    @property
    def status_text(self) -> Text:
        title, caption, accent = PHASES[self.phase]
        if time.monotonic() < self._reaction_until:
            caption, accent = "Мурр… це було приємно ♥", PINK
        elif self.detail:
            caption = self.detail
        width = max(18, min(32, self.size.width))
        text = Text(no_wrap=True, overflow="crop", justify="center")
        text.append("● ", accent)
        text.append(title + "\n", f"bold {accent}")
        text.append(caption[:width] + "\n", "#a8b7d3")
        signal = "─ · ─ · ─ · ─" if self.phase == "idle" else "▁▃▂▅▃▇▄▂▅▂▁"
        if self.phase != "idle" and self.motion:
            offset = self.frame % len(signal)
            signal = signal[offset:] + signal[:offset]
        text.append(signal, accent)
        return text

    def render(self) -> Group:
        art = self.portrait.render(
            width=max(1, self.size.width),
            height=max(1, self.size.height - 5),
            phase=self.phase,
            frame=self.frame,
            look_x=self.look_x,
            look_y=self.look_y,
            motion=self.motion,
            purring=time.monotonic() < self._reaction_until,
        )
        return Group(Align.center(art), Text(""), self.status_text)
