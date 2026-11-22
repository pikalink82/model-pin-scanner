import json
import subprocess
import sys

from conftest import FIXTURES
from model_pin_scanner.cli import main

SAMPLE = str(FIXTURES / "sample_repo")
CLEAN = str(FIXTURES / "clean_repo")


def test_scan_fails_within_threshold(capsys):
    code = main(["scan", SAMPLE, "--today", "2026-11-21", "--fail-within", "30"])
    out = capsys.readouterr().out
    assert code == 1
    assert "10 fail the 30-day threshold" in out


def test_scan_passes_when_nothing_close(capsys):
    assert main(["scan", CLEAN, "--today", "2026-11-21", "--fail-within", "30"]) == 0
    assert main(["scan", SAMPLE, "--today", "2026-11-21"]) == 0  # no threshold given: report only


def test_scan_threshold_zero_only_fails_shut_down(capsys):
    assert main(["scan", SAMPLE, "--today", "2026-01-01", "--fail-within", "0"]) == 0
    assert main(["scan", SAMPLE, "--today", "2026-02-19", "--fail-within", "0"]) == 1


def test_scan_json_to_file(tmp_path):
    out = tmp_path / "pin-report.json"
    main(["scan", SAMPLE, "--today", "2026-11-21", "--format", "json", "-o", str(out)])
    doc = json.loads(out.read_text())
    assert doc["today"] == "2026-11-21"
    assert doc["summary"]["at_risk_references"] == 14


def test_scan_writes_annotations_to_stderr(capsys):
    main(["scan", SAMPLE, "--today", "2026-11-21", "--fail-within", "30", "--github-annotations"])
    err = capsys.readouterr().err
    assert err.count("::error ") == 10 and err.count("::warning ") == 4


def test_scan_custom_data_file(tmp_path, capsys):
    data = tmp_path / "deprecations.yaml"
    data.write_text(
        "models:\n  - id: claude-sonnet-5-5\n    provider: anthropic\n    shutdown_date: '2026-12-01'\n"
        "    source_url: https://example.com\n    verified: true\n"
    )
    assert main(["scan", CLEAN, "--data", str(data), "--today", "2026-11-21", "--fail-within", "30"]) == 1
    assert "claude-sonnet-5-5" in capsys.readouterr().out


def test_bad_data_file_exits_2(tmp_path, capsys):
    data = tmp_path / "bad.yaml"
    data.write_text("models: [{id: x}]")
    assert main(["scan", CLEAN, "--data", str(data)]) == 2
    assert "missing field" in capsys.readouterr().err


def test_missing_path_exits_2(capsys):
    assert main(["scan", "/definitely/not/here"]) == 2


def test_data_command(capsys):
    assert main(["data", "--today", "2026-11-21"]) == 0
    out = capsys.readouterr().out
    assert "47 entries, 15 verified" in out and "| `gpt-5-2025-08-07` | openai | 2026-12-11 | 20 |" in out
    assert main(["data", "--format", "json", "--today", "2026-11-21"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["days_remaining"] < 0


def regress_args(*extra):
    return [
        "regress",
        str(FIXTURES / "golden.yaml"),
        "--old",
        "gpt-4o-2024-08-06",
        "--new",
        "gpt-6-luna",
        "--provider",
        "mock",
        "--mock-responses",
        str(FIXTURES / "mock_responses.yaml"),
        *extra,
    ]


def test_regress_mock_end_to_end(capsys):
    assert main(regress_args()) == 0
    out = capsys.readouterr().out
    assert "1 identical, 1 minor, 1 changed, 1 regressed, 0 error" in out
    assert main(regress_args("--fail-on", "regressed")) == 1


def test_regress_json(tmp_path):
    out = tmp_path / "r.json"
    main(regress_args("--format", "json", "-o", str(out)))
    assert json.loads(out.read_text())["summary"]["regressed"] == 1


def test_regress_mock_needs_responses(capsys):
    args = ["regress", str(FIXTURES / "golden.yaml"), "--old", "a", "--new", "b", "--provider", "mock"]
    assert main(args) == 2
    assert "--mock-responses" in capsys.readouterr().err


def test_regress_real_provider_without_key(capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = ["regress", str(FIXTURES / "golden.yaml"), "--old", "gpt-4o-2024-08-06", "--new", "gpt-6-luna"]
    assert main(args) == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_module_entry_point():
    proc = subprocess.run([sys.executable, "-m", "model_pin_scanner", "--version"], capture_output=True, text=True)
    assert proc.returncode == 0 and "0.1.0" in proc.stdout
