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


# Remote mode ships photo bytes and the bearer token off-box. Over plaintext
# HTTP to a non-local host both are readable in transit, so the config must
# fail closed rather than leave that to the operator to notice.


@pytest.mark.parametrize(
    "url",
    [
        "http://ml.example.com",
        "http://192.168.1.50:8000",
        "http://ml.example.com:8443/api",
    ],
)
def test_remote_mode_rejects_plaintext_http_to_remote_hosts(url):
    with pytest.raises(ValidationError, match="https"):
        Settings(ML_MODE="remote", REMOTE_ML_URL=url, REMOTE_ML_API_KEY="secret-token")


@pytest.mark.parametrize(
    "url",
    [
        "https://ml.example.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
    ],
)
def test_remote_mode_accepts_https_or_loopback(url):
    settings = Settings(
        ML_MODE="remote", REMOTE_ML_URL=url, REMOTE_ML_API_KEY="secret-token"
    )
    assert settings.REMOTE_ML_URL == url


def test_remote_mode_rejects_non_http_scheme():
    with pytest.raises(ValidationError, match="http"):
        Settings(
            ML_MODE="remote",
            REMOTE_ML_URL="ftp://ml.example.com",
            REMOTE_ML_API_KEY="secret-token",
        )


def test_non_remote_mode_ignores_remote_url_scheme():
    """The TLS rule must only bind when remote mode is actually in use."""
    settings = Settings(ML_MODE="full", REMOTE_ML_URL="http://ml.example.com")
    assert settings.ML_MODE == "full"
