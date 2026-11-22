"""Turn scan matches into risk findings and render them as Markdown, JSON or annotations."""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from dataclasses import dataclass

from .deprecations import DeprecationDB
from .scanner import Match, ScanResult

SHUT_DOWN = "shut_down"
CRITICAL = "critical"
WARNING = "warning"
OK = "ok"
STATUS_LABEL = {SHUT_DOWN: "SHUT DOWN", CRITICAL: "CRITICAL", WARNING: "WARNING", OK: "ok"}


@dataclass(frozen=True)
class Finding:
    match: Match
    days_remaining: int
    status: str


def status_for(days: int, fail_within: int | None, warn_within: int) -> str:
    if days <= 0:
        return SHUT_DOWN
    if fail_within is not None and days <= fail_within:
        return CRITICAL
    if days <= warn_within:
        return WARNING
    return OK


@dataclass(frozen=True)
class Report:
    today: dt.date
    files_scanned: int
    findings: tuple[Finding, ...]
    unknown: tuple[Match, ...]
    fail_within: int | None
    warn_within: int
    data_last_reviewed: str

    @property
    def failing(self) -> tuple[Finding, ...]:
        """Findings that should fail CI: within fail_within days, or already shut down."""
        if self.fail_within is None:
            return ()
        return tuple(f for f in self.findings if f.days_remaining <= self.fail_within)


def build_report(
    result: ScanResult,
    db: DeprecationDB,
    today: dt.date,
    fail_within: int | None = None,
    warn_within: int = 90,
) -> Report:
    findings = []
    unknown = []
    for m in result.matches:
        if m.deprecation is None:
            unknown.append(m)
            continue
        days = m.deprecation.days_remaining(today)
        findings.append(Finding(m, days, status_for(days, fail_within, warn_within)))
    findings.sort(key=lambda f: (f.days_remaining, f.match.path, f.match.line, f.match.column))
    return Report(
        today=today,
        files_scanned=result.files_scanned,
        findings=tuple(findings),
        unknown=tuple(unknown),
        fail_within=fail_within,
        warn_within=warn_within,
        data_last_reviewed=db.last_reviewed,
    )


def _finding_dict(f: Finding) -> dict[str, object]:
    d = f.match.deprecation
    assert d is not None
    return {
        "model": f.match.model,
        "matched_text": f.match.text,
        "canonical_id": d.id,
        "kind": f.match.kind,
        "provider": d.provider,
        "path": f.match.path,
        "line": f.match.line,
        "column": f.match.column,
        "shutdown_date": d.shutdown_date.isoformat(),
        "days_remaining": f.days_remaining,
        "status": f.status,
        "replacement": d.replacement,
        "source_url": d.source_url,
        "verified": d.verified,
        "verified_by": d.verified_by,
        "notes": d.notes,
    }


def _inventory(matches: tuple[Match, ...]) -> list[dict[str, object]]:
    grouped: dict[str, list[Match]] = defaultdict(list)
    for m in matches:
        grouped[m.model].append(m)
    return [
        {
            "model": model,
            "kind": ms[0].kind,
            "count": len(ms),
            "locations": [f"{m.path}:{m.line}" for m in ms],
        }
        for model, ms in sorted(grouped.items())
    ]


def to_json(report: Report) -> str:
    counts = {s: 0 for s in STATUS_LABEL}
    for f in report.findings:
        counts[f.status] += 1
    doc = {
        "today": report.today.isoformat(),
        "data_last_reviewed": report.data_last_reviewed,
        "fail_within_days": report.fail_within,
        "warn_within_days": report.warn_within,
        "summary": {
            "files_scanned": report.files_scanned,
            "at_risk_references": len(report.findings),
            "failing_references": len(report.failing),
            "unverified_references": sum(1 for f in report.findings if not f.match.deprecation.verified),  # type: ignore[union-attr]
            "by_status": counts,
            "other_model_ids": len({m.model for m in report.unknown}),
        },
        "findings": [_finding_dict(f) for f in report.findings],
        "other_model_ids": _inventory(report.unknown),
    }
    return json.dumps(doc, indent=2) + "\n"


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(report: Report) -> str:
    lines = ["# Model pin scan", ""]
    n = len(report.findings)
    lines.append(
        f"Scanned {report.files_scanned} files on {report.today.isoformat()}. "
        f"Found {n} reference{'s' if n != 1 else ''} to models with a known shutdown date."
    )
    if report.fail_within is not None:
        lines.append(
            f"{len(report.failing)} fail the {report.fail_within}-day threshold "
            f"(shut down or within {report.fail_within} days)."
        )
    if report.data_last_reviewed:
        lines.append(f"Deprecation data last reviewed {report.data_last_reviewed}.")
    lines.append("")
    if report.findings:
        lines += [
            "| Status | Model | Days left | Shutdown | Replacement | Location | Verified |",
            "| --- | --- | ---: | --- | --- | --- | --- |",
        ]
        for f in report.findings:
            d = f.match.deprecation
            assert d is not None
            model = f"`{_md(f.match.text)}`"
            if f.match.text != d.id:
                model += f" (= `{d.id}`)"
            verified = f"[yes]({d.evidence_url})" if d.verified else f"[no]({d.source_url})"
            lines.append(
                f"| {STATUS_LABEL[f.status]} | {model} | {f.days_remaining} | {d.shutdown_date.isoformat()} "
                f"| {_md(d.replacement) if d.replacement else 'not confirmed'} "
                f"| `{_md(f.match.path)}:{f.match.line}` | {verified} |"
            )
        lines.append("")
        if any(not f.match.deprecation.verified for f in report.findings):  # type: ignore[union-attr]
            lines += [
                "Entries marked not verified come from secondary sources. "
                "Check the linked provider page before acting.",
                "",
            ]
    else:
        lines += ["No pinned models with a known shutdown date.", ""]
    inventory = _inventory(report.unknown)
    if inventory:
        lines += [
            "## Other model IDs found (no known shutdown)",
            "",
            "| Model | Kind | Count | First location |",
            "| --- | --- | ---: | --- |",
        ]
        for item in inventory:
            locs = item["locations"]
            assert isinstance(locs, list)
            lines.append(f"| `{_md(str(item['model']))}` | {item['kind']} | {item['count']} | `{_md(locs[0])}` |")
        lines.append("")
    return "\n".join(lines)


def _gh_escape_data(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _gh_escape_prop(s: str) -> str:
    return _gh_escape_data(s).replace(":", "%3A").replace(",", "%2C")


def to_github_annotations(report: Report) -> str:
    """GitHub Actions workflow commands: errors for failing findings, warnings for the rest."""
    failing = {id(f) for f in report.failing}
    out = []
    for f in report.findings:
        if f.status == OK and id(f) not in failing:
            continue
        d = f.match.deprecation
        assert d is not None
        level = "error" if id(f) in failing else "warning"
        when = "shut down" if f.days_remaining <= 0 else f"shuts down in {f.days_remaining} days"
        msg = f"{f.match.model} {when} ({d.shutdown_date.isoformat()})."
        if d.replacement:
            msg += f" Suggested replacement: {d.replacement}."
        if not d.verified:
            msg += f" Date not verified; see {d.source_url}"
        out.append(
            f"::{level} file={_gh_escape_prop(f.match.path)},line={f.match.line},col={f.match.column},"
            f"title={_gh_escape_prop('Pinned model ' + f.match.model)}::{_gh_escape_data(msg)}"
        )
    return "\n".join(out) + ("\n" if out else "")
