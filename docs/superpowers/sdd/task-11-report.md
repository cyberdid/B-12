# Task 11 — goals, attention, initiative, reflection, preferences

Coordinator/implementer: Claude Code (Claude Opus 5.5), 26.10.2026. BASE `5045992`; commits `71fba28`, `3b47f39` (config test fix — 71fba28 briefly had 1 failing config test due to an ordering slip), `6032a15` (real-model test).

Modules: `attention.py` (AttentionPolicy), `goals.py` (GoalStore: goals/proposals/preferences), `reflection.py` (Reflector), `autonomy.py` (Scheduler, check_passes). Settings: timezone, quiet_start/end, initiative_hour_cap, initiative_cooldown_s, scheduler_tick_s. Purge store `goals` added (STORES now sessions, goals, active_turns, backups, provider_cache). API: /api/goals (+status), /api/attention, /api/proposals (+feedback). CLI: goals add/list/pause/resume/abandon, quiet on/off, stop on/off, autonomy [--reflect]. `b12 serve` runs Scheduler (disable: --no-autonomy).

Rulings:
- Nonurgent initiative = proposal delivery; quiet hours/mode block delivery, never direct replies; quiet ≠ owner stop (stop pauses background execution).
- Backoff: cooldown × 2^(consecutive ignored/dismissed), cap 4 h; engaged resets. Hour cap counts nonurgent delivered proposals in the last 60 min.
- Achieved only via trusted deterministic check (`file_contains` only for now) + live `goal_evidence` memory; model claims never complete goals. Goals created only by owner (API/CLI); guests 403.
- Reflection: JSON hypothesis citing offered live same-actor memories; foreign/invented IDs or non-JSON → rejected; deletion revision captured before the model call; reflection registered as actor active work so purge cancels it (fix after first GREEN: purge had waited 10 s on the reasoning lock and left provider_cache pending).
- Preferences append versions with reasons; purge redacts payload of versions whose evidence is forgotten, history keeps version/date.

Evidence: 6 unit attention + 11 integration autonomy + CLI/API tests; 10 mutations caught; full 404 passed / 2 skipped. Real Bolt run1 (`6032a15`, artifacts/task11-bolt-autonomy-2026-10-26-run1): goal experiment achieved 3/3 by independent file check in 1 background turn each; reflection recorded 3/3 with 2–3 cited evidence IDs, cautious grounded hypotheses.
Limits: only one trusted check kind; curiosity-candidate generation by the model is not implemented (goals come from owner); no learning claims beyond stored memories/reflections/preferences.
