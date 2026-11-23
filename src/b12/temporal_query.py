"""The time period a question asks about, read from Ukrainian text without a model.

Used by recall (flag `recall_as_of`) so that "яка була адреса в жовтні?" offers the records that
were valid in October, instead of today's records. Both gemma4:12b and gpt-6-luna answered such
questions from the current records and never called memory_search with as_of (ports-live-v1
M96, 22-23.11.2026): the runtime has to apply the period itself.

Only unambiguous points in time are recognised:
  "у/в жовтні [2025 року]"      -> that month
  "15 жовтня [2025]"            -> that day
  "минулого місяця", "у минулому місяці" -> the previous calendar month
  "2026-10-15", "15.10.2026"    -> that day
Ranges and boundaries ("з жовтня", "до жовтня", "після жовтня") are deliberately not read:
they do not name one period, and a wrong guess would hide the right records.
A month or day without a year is the latest such period not after `now`.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime

_MONTHS = (
    ("січ", "січні", "січня"),
    ("лют", "лютому", "лютого"),
    ("берез", "березні", "березня"),
    ("квіт", "квітні", "квітня"),
    ("трав", "травні", "травня"),
    ("черв", "червні", "червня"),
    ("лип", "липні", "липня"),
    ("серп", "серпні", "серпня"),
    ("верес", "вересні", "вересня"),
    ("жовт", "жовтні", "жовтня"),
    ("листопад", "листопаді", "листопада"),
    ("груд", "грудні", "грудня"),
)
_LOCATIVE = {loc: index + 1 for index, (_, loc, _) in enumerate(_MONTHS)}
_GENITIVE = {gen: index + 1 for index, (_, _, gen) in enumerate(_MONTHS)}

_YEAR = r"(?:\s+(\d{4})(?:\s*(?:року|році|р\.?))?)?"
_IN_MONTH = re.compile(rf"(?<!\w)(?:у|в)\s+({'|'.join(_LOCATIVE)}){_YEAR}(?!\w)", re.I)
_DAY_MONTH = re.compile(rf"(?<![\w.])(\d{{1,2}})\s+({'|'.join(_GENITIVE)}){_YEAR}(?!\w)", re.I)
_LAST_MONTH = re.compile(r"(?<!\w)(?:минулого\s+місяця|у\s+минулому\s+місяці)(?!\w)", re.I)
_ISO_DAY = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_DOTTED_DAY = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\d.])")
_BOUNDARY = re.compile(r"(?<!\w)(?:з|із|від|до|після|починаючи\s+з)\s*$", re.I)


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _latest_year_for_month(month: int, now: date) -> int:
    return now.year if month <= now.month else now.year - 1


def _latest_year_for_day(month: int, day: int, now: date) -> int:
    return now.year if (month, day) <= (now.month, now.day) else now.year - 1


def _preceded_by_boundary(text: str, start: int) -> bool:
    """True when the match follows "з", "до", "після"...: a range boundary, not a period."""
    return bool(_BOUNDARY.search(text[:start]))


def resolve_period(text: str, now: datetime | date) -> tuple[date, date] | None:
    """The first unambiguous period named in `text`, as inclusive (start, end) dates."""
    if not isinstance(text, str) or not text.strip():
        return None
    today = now.date() if isinstance(now, datetime) else now
    candidates: list[tuple[int, tuple[date, date]]] = []

    for match in _ISO_DAY.finditer(text):
        try:
            day = date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            continue
        candidates.append((match.start(), (day, day)))
    for match in _DOTTED_DAY.finditer(text):
        try:
            day = date(int(match[3]), int(match[2]), int(match[1]))
        except ValueError:
            continue
        candidates.append((match.start(), (day, day)))
    for match in _DAY_MONTH.finditer(text):
        if _preceded_by_boundary(text, match.start()):
            continue
        month = _GENITIVE[match[2].lower()]
        day_number = int(match[1])
        year = int(match[3]) if match[3] else _latest_year_for_day(month, day_number, today)
        try:
            day = date(year, month, day_number)
        except ValueError:
            continue
        candidates.append((match.start(), (day, day)))
    for match in _IN_MONTH.finditer(text):
        month = _LOCATIVE[match[1].lower()]
        year = int(match[2]) if match[2] else _latest_year_for_month(month, today)
        candidates.append((match.start(), _month_range(year, month)))
    for match in _LAST_MONTH.finditer(text):
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        candidates.append((match.start(), _month_range(year, month)))

    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]
