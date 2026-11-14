"""TTFT and prompt-cache reuse over multi-turn sessions with changing recalled memories (Bolt)."""
import asyncio, json, os, statistics, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
from evals.capri_comprehensive.runners.live_components import _bolt_settings
from b12.runtime import open_runtime

MEMORIES = [
    "Власник налаштував Neovim для проєкту B-12.", "На стенді B-12 замінили інтерфейсний кабель на екранований.",
    "Власник п'є каву без цукру.", "Датчик струму CURR_01 від'єднався по USB 8 листопада.",
    "Власник планує заміну батареї на стенді.", "Улюблений дистрибутив власника — Ubuntu 24.04.",
    "Шина I2C мала перешкоди живлення.", "Власник живе у Львові біля Стрийського парку.",
]
TURNS = ["Привіт.", "Який редактор я налаштував?", "Що там з кабелем на стенді?", "Яку каву я п'ю?",
         "Що сталося з датчиком струму?", "Що я планую зробити з батареєю?", "А де я живу?"]

async def main(label):
    base = Path(tempfile.mkdtemp())
    s = _bolt_settings(base / "state").model_copy(update={"num_ctx": 8192, "output_tokens": 1024,
                                                          "quiet_start": "00:00", "quiet_end": "00:00"})
    rt = open_runtime(s)
    actor = rt.control.create_actor(owner=True, consent=True)
    for m in MEMORIES:
        rt.memory.remember(m, actor)
    caps = ("memory.read", "time.read")
    rows = []
    for rep in range(3):
        sess = rt.control.create_session(actor.id)
        for i, text in enumerate(TURNS):
            task = rt.control.create_task(sess)
            grant = rt.control.issue_grant(actor.id, sess, caps, task_id=task, ttl_s=900)
            r = await rt.agent.turn(sess, grant, text, task_id=task, timeout_s=300)
            m = r.model_metrics[0] if r.model_metrics else {}
            rows.append({"rep": rep, "turn": i, "ttft": m.get("ttft_s"), "prompt": m.get("prompt_eval_count"),
                         "cached": m.get("prompt_eval_cached_count"), "prefill_s": (m.get("prompt_eval_duration") or 0) / 1e9,
                         "load_s": (m.get("load_duration") or 0) / 1e9, "recalled": len(r.evidence_ids), "state": r.state})
    rt.close()
    warm = [r for r in rows if r["turn"] > 0 and r["ttft"]]
    med = lambda k: round(statistics.median(r[k] for r in warm if r[k] is not None), 3)
    out = {"label": label, "n": len(warm), "ttft_median": med("ttft"), "ttft_max": round(max(r["ttft"] for r in warm), 3),
           "prompt_median": med("prompt"), "cached_median": med("cached"), "prefill_median": med("prefill_s"),
           "load_median": med("load_s"), "states": sorted({r["state"] for r in rows})}
    print(json.dumps(out, ensure_ascii=False))
    Path(os.environ["BENCH_OUT"]).write_text(json.dumps({"summary": out, "rows": rows}, ensure_ascii=False, indent=1))

asyncio.run(main(sys.argv[1]))
