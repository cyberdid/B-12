"""The long-horizon driver must not flag its own bookkeeping as leaked payload."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_driver():
    spec = importlib.util.spec_from_file_location("daily_check", ROOT / "scripts/daily_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_seed_then_check_inside_state_dir_passes_and_detects_real_leaks(
    scripted_ollama, tmp_path
):
    from b12.runtime import open_runtime

    driver = load_driver()
    _, settings = scripted_ollama
    settings = settings.model_copy(update={"state_dir": tmp_path / "state"})
    runtime = open_runtime(settings)
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        runtime.control.set_meta("owner_actor", actor.id)
        out = settings.state_dir / "long_horizon"  # inside the scanned state, as in real use
        out.mkdir()
        await driver.seed(runtime, out)
        record = await driver.check(runtime, out)
        assert record["ok"] and record["forgotten_bytes_found_in"] == []
        # A genuine leak elsewhere in the state is still reported.
        (settings.state_dir / "stray.txt").write_text("ЗЕЛЕНИЙЛИСТОПАД")
        leaked = await driver.check(runtime, out)
        assert not leaked["ok"] and leaked["forgotten_bytes_found_in"] == ["stray.txt"]
    finally:
        runtime.close()
