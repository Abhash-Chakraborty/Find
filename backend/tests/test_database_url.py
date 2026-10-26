"""DATABASE_URL keeps using psycopg2 under SQLAlchemy 2.1."""

import pytest
from sqlalchemy.engine import make_url

from find_api.core.config import Settings


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u:p@db:5432/find", "postgresql+psycopg2://u:p@db:5432/find"),
        ("postgres://u:p@db/find", "postgresql+psycopg2://u:p@db/find"),
        ("postgresql+psycopg2://u:p@db/find", "postgresql+psycopg2://u:p@db/find"),
        ("sqlite:///:memory:", "sqlite:///:memory:"),
    ],
)
def test_database_url_pins_the_psycopg2_driver(url, expected):
    assert Settings(DATABASE_URL=url).DATABASE_URL == expected


def test_default_url_resolves_to_an_installed_driver():
    # SQLAlchemy 2.1 maps a bare postgresql:// to psycopg, which isn't installed.
    dialect = make_url(Settings().DATABASE_URL).get_dialect()
    assert dialect.driver == "psycopg2"
