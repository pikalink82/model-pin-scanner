import pytest

from conftest import FIXTURES
from model_pin_scanner.scanner import classify, find_in_text, normalize, scan


def models(text, index):
    return [m.model for m in find_in_text(text, index)]


@pytest.mark.parametrize(
    "line,expected",
    [
        ('model = "gpt-5-2025-08-07"', ["gpt-5-2025-08-07"]),
        ("OPENAI_MODEL=gpt-4.1-mini-2025-04-14", ["gpt-4.1-mini-2025-04-14"]),
        ("model: openai/gpt-4o-2024-08-06", ["gpt-4o-2024-08-06"]),
        ("ft:gpt-4o-2024-08-06:acme::abc123", ["gpt-4o-2024-08-06"]),
        ("claude-sonnet-4@20250514", ["claude-sonnet-4-20250514"]),
        ("anthropic.claude-3-7-sonnet-20250219-v1:0", ["claude-3-7-sonnet-20250219"]),
        ("us.anthropic.claude-opus-4-1-20250805-v1:0", ["claude-opus-4-1-20250805"]),
        ("models/gemini-2.0-flash-001", ["gemini-2.0-flash-001"]),
        ("Use o3-pro-2025-06-10.", ["o3-pro-2025-06-10"]),
        ("a=gpt-5-nano-2025-08-07,b=o3-2025-04-16", ["gpt-5-nano-2025-08-07", "o3-2025-04-16"]),
        ('{"model": "o3"}', ["o3"]),
    ],
)
def test_finds_model_ids(index, line, expected):
    assert models(line, index) == expected


@pytest.mark.parametrize(
    "line",
    [
        "algo3-2025-04-16",  # o3 snapshot inside a longer word
        "my_gpt-4o_backup",
        "my-gpt-5-2025-08-07",
        "GPT-4o is our favourite",  # prose, not a pin
        "The o3 approach is fine",  # bare o3 outside a string
        "claude-code and gemini-cli are tools",
        "photo3-2025-04-16.jpg",
        "x = 'gpt-5-2025-08-07'  # model-pin-scanner: ignore",
    ],
)
def test_ignores_false_positives(index, line):
    assert models(line, index) == []


def test_longer_snapshot_is_not_mistaken_for_known_one(index):
    (m,) = find_in_text('"gpt-5-2025-08-07-preview"', index)
    assert m.model == "gpt-5-2025-08-07-preview"
    assert m.deprecation is None


def test_mini_snapshot_does_not_match_base_entry(index):
    (m,) = find_in_text("gpt-4o-mini-2024-07-18", index)
    assert m.deprecation.id == "gpt-4o-mini-2024-07-18"


def test_alias_and_snapshot_classified(index):
    alias, snap = find_in_text("gpt-4o gpt-4o-2024-08-06", index)
    assert (alias.kind, alias.deprecation) == ("alias", None)
    assert snap.kind == "snapshot" and snap.deprecation is not None


@pytest.mark.parametrize(
    "model,kind",
    [
        ("gpt-5-2025-08-07", "snapshot"),
        ("claude-sonnet-4-20250514", "snapshot"),
        ("gemini-2.0-flash-001", "snapshot"),
        ("gpt-3.5-turbo-1106", "snapshot"),
        ("command-r-08-2024", "snapshot"),
        ("claude-3-7-sonnet-latest", "alias"),
        ("claude-sonnet-4-5", "alias"),
        ("gemini-2.5-flash", "alias"),
    ],
)
def test_classify(model, kind):
    assert classify(model) == kind


def test_normalize_strips_trailing_punctuation():
    assert normalize("gpt-4o-2024-08-06.") == "gpt-4o-2024-08-06"


def test_columns_are_one_based(index):
    (m,) = find_in_text("x\n  m = 'gpt-5-2025-08-07'", index, "f.py")
    assert (m.path, m.line, m.column) == ("f.py", 2, 8)


EXPECTED_SAMPLE = {
    ("app/llm.py", "gpt-5-2025-08-07"),
    ("app/llm.py", "o3-2025-04-16"),
    ("app/llm.py", "gpt-4o-2024-08-06"),
    ("config/models.yaml", "claude-sonnet-4-5-20250929"),
    ("config/models.yaml", "claude-sonnet-4-20250514"),
    ("config/models.yaml", "claude-3-7-sonnet-20250219"),
    ("config/models.yaml", "claude-opus-4-1-20250805"),
    ("config/models.yaml", "gpt-4.1-2025-04-14"),
    ("config/models.yaml", "gemini-2.5-flash"),
    (".env.example", "gpt-4.1-mini-2025-04-14"),
    (".env.example", "gemini-2.0-flash"),
    ("Dockerfile", "gpt-4o-mini-2024-07-18"),
    ("web/client.ts", "claude-opus-4-5"),
    ("infra/deploy.tf", "gpt-5-nano-2025-08-07"),
}


def test_scan_sample_repo(db):
    result = scan(FIXTURES / "sample_repo", db)
    flagged = {(m.path.split("sample_repo/")[-1], m.model) for m in result.matches if m.deprecation}
    assert flagged == EXPECTED_SAMPLE
    unknown = {m.model for m in result.matches if not m.deprecation}
    assert unknown == {"gpt-4o", "o3", "claude-haiku-4-5", "text-embedding-3-small", "gemini-3.5-flash"}
    # node_modules, Markdown and binary files are skipped by default.
    assert result.files_scanned == 6
    assert not any("node_modules" in m.path or m.path.endswith((".md", ".png", "blob.py")) for m in result.matches)


def test_scan_all_files_includes_markdown(db):
    result = scan(FIXTURES / "sample_repo", db, all_files=True)
    assert any(m.path.endswith("docs/notes.md") and m.model == "gpt-5-mini-2025-08-07" for m in result.matches)
    assert not any(m.path.endswith(("logo.png", "blob.py")) for m in result.matches)


def test_scan_excludes(db):
    result = scan(FIXTURES / "sample_repo", db, excludes=["config", "*.ts"])
    assert not any("config/" in m.path or m.path.endswith(".ts") for m in result.matches)
    assert any(m.path.endswith("app/llm.py") for m in result.matches)


def test_scan_relative_paths(db, monkeypatch):
    monkeypatch.chdir(FIXTURES / "sample_repo")
    result = scan(".", db)
    assert ("Dockerfile", "gpt-4o-mini-2024-07-18") in {(m.path, m.model) for m in result.matches}


def test_scan_single_file(db):
    target = FIXTURES / "sample_repo" / "Dockerfile"
    result = scan(target, db)
    assert result.files_scanned == 1
    assert result.matches[0].path == target.as_posix()


def test_scan_skips_given_paths(db, tmp_path):
    data = tmp_path / "deprecations.yaml"
    data.write_text("id: gpt-5-2025-08-07\n")
    (tmp_path / "app.py").write_text('m = "o3-2025-04-16"\n')
    result = scan(tmp_path, db, skip=[data])
    assert [m.model for m in result.matches] == ["o3-2025-04-16"]


def test_scan_missing_path(db, tmp_path):
    with pytest.raises(FileNotFoundError):
        scan(tmp_path / "nope", db)
