import datetime as dt
from pathlib import Path

import pytest

from model_pin_scanner.deprecations import load

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = dt.date(2026, 11, 21)


@pytest.fixture(scope="session")
def db():
    return load()


@pytest.fixture(scope="session")
def index(db):
    return db.index()
