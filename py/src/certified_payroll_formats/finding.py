"""Findings carry the rule they came from and the official source behind it."""

from __future__ import annotations

from .data import resolve_sources

SEVERITY_ORDER = {"error": 0, "warning": 1, "advisory": 2}


def finding(rule_doc: dict, *, path=None, line=None, message: str,
            expected=None, actual=None) -> dict:
    raw = rule_doc.get("sources") or []
    sources = resolve_sources(raw) if raw and isinstance(raw[0], str) else raw
    return {
        "ruleId": rule_doc["id"],
        "severity": rule_doc["severity"],
        "path": path,
        "line": line,
        "message": message,
        "expected": expected,
        "actual": actual,
        "statement": rule_doc.get("statement"),
        "sources": sources,
    }


def sort_findings(findings: list) -> list:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f["severity"]], f["line"] or 0))


def summarize(findings: list) -> dict:
    counts = {"error": 0, "warning": 0, "advisory": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return {"valid": counts["error"] == 0, "counts": counts, "findings": sort_findings(findings)}
