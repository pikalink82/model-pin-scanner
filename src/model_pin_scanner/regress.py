"""Run golden prompts against an old and a new model and diff the outputs."""

from __future__ import annotations

import difflib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .providers import CompletionRequest, Provider, ProviderError

IDENTICAL = "identical"
MINOR = "minor"
CHANGED = "changed"
REGRESSED = "regressed"
ERROR = "error"
SEVERITY = {IDENTICAL: 0, MINOR: 1, CHANGED: 2, REGRESSED: 3, ERROR: 3}


class GoldenFileError(ValueError):
    """The golden prompts file is malformed."""


@dataclass(frozen=True)
class GoldenPrompt:
    id: str
    prompt: str
    system: str | None = None
    expect_contains: tuple[str, ...] = ()
    max_tokens: int = 1024


def _prompt_from(raw: object, pos: int, default_system: str | None) -> GoldenPrompt:
    if not isinstance(raw, dict):
        raise GoldenFileError(f"prompt {pos}: expected a mapping")
    pid = raw.get("id")
    text = raw.get("prompt")
    if not isinstance(pid, str) or not pid:
        raise GoldenFileError(f"prompt {pos}: 'id' must be a non-empty string")
    if not isinstance(text, str) or not text:
        raise GoldenFileError(f"prompt {pid}: 'prompt' must be a non-empty string")
    expect = raw.get("expect_contains") or []
    if isinstance(expect, str):
        expect = [expect]
    if not isinstance(expect, list) or not all(isinstance(e, str) for e in expect):
        raise GoldenFileError(f"prompt {pid}: 'expect_contains' must be a string or list of strings")
    max_tokens = raw.get("max_tokens", 1024)
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
        raise GoldenFileError(f"prompt {pid}: 'max_tokens' must be a positive integer")
    system = raw.get("system", default_system)
    if system is not None and not isinstance(system, str):
        raise GoldenFileError(f"prompt {pid}: 'system' must be a string")
    return GoldenPrompt(pid, text, system, tuple(expect), max_tokens)


def load_golden(path: str | Path) -> list[GoldenPrompt]:
    """Read prompts from YAML ({system?, prompts: [...]}, or a bare list) or JSONL."""
    path = Path(path)
    text = path.read_text("utf-8")
    default_system: str | None = None
    if path.suffix.lower() == ".jsonl":
        items = []
        for n, line in enumerate(text.splitlines(), start=1):
            if line.strip():
                try:
                    items.append(json.loads(line))
                except ValueError as exc:
                    raise GoldenFileError(f"line {n}: invalid JSON") from exc
    else:
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise GoldenFileError(f"invalid YAML: {exc}") from exc
        if isinstance(doc, dict):
            default_system = doc.get("system")
            items = doc.get("prompts")
        else:
            items = doc
        if not isinstance(items, list):
            raise GoldenFileError("expected a 'prompts' list")
    prompts = [_prompt_from(raw, i, default_system) for i, raw in enumerate(items)]
    if not prompts:
        raise GoldenFileError("no prompts found")
    ids = [p.id for p in prompts]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise GoldenFileError(f"duplicate prompt id(s): {', '.join(dupes)}")
    return prompts


@dataclass(frozen=True)
class Side:
    output: str | None
    error: str | None
    expectations_met: tuple[str, ...] = ()
    expectations_missed: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptResult:
    prompt: GoldenPrompt
    old: Side
    new: Side
    similarity: float
    status: str
    diff: str
    lost_expectations: tuple[str, ...] = field(default=())


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _run(provider: Provider, model: str, p: GoldenPrompt) -> Side:
    try:
        out = provider.complete(CompletionRequest(model, p.prompt, p.system, p.max_tokens, p.id))
    except ProviderError as exc:
        return Side(None, str(exc))
    low = out.lower()
    met = tuple(e for e in p.expect_contains if e.lower() in low)
    missed = tuple(e for e in p.expect_contains if e.lower() not in low)
    return Side(out, None, met, missed)


