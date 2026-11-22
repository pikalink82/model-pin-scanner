"""Command-line entry point: scan, regress, data."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from . import __version__
from .deprecations import DataFileError, load
from .providers import MockProvider, Provider, ProviderError, from_env, guess_provider
from .regress import (
    GoldenFileError,
    load_golden,
    regress_to_json,
    regress_to_markdown,
    run_regression,
    should_fail,
)
from .report import build_report, to_github_annotations, to_json, to_markdown
from .scanner import scan

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc


def _non_negative(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return n


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="model-pin-scanner",
        description="Find pinned LLM model IDs that are close to shutdown, and diff outputs across model upgrades.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="scan files for pinned model IDs and report shutdown risk")
    s.add_argument("path", nargs="?", default=".", help="directory or file to scan (default: .)")
    s.add_argument("--data", help="deprecations YAML file (default: the bundled one)")
    s.add_argument("--format", choices=["markdown", "json"], default="markdown")
    s.add_argument("--output", "-o", help="write the report here instead of stdout")
    s.add_argument(
        "--fail-within",
        type=_non_negative,
        metavar="DAYS",
        help="exit 1 if any pinned model shuts down within DAYS days (or already has)",
    )
    s.add_argument("--warn-within", type=_non_negative, default=90, metavar="DAYS", help="warning window (default 90)")
    s.add_argument("--today", type=_date, help="pretend today is YYYY-MM-DD (default: the real date, UTC)")
    s.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="skip paths matching GLOB")
    s.add_argument("--all-files", action="store_true", help="scan every text file, not just code and config")
    s.add_argument(
        "--github-annotations", action="store_true", help="also print GitHub Actions ::error/::warning lines to stderr"
    )

    r = sub.add_parser("regress", help="run golden prompts on an old and a new model and diff the outputs")
    r.add_argument("golden", help="golden prompts file (.yaml, .yml or .jsonl)")
    r.add_argument("--old", required=True, metavar="MODEL", help="current model ID")
    r.add_argument("--new", required=True, metavar="MODEL", help="candidate model ID")
    r.add_argument(
        "--provider",
        choices=["auto", "openai", "anthropic", "google", "mock"],
        default="auto",
        help="auto picks by model ID prefix; mock needs --mock-responses",
    )
    r.add_argument(
        "--mock-responses", metavar="FILE", help="YAML {models: {model: {prompt_id: text}}} for --provider mock"
    )
    r.add_argument("--threshold", type=float, default=0.9, help="similarity at or above this is a minor change (0-1)")
    r.add_argument("--format", choices=["markdown", "json"], default="markdown")
    r.add_argument("--output", "-o", help="write the report here instead of stdout")
    r.add_argument(
        "--fail-on",
        choices=["never", "regressed", "changed"],
        default="never",
        help="exit 1 on regressions/errors, or on any change, a regression or an error",
    )

    d = sub.add_parser("data", help="validate and list the deprecations data file")
    d.add_argument("--data", help="deprecations YAML file (default: the bundled one)")
    d.add_argument("--format", choices=["markdown", "json"], default="markdown")
    d.add_argument("--today", type=_date, help="pretend today is YYYY-MM-DD")
    return p


def _emit(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, "utf-8")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _today(arg: dt.date | None) -> dt.date:
    return arg or dt.datetime.now(dt.UTC).date()


def cmd_scan(args: argparse.Namespace) -> int:
    db = load(args.data)
    skip = [Path(args.data)] if args.data else []
    if args.output:
        skip.append(Path(args.output))
    result = scan(args.path, db, excludes=args.exclude, all_files=args.all_files, skip=skip)
    report = build_report(result, db, _today(args.today), args.fail_within, args.warn_within)
    _emit(to_json(report) if args.format == "json" else to_markdown(report), args.output)
    if args.github_annotations:
        sys.stderr.write(to_github_annotations(report))
    return EXIT_FAIL if report.failing else EXIT_OK


def _provider(name: str, model: str, mock: MockProvider | None) -> Provider:
    if name == "mock":
        assert mock is not None
        return mock
    return from_env(guess_provider(model) if name == "auto" else name)


def _load_mock(path: str) -> MockProvider:
    doc = yaml.safe_load(Path(path).read_text("utf-8"))
    models = doc.get("models") if isinstance(doc, dict) else None
    if not isinstance(models, dict) or not all(isinstance(v, dict) for v in models.values()):
        raise ProviderError("mock responses file must look like {models: {model: {prompt_id: text}}}")
    return MockProvider({str(k): {str(pk): str(pv) for pk, pv in v.items()} for k, v in models.items()})


def cmd_regress(args: argparse.Namespace) -> int:
    if args.provider == "mock" and not args.mock_responses:
        raise ProviderError("--provider mock needs --mock-responses FILE")
    prompts = load_golden(args.golden)
    mock = _load_mock(args.mock_responses) if args.provider == "mock" else None
    old_p = _provider(args.provider, args.old, mock)
    new_p = _provider(args.provider, args.new, mock)
    report = run_regression(
        prompts,
        args.old,
        args.new,
        old_p,
        new_p,
        threshold=args.threshold,
        progress=lambda pid: sys.stderr.write(f"running {pid}\n"),
    )
    _emit(regress_to_json(report) if args.format == "json" else regress_to_markdown(report), args.output)
    return EXIT_FAIL if should_fail(report, args.fail_on) else EXIT_OK


def cmd_data(args: argparse.Namespace) -> int:
    db = load(args.data)
    today = _today(args.today)
    rows = sorted(db.entries, key=lambda e: (e.shutdown_date, e.id))
    if args.format == "json":
        doc = [
            {
                "id": e.id,
                "provider": e.provider,
                "shutdown_date": e.shutdown_date.isoformat(),
                "days_remaining": e.days_remaining(today),
                "replacement": e.replacement,
                "aliases": list(e.aliases),
                "verified": e.verified,
                "verified_by": e.verified_by,
                "source_url": e.source_url,
            }
            for e in rows
        ]
        _emit(json.dumps(doc, indent=2), None)
        return EXIT_OK
    lines = [
        f"{len(rows)} entries, {sum(e.verified for e in rows)} verified. "
        f"Last reviewed {db.last_reviewed or 'unknown'}.",
        "",
        "| Model | Provider | Shutdown | Days left | Replacement | Verified |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for e in rows:
        lines.append(
            f"| `{e.id}` | {e.provider} | {e.shutdown_date.isoformat()} | {e.days_remaining(today)} "
            f"| {e.replacement or 'not confirmed'} | {'yes' if e.verified else 'no'} |"
        )
    _emit("\n".join(lines), None)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {"scan": cmd_scan, "regress": cmd_regress, "data": cmd_data}
    try:
        return handlers[args.command](args)
    except (DataFileError, GoldenFileError, ProviderError, FileNotFoundError, ValueError, OSError) as exc:
        sys.stderr.write(f"model-pin-scanner: error: {exc}\n")
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
