"""Structural validation against the element tree extracted from an agency's own XSD.

The Python twin of js/src/schema-check.js. Not a general XSD processor — it covers the
constructs the certified payroll schemas use: sequences of named elements with
occurrence limits and simple-type facets.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from .data import elements
from .finding import finding
from .xml_reader import Node, path_of

SCHEMA_SOURCE = {"ca-ecpr": ["ca-dir-xsd"], "ny-certpayroll": ["ny-dol-xsd"]}

RULES = {
    "namespace": ("schema.namespace", "Every element must be in the namespace the schema declares — or in no namespace, where the schema declares none."),
    "unexpected": ("schema.unexpectedElement", "The schema declares no element with this name at this position."),
    "missing": ("schema.missingElement", "A required element declared by the schema is absent."),
    "too_many": ("schema.tooManyElements", "More occurrences of an element than the schema permits."),
    "order": ("schema.elementOrder", "Elements in an xs:sequence must appear in the order the schema declares."),
    "fixed": ("schema.fixedValue", "An element declared with a fixed value must carry exactly that value."),
    "pattern": ("schema.pattern", "The value does not match the pattern the schema declares."),
    "length": ("schema.length", "The value violates a minLength or maxLength facet."),
    "range": ("schema.range", "The value violates a maxInclusive or maxExclusive facet."),
    "fraction": ("schema.fractionDigits", "The value carries more fraction digits than the schema permits."),
    "type": ("schema.type", "The value is not a valid lexical form for its declared type."),
    "enumeration": ("schema.enumeration", "The value is not one of the values the schema enumerates."),
}

DATE = re.compile(r"^-?(\d{4})-(\d{2})-(\d{2})(Z|[+-]\d{2}:\d{2})?$")
DATETIME = re.compile(
    r"^-?(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")


def is_calendar_date(year: int, month: int, day: int) -> bool:
    """xs:date and xs:dateTime require a real calendar date, not merely the right shape.

    ``2026-13-45`` matches the lexical pattern and is still not a date, and letting it
    through produces nonsense downstream when the week window is computed from it.
    """
    if month < 1 or month > 12 or day < 1:
        return False
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    return day <= [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]


def _valid_date(value: str) -> bool:
    match = DATE.match(value)
    return bool(match) and is_calendar_date(*(int(g) for g in match.groups()[:3]))


def _valid_datetime(value: str) -> bool:
    match = DATETIME.match(value)
    if not match:
        return False
    year, month, day, hour, minute, second = (int(g) for g in match.groups()[:6])
    if not is_calendar_date(year, month, day):
        return False
    if minute > 59 or second > 59:
        return False
    return hour < 24 or (hour == 24 and minute == 0 and second == 0)
INTEGER = re.compile(r"^[+-]?\d+$")
DECIMAL = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")


def _rule(kind: str, format_id: str) -> dict:
    rule_id, statement = RULES[kind]
    return {"id": rule_id, "severity": "error", "statement": statement,
            "sources": SCHEMA_SOURCE.get(format_id, [])}


def _index(format_id: str):
    defs = elements(format_id)
    children_of: dict[str, list] = {}
    for d in defs:
        if "/" not in d["path"]:
            continue
        children_of.setdefault(d["path"].rsplit("/", 1)[0], []).append(d)
    return defs[0], children_of


def _check_value(definition: dict, node: Node, out: list, format_id: str) -> None:
    value = node.text.strip()
    where = {"path": path_of(node), "line": node.line, "actual": value}

    if "fixed" in definition:
        if value != definition["fixed"]:
            out.append(finding(_rule("fixed", format_id), **where,
                               message=f'<{node.qname}> is declared fixed="{definition["fixed"]}" and must be sent empty',
                               expected="(empty)" if definition["fixed"] == "" else definition["fixed"]))
        return

    facets = definition.get("facets", {})
    declared = definition.get("type", "xs:string")

    if "enumeration" in facets:
        allowed = facets["enumeration"]
        allowed = allowed if isinstance(allowed, list) else [allowed]
        if value not in allowed:
            out.append(finding(_rule("enumeration", format_id), **where,
                               message=f"<{node.qname}> is not one of the enumerated values",
                               expected=" | ".join(allowed)))
            return

    if "pattern" in facets:
        try:
            if not re.fullmatch(facets["pattern"], value):
                out.append(finding(_rule("pattern", format_id), **where,
                                   message=f"<{node.qname}> does not match the schema pattern",
                                   expected=facets["pattern"]))
                return
        except re.error:
            pass
    if "minLength" in facets and len(value) < int(facets["minLength"]):
        out.append(finding(_rule("length", format_id), **where,
                           message=f"<{node.qname}> is shorter than minLength",
                           expected=f'at least {facets["minLength"]} characters'))
    if "maxLength" in facets and len(value) > int(facets["maxLength"]):
        out.append(finding(_rule("length", format_id), **where,
                           message=f"<{node.qname}> is longer than maxLength",
                           expected=f'at most {facets["maxLength"]} characters'))

    # An empty element is a valid xs:string with minLength 0, and is not a valid anything
    # else. Without this, a blank <totHrsStraightTime/> is simply skipped and the real
    # fault is never reported.
    if value == "" and declared in ("xs:date", "xs:dateTime", "xs:boolean",
                                    "xs:decimal", "xs:integer"):
        out.append(finding(_rule("type", format_id), **where,
                           message=f"<{node.qname}> is empty, which is not a valid {declared}",
                           expected=declared))
        return

    if declared == "xs:date" and value and not _valid_date(value):
        out.append(finding(_rule("type", format_id), **where,
                           message=f"<{node.qname}> is not a valid xs:date",
                           expected="a real calendar date, yyyy-mm-dd"))
    elif declared == "xs:dateTime" and value and not _valid_datetime(value):
        out.append(finding(_rule("type", format_id), **where,
                           message=f"<{node.qname}> is not a valid xs:dateTime",
                           expected="yyyy-mm-ddThh:mm:ss[.sss][Z]"))
    elif declared == "xs:boolean" and value and value not in ("true", "false", "1", "0"):
        out.append(finding(_rule("type", format_id), **where,
                           message=f"<{node.qname}> is not a valid xs:boolean", expected="true or false"))
    elif declared in ("xs:decimal", "xs:integer") and value:
        pattern = INTEGER if declared == "xs:integer" else DECIMAL
        if not pattern.match(value):
            out.append(finding(_rule("type", format_id), **where,
                               message=f"<{node.qname}> is not a valid {declared}", expected=declared))
            return
        try:
            number = Decimal(value)
        except InvalidOperation:
            return
        if "maxInclusive" in facets and number > Decimal(facets["maxInclusive"]):
            out.append(finding(_rule("range", format_id), **where,
                               message=f"<{node.qname}> exceeds maxInclusive",
                               expected=f'at most {facets["maxInclusive"]}'))
        if "maxExclusive" in facets and number >= Decimal(facets["maxExclusive"]):
            out.append(finding(_rule("range", format_id), **where,
                               message=f"<{node.qname}> is not below maxExclusive",
                               expected=f'less than {facets["maxExclusive"]}'))
        if "minInclusive" in facets and number < Decimal(facets["minInclusive"]):
            out.append(finding(_rule("range", format_id), **where,
                               message=f"<{node.qname}> is below minInclusive",
                               expected=f'at least {facets["minInclusive"]}'))
        if "fractionDigits" in facets:
            digits = len(value.split(".", 1)[1]) if "." in value else 0
            if digits > int(facets["fractionDigits"]):
                out.append(finding(_rule("fraction", format_id), **where,
                                   message=f"<{node.qname}> carries {digits} fraction digits",
                                   expected=f'at most {facets["fractionDigits"]}'))


def _check_node(definition: dict, node: Node, children_of: dict, out: list,
                format_id: str, expected_ns: Optional[str], report_ns: bool = True) -> None:
    # A wrong namespace is inherited by every descendant, so report it once at the
    # highest element that has it and stay quiet below.
    if node.ns != expected_ns:
        if report_ns:
            out.append(finding(_rule("namespace", format_id), path=path_of(node), line=node.line,
                               actual=node.ns or "(no namespace)",
                               expected=expected_ns or "(no namespace)",
                               message=f"<{node.qname}> and its descendants are in the wrong namespace"))
        report_ns = False

    child_defs = children_of.get(definition["path"], [])
    if not child_defs:
        _check_value(definition, node, out, format_id)
        return

    allowed = {d["name"]: d for d in child_defs}
    for child in node.children:
        if child.name not in allowed:
            out.append(finding(_rule("unexpected", format_id), path=path_of(child), line=child.line,
                               actual=child.qname, expected=", ".join(allowed),
                               message=f"<{child.qname}> is not declared under <{node.qname}>"))

    order = [d["name"] for d in child_defs]
    last = -1
    reported = False
    for child in node.children:
        if child.name not in allowed:
            continue
        position = order.index(child.name)
        if position < last and not reported:
            reported = True
            out.append(finding(_rule("order", format_id), path=path_of(child), line=child.line,
                               actual=child.name, expected=" → ".join(order),
                               message=f"<{child.qname}> appears out of sequence under <{node.qname}>"))
        last = max(last, position)

    for child_def in child_defs:
        matches = [c for c in node.children if c.name == child_def["name"]]
        minimum = int(child_def.get("minOccurs", "1"))
        raw_max = child_def.get("maxOccurs", "1")
        maximum = float("inf") if raw_max == "unbounded" else int(raw_max)
        if len(matches) < minimum:
            out.append(finding(_rule("missing", format_id),
                               path=f'{path_of(node)}/{child_def["name"]}', line=node.line,
                               actual=f"{len(matches)} present", expected=f"at least {minimum}",
                               message=f'<{child_def["name"]}> is required under <{node.qname}>'))
        if len(matches) > maximum:
            out.append(finding(_rule("too_many", format_id),
                               path=f'{path_of(node)}/{child_def["name"]}',
                               line=matches[int(maximum)].line, actual=f"{len(matches)} present",
                               expected=f"at most {maximum:.0f}",
                               message=f'too many <{child_def["name"]}> elements under <{node.qname}>'))
        for match in matches:
            _check_node(child_def, match, children_of, out, format_id, expected_ns, report_ns)


def check_against_schema(root: Node, format_id: str, expected_ns: Optional[str],
                         report_namespace: bool = True) -> list:
    """Validate a parsed document against the extracted schema for ``format_id``."""
    root_def, children_of = _index(format_id)
    out: list = []
    if root.name != root_def["name"]:
        out.append(finding(_rule("unexpected", format_id), path=root.name, line=root.line,
                           actual=root.qname, expected=root_def["name"],
                           message=f'the document element must be <{root_def["name"]}>'))
        return out
    _check_node(root_def, root, children_of, out, format_id, expected_ns, report_namespace)
    return out
