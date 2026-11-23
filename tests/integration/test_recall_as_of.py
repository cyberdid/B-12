"""recall_as_of: a question that names a period recalls the records valid in that period."""

from datetime import UTC, datetime

from b12.runtime import open_runtime

NOW = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)


def _seed(runtime, actor):
    """The ports-live-v1 M96 shape: one October address, ten November ones crowding it out."""
    ids = {}
    ids["october"] = runtime.memory.remember(
        "Адреса майстерні (основний цех, початкова локація) — вул. Вишнева, 14.",
        actor,
        valid_from="2026-09-01",
        valid_to="2026-10-31",
    ).id
    ids["moved"] = runtime.memory.remember(
        "Адреса майстерні (тимчасовий переїзд) — вул. Тополина, 8.",
        actor,
        valid_from="2026-11-01",
        valid_to="2026-11-15",
    ).id
    ids["current"] = runtime.memory.remember(
        "Адреса майстерні (основний цех) — вул. Заводська, 22.", actor, valid_from="2026-11-16"
    ).id
    ids["distractors"] = [
        runtime.memory.remember(
            f"Адреса майстерні №{n} — вул. Тестова, {n}.", actor, valid_from="2026-11-05"
        ).id
        for n in range(1, 11)
    ]
    ids["undated"] = runtime.memory.remember("Майстерня працює з дев'ятої ранку.", actor).id
    return ids


async def _recall(base, tmp_path, text, *, flag):
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / f"s{flag}", "recall_as_of": flag})
    )
    try:
        runtime.agent.clock = lambda: NOW
        actor = runtime.control.create_actor(owner=True, consent=True)
        ids = _seed(runtime, actor)
        items = await runtime.agent._recall(text, actor)
        got = {item["id"] for item in items}
        texts = {runtime.memory.get(i, actor).text for i in got}
        return got, ids, texts
    finally:
        runtime.close()


async def test_a_named_month_recalls_the_record_valid_then(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    got, ids, _ = await _recall(base, tmp_path, "Яка була адреса майстерні в жовтні?", flag=True)
    assert ids["october"] in got
    assert not (got & set(ids["distractors"])), "addresses valid only from November must go"
    assert ids["current"] not in got and ids["moved"] not in got


async def test_without_the_flag_recall_is_unchanged(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    got, ids, _ = await _recall(base, tmp_path, "Яка була адреса майстерні в жовтні?", flag=False)
    assert got & set(ids["distractors"]), "the flag off keeps the old behaviour"


async def test_a_question_without_a_period_is_not_filtered(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    _, _, on = await _recall(base, tmp_path / "a", "Яка зараз адреса майстерні?", flag=True)
    _, _, off = await _recall(base, tmp_path / "b", "Яка зараз адреса майстерні?", flag=False)
    assert on == off  # same texts recalled: no period, no filtering


async def test_a_record_without_a_validity_window_is_kept(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    got, ids, _ = await _recall(base, tmp_path, "О котрій працювала майстерня в жовтні?", flag=True)
    assert ids["undated"] in got


async def test_records_matching_more_question_words_win_the_slots(scripted_ollama, tmp_path):
    """Six warehouse addresses valid in the period match "адресою" only; the workshop address
    matches "адресою" and "майстерня" and must not be crowded out (asof-live-v1 M99-P2)."""
    _, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "s", "recall_as_of": True})
    )
    try:
        runtime.agent.clock = lambda: NOW
        actor = runtime.control.create_actor(owner=True, consent=True)
        workshop = runtime.memory.remember(
            "Адреса майстерні (тимчасовий переїзд) — вул. Тополина, 8.",
            actor,
            valid_from="2026-11-01",
            valid_to="2026-11-15",
        )
        for n in range(1, 7):
            runtime.memory.remember(
                f"Адреса складу №{n} — вул. Складська, {n}.", actor, valid_from="2026-11-05"
            )
        items = await runtime.agent._recall("За якою адресою була майстерня 10 листопада?", actor)
        assert workshop.id in {item["id"] for item in items}
    finally:
        runtime.close()
