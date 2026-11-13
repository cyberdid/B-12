"""Owner-controlled local companion profile and deterministic reminder parsing."""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

PROFILE_KEY = "companion/profile"
HISTORY_KEY = "companion/interaction_history"
PROFILE_LIMITS = {"name": 60, "style_note": 800, "catchphrase": 240, "catchphrases": 30}
HISTORY_LIMIT = 100
HISTORY_KINDS = frozenset({"chat", "pet", "reminder", "work_session"})

_PROFILE_DEFAULT: dict[str, object] = {
    "name": "",
    "style_note": "",
    "catchphrases": [],
    "history_opt_in": False,
}

_INTENT_RE = re.compile(
    r"\bremind\s+me\b|\bset\s+(?:a|an)\s+(?:reminder|alarm)\b|"
    r"\bнагадай(?:те)?(?:\s+мені)?\b|\bпостав(?:ь|те)?\s+нагадування\b",
    re.IGNORECASE,
)
_NEGATED_INTENT_RE = re.compile(
    r"\b(?:do\s+not|don['’]t)\s+remind\s+me\b|"
    r"\bне\s+нагадуй(?:те)?\b|\bне\s+поставляй\s+нагадування\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"\b(?:in|через)\s+(?P<count>\d{1,6})\s*(?P<unit>"
    r"seconds?|secs?|s|minutes?|mins?|хв(?:илину|илини|илин|илина)?|"
    r"hours?|hrs?|год(?:ину|ина|ини|ин)?|days?|день|дня|дні|днів|"
    r"weeks?|тиждень|тижня|тижні|тижнів)\b",
    re.IGNORECASE,
)
_RELATIVE_DAY_RE = re.compile(
    r"\b(?P<day>today|tomorrow|tonight|сьогодні(?:\s+(?:ввечері|увечері))?|завтра)\b\s*"
    r"(?:(?:at|о)\s*)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?)?",
    re.IGNORECASE,
)
_CLOCK_TIME_RE = re.compile(
    r"\b(?:(?:at|о)\s*)?(?P<hour>\d{1,2})"
    r"(?::(?P<minute>\d{2})|(?P<ampm>a\.?m\.?|p\.?m\.?))\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(
    r"\b(?P<date>20\d{2}-\d{2}-\d{2})[ T]+(?P<hour>\d{1,2}):(?P<minute>\d{2})\b"
)
_VAGUE_TIME_RE = re.compile(
    r"\b(?:morning|afternoon|evening|tonight|later|soon|next\s+week|"
    r"this\s+weekend|weekend|вранці|зранку|після\s+обіду|увечері|ввечері|"
    r"сьогодні\s+ввечері|завтра\s+вранці|наступного\s+тижня|вихідних)\b",
    re.IGNORECASE,
)
_TIME_HINT_RE = re.compile(
    r"\b(?:today|tomorrow|tonight|morning|afternoon|evening|later|soon|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"next\s+(?:week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"in\s+\w+\s+(?:seconds?|minutes?|hours?|days?|weeks?)|"
    r"сьогодні|завтра|вранці|зранку|увечері|ввечері|після\s+обіду|"
    r"понеділ\w*|вівтор\w*|серед\w*|четвер\w*|п[’']ятниц\w*|"
    r"субот\w*|неділ\w*|наступного\s+тижня|"
    r"через\s+\w+\s+(?:хвилин\w*|годин\w*|дн\w*|тижн\w*))\b|"
    r"\b(?:at|о)\s*\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?\b|"
    r"\b\d{1,2}:\d{2}\b|\b20\d{2}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
_TASK_MARKER_RE = re.compile(r"\b(?:to|щоб|про)\s+", re.IGNORECASE)

ReminderStatus = Literal["not_reminder", "ready", "needs_time", "needs_task", "ambiguous"]


@dataclass(frozen=True)
class ReminderParseResult:
    """Deterministic reminder interpretation; `due_at` is local-time-derived Unix time."""

    status: ReminderStatus
    task: str = ""
    due_at: float | None = None
    clarification: str = ""


def load_companion_profile(settings: QSettings) -> dict[str, object]:
    """Load bounded, validated profile data from this desktop client's QSettings."""
    raw = settings.value(PROFILE_KEY, "")
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        value = None
    if not isinstance(value, dict):
        return {**_PROFILE_DEFAULT, "catchphrases": []}

    name = str(value.get("name", _PROFILE_DEFAULT["name"])).strip()
    style_note = str(value.get("style_note", "")).strip()
    raw_phrases = value.get("catchphrases", [])
    phrases: list[str] = []
    if isinstance(raw_phrases, list):
        for phrase in raw_phrases[: PROFILE_LIMITS["catchphrases"]]:
            if not isinstance(phrase, str):
                continue
            cleaned = " ".join(phrase.split())[: PROFILE_LIMITS["catchphrase"]]
            if cleaned:
                phrases.append(cleaned)
    return {
        "name": name[: PROFILE_LIMITS["name"]],
        "style_note": style_note[: PROFILE_LIMITS["style_note"]],
        "catchphrases": phrases,
        "history_opt_in": value.get("history_opt_in") is True,
    }


def load_companion_catchphrases(settings: QSettings) -> list[str]:
    """Return owner-authored phrases in saved order for explicit UI insertion."""
    profile = load_companion_profile(settings)
    return list(profile["catchphrases"])


def save_companion_profile(settings: QSettings, profile: dict[str, object]) -> dict[str, object]:
    """Validate and persist only the owner's profile/settings locally."""
    normalized = {
        "name": str(profile.get("name", "")).strip()[: PROFILE_LIMITS["name"]],
        "style_note": str(profile.get("style_note", "")).strip()[: PROFILE_LIMITS["style_note"]],
        "catchphrases": [],
        "history_opt_in": profile.get("history_opt_in") is True,
    }
    raw_phrases = profile.get("catchphrases", [])
    if isinstance(raw_phrases, list):
        for phrase in raw_phrases:
            if len(normalized["catchphrases"]) >= PROFILE_LIMITS["catchphrases"]:
                break
            if not isinstance(phrase, str):
                continue
            cleaned = " ".join(phrase.split())[: PROFILE_LIMITS["catchphrase"]]
            if cleaned:
                normalized["catchphrases"].append(cleaned)
    settings.setValue(
        PROFILE_KEY, json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    )
    settings.sync()
    return normalized


def load_companion_history(settings: QSettings) -> list[dict[str, object]]:
    """Read the bounded local history; entries contain only event type and timestamp."""
    raw = settings.value(HISTORY_KEY, "[]")
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    events: list[dict[str, object]] = []
    for item in value[-HISTORY_LIMIT:]:
        if not isinstance(item, dict) or item.get("kind") not in HISTORY_KINDS:
            continue
        try:
            timestamp = float(item["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(timestamp) and timestamp >= 0:
            events.append({"kind": str(item["kind"]), "at": timestamp})
    return events


def record_companion_interaction(
    settings: QSettings, kind: str, *, at: float | None = None
) -> bool:
    """Record one coarse event only after explicit opt-in; never accept event payloads."""
    if (
        not isinstance(kind, str)
        or kind not in HISTORY_KINDS
        or not load_companion_profile(settings)["history_opt_in"]
    ):
        return False
    try:
        timestamp = time.time() if at is None else float(at)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(timestamp) or timestamp < 0:
        return False
    events = load_companion_history(settings)
    events.append({"kind": kind, "at": timestamp})
    settings.setValue(
        HISTORY_KEY,
        json.dumps(events[-HISTORY_LIMIT:], ensure_ascii=False, separators=(",", ":")),
    )
    settings.sync()
    return True


def companion_history_summary(settings: QSettings, *, now: float | None = None) -> dict[str, int]:
    """Summarize only the last 100 locally stored event timestamps."""
    events = load_companion_history(settings)
    timestamp_now = time.time() if now is None else now
    today = datetime.fromtimestamp(timestamp_now).date()
    days = {datetime.fromtimestamp(float(event["at"])).date() for event in events}
    today_count = sum(
        datetime.fromtimestamp(float(event["at"])).date() == today for event in events
    )
    return {"events": len(events), "days": len(days), "today": today_count}


def clear_companion_history(settings: QSettings) -> None:
    """Delete the bounded local interaction history immediately."""
    settings.remove(HISTORY_KEY)
    settings.sync()


class CompanionProfileDialog(QDialog):
    """Edit the local companion profile; history collection is explicitly opt-in."""

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.saved_profile: dict[str, object] | None = None
        self.setWindowTitle("ПРОФІЛЬ CAPRI")
        self.setMinimumSize(520, 540)
        self.setStyleSheet(
            "QDialog { background:#080d19; color:#dbe4f5; }"
            "QLabel { color:#dbe4f5; }"
            "QLineEdit, QPlainTextEdit { background:#0b1324; color:#e2e9f7; "
            "border:1px solid #2a3c58; border-radius:5px; padding:7px; }"
            "QPushButton { background:#132338; color:#b6c5de; border:1px solid #38516f; "
            "border-radius:5px; padding:7px 12px; font-weight:700; }"
            "QPushButton:hover { background:#1a334d; border-color:#69f4df; color:#69f4df; }"
        )
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Профіль Capri зберігається локально. Ім’я, стиль і власні фрази додаються до "
            "кожного запиту моделі: з локальною моделлю лишаються на цьому комп’ютері, "
            "а з хмарною надсилаються її провайдеру. Вони впливають лише на формулювання, "
            "не змінюють інструменти, дозволи чи пам’ять."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        current = load_companion_profile(settings)
        form = QFormLayout()
        self.name = QLineEdit(str(current["name"]))
        self.name.setMaxLength(PROFILE_LIMITS["name"])
        self.name.setPlaceholderText("Як до тебе звертатися")
        self.style_note = QPlainTextEdit(str(current["style_note"]))
        self.style_note.setPlaceholderText("Наприклад: більше іронії, коротші відповіді…")
        self.style_note.setMaximumHeight(110)
        self.catchphrases = QPlainTextEdit("\n".join(current["catchphrases"]))
        self.catchphrases.setPlaceholderText("Одна власна фраза на рядок")
        self.catchphrases.setMaximumHeight(120)
        form.addRow("Ім’я користувача:", self.name)
        form.addRow("Стиль спілкування:", self.style_note)
        form.addRow("Власні фрази:", self.catchphrases)
        layout.addLayout(form)

        self.history_opt_in = QCheckBox(
            "Дозволяю зберігати локальну історію взаємодії для персоналізації"
        )
        self.history_opt_in.setChecked(bool(current["history_opt_in"]))
        self.history_opt_in.setToolTip(
            "За замовчуванням вимкнено. Це налаштування згоди зберігається локально; "
            "записуються тільки тип події та час, без тексту розмов чи інструментів."
        )
        layout.addWidget(self.history_opt_in)
        explanation = QLabel(
            "Історія зберігається локально: не більше 100 подій (чат, взаємодія з персонажем, "
            "нагадування або робоча сесія). Вимкнення зупиняє нові записи; очищення видаляє старі. "
            "Жоден текст діалогів, команд чи файлів не записується."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        history = companion_history_summary(settings)
        self.history_summary = QLabel(
            f"Локальна історія: {history['events']} подій · {history['days']} днів · "
            f"сьогодні {history['today']}"
        )
        layout.addWidget(self.history_summary)
        clear_history = QDialogButtonBox()
        self.clear_history_button = clear_history.addButton(
            "ОЧИСТИТИ ІСТОРІЮ", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.clear_history_button.clicked.connect(self.clear_history)
        layout.addWidget(clear_history)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def clear_history(self) -> None:
        clear_companion_history(self.settings)
        self.history_summary.setText("Локальна історія очищена.")

    def accept(self) -> None:
        phrases = [
            line.strip() for line in self.catchphrases.toPlainText().splitlines() if line.strip()
        ]
        self.saved_profile = save_companion_profile(
            self.settings,
            {
                "name": self.name.text(),
                "style_note": self.style_note.toPlainText(),
                "catchphrases": phrases,
                "history_opt_in": self.history_opt_in.isChecked(),
            },
        )
        super().accept()


def _local_now(now: datetime | None) -> datetime:
    value = datetime.now().astimezone() if now is None else now
    return value.astimezone() if value.tzinfo is None else value


def _hour_minute(match: re.Match[str]) -> tuple[int, int] | None:
    hour = int(match.group("hour"))
    minute = int(match.groupdict().get("minute") or 0)
    suffix = (match.groupdict().get("ampm") or "").lower().replace(".", "")
    if minute > 59:
        return None
    if suffix:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    else:
        if not 0 <= hour <= 23:
            return None
        # A one-digit 1–12 hour without AM/PM is ambiguous. Require a
        # 24-hour value (e.g. 18:30) or an explicit AM/PM suffix.
        raw_hour = match.group("hour")
        if 1 <= hour <= 12 and len(raw_hour) == 1:
            return None
    return hour, minute


def _duration_delta(match: re.Match[str]) -> timedelta | None:
    count = int(match.group("count"))
    if count <= 0:
        return None
    unit = match.group("unit").lower()
    if unit.startswith(("s",)):
        return timedelta(seconds=count)
    if unit.startswith(("m", "хв")):
        return timedelta(minutes=count)
    if unit.startswith(("h", "год")):
        return timedelta(hours=count)
    if unit.startswith(("d", "д")):
        return timedelta(days=count)
    if unit.startswith(("w", "тиж")):
        return timedelta(weeks=count)
    return None


def _task_text(text: str, intent: re.Match[str], time_spans: list[tuple[int, int]]) -> str:
    tail = text[intent.end() :]
    marker = _TASK_MARKER_RE.search(tail)
    if marker:
        task_start = intent.end() + marker.end()
        task = text[task_start:]
        relative_spans = [
            (max(0, start - task_start), end - task_start)
            for start, end in time_spans
            if end > task_start
        ]
        chars = list(task)
        for start, end in relative_spans:
            if start < len(chars):
                end = min(end, len(chars))
                chars[start:end] = " " * (end - start)
        task = "".join(chars)
    else:
        chars = list(text)
        spans = [(intent.start(), intent.end()), *time_spans]
        for start, end in spans:
            chars[start:end] = " " * (end - start)
        task = "".join(chars)
    task = re.sub(
        r"^\s*(?:мені\s+)?(?:in|через|at|о|today|tomorrow|сьогодні|завтра)\b\s*",
        "",
        task,
        flags=re.IGNORECASE,
    )
    task = re.sub(r"\s+", " ", task).strip(" \t\r\n.,;:!?–—-")
    # A trailing temporal connector or date fragment is not part of the task.
    task = re.sub(
        r"\s+(?:at|о)\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?\s*$",
        "",
        task,
        flags=re.IGNORECASE,
    ).strip(" \t.,;:!?–—-")
    return task[:500]


def parse_reminder_request(text: str, *, now: datetime | None = None) -> ReminderParseResult:
    """Parse a small explicit UA/EN reminder grammar without an LLM.

    Accepted examples include ``remind me in 20 minutes to call`` and
    ``нагадай мені завтра о 18:30 зателефонувати``. Vague dates, missing
    clock times, past times, conflicts, and unsupported formats never become a
    guessed timestamp; callers should ask the owner to clarify.
    """
    if _NEGATED_INTENT_RE.search(text):
        return ReminderParseResult("not_reminder")
    intent = _INTENT_RE.search(text)
    if intent is None:
        return ReminderParseResult("not_reminder")

    local_now = _local_now(now)
    candidates: list[tuple[int, int, datetime]] = []
    ambiguous_time = False

    for match in _DURATION_RE.finditer(text):
        delta = _duration_delta(match)
        if delta is None or delta > timedelta(days=3650):
            ambiguous_time = True
            continue
        due = (local_now.astimezone(UTC) + delta).astimezone(local_now.tzinfo)
        candidates.append((match.start(), match.end(), due))

    for match in _ISO_DATE_RE.finditer(text):
        try:
            hour_minute = _hour_minute(match)
            if hour_minute is None:
                ambiguous_time = True
                continue
            day = datetime.strptime(match.group("date"), "%Y-%m-%d").date()
            due = _resolve_local_datetime(day, *hour_minute, local_now.tzinfo)
            if due is None:
                ambiguous_time = True
                continue
        except ValueError:
            ambiguous_time = True
            continue
        candidates.append((match.start(), match.end(), due))

    for match in _RELATIVE_DAY_RE.finditer(text):
        hm = _hour_minute(match)
        if hm is None:
            ambiguous_time = True
            continue
        day_word = match.group("day").lower()
        offset = (
            0
            if day_word in {"today", "tonight", "сьогодні", "сьогодні ввечері", "сьогодні увечері"}
            else 1
        )
        day = local_now.date() + timedelta(days=offset)
        due = _resolve_local_datetime(day, *hm, local_now.tzinfo)
        if due is None:
            ambiguous_time = True
            continue
        candidates.append((match.start(), match.end(), due))

    recognized_day_spans = [(start, end) for start, end, _due in candidates]
    for match in _CLOCK_TIME_RE.finditer(text):
        if any(
            start <= match.start() and match.end() <= end for start, end in recognized_day_spans
        ):
            continue
        hm = _hour_minute(match)
        if hm is None:
            ambiguous_time = True
            continue
        due = _resolve_local_datetime(local_now.date(), *hm, local_now.tzinfo)
        if due is None:
            ambiguous_time = True
            continue
        candidates.append((match.start(), match.end(), due))

    recognized_spans = [(start, end) for start, end, _due in candidates]
    for pattern in (_TIME_HINT_RE, _VAGUE_TIME_RE):
        for hint in pattern.finditer(text):
            if not any(
                start <= hint.start() and hint.end() <= end for start, end in recognized_spans
            ):
                ambiguous_time = True
                break

    if len(candidates) > 1:
        return ReminderParseResult(
            "ambiguous",
            task=_task_text(text, intent, [(a, b) for a, b, _ in candidates]),
            clarification="У фразі знайдено кілька можливих часів. Укажи один точний час.",
        )

    if ambiguous_time:
        return ReminderParseResult(
            "ambiguous",
            task=_task_text(text, intent, [(a, b) for a, b, _ in candidates]),
            clarification="Не вдалося однозначно розібрати дату або час. Укажи дату й час явно.",
        )

    if candidates:
        start, end, due = candidates[0]
        if due <= local_now:
            return ReminderParseResult(
                "ambiguous",
                task=_task_text(text, intent, [(start, end)]),
                clarification="Цей час уже минув. Укажи майбутній час.",
            )
        task = _task_text(text, intent, [(start, end)])
        if not task:
            return ReminderParseResult(
                "needs_task",
                due_at=due.timestamp(),
                clarification="Що саме потрібно нагадати?",
            )
        return ReminderParseResult("ready", task=task, due_at=due.timestamp())

    task = _task_text(text, intent, [])
    if _VAGUE_TIME_RE.search(text) or _TIME_HINT_RE.search(text):
        return ReminderParseResult(
            "ambiguous",
            task=task,
            clarification="Час звучить нечітко. Назви точну дату й час, наприклад 18:30.",
        )
    return ReminderParseResult(
        "needs_time",
        task=task,
        clarification=(
            "Коли нагадати? Назви точну дату й час або інтервал, наприклад через 20 хвилин."
        ),
    )


def _resolve_local_datetime(day, hour: int, minute: int, tzinfo) -> datetime | None:
    """Reject nonexistent or repeated wall-clock times at DST transitions."""
    candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tzinfo)
    if candidate.replace(fold=0).utcoffset() != candidate.replace(fold=1).utcoffset():
        return None
    round_trip = candidate.astimezone(UTC).astimezone(tzinfo)
    if (round_trip.date(), round_trip.hour, round_trip.minute) != (day, hour, minute):
        return None
    return candidate
