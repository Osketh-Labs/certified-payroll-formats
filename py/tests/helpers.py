"""Fixture reading and single-edit mutation, mirroring js/test/helpers.js."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


def fixture(*parts) -> str:
    return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


def mutate(source: str, replacements) -> str:
    """A fixture with one edit applied, so a test reads as fault -> finding."""
    out = source
    for old, new in replacements:
        if old not in out:
            raise AssertionError(f"mutation target not present: {old!r}")
        out = out.replace(old, new, 1)
    return out


def ids(result) -> list:
    return [f["ruleId"] for f in result["findings"]]


def count(result, rule_id: str) -> int:
    return ids(result).count(rule_id)


def first(result, rule_id: str):
    return next((f for f in result["findings"] if f["ruleId"] == rule_id), None)
