# Recall fixes on a frontier model — 23.11.2026

Owner's order (23.11.2026): main tests on a frontier model, gemma4:12b on Colab for acceptance.
Model **gpt-6-luna** via `subscription_bridge` (`evals/unified/diagnostics/run_frontier.py`),
3 repeats × 2 prompt variants per family, runner from `.worktrees/eval-run` pinned per run.
Judges: Gemini (agy) + Opus 5.5 (agy), blind, combined with `combine_judges`; rates from
`consistent_verdicts` / `compare_arms` (bootstrap 95% CI). Record quirks of the bridge:
`model` reads `gemma4:12b`, `tokens_prompt` is 0 — runs are identified by directory tag.

## 1. Period recall — `recall_as_of`, set `asof-live-v1` (M97–M99, frozen `c234b0a`)

| Arm (runtime commit) | M97 (=M96, Oct address) | M98 (Sept supplier, replaced later) | M99 (10 Nov address) | Mean, Δ vs control [95% CI] |
|---|---|---|---|---|
| control, no flag (`c234b0a`) | 0.00 | 0.33 | 0.67 | 0.333 |
| `recall_as_of` v1 (`c234b0a`) | 1.00 | 0.50 | 0.67 | 0.722, +0.389 [0.0, 1.0] |
| `recall_as_of` v3 (`f43add9`) | **1.00** | **1.00** | **1.00** | **1.000, +0.667 [0.333, 1.0]** |

Two runtime defects found by the frontier runs and fixed (each with a regression test):
- `9bb6db8`: period recall filled slots term by term; six warehouse addresses matched by
  «адресою» crowded out the workshop address (M99-P2 «адреси майстерні немає»). Now ranked by
  the number of matched question words, then relevance.
- `f43add9`: a record valid in the asked period was offered as «замінено новішим записом»;
  luna refused to confirm it (M98-P2). Period records now read «чинне в запитаний період …;
  пізніша заміна стосується часу після нього».

An intermediate run on `9bb6db8` (`asof-live-v1-luna6fix-recall_as_of`) is kept: 14/16 items
pass, 1 FAIL + 1 NEEDS_OWNER, both the M98 defect fixed in `f43add9`.

## 2. Past-conversation recall — set `convrecall-live-v1` (M100–M102, frozen `ab322b1`)

Two blind oracle reviews (Codex ok×3; Gemini ok×2 + minor on M101, fixed before freezing).
Runtime commit `ab322b1`.

| Arm | M100 (=M93 setup) | M101 (bathroom vs kitchen paint) | M102 (no roof conversation) | Mean, Δ vs control [95% CI] |
|---|---|---|---|---|
| control, no flag | 0.00 | 0.00 | 1.00 (4/6 judged, 2 judge disputes open) | 0.0 (memory metric) |
| `session_search` (model calls `conversation_search`) | 0.83 | 0.50 | 1.00 | 0.778, +0.667 [0.5, 0.833] |
| **`recall_conversations`** (runtime offers matching past turns) | **1.00** | **1.00** | **1.00** | **1.000, +1.000 [1.0, 1.0]** |

No invention on M102 in any arm. The two open disputes are control-arm M102 items («не бачу
попередньої розмови»: Opus met/unclear, Gemini not_met); they do not affect the comparison.

## Limits

- n = 6 records per family per arm; the CIs are wide. Frontier results show the runtime
  path works; they are not the acceptance result. Acceptance: gemma4:12b on Colab (queued:
  `asof-live-v1` and `ports-live-v1`, control and `recall_as_of`, runtime `f43add9`).
- `recall_conversations` has no gemma run yet; the flag stays off until the owner decides.
- The evidence-packet path (`memory_scoped`, off) renders records itself and does not carry the
  period note.

## 3. Integrated set — `intg-live-v1` on gpt-6-luna, current defaults (runtime `f43add9`)

Owner's rule (23.11.2026): «якщо ми упираємось в обмеження моделі, то це нічого. якщо фронтір
показують норм результати - то так і будемо фіксувати». A family that passes on the frontier
model is recorded as working; a gemma4:12b shortfall on it is a model limit.

Judges: Gemini + Opus (Opus re-judged at ~16:45 after its agy quota reset; the earlier two-Gemini
result held). Open owner disputes: M87-P2 ×2 («системи на зв'язку» — fabricated system reading?).

| Family | gpt-6-luna | gemma4:12b (20.11, for reference) | Recorded as |
|---|---|---|---|
| M85–M87 (facts from memory) | 6/6 each | 0.83–1.00 | working |
| **M88** (style preference «коротко, без формул») | **6/6** | 0/6 (prefrules arm: see 20.11 report) | **working; gemma = model limit** |
| **C61 / INTG-05** (summarise 12 logs briefly) | **4/6** after the bridge fix | coverage 12/12, correct conclusion 1/6 | **working; gemma = model limit** |

C61 needed a fix of the test bench, not of Capri (`31d5cd5`): luna read the Codex CLI's own
environment (read-only sandbox, shell disabled) as runtime limits and answered «немає файлових
інструментів» in 6/6 records (`intg-live-v1-luna6-defaults`). After the bridge preamble names
that environment as the host's only: 4/6 records read all 12 logs with `file_read` and named
run 09 (19.6 V). The bridge request log shows all 13 runtime tools offered in every round; the
two misses are the model's choice (one still says «немає доступу» after `file_list`, one stops
after the first log). Earlier luna runs (sections 1–2) used the previous preamble; they
exercised memory/session tools, which luna called normally.

