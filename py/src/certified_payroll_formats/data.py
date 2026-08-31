"""Loaders for the JSON dataset that sits at the root of this repository."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# ``data/`` at the repository root is canonical. ``tools/sync_packages.py`` copies it
# into this package before building a wheel, because a wheel cannot reference files above
# the package directory. Prefer the packaged copy; fall back to the root in a checkout.
_HERE = Path(__file__).resolve().parent
_PACKAGED = _HERE / "data"
_REPO_ROOT = _HERE.parents[2] / "data"
DATA_DIR = _PACKAGED if (_PACKAGED / "sources.json").exists() else _REPO_ROOT

_FORMAT_FILES = {
    "ca-ecpr": "ca-ecpr.json",
    "ny-certpayroll": "ny-certpayroll.json",
    "wa-pwia": "wa-pwia.json",
}


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def sources() -> dict:
    return _load("sources.json")["sources"]


def jurisdictions() -> list:
    return _load("jurisdictions.json")["jurisdictions"]


def jurisdiction(identifier: str):
    return next((j for j in jurisdictions() if j["id"] == identifier), None)


def wh347_data() -> dict:
    return _load("wh347.json")


def conflicts() -> list:
    return _load("conflicts.json")["conflicts"]


def format_data(format_id: str) -> dict:
    try:
        return _load(_FORMAT_FILES[format_id])
    except KeyError:
        raise ValueError(f"Unknown format: {format_id}") from None


def resolve_sources(ids) -> list:
    known = sources()
    return [{"id": i, **known.get(i, {"title": f"unknown source: {i}"})} for i in (ids or [])]


def rules(format_id: str) -> list:
    return [{**r, "sources": resolve_sources(r.get("sources"))} for r in format_data(format_id)["rules"]]


def rule(rule_id: str):
    for format_id in _FORMAT_FILES:
        for r in rules(format_id):
            if r["id"] == rule_id:
                return r
    for group in ("easyToMiss", "checks"):
        for r in wh347_data().get(group, []):
            if r["id"] == rule_id:
                return {**r, "sources": resolve_sources(r.get("sources"))}
    return None


def elements(format_id: str) -> list:
    data = format_data(format_id)
    if "elements" not in data:
        raise ValueError(f"No extracted element tree for format: {format_id}")
    return data["elements"]
