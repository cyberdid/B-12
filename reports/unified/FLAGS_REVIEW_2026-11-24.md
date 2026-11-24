# Runtime flags — keep, remove or measure (proposal, 24.11.2026)

Owner, 24.11.2026: fewer mechanisms, more consolidation. Every runtime flag below with its
measured evidence and Claude's **proposal**. Nothing is changed until the owner decides; after a
decision, "make permanent" means deleting the flag and its off path, "remove" means deleting the
flag and its code.

## On by default

| Flag | Evidence | Proposal |
|---|---|---|
| `memory_temporal` | U4: +38.3 p.p. memory on gemma4:12b, +26.7 on Bolt; on since 19.11 | make permanent |
| `goals_in_context` | F arm: M53/M55 correct; on since 19.11 | make permanent |
| `recall_as_of` | frontier: asof-live-v1 fixed; on since 23.11 | make permanent |
| `recall_conversations` | M100 0/6→6/6, M101 0/6→6/6 on luna and gemma | make permanent |
| `memory_ranking` | M103 3/6→6/6 on luna; gemma 6/6 either way, no harm | make permanent |
| `standing_intents` | M107 0/6→6/6 on luna and gemma | make permanent |
| `skills` | M108 0/6→6/6; M111 5/6, M114 5/6 on luna | make permanent |
| `preference_rules` (+`preference_placement=query`) | P1 +54.2 p.p., no regression | make permanent |
| `memory_taint` | P4 +66.7..+83.3 p.p. | make permanent |
| `memory_review` | P3 M94 +83.3..+100 p.p. | make permanent |
| `memory_review_approval` | owner's choice (option C), not a measured feature | keep as a setting |
| `memory_enrichment`, `task_ledger`, `initiative_gate` | long-standing behaviour, no A/B planned | make permanent |
| `forget_requires_approval` | control/safety setting | keep as a setting |

## Off by default

| Flag | Evidence | Proposal |
|---|---|---|
| `skill_review` | new: luna M115 6/6, M116 5/6, none for fact/web 12/12; gemma see SKILLS_LEARN report | **turn on** after the gemma judges |
| `memory_as_of` | P5 M96 0/6→0/6 (0.0 p.p.); superseded by `recall_as_of` | remove |
| `annotate_unverified_claims` (D3) | neutral; M50 not fixed; the model answers the note as if the user wrote it | remove |
| `clarify_tool` | no effect: luna never calls `clarify`, gemma refuses (M106 0/6 both arms) | remove |
| `stable_prefix` | no TTFT effect (P50 3562 vs 3570 ms); the old gain was a cold start | remove |
| `session_search` | overlaps `recall_conversations` (which fixed recall); its own disputes M90/M91 unresolved | remove |
| `parallel_reads` | never isolated; small-model benefit unlikely | remove |
| `verify_writes` | only measured inside the F arm with two other flags | measure alone once on luna, else remove |
| `memory_grounding` | frontier: nothing to fix; gemma stored an inferred trait 1/6 (M105) — a small-model issue | measure on gemma (M105, M109, M110), then decide |
| `memory_scoped` (ADR-016) | U5 benchmark never run; set still DRAFT | decide whether U5 is still wanted; if not, remove |
| `goal_contract`, `schedules` | features drafted (ADR-019, ADR-022), not decided | feature decision, not cleanup |
| `wake_word` | deferred by the owner 22.11.2026 | keep off |

## Effect

If accepted: 13 flags become permanent code, 6 flags and their code are removed, 3 get one more
measurement. Eval arms that toggled removed or permanent flags stay readable as history; new runs
use the standing regression set (`regression-gemma-v1`) as the guard.
