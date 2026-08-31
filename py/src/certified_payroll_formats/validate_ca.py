"""California eCPR: the checks the published schema cannot express."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from .data import format_data
from .finding import finding, summarize
from .schema_check import check_against_schema
from .xml_reader import XmlError, kid, kids, parse_xml, path_of, text_at

CA_NAMESPACE = "http://www.dir.ca.gov/dlse/CPR-Prod-Test/CPR.xsd"
TOLERANCE = Decimal("0.005")

DEDUCTION_ITEMS = ["fedTax", "FICA", "stateTax", "SDI", "vacationHoliday", "healthWelfare",
                   "pension", "training", "fundAdmin", "dues", "travelSubs", "savings", "other"]


def _rules() -> dict:
    return {r["id"]: r for r in format_data("ca-ecpr")["rules"]}


def _decimal(node) -> Optional[Decimal]:
    if node is None:
        return None
    try:
        return Decimal(node.text.strip())
    except (InvalidOperation, ValueError):
        return None


def _week(week_ending: str) -> list:
    end = date.fromisoformat(week_ending)
    return [(end - timedelta(days=n)).isoformat() for n in range(6, -1, -1)]


def validate_ca_ecpr(xml: str, filename: Optional[str] = None) -> dict:
    """Validate a California eCPR XML document.

    Returns ``{"valid": bool, "counts": {...}, "findings": [...]}``.
    """
    R = _rules()
    out: list = []

    try:
        root = parse_xml(xml)
    except XmlError as error:
        return summarize([finding(
            {"id": "ca.parse", "severity": "error",
             "statement": "The file must be well-formed XML.", "sources": ["ca-dir-guideline"]},
            message=str(error), line=error.line)])

    out.extend(check_against_schema(root, "ca-ecpr", CA_NAMESPACE))

    project = kid(root, "projectInfo")
    if project is not None:
        agency = text_at(project, "contractAgency")
        project_id = text_at(project, "projectID")
        fallback = [text_at(project, n) for n in ("awardingBodyID", "projectNum", "contractID")]
        if not agency:
            out.append(finding(R["ca.projectInfo.mandatory"],
                               path="eCPR/projectInfo/contractAgency", line=project.line,
                               message="contractAgency is empty; the guideline lists it as one of the two fields to fill in",
                               expected="a contract agency, e.g. CA-DIR", actual="(empty)"))
        if not project_id and not all(fallback):
            out.append(finding(R["ca.projectInfo.mandatory"],
                               path="eCPR/projectInfo/projectID", line=project.line,
                               message="projectID is empty and the documented fallback is incomplete",
                               expected="a projectID, or all three of awardingBodyID, projectNum and contractID",
                               actual="projectID=(empty), " + ", ".join(
                                   f"{n}={v or '(empty)'}" for n, v in
                                   zip(("awardingBodyID", "projectNum", "contractID"), fallback))))

    payroll_info = kid(root, "payrollInfo")
    if payroll_info is None:
        return summarize(out)

    week_ending = text_at(payroll_info, "forWeekEnding")
    non_performance = text_at(payroll_info, "statementOfNP") == "true"
    employees = kids(kid(payroll_info, "employees"), "employee")

    if non_performance and employees:
        out.append(finding(R["ca.statementOfNP.noEmployees"],
                           path="eCPR/payrollInfo/employees", line=employees[0].line,
                           message=f"statementOfNP is true but {len(employees)} employee element(s) are present",
                           expected="an empty <employees> element", actual=f"{len(employees)} employees"))
    if not non_performance and not employees:
        out.append(finding(R["ca.statementOfNP.noEmployees"],
                           path="eCPR/payrollInfo/employees", line=payroll_info.line,
                           message="statementOfNP is false but no employee elements are present",
                           expected="at least one employee", actual="none"))

    for employee in employees:
        base = path_of(employee)
        ssn = text_at(employee, "ssn")
        name_node = kid(employee, "name")

        if name_node is not None:
            identifier = name_node.attrs.get("id")
            if not identifier:
                out.append(finding(R["ca.name.idAttribute"], path=f"{base}/name@id", line=name_node.line,
                                   message="the name element carries no id attribute",
                                   expected='id="SSN::NAME"', actual="(absent)"))
            else:
                parts = identifier.split("::")
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    out.append(finding(R["ca.name.idAttribute"], path=f"{base}/name@id", line=name_node.line,
                                       message="the name id attribute is not in SSN::NAME form",
                                       expected='id="SSN::NAME"', actual=identifier))
                else:
                    if parts[1] != parts[1].upper():
                        out.append(finding(R["ca.name.idAttribute"], path=f"{base}/name@id", line=name_node.line,
                                           message="the NAME portion of the id attribute is not upper-case",
                                           expected=parts[1].upper(), actual=parts[1]))
                    if ssn and parts[0] != ssn:
                        out.append(finding(R["ca.name.idMatchesSsn"], path=f"{base}/name@id", line=name_node.line,
                                           message="the SSN portion of the id attribute does not match the ssn element",
                                           expected=ssn, actual=parts[0]))

        payroll = kid(employee, "payroll")
        if payroll is None:
            continue

        days = kids(kid(payroll, "hrsWorkedEachDay"), "day")
        dates = [d for d in (text_at(day, "date") for day in days) if d]
        if week_ending and len(dates) == 7 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", week_ending):
            expected_days = _week(week_ending)
            if sorted(dates) != expected_days:
                out.append(finding(R["ca.days.consecutive"],
                                   path=f"{base}/payroll/hrsWorkedEachDay", line=days[0].line,
                                   message="the seven day dates are not the seven consecutive days ending on forWeekEnding",
                                   expected=", ".join(expected_days), actual=", ".join(sorted(dates))))

        totals = kid(payroll, "totHrs")
        for day_field, total_field in (("straightTime", "totHrsStraightTime"),
                                       ("overtime", "totHrsOvertime"),
                                       ("doubletime", "totHrsDoubletime")):
            summed = sum((_decimal(kid(day, day_field)) or Decimal(0)) for day in days)
            stated = _decimal(kid(totals, total_field))
            if stated is not None and abs(summed - stated) >= TOLERANCE:
                out.append(finding(R["ca.totals.matchDays"],
                                   path=f"{base}/payroll/totHrs/{total_field}",
                                   line=kid(totals, total_field).line,
                                   message=f"{total_field} does not equal the sum of the per-day {day_field} values",
                                   expected=f"{summed}", actual=f"{stated}"))

        deductions = kid(payroll, "deductionsContribPay")
        if deductions is not None:
            summed = sum((_decimal(kid(deductions, n)) or Decimal(0)) for n in DEDUCTION_ITEMS)
            stated = _decimal(kid(deductions, "total"))
            if stated is not None and abs(summed - stated) >= TOLERANCE:
                out.append(finding(R["ca.deductions.totalMatchesItems"],
                                   path=f"{base}/payroll/deductionsContribPay/total",
                                   line=kid(deductions, "total").line,
                                   message="total does not equal the sum of the itemised deductions and contributions",
                                   expected=f"{summed:.2f}", actual=f"{stated:.2f}"))

        gross = kid(payroll, "grossAmountEarned")
        this_project = _decimal(kid(gross, "thisProject"))
        all_work = _decimal(kid(gross, "allWork"))
        if this_project is not None and all_work is not None and this_project > all_work + TOLERANCE:
            out.append(finding(R["ca.gross.projectNotAboveAll"],
                               path=f"{base}/payroll/grossAmountEarned", line=gross.line,
                               message="thisProject exceeds allWork",
                               expected=f"at most {all_work:.2f}", actual=f"{this_project:.2f}"))

    if filename:
        naming = format_data("ca-ecpr")["fileNaming"]
        if not re.fullmatch(naming["regex"].lstrip("^").rstrip("$"), filename):
            out.append(finding(R["ca.filename.convention"], path=None, line=None,
                               message="the filename does not follow the convention in the eCPR XML guideline",
                               expected=naming["example"], actual=filename))

    return summarize(out)