def compare(p: GoldenPrompt, old: Side, new: Side, threshold: float, old_label: str, new_label: str) -> PromptResult:
    if old.output is None or new.output is None:
        return PromptResult(p, old, new, 0.0, ERROR, "")
    a, b = _normalize(old.output), _normalize(new.output)
    similarity = 1.0 if a == b else difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    lost = tuple(e for e in old.expectations_met if e in new.expectations_missed)
    if lost:
        status = REGRESSED
    elif a == b:
        status = IDENTICAL
    elif similarity >= threshold:
        status = MINOR
    else:
        status = CHANGED
    diff = "\n".join(
        difflib.unified_diff(
            old.output.splitlines(), new.output.splitlines(), fromfile=old_label, tofile=new_label, lineterm=""
        )
    )
    return PromptResult(p, old, new, round(similarity, 4), status, diff, lost)


@dataclass(frozen=True)
class RegressReport:
    old_model: str
    new_model: str
    threshold: float
    results: tuple[PromptResult, ...]

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    def worst(self) -> int:
        return max((SEVERITY[r.status] for r in self.results), default=0)


def run_regression(
    prompts: list[GoldenPrompt],
    old_model: str,
    new_model: str,
    old_provider: Provider,
    new_provider: Provider,
    threshold: float = 0.9,
    progress: Callable[[str], None] | None = None,
) -> RegressReport:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    results = []
    for p in prompts:
        if progress:
            progress(p.id)
        old = _run(old_provider, old_model, p)
        new = _run(new_provider, new_model, p)
        results.append(compare(p, old, new, threshold, old_model, new_model))
    return RegressReport(old_model, new_model, threshold, tuple(results))


def should_fail(report: RegressReport, fail_on: str) -> bool:
    if fail_on == "never":
        return False
    if fail_on == "changed":
        return report.worst() >= SEVERITY[CHANGED]
    if fail_on == "regressed":
        return report.worst() >= SEVERITY[REGRESSED]
    raise ValueError(f"unknown fail_on value {fail_on!r}")


def regress_to_json(report: RegressReport) -> str:
    def side(s: Side) -> dict[str, object]:
        return {
            "output": s.output,
            "error": s.error,
            "expectations_met": list(s.expectations_met),
            "expectations_missed": list(s.expectations_missed),
        }

    doc = {
        "old_model": report.old_model,
        "new_model": report.new_model,
        "threshold": report.threshold,
        "summary": {s: report.count(s) for s in SEVERITY},
        "results": [
            {
                "id": r.prompt.id,
                "status": r.status,
                "similarity": r.similarity,
                "lost_expectations": list(r.lost_expectations),
                "old": side(r.old),
                "new": side(r.new),
                "diff": r.diff,
            }
            for r in report.results
        ],
    }
    return json.dumps(doc, indent=2) + "\n"


def _fence(text: str) -> str:
    """A backtick fence longer than any backtick run in text, so model output cannot close it."""
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return ticks


def regress_to_markdown(report: RegressReport) -> str:
    lines = [
        f"# Regression: `{report.old_model}` -> `{report.new_model}`",
        "",
        f"{len(report.results)} prompts. "
        + ", ".join(f"{report.count(s)} {s}" for s in SEVERITY)
        + f". Similarity threshold {report.threshold}.",
        "",
        "| Prompt | Status | Similarity | Lost expectations |",
        "| --- | --- | ---: | --- |",
    ]
    for r in report.results:
        lost = ", ".join(r.lost_expectations) or "-"
        lines.append(f"| `{r.prompt.id}` | {r.status} | {r.similarity:.2f} | {lost.replace('|', chr(92) + '|')} |")
    lines.append("")
    for r in report.results:
        if r.status == IDENTICAL:
            continue
        lines += [f"## `{r.prompt.id}`: {r.status}", ""]
        for label, s in (("old", r.old), ("new", r.new)):
            if s.error:
                lines += [f"{label} error: {s.error}", ""]
            elif s.expectations_missed:
                lines += [f"{label} missed expected text: {', '.join(s.expectations_missed)}", ""]
        if r.diff:
            fence = _fence(r.diff)
            lines += [f"{fence}diff", r.diff.rstrip("\n"), fence, ""]
    return "\n".join(lines)
