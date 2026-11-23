from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def test_production_refuses_debug_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", debug=True, _env_file=None)


def test_unknown_environment_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="prod", _env_file=None)  # type: ignore[arg-type]


def test_prefixed_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PFA_DEBUG", "true")
    assert Settings(_env_file=None).debug is True


def test_unprefixed_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    # Other tools set generic names such as DEBUG; they must not change this app.
    monkeypatch.delenv("PFA_DEBUG", raising=False)
    monkeypatch.setenv("DEBUG", "true")
    assert Settings(_env_file=None).debug is False


def test_every_variable_in_env_example_is_a_real_setting() -> None:
    """Stops .env.example drifting away from the code (declared but silently ignored)."""
    names = [
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert names, "the example file should not be empty"
    for name in names:
        assert name.startswith("PFA_"), f"{name} is missing the PFA_ prefix"
        assert name.removeprefix("PFA_").lower() in Settings.model_fields, f"{name} is not used"
