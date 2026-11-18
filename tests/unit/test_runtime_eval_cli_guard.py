import sys

import pytest


def test_single_scenario_runtime_cli_refuses_to_run_outside_sandbox(monkeypatch, tmp_path):
    from evals.capri_comprehensive.runners.runner import main

    monkeypatch.delenv("B12_EVAL_SANDBOX", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "scenario.yaml",
            "--runtime-dir",
            str(tmp_path / "runtime"),
        ],
    )

    with pytest.raises(SystemExit, match="refusing to run host tools outside the sandbox"):
        main()
