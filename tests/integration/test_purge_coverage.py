"""Global purge must reach every store that holds the owner's data, including voice biometrics."""


async def test_runtime_wires_the_speaker_store_into_the_purge_coordinator(
    scripted_ollama, tmp_path
):
    from b12.runtime import open_runtime

    _, base = scripted_ollama
    settings = base.model_copy(update={"state_dir": tmp_path / "state"})
    runtime = open_runtime(settings)
    try:
        assert runtime.purge.speakers is not None
        assert runtime.purge.speakers.path == settings.state_dir / "voice" / "speakers.sqlite3"
    finally:
        runtime.close()
