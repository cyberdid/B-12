"""Structured evidence packets for applying autobiographical memory (ADR-016).

The lexical similarity links are candidate relationships only. They do not establish that two
records semantically contradict each other.
"""

import re
from datetime import UTC, datetime


def memory_state(record, now: datetime, *, replaced: bool = False) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    def parse_bound(value, *, end=False):
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        if len(value) == 10 and end:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed

    if replaced:
        return "замінено"
    start = parse_bound(record.valid_from)
    end = parse_bound(record.valid_to, end=True)
    if start and now < start:
        return "ще не чинне"
    if end and now > end:
        return "минуло"
    return "чинне"


def memory_meta(record, now: datetime, *, replaced: bool = False) -> dict:
    """Return time, provenance and scope separately from memory text."""
    origin = {
        "explicit": "власник сказав прямо",
        "inferred": "помічник вивів",
    }.get(record.origin, "невідоме походження")
    return {
        "kind": record.kind,
        "event": record.event_time,
        "recorded": record.created_at,
        "valid": {"from": record.valid_from, "to": record.valid_to},
        "state": memory_state(record, now, replaced=replaced),
        "applies_when": record.applies_when,
        "origin": origin,
        "reliability": record.reliability,
        "source": record.source_locator or record.source,
        "source_refs": list(record.sources),
    }


def _shared_subject_terms(left: str, right: str) -> set[str]:
    """Cheap candidate-link heuristic; it identifies similarity, not semantic negation."""
    from b12.memory import _STOP_TERMS, _forms

    def terms(text):
        words = [
            word.replace("’", "'").replace("ʼ", "'").lower()
            for word in re.findall(r"[^\W_]+(?:['’ʼ][^\W_]+)*", text, flags=re.UNICODE)
        ]
        return {
            form
            for word in words
            if len(word) >= 3 and word not in _STOP_TERMS
            for form in _forms(word)
            if form not in _STOP_TERMS
        }

    return terms(left) & terms(right)


def evidence_packet(records, now: datetime) -> list[dict]:
    """Build `{id,text,meta}` records and add likely same-subject candidate links."""
    visible = [(record, replaced) for record, replaced in records]
    metadata = {
        record.id: memory_meta(record, now, replaced=replaced)
        for record, replaced in visible
    }
    current = [
        record
        for record, replaced in visible
        if not replaced and metadata[record.id]["state"] == "чинне"
    ]
    links = {record.id: [] for record in current}
    for index, first in enumerate(current):
        for second in current[index + 1 :]:
            if first.text.strip() != second.text.strip() and len(
                _shared_subject_terms(first.text, second.text)
            ) >= 2:
                links[first.id].append(second.id)
                links[second.id].append(first.id)
    result = []
    for record, _replaced in visible:
        meta = metadata[record.id]
        if links.get(record.id):
            meta["conflicts_with"] = sorted(set(links[record.id]))
        result.append({"id": record.id, "text": record.text, "meta": meta})
    return result
