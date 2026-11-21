import datetime as dt
from pathlib import Path

import pytest

from model_pin_scanner.deprecations import DataFileError, parse

OPENAI_DEC_11 = [
    "gpt-5-2025-08-07",
    "gpt-5-mini-2025-08-07",
    "gpt-5-nano-2025-08-07",
    "gpt-5-pro-2025-10-06",
    "o3-2025-04-16",
    "o3-pro-2025-06-10",
]
OPENAI_JAN_14 = [
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20",
    "gpt-4o-mini-2024-07-18",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini-2025-04-14",
]

OFFICIAL_PAGES = {
    "openai": "https://platform.openai.com/docs/deprecations",
    "anthropic": "https://platform.claude.com/docs/en/about-claude/model-deprecations",
    "google": "https://ai.google.dev/gemini-api/docs/deprecations",
}


def test_bundled_file_loads(db):
    assert len(db.entries) >= 20
    assert db.last_reviewed == "2026-11-21"
    assert {e.provider for e in db.entries} == {"openai", "anthropic", "google"}


@pytest.mark.parametrize("model_id", OPENAI_DEC_11)
def test_openai_december_snapshots(index, model_id):
    assert index[model_id].shutdown_date == dt.date(2026, 12, 11)


@pytest.mark.parametrize("model_id", OPENAI_JAN_14)
def test_openai_january_snapshots(index, model_id):
    assert index[model_id].shutdown_date == dt.date(2027, 1, 14)


def test_every_entry_cites_its_providers_official_page(db):
    for e in db.entries:
        assert e.source_url == OFFICIAL_PAGES[e.provider], e.id


def test_unverified_entries_are_flagged_and_documented(db):
    decisions = (Path(__file__).parents[1] / "DECISIONS.md").read_text("utf-8")
    for e in db.entries:
        if not e.verified:
            assert f"`{e.id}`" in decisions, f"{e.id} is unverified but not listed in DECISIONS.md"


def test_aliases_resolve_to_snapshot(index):
    assert index["claude-sonnet-4-5"].id == "claude-sonnet-4-5-20250929"
    assert index["gemini-2.0-flash"].id == "gemini-2.0-flash-001"


def test_floating_openai_aliases_are_not_listed(index):
    # Only dated snapshots were announced; the floating aliases keep working.
    for alias in ("gpt-5", "gpt-5-mini", "gpt-4o", "gpt-4.1", "o3"):
        assert alias not in index


def test_days_remaining(index):
    assert index["gpt-5-2025-08-07"].days_remaining(dt.date(2026, 11, 21)) == 20


BASE = """
models:
  - id: m-1
    provider: openai
    shutdown_date: "2027-01-01"
    source_url: https://example.com/d
    verified: true
"""


def test_minimal_valid_file():
    db = parse(BASE)
    assert db.entries[0].replacement is None
    assert db.entries[0].aliases == ()


@pytest.mark.parametrize(
    "old,new,message",
    [
        ("    verified: true\n", "", "missing field"),
        ('"2027-01-01"', '"Jan 1"', "YYYY-MM-DD"),
        ("provider: openai", "provider: acme", "provider must be"),
        ("https://example.com/d", "http://example.com/d", "https URL"),
        ("verified: true", 'verified: "yes"', "true or false"),
    ],
)
def test_validation_errors(old, new, message):
    with pytest.raises(DataFileError, match=message):
        parse(BASE.replace(old, new))


def test_duplicate_alias_rejected():
    text = BASE + BASE.split("models:\n")[1].replace("id: m-1", "id: m-2\n    aliases: [M-1]")
    with pytest.raises(DataFileError, match="duplicate"):
        parse(text)


def test_not_a_mapping():
    with pytest.raises(DataFileError):
        parse("- just a list")
    with pytest.raises(DataFileError, match="invalid YAML"):
        parse("models: [")
