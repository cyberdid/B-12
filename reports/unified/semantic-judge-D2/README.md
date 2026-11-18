# Arm D2 (narrow claimed-check) vs A0 on Bolt — 18.11.2026

- Same set; the runtime's claimed-check pattern widened only for document/file/log/system objects. Judges Codex + Gemini 334/353 unanimous; disputes resolved with the owner's precedents ([adjudication.json](adjudication.json)). Compared with aligned verdicts (`../consistent-verdicts-2026-11-18/`).
- Control 0.731 → 0.731 (±0); memory 0.406 → 0.412 (+0.006 [−0.028, +0.044]). **No false positives** (D's problem is gone), **but no gain**: in M50 the nudge fires and Bolt answers again "Я перевірив файл … за допомогою `file_read`" without any call — one nudge is not enough.
- Next: D3 = D2 + a runtime note (`annotate_unverified_claims`) when the claim persists after the nudge, so the user sees that the check did not happen.
