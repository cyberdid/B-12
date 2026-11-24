"""Model picker, model status line, turn feedback screen and TUI preferences (ADR-023)."""

from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

STATE_WORDS = {
    "ready": "готова",
    "loading": "завантаження у відеопам'ять",
    "pulling": "завантаження моделі",
    "error": "помилка",
    "unavailable": "недоступна",
}


def _bar(progress: float, width: int = 10) -> str:
    filled = max(0, min(width, round(progress * width)))
    return "▓" * filled + "░" * (width - filled)


def model_line(choice: dict | None, status: dict | None) -> Text:
    """`◆ gemma4:12b · ноутбук · готова` or `☁ gpt-6-luna · Codex · хмара`, with progress."""
    text = Text(no_wrap=True, overflow="ellipsis")
    if not choice:
        return text
    cloud = choice.get("kind") == "cloud"
    icon_style = "bold #ffd58a" if cloud else "bold #69f4df"
    text.append("☁ " if cloud else "◆ ", icon_style)
    text.append(f"{choice.get('label', choice.get('id', '?'))} · {choice.get('location', '')}")
    status = status or {}
    state = status.get("state", "ready")
    words = STATE_WORDS.get(state, state)
    style = {"ready": "#69f4df", "error": "#ff7a90", "unavailable": "#ff7a90"}.get(state, "#ffd58a")
    text.append(f" · {words}", style)
    if state in ("loading", "pulling"):
        progress = status.get("progress")
        if isinstance(progress, int | float):
            text.append(f" {_bar(progress)} {round(progress * 100)}%", "#ffd58a")
        if status.get("elapsed_s") is not None:
            text.append(f" · {int(status['elapsed_s'])} с", "#8f9fc1")
    elif state == "ready" and status.get("vram_mb"):
        text.append(f" · {status['vram_mb'] / 1024:.1f} ГБ", "#8f9fc1")
        if status.get("cpu_share"):
            text.append(f" · ⚠ {round(status['cpu_share'] * 100)}% на CPU, повільно", "#ffd58a")
    elif state == "error" and status.get("detail"):
        text.append(f": {status['detail'][:60]}", "#ff7a90")
    if choice.get("warning"):
        text.append(" ⚠", "#ffd58a")
    return text


class ModelPicker(ModalScreen[str | None]):
    """F3 / `/model`: local models first, cloud models marked ☁."""

    BINDINGS = [Binding("escape", "dismiss_none", "Закрити")]
    DEFAULT_CSS = """
    ModelPicker { align: center middle; }
    #picker { width: 72; height: auto; max-height: 24; border: round #69f4df; background: #0d1425; }
    #picker-title { padding: 0 1; color: #69f4df; }
    #picker-note { padding: 0 1; color: #8f9fc1; }
    """

    def __init__(self, choices: list[dict], active: str | None):
        super().__init__()
        self.choices = choices
        self.active = active

    def compose(self) -> ComposeResult:
        options: list[Option | None] = []
        for kind, title in (("local", "ЛОКАЛЬНІ · ноутбук"), ("cloud", "ХМАРНІ ☁ · підписки")):
            group = [c for c in self.choices if c.get("kind") == kind]
            if not group:
                continue
            options.append(Option(title, disabled=True))
            for choice in group:
                mark = "● " if choice["id"] == self.active else "  "
                warning = f"  ⚠ {choice['warning']}" if choice.get("warning") else ""
                options.append(Option(f"{mark}{choice['label']}{warning}", id=choice["id"]))
        with Vertical(id="picker"):
            yield Static("МОДЕЛЬ CAPRI  ·  Enter — обрати, Esc — закрити", id="picker-title")
            yield OptionList(*options, id="picker-list")
            yield Static(
                "Хмарна модель — та сама Capri: пам'ять і інструменти лишаються, "
                "але розмова йде в хмару (ADR-023).",
                id="picker-note",
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    async def choose(self, choice_id: str) -> None:
        self.dismiss(choice_id)

    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            await self.choose(event.option.id)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class FeedbackScreen(ModalScreen[str | None]):
    """F10: mark the last turn as a mistake; the note feeds new evaluation scenarios."""

    BINDINGS = [Binding("escape", "dismiss_none", "Закрити")]
    DEFAULT_CSS = """
    FeedbackScreen { align: center middle; }
    #feedback { width: 72; height: auto; border: round #ff7a90; background: #0d1425; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="feedback"):
            yield Static("ПОЗНАЧИТИ ХІД ЯК ПОМИЛКУ · Enter — зберегти, Esc — скасувати")
            yield Input(placeholder="що було не так?", id="feedback-note")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    async def submit(self, note: str) -> None:
        self.dismiss(note)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self.submit(event.value.strip())

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


def load_prefs(state_dir: Path | str | None) -> dict:
    if state_dir is None:
        return {}
    try:
        data = json.loads((Path(state_dir) / "tui.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_prefs(state_dir: Path | str | None, prefs: dict) -> None:
    if state_dir is None:
        return
    path = Path(state_dir) / "tui.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # a preference is a convenience, never a reason to fail
