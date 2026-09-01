"""New York certified payroll bulk upload: the checks the schema cannot express."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from .data import format_data
from .finding import finding, summarize
from .schema_check import check_against_schema, is_calendar_date
from .xml_reader import XmlError, kid, kids, parse_xml, path_of, text_at

US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
}


def _rules() -> dict:
    return {r["id"]: r for r in format_data("ny-certpayroll")["rules"]}


def _week_window(week_ending):
    """The seven-day window, or None when the week ending date is not a real calendar date.

    A value like 2026-13-45 is already reported by the schema check; deriving a window
    from it would either raise or roll over into another month and flag every day.
    """
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", week_ending or "")
    if not match or not is_calendar_date(*(int(g) for g in match.groups())):
        return None
    end = date.fromisoformat(week_ending)
    return [(end - timedelta(days=n)).isoformat() for n in range(6, -1, -1)]


def validate_ny_cert_payroll(xml: str, filename: Optional[str] = None) -> dict:
    """Validate a New York certified payroll XML document."""
    R = _rules()
    out: list = []

    try:
        root = parse_xml(xml)
    except XmlError as error:
        return summarize([finding(
            {"id": "ny.parse", "severity": "error",
             "statement": "The file must be well-formed XML.", "sources": ["ny-dol-buf"]},
            message=str(error), line=error.line)])

    if root.ns:
        out.append(finding(R["ny.root.noNamespace"], path=root.qname, line=root.line,
                           message="the document is in a namespace; NYDOL_CertPayroll.xsd declares none, "
                                   "so a namespaced instance does not validate",
                           expected="(no namespace)", actual=root.ns))

    out.extend(check_against_schema(root, "ny-certpayroll", None, report_namespace=not root.ns))

    window = _week_window((text_at(root, "weekEndingDate") or "")[:10])

    seen: dict = {}

    for eww in kids(kid(root, "employeeWorkWeeks"), "employeeWorkWeek"):
        employee = kid(eww, "employee")
        if employee is None:
            continue
        base = path_of(employee)

        ssn_last4 = text_at(employee, "ssnLast4")
        date_of_birth = text_at(employee, "dateOfBirth")
        if bool(ssn_last4) == bool(date_of_birth):
            out.append(finding(R["ny.employee.exactlyOneIdentifier"], path=base, line=employee.line,
                               message=("the employee carries both ssnLast4 and dateOfBirth" if ssn_last4
                                        else "the employee carries neither ssnLast4 nor dateOfBirth"),
                               expected="exactly one of ssnLast4 or dateOfBirth",
                               actual="both present" if ssn_last4 else "neither present"))

        state = text_at(employee, "address/state")
        if state and len(state) == 2 and state.upper() in US_STATE_ABBREVIATIONS:
            out.append(finding(R["ny.address.stateFullName"], path=f"{base}/address/state",
                               line=kid(kid(employee, "address"), "state").line,
                               message="address/state carries a two-letter abbreviation; the portal requires the full state name",
                               expected="the full state name, e.g. New York", actual=state))

        key = "|".join([(text_at(employee, "firstName") or "").lower(),
                        (text_at(employee, "lastName") or "").lower(),
                        ssn_last4 or date_of_birth or ""])
        if key in seen:
            out.append(finding(R["ny.employee.noDuplicates"], path=base, line=employee.line,
                               message=f"this employee already appears in the file at line {seen[key]}",
                               expected="one employeeWorkWeek per employee per file",
                               actual="a duplicate entry"))
        else:
            seen[key] = employee.line

        for work_week in kids(kid(eww, "workWeeks"), "workWeek"):
            dates: list = []
            for day_node in kids(kid(work_week, "days"), "day"):
                value = text_at(day_node, "day")
                if not value:
                    continue
                dates.append(value)
                if window and value not in window:
                    out.append(finding(R["ny.days.withinWeek"],
                                       path=f"{path_of(work_week)}/days/day", line=day_node.line,
                                       message="the day date falls outside the seven-day window ending on weekEndingDate",
                                       expected=f"{window[0]} … {window[6]}", actual=value))
            for duplicate in sorted({d for d in dates if dates.count(d) > 1}):
                out.append(finding(R["ny.days.withinWeek"], path=f"{path_of(work_week)}/days",
                                   line=work_week.line,
                                   message="a day date repeats within one workWeek",
                                   expected="distinct dates", actual=duplicate))

    if filename and not filename.lower().endswith(".xml"):
        out.append(finding({"id": "ny.filename.extension", "severity": "error",
                            "statement": "The file extension must be .xml.", "sources": ["ny-dol-buf"]},
                           path=None, line=None, message="the filename does not end in .xml",
                           expected=".xml", actual=filename))

    return summarize(out)
