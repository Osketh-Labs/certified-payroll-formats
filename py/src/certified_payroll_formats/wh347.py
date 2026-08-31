"""WH-347 (revised January 2025): map a canonical weekly payroll record onto the form's
columns, and check the record against the rules in WHD's instructions.

The canonical record is a plain dict::

    {
      "project": {"name", "number", "location", "wageDeterminations": [{"number", "revision"}]},
      "contractor": {"name", "address", "role": "prime" | "subcontractor"},
      "payroll": {"number", "weekEndingDate", "final"},
      "workers": [{
        "entryNo", "lastName", "firstName", "middleInitial", "identifyingNumber",
        "status": "J" | "RA", "apprenticeLevel", "classification",
        "days": [{"date", "straightTime", "overtime"}],
        "rate": {"straightTime", "overtime"},
        "fringeCredit", "cashInLieu", "hourlyFringeCredit", "hourlyCashInLieu",
        "grossThisProject", "grossAllWork",
        "deductions": {"taxWithholdings", "fica", "other": [{"name", "amount"}], "total"},
        "netPay", "statedTotalHours",
      }],
      "fringePlans": [...], "apprenticePrograms": [...],
    }
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from .data import wh347_data
from .finding import finding, summarize

TOLERANCE = Decimal("0.005")


@lru_cache(maxsize=None)
def _checks() -> dict:
    return {c["id"]: c for c in wh347_data()["checks"]}


def _dec(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def field_map() -> dict:
    """The published field map: header fields, columns 1A–9, page 2, and the rule lists."""
    return wh347_data()


def total_hours(worker: dict) -> Decimal:
    """Total hours for a worker row — column 5."""
    return sum((_dec(d.get("straightTime")) + _dec(d.get("overtime"))
                for d in worker.get("days", [])), Decimal(0))


def to_wh347(record: dict) -> dict:
    """Render a canonical record as WH-347 column values."""
    project = record.get("project", {})
    contractor = record.get("contractor", {})
    payroll = record.get("payroll", {})
    workers = record.get("workers", [])

    determinations = "; ".join(
        f'{wd["number"]} rev. {wd["revision"]}' if wd.get("revision") else wd["number"]
        for wd in project.get("wageDeterminations", [])
    ) or None

    header = {
        "finalPayroll": bool(payroll.get("final")),
        "role": contractor.get("role"),
        "projectName": project.get("name"),
        "projectOrContractNumber": project.get("number"),
        "payrollNumber": payroll.get("number"),
        "businessName": contractor.get("name"),
        "projectLocation": project.get("location"),
        "wageDeterminationNumber": determinations,
        "weekEndingDate": payroll.get("weekEndingDate"),
        "businessAddress": contractor.get("address"),
    }

    rows = []
    for w in workers:
        straight = sum((_dec(d.get("straightTime")) for d in w.get("days", [])), Decimal(0))
        overtime = sum((_dec(d.get("overtime")) for d in w.get("days", [])), Decimal(0))
        deductions = w.get("deductions", {}) or {}
        rows.append({
            "1A": w.get("entryNo"),
            "1B": w.get("lastName"),
            "1C": w.get("firstName"),
            "1D": w.get("middleInitial"),
            "1E": w.get("identifyingNumber"),
            "2": (f'RA ({w["apprenticeLevel"]})'
                  if w.get("status") == "RA" and w.get("apprenticeLevel") else w.get("status")),
            "3": w.get("classification"),
            "4": [{"date": d.get("date"), "ST": d.get("straightTime", 0), "OT": d.get("overtime", 0)}
                  for d in w.get("days", [])],
            "5": straight + overtime,
            "6A": {"straightTime": (w.get("rate") or {}).get("straightTime"),
                   "overtime": (w.get("rate") or {}).get("overtime")},
            "6B": w.get("fringeCredit", 0),
            "6C": w.get("cashInLieu", 0),
            "7A": w.get("grossThisProject"),
            "7B": w.get("grossAllWork"),
            "8": {"taxWithholdings": deductions.get("taxWithholdings", 0),
                  "fica": deductions.get("fica", 0),
                  "other": deductions.get("other", []),
                  "total": deductions.get("total", 0)},
            "9": w.get("netPay"),
        })

    fringe_plans = record.get("fringePlans", [])
    apprentice_programs = record.get("apprenticePrograms", [])
    any_apprentice = any(w.get("status") == "RA" for w in workers)
    any_credit = any(_dec(w.get("fringeCredit")) > 0 for w in workers)
    any_cash = any(_dec(w.get("cashInLieu")) > 0 for w in workers)

    return {
        "header": header,
        "rows": rows,
        "pageTwo": {
            "identifiers": {k: header[k] for k in
                            ("projectName", "projectOrContractNumber", "payrollNumber",
                             "businessName", "projectLocation", "weekEndingDate")},
            "checkboxes": {1: True, 2: True, 3: True, 6: True,
                           4: any_apprentice, 5: any_credit or any_cash},
            "box4": apprentice_programs if any_apprentice else "Not Applicable",
            "box5Table": [
                {"workerEntryNumber": w.get("entryNo"),
                 "workerName": ", ".join(x for x in (w.get("lastName"), w.get("firstName")) if x),
                 "plans": fringe_plans,
                 "hourlyCredit": w.get("hourlyFringeCredit")}
                for w in workers if _dec(w.get("fringeCredit")) > 0
            ] if any_credit else [],
            "addenda": {"box4Required": len(apprentice_programs) > 3,
                        "box5Required": len(fringe_plans) > 6},
        },
    }


def check_wh347(record: dict) -> dict:
    """Check a canonical record against the WH-347 instructions."""
    C = _checks()
    out: list = []
    workers = record.get("workers", [])

    payroll_number = (record.get("payroll") or {}).get("number")
    if payroll_number is not None and not (payroll_number >= 1):
        out.append(finding(C["wh347.header.payrollNumber"], path="payroll.number",
                           message="the certified payroll number must be 1 or greater",
                           expected=">= 1", actual=str(payroll_number)))
    for i, wd in enumerate((record.get("project") or {}).get("wageDeterminations", [])):
        if not wd.get("revision"):
            out.append(finding(C["wh347.header.wageDeterminationRevision"],
                               path=f"project.wageDeterminations[{i}]",
                               message=f'wage determination {wd.get("number")} carries no revision number',
                               expected="a revision number", actual="(absent)"))

    entry_to_worker: dict = {}
    worker_to_entry: dict = {}
    entry_numbers: list = []

    for i, w in enumerate(workers):
        where = f"workers[{i}]"
        identifier = str(w.get("identifyingNumber") or "")
        if identifier.replace("-", "").replace(" ", "").isdigit() \
                and len(identifier.replace("-", "").replace(" ", "")) == 9:
            out.append(finding(C["wh347.column1E.notFullSsn"], path=f"{where}.identifyingNumber",
                               message="column 1E looks like a full Social Security number",
                               expected="the last four digits, or a worker-specific number",
                               actual=identifier))
        if w.get("status") == "RA" and not w.get("apprenticeLevel"):
            out.append(finding(C["wh347.column2.apprenticeLevel"], path=f"{where}.apprenticeLevel",
                               message="a registered apprentice row carries no level of progression",
                               expected="the level of progression in the approved program",
                               actual="(absent)"))

        identity = "|".join(str(x) for x in (w.get("lastName"), w.get("firstName"),
                                             w.get("identifyingNumber"))).lower()
        entry_numbers.append(w.get("entryNo"))
        if identity in worker_to_entry and worker_to_entry[identity] != w.get("entryNo"):
            out.append(finding(C["wh347.column1A.entryNoPerWorker"], path=f"{where}.entryNo",
                               message="the same worker appears under two different entry numbers; "
                                       "classification rows share one entry number",
                               expected=str(worker_to_entry[identity]), actual=str(w.get("entryNo"))))
        worker_to_entry[identity] = w.get("entryNo")
        if w.get("entryNo") in entry_to_worker and entry_to_worker[w["entryNo"]] != identity:
            out.append(finding(C["wh347.column1A.entryNoPerWorker"], path=f"{where}.entryNo",
                               message="two different workers share one entry number",
                               expected="a distinct entry number per worker", actual=str(w.get("entryNo"))))
        entry_to_worker[w.get("entryNo")] = identity

        hours = total_hours(w)
        if w.get("statedTotalHours") is not None and abs(hours - _dec(w["statedTotalHours"])) >= TOLERANCE:
            out.append(finding(C["wh347.column5.matchesColumn4"], path=f"{where}.statedTotalHours",
                               message="the stated weekly total does not equal the sum of the daily hours in column 4",
                               expected=f"{hours:.2f}", actual=f'{_dec(w["statedTotalHours"]):.2f}'))

        straight = sum((_dec(d.get("straightTime")) for d in w.get("days", [])), Decimal(0))
        overtime = sum((_dec(d.get("overtime")) for d in w.get("days", [])), Decimal(0))
        if straight > 40 and overtime == 0:
            out.append(finding(C["wh347.column4.overtimeThreshold"], path=f"{where}.days",
                               message=f"{straight} straight-time hours with no overtime recorded",
                               expected="overtime beyond 40 hours in the week, counting hours worked off site",
                               actual=f"{straight} ST / {overtime} OT"))

        if w.get("hourlyFringeCredit") is not None and w.get("fringeCredit") is not None:
            expected = hours * _dec(w["hourlyFringeCredit"])
            if abs(expected - _dec(w["fringeCredit"])) >= TOLERANCE:
                out.append(finding(C["wh347.column6B.matchesFringeTable"], path=f"{where}.fringeCredit",
                                   message="column 6B does not equal total hours × the page 2 hourly credit",
                                   expected=f"{expected:.2f}", actual=f'{_dec(w["fringeCredit"]):.2f}'))
        if w.get("hourlyCashInLieu") is not None and w.get("cashInLieu") is not None:
            expected = hours * _dec(w["hourlyCashInLieu"])
            if abs(expected - _dec(w["cashInLieu"])) >= TOLERANCE:
                out.append(finding(C["wh347.column6C.matchesCashRate"], path=f"{where}.cashInLieu",
                                   message="column 6C does not equal total hours × the hourly cash-in-lieu rate",
                                   expected=f"{expected:.2f}", actual=f'{_dec(w["cashInLieu"]):.2f}'))

        if w.get("grossThisProject") is not None and w.get("grossAllWork") is not None \
                and _dec(w["grossThisProject"]) > _dec(w["grossAllWork"]) + TOLERANCE:
            out.append(finding(C["wh347.column7.projectNotAboveAll"], path=f"{where}.grossThisProject",
                               message="column 7A exceeds column 7B",
                               expected=f'at most {_dec(w["grossAllWork"]):.2f}',
                               actual=f'{_dec(w["grossThisProject"]):.2f}'))

        deductions = w.get("deductions")
        if deductions and deductions.get("total") is not None:
            items = (_dec(deductions.get("taxWithholdings")) + _dec(deductions.get("fica"))
                     + sum((_dec(o.get("amount")) for o in deductions.get("other", [])), Decimal(0)))
            if abs(items - _dec(deductions["total"])) >= TOLERANCE:
                out.append(finding(C["wh347.column8.totalMatchesItems"], path=f"{where}.deductions.total",
                                   message="the column 8 total does not equal the sum of its parts",
                                   expected=f"{items:.2f}", actual=f'{_dec(deductions["total"]):.2f}'))
            if w.get("grossAllWork") is not None and w.get("netPay") is not None:
                expected = _dec(w["grossAllWork"]) - _dec(deductions["total"])
                if abs(expected - _dec(w["netPay"])) >= TOLERANCE:
                    out.append(finding(C["wh347.column9.netMatchesGrossLessDeductions"],
                                       path=f"{where}.netPay",
                                       message="column 9 does not equal column 7B less the column 8 total",
                                       expected=f"{expected:.2f}", actual=f'{_dec(w["netPay"]):.2f}'))

        if _dec(w.get("fringeCredit")) == 0 and _dec(w.get("cashInLieu")) > 0 \
                and record.get("fringePlans"):
            out.append(finding(C["wh347.pageTwo.box5CashOnly"], path=f"{where}.cashInLieu",
                               message="fringe obligations are met entirely in cash for this worker, "
                                       "yet fringe plans are listed for the box 5 table",
                               expected="box 5 checked with the table left blank",
                               actual=f'{len(record["fringePlans"])} plan(s) listed'))

    unique = sorted({n for n in entry_numbers if n is not None})
    if unique and unique != list(range(1, len(unique) + 1)):
        out.append(finding(C["wh347.column1A.sequential"], path="workers[].entryNo",
                           message="worker entry numbers are not sequential from 1",
                           expected=", ".join(str(n) for n in range(1, len(unique) + 1)),
                           actual=", ".join(str(n) for n in unique)))

    if len(record.get("apprenticePrograms", [])) > 3:
        out.append(finding(C["wh347.pageTwo.box4Addendum"], path="apprenticePrograms",
                           message="more than three apprenticeship programs require an addendum to box 4",
                           expected="at most 3 on the form itself",
                           actual=str(len(record["apprenticePrograms"]))))
    if len(record.get("fringePlans", [])) > 6:
        out.append(finding(C["wh347.pageTwo.box5Addendum"], path="fringePlans",
                           message="more than six fringe benefit plans require an addendum to the box 5 table",
                           expected="at most 6 on the form itself", actual=str(len(record["fringePlans"]))))

    return summarize(out)
