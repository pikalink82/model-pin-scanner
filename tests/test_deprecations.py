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
    assert db.last_reviewed == "2026-11-22"
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
    assert index["gpt-5"].id == "gpt-5-2025-08-07"
    assert index["o3"].id == "o3-2025-04-16"


def test_openai_aliases_follow_the_official_page(index):
    # The page retires these aliases together with their snapshots ...
    for alias in ("gpt-5", "gpt-5-mini", "gpt-5-nano", "o3", "gpt-4", "gpt-3.5-turbo", "o4-mini"):
        assert alias in index, alias
    assert index["gpt-4"].shutdown_date == dt.date(2026, 10, 23)
    # ... but lists only the GPT-4o and GPT-4.1 snapshots, so these aliases keep working.
    for alias in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"):
        assert alias not in index, alias


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


@pytest.mark.parametrize(
    ("pin", "entry_id"),
    [
        ("claude-3-opus-20240229", "claude-3-opus-20240229"),
        ("claude-3-5-sonnet-latest", "claude-3-5-sonnet-20241022"),
        ("claude-2.1", "claude-2.1"),
        ("gpt-4-32k", "gpt-4-32k"),
        ("gpt-4.5-preview-2025-02-27", "gpt-4.5-preview"),
        ("o1-preview-2024-09-12", "o1-preview"),
        ("gemini-1.5-flash", "gemini-1.5-flash-002"),
    ],
)
def test_long_retired_models_are_known_and_shut_down(index, pin, entry_id):
    entry = index[pin]
    assert entry.id == entry_id
    assert entry.days_remaining(dt.date(2026, 11, 22)) < 0


SDK_TABLE = (
    "https://github.com/anthropics/anthropic-sdk-python/blob/"
    "8baaef1c4d23b2e4861d05da0dca65252e879eb8/src/anthropic/resources/messages/messages.py#L71-L92"
)


def test_entries_come_from_the_official_pages(db, index):
    unverified = {e.id for e in db.entries if not e.verified}
    assert unverified == {
        "gemini-1.5-pro-002",
        "gemini-1.5-flash-002",
        "gemini-1.5-flash-8b-001",
        "gemini-1.5-pro-001",
        "gemini-1.5-flash-001",
    }
    # Only the two Claude 1 100k variants, missing from the docs page, lean on the SDK table.
    assert {e.id for e in db.entries if e.verified_by} == {"claude-1.3-100k", "claude-instant-1.1-100k"}
    assert all(e.verified_by == SDK_TABLE for e in db.entries if e.verified_by)
    # From Anthropic's page on 2026-11-22: Opus 4.1 is retired, Opus 4.5 is active, and
    # Mythos Preview is deprecated with no retirement date yet.
    assert index["claude-opus-4-1-20250805"].shutdown_date == dt.date(2026, 8, 5)
    assert "claude-opus-4-5-20251101" not in index and "claude-mythos-preview" not in index
    # From Google's page: the 2.5 models shut down on 2026-12-01, not in October.
    assert index["gemini-2.5-pro"].shutdown_date == dt.date(2026, 12, 1)


def test_verified_by_needs_a_verified_https_entry():
    from model_pin_scanner.deprecations import DataFileError, parse

    entry = """
models:
  - id: m-1
    provider: anthropic
    shutdown_date: "2027-01-01"
    source_url: https://example.com/d
    verified: {verified}
    verified_by: {url}
"""
    assert parse(entry.format(verified="true", url="https://example.com/sdk")).entries[0].verified_by
    with pytest.raises(DataFileError, match="only allowed on a verified entry"):
        parse(entry.format(verified="false", url="https://example.com/sdk"))
    with pytest.raises(DataFileError, match="https URL"):
        parse(entry.format(verified="true", url="http://example.com/sdk"))
