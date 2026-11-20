"""Task H1: clarify tool with 2-4 choices, turn wait/resume, API/CLI/voice answer, timeout."""

import asyncio
import json

import numpy as np

from b12.audio.asr import TranscriptResult
from b12.audio.duplex import DuplexSession
from b12.audio.pipeline import VoicePipeline
from b12.audio.tts import SynthesizedAudio
from b12.auth import owner_capabilities
from b12.runtime import open_runtime


def _install_fast_voice(pipeline: VoicePipeline, transcripts: list[str]) -> list[str]:
    spoken: list[str] = []
    queue = list(transcripts)

    def fake_transcribe(audio_16k, *, language="auto"):
        text = queue.pop(0) if queue else ""
        return TranscriptResult(
            text=text,
            language="uk",
            language_probability=0.99,
            duration_s=len(audio_16k) / 16000.0,
            asr_latency_ms=2.0,
            provenance_id="prov-clarify",
        )

    def fast_synth(text, *, lang="auto"):
        spoken.append(text)
        pcm = (np.sin(np.linspace(0, 40, 1600)) * 6000).astype(np.int16).tobytes()
        return SynthesizedAudio(
            text=text,
            language="uk",
            sample_rate=16000,
            pcm_int16=pcm,
            ttfa_ms=1.5,
            duration_s=0.1,
        )

    pipeline.asr.transcribe = fake_transcribe
    pipeline.tts.synthesize = fast_synth
    return spoken


def _speech_chunk() -> np.ndarray:
    t = np.linspace(0.0, 0.5, 8000, endpoint=False)
    return (0.25 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)


async def test_turn_waits_and_resumes_with_the_answer(scripted_ollama, tmp_path):
    state, base = scripted_ollama

    # Off by default: clarify is neither registered nor offered.
    off_rt = open_runtime(base.model_copy(update={"state_dir": tmp_path / "off"}))
    try:
        assert "clarify" not in {t["name"] for t in off_rt.registry.catalog()}
        actor = off_rt.control.create_actor(owner=True, consent=True)
        session = off_rt.control.create_session(actor.id)
        task = off_rt.control.create_task(session)
        grant = off_rt.control.issue_grant(
            actor.id, session, owner_capabilities(off_rt.settings), task_id=task, ttl_s=600
        )
        state["script"] = [{"content": "Привіт."}]
        await off_rt.agent.turn(session, grant, "Привіт", task_id=task, timeout_s=60)
        offered = {t["function"]["name"] for t in state["requests"][-1].get("tools", [])}
        assert "clarify" not in offered
    finally:
        off_rt.close()

    # On: clarify is offered (capability time.read), pauses the turn, and resumes with same turn_id.
    state["requests"].clear()
    rt = open_runtime(base.model_copy(update={"state_dir": tmp_path / "on", "clarify_tool": True}))
    try:
        catalog = {t["name"]: t for t in rt.registry.catalog()}
        assert catalog["clarify"]["capability"] == "time.read"

        actor = rt.control.create_actor(owner=True, consent=True)
        session = rt.control.create_session(actor.id)
        task = rt.control.create_task(session)
        grant = rt.control.issue_grant(actor.id, session, ("time.read",), task_id=task, ttl_s=600)
        state["script"] = [
            {
                "tool_calls": [
                    (
                        "clarify",
                        {
                            "question": "Який порт використати?",
                            "choices": ["8080", "9090"],
                            "allow_other": True,
                        },
                    )
                ]
            },
            {"content": "Запускаю на порту 9090."},
        ]
        waiting = await rt.agent.turn(session, grant, "Запусти сервер", task_id=task, timeout_s=60)
        assert waiting.state == "awaiting_clarify"
        assert len(waiting.pending_operations) == 1
        assert waiting.events[-1].type == "clarify_pending"
        assert waiting.events[-1].data["question"] == "Який порт використати?"
        assert waiting.events[-1].data["choices"] == ["8080", "9090"]
        assert waiting.persisted is False

        op_id = waiting.pending_operations[0]
        pending = rt.control.pending_clarifications(actor_id=actor.id)
        assert len(pending) == 1
        assert pending[0]["operation_id"] == op_id
        assert pending[0]["turn_id"] == waiting.turn_id

        rt.control.answer_clarify(op_id, "9090", actor_id=actor.id)
        done = await rt.agent.resume(waiting.turn_id, timeout_s=60)
        assert done.turn_id == waiting.turn_id
        assert done.state == "completed"
        assert done.persisted is True
        assert done.content == "Запускаю на порту 9090."
        assert done.tool_results[-1].name == "clarify"
        assert done.tool_results[-1].status == "completed"
        assert done.tool_results[-1].content == {"answer": "9090", "status": "answered"}
        assert rt.control.pending_clarifications(actor_id=actor.id) == []

        # Tool payload sent to the model on resume has the exact answer/status object.
        tool_msg = next(
            m for m in reversed(state["requests"][-1]["messages"]) if m["role"] == "tool"
        )
        assert json.loads(tool_msg["content"])["content"] == {
            "answer": "9090",
            "status": "answered",
        }
    finally:
        rt.close()


