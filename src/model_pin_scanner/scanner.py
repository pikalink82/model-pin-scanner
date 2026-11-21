"""Find LLM model IDs in a directory tree."""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .deprecations import Deprecation, DeprecationDB

IGNORE_MARKER = "model-pin-scanner: ignore"
MAX_FILE_BYTES = 2_000_000

DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "dist",
        "build",
        "site-packages",
        ".next",
        ".nuxt",
        "target",
        "vendor",
        ".terraform",
        ".idea",
        ".vscode",
    }
)

TEXT_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".ipynb",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".vue",
        ".svelte",
        ".go",
        ".rb",
        ".java",
        ".kt",
        ".kts",
        ".rs",
        ".cs",
        ".php",
        ".swift",
        ".scala",
        ".ex",
        ".exs",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".yaml",
        ".yml",
        ".json",
        ".jsonc",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".properties",
        ".tf",
        ".tfvars",
        ".hcl",
        ".sql",
        ".xml",
        ".gradle",
        ".r",
        ".lua",
        ".dart",
    }
)
TEXT_FILENAMES = frozenset({"dockerfile", "containerfile", "makefile", "procfile", "justfile"})

# Lowercase only: real model IDs are lowercase, while prose ("GPT-4o is great") is not a pin.
_CORE = (
    r"gpt-\d[a-z0-9.\-]*"
    r"|chatgpt-4o-latest"
    r"|o[1-9](?:-(?:mini|pro|preview|deep-research))*(?:-\d{4}-\d{2}-\d{2})?"
    r"|(?:text-embedding|dall-e|whisper|tts)-[a-z0-9][a-z0-9.\-]*"
    r"|claude-(?:\d|instant|opus|sonnet|haiku)[a-z0-9.\-]*(?:@\d{8})?(?::\d+)?"
    r"|gemini-\d[a-z0-9.\-]*"
    r"|(?:mistral-(?:large|medium|small|tiny|saber)|codestral|pixtral|ministral)[a-z0-9.\-]*"
    r"|command-r(?:-plus)?(?:-\d{2}-\d{4})?"
    r"|deepseek-(?:chat|reasoner|v\d|r\d)[a-z0-9.\-]*"
    r"|grok-\d[a-z0-9.\-]*"
)
# Not preceded by a letter, digit, underscore or hyphen, so "algo3-..." or "my-gpt-4o" never match.
# "/" and "." are allowed before the ID: "openai/gpt-4o", "anthropic.claude-...", "us.anthropic.claude-...".
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_\-])(?:" + _CORE + r")(?![A-Za-z0-9_\-])")

_SNAPSHOT_RE = re.compile(r"(?:-\d{4}-\d{2}-\d{2}|-\d{8}|-\d{3}|-\d{2}-\d{4}|-\d{4})$")
_BEDROCK_SUFFIX_RE = re.compile(r"-v\d+(?::\d+)?$")
_BARE_O_SERIES_RE = re.compile(r"^o\d$")
_QUOTES = "\"'`"


@dataclass(frozen=True)
class Match:
    path: str  # relative, POSIX separators
    line: int  # 1-based
    column: int  # 1-based
    text: str  # as written in the file
    model: str  # normalized ID used for lookup
    kind: str  # "snapshot" or "alias"
    deprecation: Deprecation | None


def normalize(token: str) -> str:
    """Reduce provider-specific spellings to the plain model ID."""
    model = token.lower().rstrip(".-")
    if model.startswith("claude-"):
        model = _BEDROCK_SUFFIX_RE.sub("", model)  # anthropic.claude-sonnet-4-20250514-v1:0
        model = model.replace("@", "-")  # Vertex AI: claude-sonnet-4@20250514
        model = re.sub(r":\d+$", "", model)
    return model


def classify(model: str) -> str:
    if model.endswith("-latest"):
        return "alias"
    return "snapshot" if _SNAPSHOT_RE.search(model) else "alias"


def find_in_text(text: str, index: dict[str, Deprecation], path: str = "<text>") -> list[Match]:
    matches: list[Match] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if IGNORE_MARKER in line:
            continue
        for m in TOKEN_RE.finditer(line):
            raw = m.group(0).rstrip(".-")
            if not raw:
                continue
            if _BARE_O_SERIES_RE.match(raw):
                # A bare "o3" is only a model ID when it is a quoted string value.
                before = line[m.start() - 1] if m.start() > 0 else ""
                after = line[m.start() + len(raw)] if m.start() + len(raw) < len(line) else ""
                if not (before and before in _QUOTES and after == before):
                    continue
            model = normalize(raw)
            matches.append(
                Match(
                    path=path,
                    line=lineno,
                    column=m.start() + 1,
                    text=raw,
                    model=model,
                    kind=classify(model),
                    deprecation=index.get(model),
                )
            )
    return matches


def _is_candidate(name: str, all_files: bool) -> bool:
    if all_files:
        return True
    low = name.lower()
    if low in TEXT_FILENAMES or low.startswith(("dockerfile", "containerfile")):
        return True
    if low == ".env" or low.startswith(".env.") or low.endswith(".env"):
        return True
    return os.path.splitext(low)[1] in TEXT_EXTENSIONS


def _excluded(rel: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat.rstrip("/") + "/*") for pat in patterns)


def iter_files(
    root: Path, excludes: Iterable[str] = (), all_files: bool = False, skip: Iterable[Path] = ()
) -> Iterator[tuple[Path, str]]:
    """Yield (absolute path, relative POSIX path) for each file worth scanning."""
    excludes = tuple(excludes)
    skip_set = {p.resolve() for p in skip}
    if root.is_file():
        yield root, root.name
        return
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        kept = []
        for d in sorted(dirnames):
            rel_dir = (base / d).relative_to(root).as_posix()
            if d in DEFAULT_EXCLUDED_DIRS or _excluded(rel_dir, excludes):
                continue
            kept.append(d)
        dirnames[:] = kept
        for name in sorted(filenames):
            full = base / name
            rel = full.relative_to(root).as_posix()
            if not _is_candidate(name, all_files) or _excluded(rel, excludes):
                continue
            if full.is_symlink() or full.resolve() in skip_set:
                continue
            yield full, rel


def read_text(path: Path) -> str | None:
    """Return file contents, or None for binary, oversized or unreadable files."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class ScanResult:
    files_scanned: int
    matches: tuple[Match, ...]


def scan(
    root: str | Path,
    db: DeprecationDB,
    excludes: Iterable[str] = (),
    all_files: bool = False,
    skip: Iterable[Path] = (),
) -> ScanResult:
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"path not found: {root}")
    index = db.index()
    prefix = root.as_posix()
    files = 0
    found: list[Match] = []
    for full, rel in iter_files(root, excludes, all_files, skip):
        text = read_text(full)
        if text is None:
            continue
        files += 1
        if root.is_file():
            shown = prefix
        elif prefix in (".", ""):
            shown = rel
        else:
            shown = f"{prefix.rstrip('/')}/{rel}"
        found.extend(find_in_text(text, index, shown))
    return ScanResult(files_scanned=files, matches=tuple(found))
