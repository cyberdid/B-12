"""Compaction-recall evaluation harness (H4): trim vs trim+memory on a synthetic owner chat.

Generates a deterministic 40-turn synthetic Ukrainian owner conversation with 12 planted facts
in the middle (6 head filler turns -> 12 planted-fact turns -> 22 tail filler turns).
Questions are answered strictly from post-admission context (no tools granted), scored by
normalized exact match against the planted values, and summarized with recall and prompt
tokens per policy (`trim`, `trim+memory`).

The `summary` policy is intentionally NOT implemented here; Track G measures `trim` vs
`trim+memory` first, and `summary` (flag `history_summary`) is gated on those results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import re
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from b12.audio.voice_guards import normalize as normalize_uk
from b12.config import Settings
from b12.model_profile import ModelProfile
from b12.runtime import open_runtime

POLICIES: tuple[str, ...] = ("trim", "trim+memory")
_BASE_DAY = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
_NO_ANSWER_MARKER = "НЕМАЄ В КОНТЕКСТІ"
_QUESTION_SUFFIX = (
    "\n\n[Інструкція оцінки: відповідай виключно на основі повідомлень вище та блоку Evidence, "
    "якщо він присутній. Не використовуй припущень або зовнішніх знань. Напиши ТІЛЬКИ точне "
    "коротке значення без вступних слів і пояснень. Якщо точного значення немає в контексті, "
    f"напиши рівно: {_NO_ANSWER_MARKER}]"
)


@dataclass(frozen=True)
class PlantedFact:
    fact_id: str
    topic: str
    user_turn: str
    assistant_turn: str
    memory_text: str
    question: str
    expected_value: str


PLANTED_FACTS: tuple[PlantedFact, ...] = (
    PlantedFact(
        fact_id="F01",
        topic="monitoring_port",
        user_turn=(
            "Зафіксуй для тестового стенду: локальний моніторинговий шлюз слухає на порту 8443."
        ),
        assistant_turn=(
            "Добре, зафіксував у контексті цієї розмови: локальний моніторинговий шлюз на "
            "стенді налаштовано на порт 8443. Якщо пізніше знадобиться перевірити сервіс або "
            "змінити конфігурацію доступу, спиратимемося саме на це значення."
        ),
        memory_text="Локальний моніторинговий шлюз працює на порту 8443.",
        question="На якому порту працює локальний моніторинговий шлюз?",
        expected_value="8443",
    ),
    PlantedFact(
        fact_id="F02",
        topic="telemetry_codename",
        user_turn="Кодова назва нашого резервного мікросервісу телеметрії — Kestrel-9.",
        assistant_turn=(
            "Зрозумів: резервний мікросервіс телеметрії має кодову назву Kestrel-9. "
            "Використовуватиму саме цю назву в подальших обговореннях архітектури та журналювання."
        ),
        memory_text="Кодова назва резервного мікросервісу телеметрії — Kestrel-9.",
        question="Яка кодова назва резервного мікросервісу телеметрії?",
        expected_value="Kestrel-9",
    ),
    PlantedFact(
        fact_id="F03",
        topic="backup_time",
        user_turn="Щоденний архівний бекап лабораторії запускається о 03:45 за київським часом.",
        assistant_turn=(
            "Прийнято: вікно щоденного архівного бекапу лабораторії призначене на 03:45 за "
            "київським часом, щоб не перетинатися з денними обчисленнями й тестами стенду."
        ),
        memory_text="Щоденний архівний бекап лабораторії запускається о 03:45.",
        question="О котрій годині запускається щоденний архівний бекап лабораторії?",
        expected_value="03:45",
    ),
    PlantedFact(
        fact_id="F04",
        topic="night_tea",
        user_turn="Під час нічного чергування я заварюю лише зелений чай сенча без цукру.",
        assistant_turn=(
            "Запам'ятаю цей синтетичний орієнтир для вечірніх і нічних змін: під час нічного "
            "чергування власник заварює зелений чай сенча без додавання цукру."
        ),
        memory_text="Під час нічного чергування власник заварює зелений чай сенча.",
        question="Який чай власник заварює під час нічного чергування?",
        expected_value="сенча",
    ),
    PlantedFact(
        fact_id="F05",
        topic="tsdb_engine",
        user_turn="Для сховища часових рядів на тестовому сервері ми обрали рушій VictoriaMetrics.",
        assistant_turn=(
            "Добре, зафіксовано вибір інфраструктури: як сховище часових рядів на тестовому "
            "сервері обрано рушій VictoriaMetrics для збору телеметрії та побудови графіків."
        ),
        memory_text="Для сховища часових рядів на тестовому сервері обрано рушій VictoriaMetrics.",
        question="Який рушій обрано для сховища часових рядів на тестовому сервері?",
        expected_value="VictoriaMetrics",
    ),
    PlantedFact(
        fact_id="F06",
        topic="conference_city",
        user_turn=(
            "Осіння технічна конференція зі вбудованих систем відбудеться у місті Івано-Франківськ."
        ),
        assistant_turn=(
            "Відмітив у робочому плані: осіння технічна конференція зі вбудованих систем "
            "запланована в місті Івано-Франківськ. Повернуся до цього пункту при плануванні "
            "поїздки."
        ),
        memory_text="Осіння конференція зі вбудованих систем відбудеться у місті Івано-Франківськ.",
        question="У якому місті відбудеться осіння конференція зі вбудованих систем?",
        expected_value="Івано-Франківськ",
    ),
    PlantedFact(
        fact_id="F07",
        topic="irrigation_interval",
        user_turn="Насос автоматичного поливу теплиці вмикається з інтервалом 18 годин.",
        assistant_turn=(
            "Гаразд: розклад насоса автоматичного поливу теплиці виставлено на цикл кожні "
            "18 годин. За потреби нагадаю це значення перед налаштуванням контролера."
        ),
        memory_text="Насос автоматичного поливу теплиці вмикається з інтервалом 18 годин.",
        question="З яким інтервалом вмикається насос поливу теплиці?",
        expected_value="18 годин",
    ),
    PlantedFact(
        fact_id="F08",
        topic="editor_theme",
        user_turn="Тема оформлення мого редактора коду в майстерні називається Nordic-Slate.",
        assistant_turn=(
            "Зафіксовано: робоча тема оформлення редактора коду в майстерні має назву "
            "Nordic-Slate. Це допоможе зберегти однакову палітру під час оновлення профілю."
        ),
        memory_text="Тема оформлення редактора коду в майстерні називається Nordic-Slate.",
        question="Як називається тема оформлення редактора коду в майстерні?",
        expected_value="Nordic-Slate",
    ),
    PlantedFact(
        fact_id="F09",
        topic="cable_budget",
        user_turn="Місячний ліміт витрат на тестові кабелі й перехідники складає 4250 грн.",
        assistant_turn=(
            "Зрозуміло: місячний бюджетний ліміт витрат на тестові кабелі та перехідники "
            "встановлено на рівні 4250 грн для контролю дрібних закупівель."
        ),
        memory_text="Місячний ліміт витрат на тестові кабелі складає 4250 грн.",
        question="Який місячний ліміт витрат на тестові кабелі?",
        expected_value="4250 грн",
    ),
    PlantedFact(
        fact_id="F10",
        topic="calibration_monitor",
        user_turn="Основний калібрувальний монітор на робочому столі — модель Dell-U2723QE.",
        assistant_turn=(
            "Добре, запам'ятав конфігурацію робочого місця: основний калібрувальний монітор "
            "на робочому столі — це модель Dell-U2723QE з апаратною перевіркою кольорів."
        ),
        memory_text="Основний калібрувальний монітор на робочому столі — Dell-U2723QE.",
        question="Яка модель основного калібрувального монітора на робочому столі?",
        expected_value="Dell-U2723QE",
    ),
    PlantedFact(
        fact_id="F11",
        topic="uart_baud",
        user_turn=(
            "Швидкість послідовного порту UART для діагностики контролера становить 115200 бод."
        ),
        assistant_turn=(
            "Прийнято: для діагностики контролера через послідовний інтерфейс UART "
            "використовується швидкість 115200 бод. Це стандартна база для зняття логів "
            "завантаження."
        ),
        memory_text="Швидкість послідовного порту UART для діагностики контролера — 115200 бод.",
        question="Яка швидкість послідовного порту UART для діагностики контролера?",
        expected_value="115200",
    ),
    PlantedFact(
        fact_id="F12",
        topic="pressure_sensor",
        user_turn="Сенсорний модуль тиску в пневмосистемі має маркування Boreal-7.",
        assistant_turn=(
            "Зафіксував технічну довідку: сенсорний модуль тиску в пневмосистемі стенду "
            "використовує маркування Boreal-7. Посилатимусь на це позначення в інструкціях."
        ),
        memory_text="Сенсорний модуль тиску в пневмосистемі має маркування Boreal-7.",
        question="Яке маркування має сенсорний модуль тиску в пневмосистемі?",
        expected_value="Boreal-7",
    ),
)

_HEAD_TOPICS = (
    "організація робочих нотаток у чистому локальному каталозі",
    "перевірка рівнів гучності в тихій кімнаті перед тестуванням",
    "узгодження формату щоденного короткого звіту без зайвої води",
    "перегляд структури профілів налаштування без прив'язки до мережі",
    "перелік контрольних кроків перед запуском автономного режиму",
    "підготовка тестового журналу для перевірки повторних сценаріїв",
)

_TAIL_TOPICS = (
    "структура каталогів для архівних знімків стану без дублювання",
    "розподіл завдань на ранок і вечір у тихому режимі сповіщень",
    "перевірка читабельності коротких відповідей у термінальному інтерфейсі",
    "послідовність кроків при відновленні перерваного діалогу",
    "правила форматування дат у локальному журналі активності",
    "оцінка затримок між черговими репліками в тестовому прогоні",
    "контроль чистоти тимчасових директорій після завершення перевірки",
    "розмежування локальних нотаток та зовнішніх довідкових джерел",
    "пріоритети відображення статусу активних підзадач у консолі",
    "стабільність префіксу системного підказника при серії запитів",
    "поведінка парсера українських скорочень та чисел у підсумках",
    "підготовка списку регресійних тестів перед фіксацією гілки",
    "перевірка ізоляції тестової бази даних у тимчасовому просторі",
    "пороги спрацьовування фільтра шуму в спокійному середовищі",
    "зведення метрик тривалості відповіді за медіаною та дев'яносто п'ятим процентилем",
    "узгодження назв конфігураційних прапорців між модулями ядра",
    "оформлення технічних приміток українською мовою без сленгу",
    "реєстрація контрольних подій у журналі аудиту без сторонніх записів",
    "перевірка стабільності порядку інструментів у схемі моделі",
    "планування коротких перевірочних циклів для оцінки точності",
    "збереження цілісності локальних налаштувань під час перезапуску",
    "підготовка підсумкової таблиці експериментів для перегляду власником",
)


def build_synthetic_conversation(
    *, head_turns: int = 6, tail_turns: int = 22
) -> list[dict[str, Any]]:
    """Build a synthetic long owner conversation with 12 planted facts in the middle."""
    if head_turns < 1 or tail_turns < 1:
        raise ValueError("head_turns and tail_turns must be positive")
    turns: list[dict[str, Any]] = []
    for idx in range(head_turns):
        topic = _HEAD_TOPICS[idx % len(_HEAD_TOPICS)]
        turns.append(
            {
                "turn_key": f"head-{idx + 1:02d}",
                "fact_id": None,
                "user": f"Поточне обговорення #{idx + 1}: проаналізуймо {topic}.",
                "assistant": (
                    f"Зафіксував робочий контекст #{idx + 1} щодо теми «{topic}». "
                    "Цей крок слугує загальним вступним тлом для довгої розмови: "
                    "перевіряємо узгодженість термінології, порядок кроків та формат коротких "
                    "підсумків перед тим, як переходити до конкретних параметрів стенду."
                ),
            }
        )
    for fact in PLANTED_FACTS:
        turns.append(
            {
                "turn_key": f"fact-{fact.fact_id}",
                "fact_id": fact.fact_id,
                "user": fact.user_turn,
                "assistant": fact.assistant_turn,
            }
        )
    for idx in range(tail_turns):
        topic = _TAIL_TOPICS[idx % len(_TAIL_TOPICS)]
        turns.append(
            {
                "turn_key": f"tail-{idx + 1:02d}",
                "fact_id": None,
                "user": f"Наступне робоче питання #{idx + 1}: уточни деталі про {topic}.",
                "assistant": (
                    f"Розглянуто робочий пункт #{idx + 1} у межах теми «{topic}». "
                    "Усі проміжні спостереження впорядковані послідовно: параметри перевірено, "
                    "зайві повтори відсіяно, а поточні кроки задокументовано в стандартному "
                    "робочому форматі для подальшої звірки без залучення зовнішніх сервісів."
                ),
            }
        )
    return turns


def normalize_answer(text: str) -> str:
    """Normalize an answer string for exact-match comparison."""
    cleaned = normalize_uk(text or "")
    cleaned = cleaned.strip(" \t\r\n.,!?;:\"'«»()[]")
    return " ".join(cleaned.split()).lower()


def score_exact_match(reply: str, expected: str) -> float:
    """Return 1.0 when normalized reply matches expected exactly, else 0.0."""
    norm_expected = normalize_answer(expected)
    norm_reply = normalize_answer(reply)
    if not norm_expected or not norm_reply:
        return 0.0
    return 1.0 if norm_reply == norm_expected else 0.0


def score_contains_match(reply: str, expected: str) -> float:
    """Diagnostic token-boundary match when the reply embeds the exact planted value."""
    norm_expected = normalize_answer(expected)
    norm_reply = normalize_answer(reply)
    if not norm_expected or not norm_reply:
        return 0.0
    if normalize_answer(_NO_ANSWER_MARKER) in norm_reply:
        return 0.0
    pattern = r"(?<!\w)" + re.escape(norm_expected) + r"(?!\w)"
    return 1.0 if re.search(pattern, norm_reply) else 0.0


def _git_commit() -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return done.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def _seed_state(
    settings: Settings,
    state_dir: Path,
    turns: list[dict[str, Any]],
    *,
    seed_memories: bool,
) -> tuple[str, str]:
    rt = open_runtime(
        settings.model_copy(
            update={
                "state_dir": state_dir,
                "host_access": "none",
                "memory_enrichment": False,
            }
        )
    )
    try:
        actor = rt.control.create_actor(owner=True, consent=True)
        session_id = rt.control.create_session(actor.id)
        for turn in turns:
            messages = [
                {"id": str(uuid4()), "role": "user", "content": turn["user"]},
                {"id": str(uuid4()), "role": "assistant", "content": turn["assistant"]},
            ]
            rt.sessions.commit_turn(session_id, actor.id, str(uuid4()), messages, tags={})
        if seed_memories:
            for fact in PLANTED_FACTS:
                rt.memory.remember(
                    fact.memory_text,
                    actor,
                    kind="fact",
                    origin="explicit",
                    source="compaction_recall_seed",
                )
        return actor.id, session_id
    finally:
        rt.close()


async def _run_policy(
    settings: Settings,
    root: Path,
    turns: list[dict[str, Any]],
    *,
    policy: str,
    history_turns: int | None,
) -> dict[str, Any]:
    seed_memories = policy == "trim+memory"
    seed_dir = root / f"seed-{policy}"
    actor_id, session_id = _seed_state(settings, seed_dir, turns, seed_memories=seed_memories)

    per_question: list[dict[str, Any]] = []
    for fact in PLANTED_FACTS:
        q_dir = root / f"run-{policy}-{fact.fact_id}"
        shutil.copytree(seed_dir, q_dir)
        rt = open_runtime(
            settings.model_copy(
                update={
                    "state_dir": q_dir,
                    "host_access": "none",
                    "memory_enrichment": False,
                }
            )
        )
        try:
            rt.agent.clock = lambda: _BASE_DAY
            if history_turns is not None:
                rt.agent.history_turns = history_turns

            captured_context: list[str] = []
            original_chat = rt.agent.model.chat

            async def _spy_chat(
                admitted,
                *,
                on_delta=None,
                cancel=None,
                deadline=None,
                _orig=original_chat,
                _buf=captured_context,
            ):
                msgs = admitted.payload().get("messages") or []
                last_user = max(
                    (i for i, m in enumerate(msgs) if m.get("role") == "user"),
                    default=-1,
                )
                _buf.append(
                    "\n".join(m.get("content", "") for i, m in enumerate(msgs) if i != last_user)
                )
                return await _orig(admitted, on_delta=on_delta, cancel=cancel, deadline=deadline)

            rt.agent.model.chat = _spy_chat  # type: ignore[method-assign]
            task = rt.control.create_task(session_id)
            grant = rt.control.issue_grant(
                actor_id,
                session_id,
                ("eval.post_admission",),
                task_id=task,
                ttl_s=600,
            )
            prompt_text = f"{fact.question}{_QUESTION_SUFFIX}"
            result = await rt.agent.turn(
                session_id,
                grant,
                prompt_text,
                task_id=task,
                timeout_s=300,
                persist=False,
            )
            prompt_tokens = sum(
                int(m.get("prompt_eval_count", 0) or 0) for m in result.model_metrics
            )
            context_blob = "\n".join(captured_context)
            pattern = r"(?<!\w)" + re.escape(fact.expected_value) + r"(?!\w)"
            in_context = bool(re.search(pattern, context_blob, flags=re.IGNORECASE))
            exact = score_exact_match(result.content, fact.expected_value)
            relaxed = score_contains_match(result.content, fact.expected_value)
            per_question.append(
                {
                    "fact_id": fact.fact_id,
                    "topic": fact.topic,
                    "question": fact.question,
                    "expected": fact.expected_value,
                    "reply": result.content,
                    "state": result.state,
                    "score": exact,
                    "relaxed_score": relaxed,
                    "prompt_tokens": prompt_tokens,
                    "value_in_post_admission_context": in_context,
                }
            )
        finally:
            rt.close()

    token_counts = [item["prompt_tokens"] for item in per_question]
    correct = int(sum(item["score"] for item in per_question))
    relaxed_correct = int(sum(item["relaxed_score"] for item in per_question))
    total = len(per_question)
    return {
        "policy": policy,
        "total": total,
        "correct": correct,
        "recall": round(correct / total, 4) if total else 0.0,
        "relaxed_recall": round(relaxed_correct / total, 4) if total else 0.0,
        "prompt_tokens": sum(token_counts),
        "prompt_tokens_mean": round(statistics.mean(token_counts), 2) if token_counts else 0.0,
        "prompt_tokens_p50": round(statistics.median(token_counts), 2) if token_counts else 0.0,
        "per_question": per_question,
    }


async def measure_compaction_recall(
    settings: Settings,
    *,
    policies: tuple[str, ...] = POLICIES,
    head_turns: int = 6,
    tail_turns: int = 22,
    history_turns: int | None = None,
) -> dict[str, Any]:
    """Run compaction-recall across selected policies and return the JSON summary report."""
    for policy in policies:
        if policy not in POLICIES:
            raise ValueError(
                f"unsupported policy {policy!r}; supported policies are {POLICIES} "
                "('summary' is deferred until after Track G measurement)"
            )
    turns = build_synthetic_conversation(head_turns=head_turns, tail_turns=tail_turns)
    profile = ModelProfile(settings)
    policy_results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="b12-compaction-") as tmp:
        root = Path(tmp)
        for policy in policies:
            policy_results[policy] = await _run_policy(
                settings,
                root,
                turns,
                policy=policy,
                history_turns=history_turns,
            )

    return {
        "host": platform.node() or "unknown",
        "os": platform.platform(),
        "git_commit": _git_commit(),
        "model": settings.model,
        "model_digest": profile.spec.manifest_digest,
        "profile_revision": profile.spec.revision,
        "num_ctx": settings.num_ctx,
        "output_tokens": settings.output_tokens,
        "facts_count": len(PLANTED_FACTS),
        "conversation_turns": len(turns),
        "policies": policy_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model-profile", type=Path, required=True)
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--output-tokens", type=int, default=512)
    parser.add_argument("--head-turns", type=int, default=6)
    parser.add_argument("--tail-turns", type=int, default=22)
    parser.add_argument("--history-turns", type=int, default=None)
    parser.add_argument(
        "--policies",
        nargs="+",
        default=list(POLICIES),
        help="Policies to evaluate (only 'trim' and 'trim+memory' are implemented in H4)",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="b12-compaction-cfg-") as cfg_dir:
        settings = Settings(
            state_dir=Path(cfg_dir) / "state",
            model=args.model,
            ollama_url=args.ollama_url,
            model_profile=args.model_profile,
            tokenizer_dir=args.tokenizer_dir,
            num_ctx=args.num_ctx,
            output_tokens=args.output_tokens,
        )
        report = asyncio.run(
            measure_compaction_recall(
                settings,
                policies=tuple(args.policies),
                head_turns=args.head_turns,
                tail_turns=args.tail_turns,
                history_turns=args.history_turns,
            )
        )

    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