async def test_voice_reply_answers_pending_clarify(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    rt = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "voice", "clarify_tool": True})
    )
    try:
        owner = rt.control.create_actor(owner=True, consent=True)
        session = rt.control.create_session(owner.id)
        rt.control.set_meta("owner_actor", owner.id)
        pipeline = VoicePipeline(rt)
        spoken = _install_fast_voice(pipeline, ["Налаштуй резервне копіювання", "Щодня"])
        duplex = DuplexSession(rt, session_id=session, actor_id=owner.id, pipeline=pipeline)
        try:
            state["script"] = [
                {
                    "tool_calls": [
                        (
                            "clarify",
                            {
                                "question": "Як часто робити копії?",
                                "choices": ["Щодня", "Щотижня"],
                            },
                        )
                    ]
                },
                {"content": "Добре, налаштувала щоденне копіювання."},
            ]
            audio = _speech_chunk()
            first = await duplex.process_cleaned_utterance(
                audio,
                pipeline.asr.transcribe(audio),
                live_playback=False,
            )
            assert first is not None
            assert first.state == "awaiting_clarify"
            assert first.turn_id is not None
            assert any("Як часто робити копії?" in text for text in spoken)

            second = await duplex.process_cleaned_utterance(
                audio,
                pipeline.asr.transcribe(audio),
                live_playback=False,
            )
            assert second is not None
            assert second.turn_id == first.turn_id
            assert second.state == "completed"
            assert second.reply_text == "Добре, налаштувала щоденне копіювання."
            assert rt.control.pending_clarifications(session_id=session, actor_id=owner.id) == []
            assert len(state["requests"]) == 2
            tool_msg = next(
                m for m in reversed(state["requests"][1]["messages"]) if m["role"] == "tool"
            )
            assert json.loads(tool_msg["content"])["content"] == {
                "answer": "Щодня",
                "status": "answered",
            }
        finally:
            duplex.close()
    finally:
        rt.close()


async def test_timeout_returns_timed_out_and_the_turn_finishes(scripted_ollama, tmp_path):
    state, base = scripted_ollama
    rt = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "timeout", "clarify_tool": True})
    )
    try:
        rt.control.clarify_ttl_s = 0.02
        actor = rt.control.create_actor(owner=True, consent=True)
        session = rt.control.create_session(actor.id)
        task = rt.control.create_task(session)
        grant = rt.control.issue_grant(
            actor.id, session, owner_capabilities(rt.settings), task_id=task, ttl_s=600
        )
        state["script"] = [
            {
                "tool_calls": [
                    (
                        "clarify",
                        {
                            "question": "Перезапустити службу?",
                            "choices": ["Так", "Ні"],
                        },
                    )
                ]
            },
            {"content": "Відповідь не надійшла вчасно, залишаю все без змін."},
        ]
        waiting = await rt.agent.turn(session, grant, "Онови сервіс", task_id=task, timeout_s=60)
        assert waiting.state == "awaiting_clarify"

        await asyncio.sleep(0.05)
        done = await rt.agent.resume(waiting.turn_id, timeout_s=60)
        assert done.turn_id == waiting.turn_id
        assert done.state == "completed"
        assert done.persisted is True
        assert done.tool_results[-1].name == "clarify"
        assert done.tool_results[-1].status == "completed"
        assert done.tool_results[-1].content == {"answer": "", "status": "timed_out"}
        assert done.content == "Відповідь не надійшла вчасно, залишаю все без змін."
        assert rt.control.pending_clarifications(actor_id=actor.id) == []
    finally:
        rt.close()


