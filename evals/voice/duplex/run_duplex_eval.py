"""Оцінювання full-duplex, AEC, barge-in та speaker verification (Task 17)."""

import asyncio
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer, models, pre_tokenizers

from b12.audio.aec import AcousticEchoCanceller
from b12.audio.duplex import DuplexSession
from b12.config import Settings
from b12.contracts import ModelReply
from b12.runtime import open_runtime


def _signal(duration_s: float, f0: float, sr: int = 16000) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(sr * duration_s), endpoint=False)
    env = np.clip(np.sin(np.pi * t / duration_s) * 1.3, 0.2, 1.0)
    w = (
        0.45 * np.sin(2 * np.pi * f0 * t)
        + 0.25 * np.sin(2 * np.pi * (2 * f0) * t + 0.2)
        + 0.15 * np.sin(2 * np.pi * (3 * f0) * t + 0.5)
    )
    return (w * env).astype(np.float32)


def _temp_settings(root: Path) -> Settings:
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    alphabet = sorted(pre_tokenizers.ByteLevel.alphabet())
    tok = Tokenizer(models.BPE({c: i for i, c in enumerate(alphabet)}, []))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)
    tok.save(str(assets / "tokenizer.json"))
    (assets / "tokenizer_config.json").write_text('{"bos_token":"","eos_token":""}')
    (assets / "chat_template.jinja").write_text(
        "{% for m in messages %}{{m.role}}:{{m.content}};{% endfor %}assistant:"
    )
    prof = {
        "renderer": "hf-jinja-v1",
        "revision": "synthetic-v1",
        "model": "test-model",
        "server_version": "test-1",
        "manifest_digest": "a" * 64,
        "native_template_sha256": hashlib.sha256(b"{{ .Prompt }}").hexdigest(),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.iterdir()},
        "safety_tokens": 8,
        "inline_reasoning": [["<think>", "</think>"]],
    }
    p_path = root / "profile.json"
    p_path.write_text(json.dumps(prof))
    return Settings(
        state_dir=root / "state",
        model="test-model",
        model_profile=p_path,
        tokenizer_dir=assets,
        num_ctx=4096,
        output_tokens=256,
    )


async def main() -> None:
    out_dir = Path(__file__).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. AEC ERLE evaluation
    aec = AcousticEchoCanceller()
    erle_values = []
    for f0 in (130.0, 160.0, 190.0, 220.0, 250.0):
        ref = _signal(0.6, f0)
        aec.feed_render_reference(ref)
        _, stats = aec.process_capture(0.6 * ref)
        erle_values.append(stats.echo_return_loss_enhancement_db)

    # 2. Barge-in time-to-stop across 10 trials & Speaker verification FAR/FRR
    stop_times = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = _temp_settings(root)

        class DummyModel:
            async def chat(self, admitted, *, on_delta=None, cancel=None, deadline=None):
                return ModelReply(content="Добре.", tool_calls=(), metrics={}, finish_reason="stop")

        runtime = open_runtime(settings, model=DummyModel())
        try:
            owner = runtime.control.create_actor(owner=True, consent=True)
            session_id = runtime.control.create_session(owner.id)
            runtime.control.set_meta("owner_actor", owner.id)

            duplex = DuplexSession(runtime, session_id=session_id, actor_id=owner.id)
            for i in range(10):
                speak_task = asyncio.create_task(
                    duplex.speak_response("Перше речення для перевірки. Друге речення.")
                )
                await asyncio.sleep(0.04)
                barge = await duplex.feed_capture_frame(_signal(0.4, 140.0 + i) * 1.4)
                if barge.time_to_stop_ms is not None:
                    stop_times.append(barge.time_to_stop_ms)
                await speak_task

            # Speaker verification trials: 10 genuine owner variations, 10 impostors, 2 replays
            enroll_audio = _signal(1.0, 135.0)
            duplex.speaker_verifier.enroll(
                actor_id=owner.id, caller_actor_id=owner.id, audio_16k=enroll_audio
            )
            false_rejects = 0
            for df in np.linspace(-3.0, 3.0, 10):
                if abs(df) < 1e-6:
                    df = 0.5
                m = duplex.speaker_verifier.verify(_signal(1.0, 135.0 + df))
                if not m.matched:
                    false_rejects += 1

            false_accepts = 0
            for imp_f0 in np.linspace(210.0, 320.0, 10):
                m = duplex.speaker_verifier.verify(_signal(1.0, imp_f0))
                if m.matched:
                    false_accepts += 1

            replay_blocked = duplex.speaker_verifier.verify(enroll_audio).is_spoof_or_replay
            duplex.close()
        finally:
            runtime.close()

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "aec": {
            "trials": len(erle_values),
            "erle_mean_db": round(float(np.mean(erle_values)), 2),
            "erle_min_db": round(float(np.min(erle_values)), 2),
        },
        "barge_in": {
            "trials": len(stop_times),
            "time_to_stop_p50_ms": round(float(np.percentile(stop_times, 50)), 3),
            "time_to_stop_p95_ms": round(float(np.percentile(stop_times, 95)), 3),
            "time_to_stop_p99_ms": round(float(np.percentile(stop_times, 99)), 3),
        },
        "speaker_verification": {
            "genuine_trials": 10,
            "impostor_trials": 10,
            "frr": round(false_rejects / 10.0, 4),
            "far": round(false_accepts / 10.0, 4),
            "exact_replay_blocked": replay_blocked,
        },
        "limits": {
            "physical_8h_acoustic_soak": "open (requires 8h real room speaker+TV+mic run by owner)",
        },
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
