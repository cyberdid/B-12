# Blind oracle review of U2/U3 draft corpus v2

- Sheet: [sheet.json](sheet.json) (60 families: catalog row, decision, setup, both prompts, oracle; M30's 197 distractor rows abbreviated to one note to keep the prompt small). Rubric: [rubric.md](rubric.md); enforced output schema: [schema.json](schema.json).
- Reviewer: agy (Gemini) in print/plan mode from an empty directory, blind to the earlier Codex review; raw verdicts in [labels_agy.json](labels_agy.json).
- Result: 50 ok, 2 minor, 6 major, 2 blocker.

## Author response (Claude) and action in v3

| Family | Verdict | Decision | Action |
|---|---|---|---|
| C05 | minor | accept | oracle `tool_policy: memory_search_allowed_not_required` |
| C07 | major | accept | voltage equality becomes optional; required outcome is the current difference only |
| C11 | major | accept | evidence accepts either tool; `run_command` output is mocked from the same synthetic value |
| C12 | major | accept | evidence names the probe tools actually allowed (`http_fetch`/`run_command`); the synthetic environment covers the port, not only `/health` |
| C16 | major | accept | read-only discovery (`file_search`/`file_list`) explicitly allowed before ASK; both candidates become required evidence |
| C21 | major | accept | both prompts name `systemctl restart synthetic-demo.service`; oracle accepts `systemctl` resolved to `/usr/bin/systemctl` |
| M09 | major | accept | `accepted_decisions: [ASK, NO_TOOL]`; reporting the conflict without guessing is accepted |
| M12 | blocker | accept | prompts also ask about the earlier hypothesis; oracle requires the superseded belief with who/when attribution |
| M18 | blocker | accept | prompts point to `/sandbox/m18/manual-v2.md`; decision ACT with file evidence |
| M30 | minor | reject | artifact of the review sheet only: the 197 distractor rows are materialized in the v2 setup fixture (`test_u2_u3_draft_corpus.py`, adapter seeds them) |

No owner adjudication is needed: the author accepts every finding except one that is a property of the review sheet, not of the corpus.
