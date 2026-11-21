"""Check action.yml and run its scan step locally with bash, the way a runner would."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES

ROOT = Path(__file__).parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())


def step(step_id):
    return next(s for s in ACTION["runs"]["steps"] if s.get("id") == step_id)


def test_action_metadata():
    assert ACTION["runs"]["using"] == "composite"
    assert set(ACTION["inputs"]) == {
        "path", "fail-within-days", "warn-within-days", "data-file", "exclude", "all-files", "python-version"
    }  # fmt: skip
    assert ACTION["inputs"]["fail-within-days"]["default"] == "30"
    assert set(ACTION["outputs"]) == {"at-risk", "failing", "report-json"}


def test_no_expression_interpolation_inside_scripts():
    # Inputs reach scripts only through env, so a crafted input cannot inject shell code.
    for s in ACTION["runs"]["steps"]:
        if "run" in s:
            assert not re.search(r"\$\{\{", s["run"]), s.get("name")


def run_scan_step(tmp_path, **inputs):
    defaults = {
        "MPS_PATH": ".",
        "MPS_FAIL_WITHIN": "30",
        "MPS_WARN_WITHIN": "90",
        "MPS_DATA": "",
        "MPS_EXCLUDE": "",
        "MPS_ALL_FILES": "false",
    }
    defaults.update(inputs)
    summary, output = tmp_path / "summary.md", tmp_path / "output.txt"
    env = {
        **os.environ,
        **defaults,
        "MPS_PYTHON": sys.executable,
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_OUTPUT": str(output),
    }
    proc = subprocess.run(
        ["bash", "-e", "-c", step("scan")["run"]], env=env, capture_output=True, text=True, cwd=FIXTURES
    )
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines()) if output.exists() else {}
    return proc, summary.read_text() if summary.exists() else "", outputs


pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def test_scan_step_fails_on_sample_repo(tmp_path):
    proc, summary, outputs = run_scan_step(tmp_path, MPS_PATH="sample_repo")
    assert proc.returncode == 1
    assert "::error file=sample_repo/app/llm.py,line=7" in proc.stderr
    assert "Pinned LLM models shut down within 30 days" in proc.stdout
    assert "# Model pin scan" in summary
    assert outputs["failing"] != "0" and int(outputs["at-risk"]) >= int(outputs["failing"])
    assert json.loads(Path(outputs["report-json"]).read_text())["fail_within_days"] == 30


def test_scan_step_passes_on_clean_repo(tmp_path):
    proc, summary, outputs = run_scan_step(tmp_path, MPS_PATH="clean_repo")
    assert proc.returncode == 0, proc.stderr
    assert outputs == {"at-risk": "0", "failing": "0", "report-json": str(tmp_path / "model-pin-scanner/report.json")}


def test_scan_step_passes_inputs_through(tmp_path):
    proc, _, outputs = run_scan_step(
        tmp_path, MPS_PATH="sample_repo", MPS_EXCLUDE="sample_repo/config\n*.ts\n", MPS_ALL_FILES="true"
    )
    report = json.loads(Path(outputs["report-json"]).read_text())
    paths = {f["path"] for f in report["findings"]}
    assert not any("config/" in p or p.endswith(".ts") for p in paths)
    assert "sample_repo/docs/notes.md" in paths
