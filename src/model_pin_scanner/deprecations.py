"""Load and validate the deprecations data file."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

PROVIDERS = frozenset({"openai", "anthropic", "google", "other"})
REQUIRED_FIELDS = ("id", "provider", "shutdown_date", "source_url", "verified")


class DataFileError(ValueError):
    """The deprecations data file is malformed."""


@dataclass(frozen=True)
class Deprecation:
    id: str
    provider: str
    shutdown_date: dt.date
    replacement: str | None
    source_url: str
    verified: bool
    aliases: tuple[str, ...] = field(default=())
    notes: str = ""

    def days_remaining(self, today: dt.date) -> int:
        return (self.shutdown_date - today).days


@dataclass(frozen=True)
class DeprecationDB:
    entries: tuple[Deprecation, ...]
    last_reviewed: str = ""

    def index(self) -> dict[str, Deprecation]:
        """Map every lowercased ID and alias to its entry."""
        out: dict[str, Deprecation] = {}
        for entry in self.entries:
            for key in (entry.id, *entry.aliases):
                out[key.lower()] = entry
        return out


def _parse_date(value: object, where: str) -> dt.date:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            pass
    raise DataFileError(f"{where}: shutdown_date must be YYYY-MM-DD, got {value!r}")


def _parse_entry(raw: object, pos: int) -> Deprecation:
    where = f"models[{pos}]"
    if not isinstance(raw, dict):
        raise DataFileError(f"{where}: expected a mapping")
    missing = [name for name in REQUIRED_FIELDS if name not in raw]
    if missing:
        raise DataFileError(f"{where}: missing field(s) {', '.join(missing)}")
    model_id = raw["id"]
    if not isinstance(model_id, str) or not model_id.strip():
        raise DataFileError(f"{where}: id must be a non-empty string")
    where = f"models[{pos}] ({model_id})"
    provider = raw["provider"]
    if provider not in PROVIDERS:
        raise DataFileError(f"{where}: provider must be one of {sorted(PROVIDERS)}")
    if not isinstance(raw["verified"], bool):
        raise DataFileError(f"{where}: verified must be true or false")
    source_url = raw["source_url"]
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        raise DataFileError(f"{where}: source_url must be an https URL")
    replacement = raw.get("replacement")
    if replacement is not None and not isinstance(replacement, str):
        raise DataFileError(f"{where}: replacement must be a string or null")
    aliases = raw.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        raise DataFileError(f"{where}: aliases must be a list of strings")
    return Deprecation(
        id=model_id.strip(),
        provider=provider,
        shutdown_date=_parse_date(raw["shutdown_date"], where),
        replacement=replacement,
        source_url=source_url,
        verified=raw["verified"],
        aliases=tuple(a.strip() for a in aliases),
        notes=str(raw.get("notes") or ""),
    )


def parse(text: str) -> DeprecationDB:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DataFileError(f"invalid YAML: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("models"), list):
        raise DataFileError("top level must be a mapping with a 'models' list")
    entries = tuple(_parse_entry(raw, i) for i, raw in enumerate(doc["models"]))
    seen: set[str] = set()
    for entry in entries:
        for key in (entry.id, *entry.aliases):
            low = key.lower()
            if low in seen:
                raise DataFileError(f"duplicate model ID or alias: {key}")
            seen.add(low)
    return DeprecationDB(entries=entries, last_reviewed=str(doc.get("last_reviewed") or ""))


def load(path: str | Path | None = None) -> DeprecationDB:
    """Load a data file, or the bundled one when path is None."""
    if path is None:
        text = resources.files("model_pin_scanner").joinpath("data/deprecations.yaml").read_text("utf-8")
    else:
        text = Path(path).read_text("utf-8")
    return parse(text)