async def test_clarify_api_cli_and_validation_contracts(scripted_ollama, tmp_path):
    import os
    import sys
    from pathlib import Path

    import httpx

    from b12.api import create_app

    state, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "api_state", "clarify_tool": True})

    # Bootstrap owner + token
    boot = open_runtime(settings)
    owner = boot.control.create_actor(owner=True, consent=True)
    boot.control.set_meta("owner_actor", owner.id)
    boot.control.set_meta("cli_session", boot.control.create_session(owner.id))
    boot.close()

    app = create_app(settings, allowed_hosts=("testserver",), port=80)
    async with app.router.lifespan_context(app):
        token = (settings.state_dir / "api" / "owner.token").read_text().strip()
        headers = {"Authorization": f"Bearer {token}"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            session = (await client.post("/api/sessions", json={}, headers=headers)).json()[
                "session_id"
            ]
            # 1) Invalid choices count (1 choice) fails schema validation cleanly
            # 2) Valid clarify -> POST /api/clarify/{operation_id} skip -> resume
            state["script"] = [
                {
                    "tool_calls": [
                        ("clarify", {"question": "Один?", "choices": ["Лише один"]}),
                    ]
                },
                {
                    "tool_calls": [
                        (
                            "clarify",
                            {
                                "question": "Формат?",
                                "choices": ["JSON", "YAML"],
                                "allow_other": False,
                            },
                        )
                    ]
                },
                {"content": "Пропущено."},
            ]
            resp = await client.post(
                "/api/chat",
                json={"session_id": session, "text": "Експорт"},
                headers=headers,
            )
            waiting = [json.loads(line) for line in resp.text.splitlines() if line][-1]
            assert waiting["state"] == "awaiting_clarify"
            assert waiting["tool_results"][0]["status"] == "denied"
            assert waiting["tool_results"][0]["error_code"] == "invalid_arguments"
            op_id = waiting["pending_operations"][0]

            # Foreign actor cannot answer owner's clarify
            guest = (
                await client.post(
                    "/api/guests",
                    json={"consent": True, "capabilities": ["time.read"]},
                    headers=headers,
                )
            ).json()
            guest_resp = await client.post(
                f"/api/clarify/{op_id}",
                json={"answer": "JSON"},
                headers={"Authorization": f"Bearer {guest['token']}"},
            )
            assert guest_resp.status_code == 404

            # allow_other=False rejects non-matching custom answer
            bad_choice = await client.post(
                f"/api/clarify/{op_id}", json={"answer": "XML"}, headers=headers
            )
            assert bad_choice.status_code == 422

            # Skip works regardless of allow_other
            skipped = await client.post(
                f"/api/clarify/{op_id}", json={"skip": True}, headers=headers
            )
            assert skipped.status_code == 200
            assert skipped.json()["status"] == "skipped"

            resumed = await client.post(f"/api/turns/{waiting['turn_id']}/resume", headers=headers)
            done = [json.loads(line) for line in resumed.text.splitlines() if line][-1]
            assert done["state"] == "completed"
            assert done["tool_results"][-1]["content"] == {"answer": "", "status": "skipped"}

    # CLI `b12 answer <id> <text>` + `b12 resume <turn_id>` across real processes
    src_root = str(Path(__file__).resolve().parents[2] / "src")
    cli_env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": src_root,
        "HOME": str(tmp_path / "home"),
        "B12_STATE_DIR": str(tmp_path / "cli_state"),
        "B12_MODEL": settings.model,
        "B12_OLLAMA_URL": settings.ollama_url,
        "B12_MODEL_PROFILE": str(settings.model_profile),
        "B12_TOKENIZER_DIR": str(settings.tokenizer_dir),
        "B12_NUM_CTX": str(settings.num_ctx),
        "B12_OUTPUT_TOKENS": str(settings.output_tokens),
        "B12_CLARIFY_TOOL": "true",
    }

    async def run_cli(*args):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "b12.cli",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=cli_env,
        )
        out, err = await asyncio.wait_for(proc.communicate(), 30)
        return proc.returncode, out.decode(), err.decode()

    assert (await run_cli("init"))[0] == 0
    state["script"] = [
        {"tool_calls": [("clarify", {"question": "Колір?", "choices": ["Синій", "Зелений"]})]},
        {"content": "Обрано Синій."},
    ]
    code, out, _ = await run_cli("chat", "-m", "Обери тему", "--json")
    waiting_cli = json.loads(out)
    assert code == 2 and waiting_cli["state"] == "awaiting_clarify"
    cli_op = waiting_cli["pending_operations"][0]

    code, out, _ = await run_cli("answer", cli_op, "Синій")
    answered = json.loads(out)
    assert code == 0 and answered["status"] == "answered" and answered["answer"] == "Синій"

    code, out, _ = await run_cli("resume", waiting_cli["turn_id"], "--json")
    done_cli = json.loads(out)
    assert code == 0 and done_cli["state"] == "completed"
    assert done_cli["tool_results"][-1]["content"] == {"answer": "Синій", "status": "answered"}
