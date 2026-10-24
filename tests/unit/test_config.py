import os
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from b12.config import Settings


@pytest.mark.parametrize("changes", [
    {"max_rounds": -1}, {"max_rounds": 0}, {"max_tool_calls": 0},
    {"num_ctx": 0}, {"output_tokens": 0}, {"num_ctx": 512, "output_tokens": 512},
    {"num_ctx": 512, "output_tokens": 513}, {"tool_timeout_s": -1},
    {"tool_timeout_s": float("inf")}, {"tool_timeout_s": float("nan")},
    {"model": " "}, {"host_access": "unvalidated"}, {"max_rounds": True},
])
def test_invalid_resource_limits_are_rejected(tmp_path, changes):
    with pytest.raises(ValidationError):
        Settings(state_dir=tmp_path, **changes)


@pytest.mark.parametrize("url", [
    "localhost:11434", "http://", "file:///tmp/ollama", "ftp://localhost:11434",
    "http://user:secret@localhost:11434", "http://localhost:99999", "http://local host:11434",
    "http://localhost:11434?token=secret", "http://localhost:11434#fragment",
    "http://localhost:11434\\evil", "http://[broken", "http://localhost:bad",
    "http://localhost:", "http://bad\x7fhost:11434",
])
def test_invalid_ollama_endpoint_is_rejected(tmp_path, url):
    with pytest.raises(ValidationError):
        Settings(state_dir=tmp_path, ollama_url=url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434", "http://[::1]:11434", "https://inference.example.org/ollama",
])
def test_explicit_http_endpoints_are_supported(tmp_path, url):
    assert Settings(state_dir=tmp_path, ollama_url=url).ollama_url == url


@pytest.mark.parametrize("path", ["", "relative/state", "/", "bad\0path"])
def test_invalid_state_paths_are_rejected(path):
    with pytest.raises(ValidationError):
        Settings(state_dir=path)


def test_state_path_may_not_be_an_existing_file(tmp_path):
    path = tmp_path / "file"
    path.write_text("unchanged")
    with pytest.raises(ValidationError):
        Settings(state_dir=path)
    assert path.read_text() == "unchanged"


def test_state_path_may_not_have_a_file_as_parent(tmp_path):
    parent = tmp_path / "file"
    parent.write_text("unchanged")
    with pytest.raises(ValidationError):
        Settings(state_dir=parent / "child")


def test_loading_settings_does_not_create_state_directory(tmp_path):
    path = tmp_path / "new" / "state"
    settings = Settings.from_env({"B12_STATE_DIR": str(path)})
    assert settings.state_dir == path
    assert not path.exists()


def test_environment_mapping_is_explicit_and_typed(tmp_path, monkeypatch):
    monkeypatch.setenv("B12_MODEL", "ambient-must-not-leak")
    environ = {
        "B12_STATE_DIR": str(tmp_path), "B12_MODEL": "test-model", "B12_NUM_CTX": "8192",
        "B12_OUTPUT_TOKENS": "1024", "B12_MAX_ROUNDS": "3", "B12_MAX_TOOL_CALLS": "6",
        "B12_TOOL_TIMEOUT_S": "2.5", "B12_HOST_ACCESS": "full",
        "B12_OLLAMA_URL": "https://inference.example.org",
    }
    settings = Settings.from_env(environ)
    assert settings.model_dump() == {
        "state_dir": tmp_path, "model": "test-model", "num_ctx": 8192,
        "output_tokens": 1024, "max_rounds": 3, "max_tool_calls": 6,
        "tool_timeout_s": 2.5, "host_access": "full",
        "ollama_url": "https://inference.example.org",
    }
    assert Settings.from_env({}).model != "ambient-must-not-leak"


def test_environment_defaults_use_xdg_state_home(tmp_path):
    settings = Settings.from_env({"XDG_STATE_HOME": str(tmp_path)})
    assert settings.state_dir == tmp_path / "b12"


def test_environment_none_uses_process_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("B12_STATE_DIR", str(tmp_path))
    assert Settings.from_env().state_dir == tmp_path


@pytest.mark.parametrize("value", ["", "true", "1.5", "NaN"])
def test_malformed_integer_environment_limit_is_rejected(value):
    with pytest.raises((ValidationError, ValueError)):
        Settings.from_env({"B12_MAX_ROUNDS": value})


def test_example_configuration_validates_without_creating_state():
    example = Path(__file__).resolve().parents[2] / "config.example.toml"
    data = tomllib.loads(example.read_text())
    existed = Path(data["state_dir"]).expanduser().exists()
    settings = Settings(**data)
    assert settings.output_tokens < settings.num_ctx
    assert settings.state_dir.exists() == existed
    assert os.path.isabs(settings.state_dir)
