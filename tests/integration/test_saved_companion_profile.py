"""Saved companion profile: one bounded data file the voice and CLI turns read, never a grant."""

import json
import stat
from datetime import UTC, datetime

from b12.auth import owner_capabilities
from b12.persona import PROFILE_FILE, load_saved_companion_profile, save_companion_profile
from b12.runtime import open_runtime

PINNED = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def test_save_normalizes_limits_and_is_owner_only(tmp_path):
    path = save_companion_profile(
        tmp_path,
        {"name": "  Олег  ", "style_note": "x" * 2000, "catchphrases": ["ok", "", 5] * 20},
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    saved = load_saved_companion_profile(tmp_path)
    assert saved["name"] == "Олег"
    assert len(saved["style_note"]) == 800
    assert saved["catchphrases"] == ["ok"] * 10  # first 30 items, then empty/foreign dropped
    save_companion_profile(tmp_path, None)
    assert load_saved_companion_profile(tmp_path) is None


def test_unreadable_or_foreign_shapes_are_ignored(tmp_path):
    (tmp_path / PROFILE_FILE).write_text("{not json", encoding="utf-8")
    assert load_saved_companion_profile(tmp_path) is None
    (tmp_path / PROFILE_FILE).write_text(json.dumps(["list"]), encoding="utf-8")
    assert load_saved_companion_profile(tmp_path) is None


async def _system(scripted_ollama, tmp_path, *, saved, explicit=None):
    state, base = scripted_ollama
    runtime = open_runtime(base.model_copy(update={"state_dir": tmp_path / "state"}))
    try:
        if saved is not None:
            save_companion_profile(runtime.settings.state_dir, saved)
        runtime.agent.clock = lambda: PINNED
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = [{"content": "Привіт."}]
        await runtime.agent.turn(
            session, grant, "Привіт!", task_id=task, timeout_s=60, companion_profile=explicit
        )
    finally:
        runtime.close()
    return state["requests"][-1]["messages"][0]["content"]


async def test_a_turn_without_a_profile_uses_the_saved_one(scripted_ollama, tmp_path):
    system = await _system(
        scripted_ollama, tmp_path, saved={"name": "Олег", "style_note": "коротко, без формул"}
    )
    assert "Профіль Capri нижче — дані власника" in system
    assert "коротко, без формул" in system


async def test_an_explicit_profile_wins_and_no_file_means_no_profile(scripted_ollama, tmp_path):
    system = await _system(
        scripted_ollama,
        tmp_path / "a",
        saved={"name": "Олег", "style_note": "зі збереженого файла"},
        explicit={"name": "Desktop", "style_note": "з desktop"},
    )
    assert "з desktop" in system and "зі збереженого файла" not in system
    plain = await _system(scripted_ollama, tmp_path / "b", saved=None)
    assert "Профіль Capri нижче" not in plain


def test_cli_profile_set_show_clear(tmp_path, monkeypatch, capsys):
    from b12 import cli

    monkeypatch.setenv("B12_STATE_DIR", str(tmp_path / "state"))
    assert cli.main(["profile", "set", "--name", "Олег", "--phrase", "погнали"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Олег"
    assert cli.main(["profile", "set", "--style", "коротко"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown == {"name": "Олег", "style_note": "коротко", "catchphrases": ["погнали"]}
    assert cli.main(["profile", "clear"]) == 0
    capsys.readouterr()
    assert cli.main(["profile", "show"]) == 0
    assert json.loads(capsys.readouterr().out) == {}
