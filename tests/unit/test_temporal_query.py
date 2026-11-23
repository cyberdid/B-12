"""resolve_period: the time period a Ukrainian question asks about (recall_as_of)."""

from datetime import date, datetime

import pytest

from b12.temporal_query import resolve_period

NOW = datetime(2026, 12, 1, 10, 0)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Яка була адреса майстерні в жовтні?", (date(2026, 10, 1), date(2026, 10, 31))),
        ("За якою адресою працювала майстерня у жовтні?", (date(2026, 10, 1), date(2026, 10, 31))),
        ("Що ми купували у березні?", (date(2026, 3, 1), date(2026, 3, 31))),
        ("Хто був постачальником у грудні?", (date(2026, 12, 1), date(2026, 12, 31))),
        ("А в жовтні 2025 року?", (date(2025, 10, 1), date(2025, 10, 31))),
        ("Що було 15 жовтня?", (date(2026, 10, 15), date(2026, 10, 15))),
        ("Що було 25 грудня?", (date(2025, 12, 25), date(2025, 12, 25))),  # not yet this year
        ("Яка ціна була минулого місяця?", (date(2026, 11, 1), date(2026, 11, 30))),
        ("Що сталося 2026-10-15?", (date(2026, 10, 15), date(2026, 10, 15))),
        ("Що сталося 15.10.2026?", (date(2026, 10, 15), date(2026, 10, 15))),
        ("у лютому", (date(2026, 2, 1), date(2026, 2, 28))),
    ],
)
def test_named_periods_are_resolved(text, expected):
    assert resolve_period(text, NOW) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Яка зараз адреса майстерні?",
        "Що змінилося з 15 жовтня?",
        "Нагадай до 15 жовтня",
        "Що буде після 3 листопада?",
        "",
        "Привіт!",
        "31 лютого",  # impossible date
    ],
)
def test_no_period_or_a_range_boundary_gives_none(text):
    assert resolve_period(text, NOW) is None


def test_january_last_month_wraps_the_year():
    assert resolve_period("минулого місяця", date(2026, 1, 10)) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )


def test_first_named_period_wins():
    assert resolve_period("у жовтні, а не 3 листопада", NOW) == (
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
