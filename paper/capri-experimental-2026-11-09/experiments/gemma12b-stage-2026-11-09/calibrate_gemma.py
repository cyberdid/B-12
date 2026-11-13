"""Bounded token-accounting pilot. No Agent, host tools, user memory or production config."""
import asyncio
import json
import logging
from pathlib import Path
import time

import httpx

from b12.config import Settings
from b12.context import ContextBuilder
from b12.model import OllamaModel
from b12.model_errors import ModelError

OUT = Path(__file__).resolve().parent
SCHEMA = [{"type": "function", "function": {
    "name": "echo", "description": "Return the supplied text; calibration only, never executed.",
    "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                   "required": ["text"], "additionalProperties": False},
}}]
CASES = [
    ("ua", "Відповідай українською.", [{"role": "user", "content": "Напиши лише слово: привіт"}], []),
    ("emoji", "Be concise.", [{"role": "user", "content": "Repeat exactly: Київ 👋 café"}], []),
    ("schema", "Use the supplied echo tool once.", [{"role": "user", "content": "Echo: мітка"}], SCHEMA),
    ("tool-history", "Report the tool's result briefly.", [
        {"role": "user", "content": "Echo: мітка"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "probe-call-1", "type": "function", "function": {"name": "echo", "arguments": {"text": "мітка"}}}
        ]},
        {"role": "tool", "tool_call_id": "probe-call-1", "tool_name": "echo", "content": "мітка"},
    ], SCHEMA),
]


async def main():
    data = json.loads((OUT / "gemma-assets-preflight.json").read_text())
    assets = Path(data["assets"]["tokenizer.json"]["local_path"]).parent
    settings = Settings(
        state_dir=Path("/tmp/capri-gemma-profile-probe"), model="gemma4:12b",
        model_profile=OUT / "gemma4-12b-candidate-profile.json", tokenizer_dir=assets,
        num_ctx=4096, output_tokens=32, temperature=0.0, seed=42,
        model_timeout_s=45, host_access="none",
    )
    builder = ContextBuilder(settings)
    model = OllamaModel(settings)
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        before = (await client.get("http://127.0.0.1:11434/api/ps")).json()
    if before.get("models"):
        raise SystemExit("Another model is loaded; keep this pilot isolated and do not unload it.")
    observed = []
    deadline = time.monotonic() + 180
    try:
        for repeat in range(1, 3):
            for name, system, messages, tools in CASES:
                if time.monotonic() >= deadline:
                    observed.append({"case": name, "repeat": repeat, "status": "not-run-budget"})
                    break
                row = {"case": name, "repeat": repeat}
                began = time.monotonic()
                try:
                    request = builder.build(system, messages, tools=tools)
                    row.update(input_tokens=request.input_tokens, profile_identity=request.profile_identity)
                    reply = await model.chat(request, deadline=min(deadline, time.monotonic() + 45))
                    row.update(
                        status="returned", metrics=dict(reply.metrics),
                        finish_reason=reply.finish_reason,
                        exact_prompt_count=reply.metrics.get("prompt_eval_count") == request.input_tokens,
                        public_output=reply.content,
                        tool_calls=[call.model_dump(mode="json") for call in reply.tool_calls],
                    )
                except ModelError as error:
                    row.update(status="rejected", error_code=error.code, detail=str(error))
                row["elapsed_s"] = time.monotonic() - began
                observed.append(row)
                (OUT / "gemma-calibration-results.json").write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n")
                print(name, repeat, row["status"], row.get("error_code", row.get("exact_prompt_count")), flush=True)
                # A systematic deployment/count mismatch should be investigated before more inference.
                if row.get("error_code") in {"profile_mismatch", "context_mismatch", "admission_invalid"}:
                    return
    finally:
        (OUT / "gemma-calibration-results.json").write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n")
        cleanup = {"unload_acknowledged": await model.unload(timeout_s=10), "loaded_models_before": before}
        (OUT / "gemma-calibration-cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