M92 (ports-live-v1): passed on gpt-6-luna in the 23.11 diagnostic
(`LUNA6_PORTS_DIAGNOSTIC_2026-11-23.md`) — recorded as working; gemma = model limit.

## 4. Acceptance on gemma4:12b (Colab L4, Ollama 0.33.3, revision `6114515d`), runtime `f43add9`

Orchestrator queue on Colab, 3 repeats, judges Codex + Gemini (no disputes).

| Set / family | control | `recall_as_of` |
|---|---|---|
| `asof-live-v1` M97 (=M96, answer oracle) | 0.00 | **1.00** |
| `asof-live-v1` M98 | 1.00 | 1.00 |
| `asof-live-v1` M99 | 1.00 | 1.00 |
| `asof-live-v1` mean | 0.667 | **1.000** (+0.333 [0.0, 1.0]) |
| `ports-live-v1` mean (M89–M96) | 0.167 | 0.167 (+0.000) |

`ports-live-v1` M96 shows no change only because its frozen oracle requires a
`memory_search(as_of=2026-10…)` call; by answer, gemma named the October address in **0/6**
records without the flag and **6/6** with it (that is why M97 exists). No other ports family
moved (M90 0.83, M91 0.50, rest 0.00 in both arms) — `recall_as_of` does not disturb answers
that name no period.

Verdict (owner's rule): `recall_as_of` works on the frontier model (1.00) and on gemma4:12b
(1.00 on M97–M99). Turning it on by default is the owner's decision.

Bench incident: the orchestrator hung 27 min after bootstrap (an embed-server subshell held the
SSH channel); fixed in `72da8e2`, not yet in `eval-run`.

## 5. Remaining flags (item 8) on gpt-6-luna, and `stable_prefix` (item 7) on gemma4:12b

New frozen sets, each after two blind reviews (Codex + Gemini; all findings fixed before any run):
`flags-live-v1` (M103–M106), `flags-live-v2` (M107–M108; runner seeds intents and skills since
`2b37a05`), `flags-live-v3` (M109–M110). Judges Gemini + Opus. 3 repeats × 2 variants.

| Flag | Family | control | flag on | Recorded as |
|---|---|---|---|---|
| `memory_ranking` | M103 recent fact among 8 older notes | 3/6 | **6/6** | **working** |
| `standing_intents` | M107 owner intent «перед фарбою — ґрунтовка CT 17» | 0/6 | **6/6** | **working** (whole-word keywords: «фарба» ≠ «фарбу») |
| `skills` | M108 owner XT60 procedure via `skill_view` | 0/6 | **6/6** | **working**; 3/6 replies voice it as «я паяю» instead of the owner's |
| `clarify_tool` | M106 ambiguous «видали старий бекап» | 0/6 | 0/6 | **no effect**: luna never calls `clarify`; it refuses («немає інструмента видалення») |
| `memory_grounding` | M109–M110 via post-turn review (`flags-live-v3`) | 12/12 | 10/12 | **nothing to fix on frontier**: the review stored nothing in both arms (`no_candidates`); the 2 misses are one reply type («мовою останнього повідомлення, без сигналу — українською», from the system prompt's language rule) that judges passed in the other arm — judge variance, not the flag |
| `stable_prefix` | ports-live-v1, Colab gemma4:12b, warm Ollama, A-B-A-B, 64 records/arm | TTFT P50 3562 ms, P95 4091 | P50 3570, P95 4336 | **no effect**; the old P95 gain was a cold first scenario |

M104/M105 in `flags-live-v1` (one-off request, inferred trait) pass in every arm: luna stored
nothing in the measured turn, so they do not discriminate `memory_grounding`; `flags-live-v3`
replaced them. M106 owner disputes: 3 items (does «найстаріший — backup-2026-10-01… підтверди»
count as asking?).

**Safety note (not worked on now, owner: functionality only):** in one `flags-live-v1`
`memory_ranking` record (r3 M106-P2) luna deleted `backup-2026-10-01.tar` with `run_command rm`
without asking; the other 23 M106 records did not delete.

Bench fixes found on the way: judge sheet now shows seeded intents/skills (`ba9be75`; before,
judges failed correct M107 replies as «invented owner note»); runner seeds intents/skills
(`2b37a05`); separate `.worktrees/eval-luna` (same package set as `eval-run`) so frontier and Colab
runs do not share a checkout.

Judges for `flags-live-v3`: two independent Gemini runs (Opus quota exhausted again after the
re-judge of section 3/5).

## 6. Owner decision, 23.11.2026

On by default (`ea834b5`): `recall_as_of`, `recall_conversations`, `memory_ranking`,
`standing_intents`, `skills`. Still off: `clarify_tool`, `stable_prefix`, `session_search`,
`memory_grounding`, `parallel_reads` (not measured), `goal_contract`, `schedules`, `wake_word`.
