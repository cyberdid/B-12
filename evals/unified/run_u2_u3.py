"""Run one U2/U3 draft scenario through the real B-12 agent turn and record raw output.

The runner never reads the oracle: scoring is a separate, blind step. It seeds a fresh
runtime with `setup_adapter.build_runtime`, opens it with the evaluation model settings,
issues the speaking actor a grant exactly as `RuntimeTurnExecutor` does, runs one turn
with the model-visible `user_prompt`, and writes a JSON record with the reply, every tool
call (name, arguments, status), policy decisions, evidence translated back to declared
fixture ids, latency and the adapter report.

Real model runs belong inside the bubblewrap worker (`run_u2_u3_sandboxed.sh`), where
/sandbox and /actors are fresh tmpfs mounts. BLOCKED scenarios are recorded, not run.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from evals.unified.setup_adapter import build_runtime

TURN_TIMEOUT_S = 600.0

# U2 style arms (reports/unified/U2_BREVITY_REPRODUCTION.md), exact wording.
A0_SENTENCE = "У побуті будь лаконічною; складні й технічні відповіді давай точно та повно."
A1_SENTENCE = (
    "У побуті будь лаконічною: на привітання, питання про тебе, втому чи емоції відповідай 1–3 "
    "короткими реченнями (до ~300 символів), без списків і заголовків. Складні й технічні "
    "відповіді, звіти та аналіз давай точно та повно."
)
E1_INSTRUCTION = (
    "Це правило стосується лише фінального повідомлення користувачу після завершення роботи. "
    "Воно не змінює вибір інструментів, аргументи, порядок перевірок, повноту аналізу, критерії "
    "завершення або фактичний статус задачі. Для побутових відповідей пиши 1–3 короткі речення, "
    "приблизно до 300 символів, без списків і заголовків. Складні технічні відповіді та звіти "
    "подавай точно й повно."
)
ARMS = ("A0", "A1", "E1", "D", "D2", "D3")

# Arm D (U2 control arm "deterministic completion verifier"; owner approved 18.11.2026 as an
# experiment). The runtime already re-asks once when a turn with no tool result claims a check
# (b12.agent._ACTION_CLAIM / _ACTION_NUDGE), but only for a few objects (logs, file, system,
# state, data, config): "прочитав настанову/інструкцію" (M18, M50) slipped through. Arm D widens
# that one pattern for the run; the prompt stays A0. If D helps, the Capri fix is this pattern.
BROAD_ACTION_CLAIM = re.compile(
    r"(?<!не )\b(?:я\s+)?(?:перевіри(?:в|ла|ли)|перегляну(?:в|ла|ли)|прочита(?:в|ла|ли)|"
    r"проаналізува(?:в|ла|ли)|подиви(?:вся|лася|лись)|відкри(?:в|ла|ли)|знай(?:шов|шла|шли))\b",
    re.IGNORECASE,
)

# Arm D2 (18.11.2026, after D's false positives): the same verbs, but only with a document,
# file, log or system object; "знайшов" and anything about recalled memories are left alone.
NARROW_ACTION_CLAIM = re.compile(
    r"(?<!не )\b(?:я\s+)?(?:перевіри(?:в|ла|ли)|перегляну(?:в|ла|ли)|прочита(?:в|ла|ли)|"
    r"відкри(?:в|ла|ли)|проаналізува(?:в|ла|ли))\s+(?:\S+\s+)?"
    r"(?:файл\w*|настанов\w*|інструкці\w*|документ\w*|журнал\w*|лог\w*|конфіг\w*|"
    r"каталог\w*|тек\w*|протокол\w*|специфікаці\w*|систем\w*|`)",
    re.IGNORECASE,
)


def apply_arm(system_prompt, arm):
    """Return the system prompt for a U2 style arm; A0 is the unchanged baseline."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    if system_prompt.count(A0_SENTENCE) != 1:
        raise ValueError("baseline prompt must contain the A0 sentence exactly once")
    if arm == "A1":
        return system_prompt.replace(A0_SENTENCE, A1_SENTENCE)
    if arm == "E1":
        return f"{system_prompt.rstrip()} {E1_INSTRUCTION}"
    return system_prompt  # A0, D, D2 and D3 share the baseline prompt


