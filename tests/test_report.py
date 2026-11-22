import json

import pytest

from conftest import FIXTURES, TODAY
from model_pin_scanner.report import (
    CRITICAL,
    OK,
    SHUT_DOWN,
    WARNING,
    build_report,
    status_for,
    to_github_annotations,
    to_json,
    to_markdown,
)
from model_pin_scanner.scanner import ScanResult, find_in_text, scan


@pytest.mark.parametrize(
    "days,fail,status",
    [
        (-5, None, SHUT_DOWN),
        (0, 30, SHUT_DOWN),
        (1, 30, CRITICAL),
        (30, 30, CRITICAL),
        (31, 30, WARNING),
        (90, None, WARNING),
        (91, None, OK),
        (100, 120, CRITICAL),
    ],
)
def test_status_for(days, fail, status):
    assert status_for(days, fail, warn_within=90) == status


def report_for(text, db, fail_within=None):
    return build_report(ScanResult(1, tuple(find_in_text(text, db.index(), "f.py"))), db, TODAY, fail_within)


def test_findings_sorted_by_urgency_and_failing(db):
    r = report_for("gpt-4o-2024-08-06 gpt-5-2025-08-07 claude-3-7-sonnet-20250219 gpt-4o", db, fail_within=30)
    assert [f.match.model for f in r.findings] == [
        "claude-3-7-sonnet-20250219",
        "gpt-5-2025-08-07",
        "gpt-4o-2024-08-06",
    ]
    assert [f.days_remaining for f in r.findings] == [-275, 20, 54]
    assert {f.match.model for f in r.failing} == {"claude-3-7-sonnet-20250219", "gpt-5-2025-08-07"}
    assert [m.model for m in r.unknown] == ["gpt-4o"]


def test_no_threshold_means_nothing_fails(db):
    assert report_for("claude-3-7-sonnet-20250219", db).failing == ()


def test_json_report_shape(db):
    report = build_report(scan(FIXTURES / "sample_repo", db), db, TODAY, fail_within=30)
    doc = json.loads(to_json(report))
    assert doc["summary"]["files_scanned"] == 6
    assert doc["summary"]["at_risk_references"] == 15
    assert doc["summary"]["failing_references"] == 11
    assert doc["summary"]["unverified_references"] == 0
    assert doc["summary"]["by_status"] == {"shut_down": 4, "critical": 7, "warning": 4, "ok": 0}
    first = doc["findings"][0]
    assert set(first) >= {"model", "path", "line", "shutdown_date", "days_remaining", "replacement", "source_url"}
    gpt5 = next(f for f in doc["findings"] if f["model"] == "gpt-5-2025-08-07")
    assert gpt5["days_remaining"] == 20 and gpt5["status"] == "critical" and gpt5["verified"] is True
    assert {i["model"] for i in doc["other_model_ids"]} >= {"gpt-4o"}


def test_markdown_report(db):
    md = to_markdown(report_for("anthropic.claude-3-7-sonnet-20250219-v1:0 gpt-5-mini-2025-08-07", db, 30))
    assert "| SHUT DOWN | `claude-3-7-sonnet-20250219-v1:0` (= `claude-3-7-sonnet-20250219`) | -275 |" in md
    assert "| CRITICAL | `gpt-5-mini-2025-08-07` | 20 | 2026-12-11 | gpt-6.1-terra |" in md
    assert "2 fail the 30-day threshold" in md
    assert "[yes](https://platform.openai.com/docs/deprecations)" in md


def test_markdown_marks_unverified_entries(db):
    md = to_markdown(report_for("gemini-1.5-flash", db, 30))
    assert "[no](https://ai.google.dev/gemini-api/docs/deprecations)" in md
    assert "Check the linked provider page before acting." in md


def test_markdown_when_clean(db):
    md = to_markdown(report_for("claude-sonnet-5-5", db))
    assert "No pinned models with a known shutdown date." in md
    assert "`claude-sonnet-5-5`" in md


def test_github_annotations(db):
    out = to_github_annotations(report_for("gpt-5-2025-08-07 gpt-4o-2024-08-06", db, fail_within=30))
    lines = out.splitlines()
    assert lines[0].startswith("::error file=f.py,line=1,col=1,title=Pinned model gpt-5-2025-08-07::")
    assert "shuts down in 20 days" in lines[0] and "gpt-6.1-sol" in lines[0]
    assert lines[1].startswith("::warning file=f.py,line=1,col=18,")


def test_github_annotation_escaping(db):
    r = build_report(ScanResult(1, tuple(find_in_text("gpt-5-2025-08-07", db.index(), "a,b:c%.py"))), db, TODAY, 30)
    assert "file=a%2Cb%3Ac%25.py" in to_github_annotations(r)
