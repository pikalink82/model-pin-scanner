import json

import pytest
import yaml

from conftest import FIXTURES
from model_pin_scanner.providers import MockProvider
from model_pin_scanner.regress import (
    CHANGED,
    ERROR,
    IDENTICAL,
    MINOR,
    REGRESSED,
    GoldenFileError,
    GoldenPrompt,
    Side,
    _fence,
    compare,
    load_golden,
    regress_to_json,
    regress_to_markdown,
    run_regression,
    should_fail,
)


def fixture_report(threshold=0.9):
    prompts = load_golden(FIXTURES / "golden.yaml")
    mock = MockProvider(yaml.safe_load((FIXTURES / "mock_responses.yaml").read_text())["models"])
    return run_regression(prompts, "gpt-4o-2024-08-06", "gpt-6-luna", mock, mock, threshold)


def test_load_golden_yaml():
    prompts = load_golden(FIXTURES / "golden.yaml")
    assert [p.id for p in prompts] == ["refund-policy", "hours", "card-message", "delivery-zip"]
    assert prompts[0].system.startswith("You are a concise")
    assert prompts[1].expect_contains == ("10 AM",)
    assert prompts[2].max_tokens == 64


def test_load_golden_jsonl(tmp_path):
    f = tmp_path / "g.jsonl"
    f.write_text('{"id": "a", "prompt": "x"}\n\n{"id": "b", "prompt": "y", "system": "s"}\n')
    prompts = load_golden(f)
    assert [(p.id, p.system) for p in prompts] == [("a", None), ("b", "s")]


@pytest.mark.parametrize(
    "content,message",
    [
        ("prompts: []", "no prompts"),
        ("prompts: [{id: a}]", "'prompt'"),
        ("prompts: [{prompt: x}]", "'id'"),
        ("prompts: [{id: a, prompt: x}, {id: a, prompt: y}]", "duplicate"),
        ("prompts: [{id: a, prompt: x, max_tokens: 0}]", "max_tokens"),
        ("prompts: [{id: a, prompt: x, expect_contains: 3}]", "expect_contains"),
        ("hello: 1", "'prompts' list"),
    ],
)
def test_golden_errors(tmp_path, content, message):
    f = tmp_path / "g.yaml"
    f.write_text(content)
    with pytest.raises(GoldenFileError, match=message):
        load_golden(f)


def test_fixture_run_statuses():
    report = fixture_report()
    by_id = {r.prompt.id: r for r in report.results}
    assert by_id["hours"].status == IDENTICAL
    assert by_id["card-message"].status == MINOR
    assert by_id["refund-policy"].status == REGRESSED
    assert set(by_id["refund-policy"].lost_expectations) == {"refund", "photo"}
    assert by_id["delivery-zip"].status == CHANGED
    assert report.count(IDENTICAL) == 1


def test_whitespace_only_change_is_identical():
    p = GoldenPrompt("a", "x")
    r = compare(p, Side("one  two\n", None), Side("one two", None), 0.9, "old", "new")
    assert r.status == IDENTICAL and r.similarity == 1.0


def test_provider_error_becomes_error_status():
    mock = MockProvider({"old": {"a": "fine"}})
    report = run_regression([GoldenPrompt("a", "x")], "old", "new", mock, mock)
    (r,) = report.results
    assert r.status == ERROR and "no responses for model new" in r.new.error


def test_should_fail():
    report = fixture_report()
    assert not should_fail(report, "never")
    assert should_fail(report, "regressed")
    assert should_fail(report, "changed")
    ok = fixture_report(threshold=0.0)
    assert should_fail(ok, "regressed")  # still regressed: lost "refund" and "photo"
    mock = MockProvider({"a": {"p": "same"}, "b": {"p": "same"}})
    clean = run_regression([GoldenPrompt("p", "x")], "a", "b", mock, mock)
    assert not should_fail(clean, "changed")


def test_threshold_validated():
    with pytest.raises(ValueError):
        run_regression([], "a", "b", MockProvider({}), MockProvider({}), threshold=1.5)


def test_markdown_and_json_output():
    report = fixture_report()
    md = regress_to_markdown(report)
    assert "# Regression: `gpt-4o-2024-08-06` -> `gpt-6-luna`" in md
    assert "| `refund-policy` | regressed |" in md
    assert "```diff" in md
    assert (
        "\n-Yes, we offer a full refund for wilted roses. Please send a photo within 24 hours of delivery.\n+We" in md
    )
    assert "## `hours`" not in md  # identical prompts get no detail section
    doc = json.loads(regress_to_json(report))
    assert doc["summary"] == {"identical": 1, "minor": 1, "changed": 1, "regressed": 1, "error": 0}
    assert doc["results"][0]["new"]["expectations_missed"] == ["refund", "photo"]


def test_fence_outgrows_backticks_in_output():
    assert _fence("plain") == "```"
    assert _fence("has ```` inside") == "`````"
