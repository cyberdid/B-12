# Evidence and reproducibility notes

The files below were inspected locally on 2026-11-08. Hashes identify the inspected files; the files are not included in this paper project and are not asserted to be publicly available. Review all raw traces for private data before any release.

- /home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task14-eval-2026-10-27-merged/metadata-ctx4096.json: SHA-256 248d70bee37caa2904b7f23bc8146147c6ef8d026a7e72150837558f947a4503
- /home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task14-eval-2026-10-27-merged/summary.json: SHA-256 b9c70a4a06c1906a93b25490d23477b00d875bd17add0f4c4c8fd83c0d22e284
- /home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task14-eval-2026-10-27-merged/latency-ctx4096.json: SHA-256 241aba8495b3d6b8bd61177f425e7ac3f898c38641c29923b6e1dee4c093b327
- /home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task4-calibration-2026-10-25-run3/metadata.json: SHA-256 80bf2651a1d7707a2c0311c8c4b6154b7f4c4f85c7fb84423bb81dfd13f3e4b5
- /home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task4-calibration-2026-10-25-run3/summary.json: SHA-256 3543520255020e204f72da50f8afc2c1eb7269b56a21e069bc98a4b2a9896e0c

The 4096 evaluation metadata pins commit 60a4c0b49b2fe5705fb0384b6b5f54f57880030e, Ollama 0.33.3, model alias b12-bolt-e4b:q4km, temperature 0, seed 42, and output limit 512. Summary reports 496/541 and 117/150 multi-step tool runs; one conversation run accounts for the nonuniform repeat count. The 8192 run has one repeat.

The eight-hour operational result is taken from the project log and operations topic: 8.007 active hours in four segments, not uninterrupted. Its original raw event file was not independently inspected for this draft.

No human evaluation, comparative model experiment, fresh GPU inference or live voice acceptance was conducted for these manuscripts. Author metadata and public artifact release remain for author review.