def _plain(value):
    """Runtime events hold read-only mappings and tuples; records must be plain JSON."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _load(root, relative):
    return json.loads((Path(root) / relative).read_text(encoding="utf-8"))


def _grant(runtime, actor, session, declared_tools=None):
    """Issue the turn grant as RuntimeTurnExecutor does, narrowed to the declared tools.

    The control path checks capabilities, not tool names, so the narrowing is the union of
    the declared tools' capabilities: tools sharing a capability stay visible.
    """
    from b12.auth import GUEST_CAPABILITIES, owner_capabilities

    task = runtime.control.create_task(session)
    if actor.owner:
        capabilities = owner_capabilities(runtime.settings)
        full = runtime.settings.host_access == "full"
    else:
        capabilities, full = tuple(sorted(GUEST_CAPABILITIES)), False
    policy = {"declared_available_tools": declared_tools, "applied": False}
    if declared_tools is not None:
        tools = runtime.registry._tools  # name -> registered tool with its capability
        wanted = {tools[name].capability for name in declared_tools if name in tools}
        capabilities = tuple(c for c in capabilities if c in wanted)
        policy = {
            "declared_available_tools": declared_tools,
            "applied": True,
            "level": "capability",
            "granted_capabilities": list(capabilities),
            "visible_tools": sorted(
                name for name, tool in tools.items() if tool.capability in capabilities
            ),
        }
    grant = runtime.control.issue_grant(
        actor.id,
        session,
        capabilities,
        task_id=task,
        ttl_s=TURN_TIMEOUT_S + 3600,
        full_execution=full,
    )
    return grant, task, policy


def _calls(result):
    started = {
        e.data["call_id"]: {"name": e.data.get("name"), "arguments": e.data.get("arguments")}
        for e in result.events
        if e.type == "tool_started" and e.data.get("call_id")
    }
    calls = []
    for r in result.tool_results:
        call = started.pop(r.call_id, {"name": r.name, "arguments": None})
        calls.append({**call, "status": r.status, "error_code": r.error_code})
    for e in result.events:
        if e.type in ("approval_pending", "clarify_pending") and e.data.get("call_id") in started:
            call = started.pop(e.data["call_id"])
            calls.append({**call, "status": e.type, "error_code": None})
    calls.extend({**call, "status": "no_result", "error_code": None} for call in started.values())
    return calls


RUNTIME_FLAGS = (
    "verify_writes",
    "goals_in_context",
    "memory_scoped",
    "preference_rules",
    "memory_grounding",
    "memory_taint",
    "memory_as_of",
    "session_search",
    "memory_ranking",
    "goal_contract",
    "standing_intents",
    "clarify_tool",
    "stable_prefix",
    "parallel_reads",
)


def run_scenario(
    row,
    root,
    settings,
    work_dir,
    *,
    files_root,
    existing_files_root=False,
    arm="A0",
    memory_temporal=False,
    runtime_flags=(),
    preference_placement="system",
):
    """Run one manifest row; return the raw record (no scoring)."""
    record = {
        "scenario_id": row["scenario_id"],
        "family_id": row["family_id"],
        "track": row["track"],
        "input_fixture_sha256": row["input_fixture_sha256"],
        "setup_fixture_sha256": row.get("setup_fixture_sha256"),
    }
    if row.get("notes", "").startswith("BLOCKED:"):
        return {**record, "status": "BLOCKED", "reason": row["notes"]}
    prompt = _load(root, row["input_fixture"])["user_prompt"]
    setup = _load(root, row["setup_fixture"])["harness_setup"]
    work_dir = Path(work_dir)
    report = build_runtime(
        setup,
        work_dir / "state",
        settings,
        files_root=files_root,
        existing_files_root=existing_files_root,
        temporal=memory_temporal,
        scoped="memory_scoped" in runtime_flags,
    )
    from b12.runtime import open_runtime

    runtime = open_runtime(
        settings.model_copy(
            update={
                "state_dir": work_dir / "state",
                "memory_temporal": memory_temporal,
                # Every arm flag explicit: Settings defaults change over time (goals_in_context
                # became on by default on 19.11.2026), an arm must not inherit them silently.
                **{flag: flag in runtime_flags for flag in RUNTIME_FLAGS},
                "preference_placement": preference_placement,
                "annotate_unverified_claims": arm == "D3",
            }
        )
    )
    runtime.agent.system_prompt = apply_arm(runtime.agent.system_prompt, arm)
    from evals.unified.env_stub import stub_environment

    environment_stub = stub_environment(runtime.registry, setup.get("synthetic_environment"))
    if setup.get("synthetic_clock"):
        # The scenario's "today" (used only by temporal memory, ADR-015).
        pinned = datetime.fromisoformat(setup["synthetic_clock"])
        runtime.agent.clock = lambda: pinned
    import b12.agent as agent_module

    default_claim = agent_module._ACTION_CLAIM
    if arm == "D":
        agent_module._ACTION_CLAIM = BROAD_ACTION_CLAIM
    elif arm in ("D2", "D3"):
        agent_module._ACTION_CLAIM = NARROW_ACTION_CLAIM
    prompt_sha = hashlib.sha256(runtime.agent.system_prompt.encode()).hexdigest()
    loop = asyncio.new_event_loop()
    try:
        speaker = report["speaking_actor"]
        actor = runtime.control.resolve_actor(report["actors"][speaker])
        session = report["sessions"][speaker]
        grant, task, tool_policy = _grant(runtime, actor, session, setup.get("available_tools"))
        result = loop.run_until_complete(
            runtime.agent.turn(session, grant, prompt, task_id=task, timeout_s=TURN_TIMEOUT_S)
        )
    finally:
        agent_module._ACTION_CLAIM = default_claim
        runtime.close()
        loop.close()
    real_to_declared = {real: declared for declared, real in report["memory_ids"].items()}
    metrics = list(result.model_metrics)
    ttft = next((m.get("ttft_s") for m in metrics if m.get("ttft_s")), None)
    return _plain(
        {
            **record,
            "status": "EXECUTED",
            "u2_arm": arm,
            "memory_temporal": memory_temporal,
            "runtime_flags": sorted(
                (
                    *runtime_flags,
                    *(["preference_placement=query"] if preference_placement == "query" else []),
                )
            ),
            "environment_stub": environment_stub,
            "action_claim_pattern": {
                "D": "broad (arm D)",
                "D2": "narrow (arm D2)",
                "D3": "narrow + runtime note (arm D3)",
            }.get(arm, "runtime default"),
            "system_prompt_sha256": prompt_sha,
            "model": settings.model,
            "runtime_state": result.state,
            "error_code": result.error_code,
            "reply": result.content,
            "tool_calls": _calls(result),
            "policy_decisions": [e.data for e in result.events if e.type == "policy_decision"],
            "evidence_ids": [real_to_declared.get(e, f"runtime:{e}") for e in result.evidence_ids],
            "pending_operations": list(result.pending_operations),
            "ttft_ms": round(ttft * 1000, 2) if ttft is not None else None,
            "tokens_prompt": sum(int(m.get("prompt_eval_count", 0) or 0) for m in metrics),
            "tokens_completion": sum(int(m.get("eval_count", 0) or 0) for m in metrics),
            "seed_report": {
                k: report[k] for k in ("dropped_fields", "applied_relations", "revoked_memories")
            },
            "tool_policy": tool_policy,
        }
    )


def settings_for_setup(template, setup, state_dir):
    """Evaluation settings for one scenario: quiet hours off, sudo per the setup."""
    return template.model_copy(
        update={
            "state_dir": Path(state_dir),
            "quiet_start": "00:00",
            "quiet_end": "00:00",
            "sudo_access": "approval" if setup.get("sudo_access") == "approval" else "off",
        }
    )


def main(argv=None):
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("scenario_id")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument(
        "--model-alias", choices=("pinned_primary", "any_swappable"), default="pinned_primary"
    )
    parser.add_argument("--variant", default="")
    parser.add_argument("--arm", choices=ARMS, default="A0", help="U2 style arm")
    parser.add_argument(
        "--memory-temporal", action="store_true", help="ADR-015 temporal memory (U4 arm)"
    )
    parser.add_argument(
        "--memory-scoped", action="store_true", help="ADR-016 scoped memory (U5 arm)"
    )
    parser.add_argument(
        "--preference-rules", action="store_true", help="answer preferences from memory as rules"
    )
    parser.add_argument(
        "--preference-placement",
        choices=("system", "query"),
        default="system",
        help="where preference_rules sit: system or beside the query",
    )
    parser.add_argument(
        "--memory-grounding", action="store_true", help="grounding rules for memory writes"
    )
    parser.add_argument(
        "--memory-taint", action="store_true", help="taint memory writes after network calls"
    )
    parser.add_argument(
        "--memory-as-of", action="store_true", help="historical as_of parameter on memory_search"
    )
    parser.add_argument(
        "--session-search", action="store_true", help="FTS5 conversation_search tool"
    )
    parser.add_argument(
        "--memory-ranking",
        action="store_true",
        help="recency/importance memory ranking and importance field",
    )
    parser.add_argument(
        "--goal-contract", action="store_true", help="ADR-019 goal completion contract"
    )
    parser.add_argument(
        "--standing-intents", action="store_true", help="inject matched standing intents"
    )
    parser.add_argument(
        "--clarify-tool", action="store_true", help="offer clarify(question, choices) tool"
    )
    parser.add_argument(
        "--stable-prefix",
        action="store_true",
        help="keep fixed persona/policy bytes before volatile system parts",
    )
    parser.add_argument(
        "--parallel-reads",
        action="store_true",
        help="run consecutive *.read tool calls concurrently via asyncio.gather",
    )
    parser.add_argument("--verify-writes", action="store_true", help="runtime write read-back")
    parser.add_argument("--goals-in-context", action="store_true", help="goal state in context")
    parser.add_argument(
        "--model-timeout",
        type=float,
        default=None,
        help="per model round, e.g. for subscription bridges",
    )
    parser.add_argument(
        "--num-ctx", type=int, default=None, help="override the context window (cloud models)"
    )
    parser.add_argument(
        "--output-tokens", type=int, default=None, help="override the reply budget (cloud models)"
    )
    args = parser.parse_args(argv)
    if os.environ.get("B12_EVAL_SANDBOX") != "1":
        parser.exit(
            2,
            "run_u2_u3 seeds files at /sandbox and gives the model host tools; "
            "run it only through run_u2_u3_sandboxed.sh\n",
        )
    from evals.capri_comprehensive.runners.runtime_executor import model_templates

    root = Path.cwd()
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))["scenarios"]
    row = next((r for r in rows if r["scenario_id"] == args.scenario_id), None)
    if row is None:
        parser.exit(2, f"unknown scenario {args.scenario_id}\n")
    work = Path("/tmp/u2u3-work")
    template = model_templates(work / "template", args.variant)[args.model_alias]
    setup = _load(root, row["setup_fixture"])["harness_setup"] if row.get("setup_fixture") else {}
    settings = settings_for_setup(template, setup, work / "state")
    if args.model_timeout:
        settings = settings.model_copy(update={"model_timeout_s": args.model_timeout})
    if args.output_tokens:
        settings = settings.model_copy(update={"output_tokens": args.output_tokens})
    if args.num_ctx:
        # Cloud models behind the subscription bridge have windows far beyond 8192; the owner
        # lifted the local context limit for them so admission never trims their context.
        settings = settings.model_copy(update={"num_ctx": args.num_ctx})
    socket_value = os.environ.get("B12_EVAL_BROKER_SOCKET")
    if not socket_value or not Path(socket_value).is_socket():
        parser.exit(2, "model broker socket is unavailable\n")
    if os.environ.get("B12_EVAL_OLLAMA_URL") != "http://127.0.0.1:11434":
        parser.exit(2, "runtime model URL must point to the isolated loopback bridge\n")
    from evals.socket_bridge import SocketBridge

    # Inside the network namespace the only model route is this loopback relay to the
    # host-side allowlist broker (same as run_networkless_runtime_suite).
    with SocketBridge(Path(socket_value), host="127.0.0.1", port=11434):
        record = run_scenario(
            row,
            root,
            settings,
            work,
            files_root=Path("/"),
            existing_files_root=True,
            arm=args.arm,
            memory_temporal=args.memory_temporal,
            preference_placement=args.preference_placement,
            runtime_flags=tuple(
                flag
                for flag, on in (
                    ("verify_writes", args.verify_writes),
                    ("goals_in_context", args.goals_in_context),
                    ("memory_scoped", args.memory_scoped),
                    ("preference_rules", args.preference_rules),
                    ("memory_grounding", args.memory_grounding),
                    ("memory_taint", args.memory_taint),
                    ("memory_as_of", args.memory_as_of),
                    ("session_search", args.session_search),
                    ("memory_ranking", args.memory_ranking),
                    ("goal_contract", args.goal_contract),
                    ("standing_intents", args.standing_intents),
                    ("clarify_tool", args.clarify_tool),
                    ("stable_prefix", args.stable_prefix),
                    ("parallel_reads", args.parallel_reads),
                )
                if on
            ),
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.scenario_id}.json"
    text = json.dumps(record, ensure_ascii=False, indent=1) + "\n"  # fail before creating
    fd = os.open(out, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"{args.scenario_id}: {record['status']}", file=sys.stderr)


if __name__ == "__main__":
    main()
