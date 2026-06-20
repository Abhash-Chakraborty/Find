import pytest
from pydantic import ValidationError

from find_api.core.config import Settings


def test_remote_mode_requires_remote_ml_url():
    with pytest.raises(ValidationError, match="REMOTE_ML_URL"):
        Settings(ML_MODE="remote", REMOTE_ML_API_KEY="secret-token")


def test_remote_mode_requires_remote_ml_api_key():
    with pytest.raises(ValidationError, match="REMOTE_ML_API_KEY"):
        Settings(ML_MODE="remote", REMOTE_ML_URL="http://localhost:8000")


def test_remote_mode_rejects_whitespace_remote_ml_url():
    with pytest.raises(ValidationError, match="REMOTE_ML_URL"):
        Settings(
            ML_MODE="remote",
            REMOTE_ML_URL="   ",
            REMOTE_ML_API_KEY="secret-token",
        )


def test_remote_mode_rejects_whitespace_remote_ml_api_key():
    with pytest.raises(ValidationError, match="REMOTE_ML_API_KEY"):
        Settings(
            ML_MODE="remote",
            REMOTE_ML_URL="http://localhost:8000",
            REMOTE_ML_API_KEY="   ",
        )


def test_remote_mode_accepts_valid_remote_config():
    settings = Settings(
        ML_MODE="remote",
        REMOTE_ML_URL="http://localhost:8000",
        REMOTE_ML_API_KEY="secret-token",
    )

    assert settings.ML_MODE == "remote"
    assert settings.REMOTE_ML_URL == "http://localhost:8000"
    assert settings.REMOTE_ML_API_KEY == "secret-token"
