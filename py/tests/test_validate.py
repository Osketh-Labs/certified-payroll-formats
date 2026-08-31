"""Validator behaviour, checked against the fixtures in fixtures/.

These mirror js/test/validate.test.js one for one: the two implementations must agree
on which rule fires for which fault.
"""

import unittest
from pathlib import Path

from certified_payroll_formats import validate_ca_ecpr, validate_ny_cert_payroll

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def read(*parts) -> str:
    return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


def ids(result) -> list:
    return [f["ruleId"] for f in result["findings"]]


class California(unittest.TestCase):
    def test_valid_fixture_produces_no_findings(self):
        result = validate_ca_ecpr(read("ca", "valid.xml"), filename="6789_9_082826.xml")
        self.assertEqual(result["findings"], [])
        self.assertTrue(result["valid"])

    def test_invalid_fixture_produces_one_finding_per_seeded_fault(self):
        result = validate_ca_ecpr(read("ca", "invalid.xml"), filename="invalid.xml")
        found = ids(result)
        for expected in [
            "schema.pattern",            # licenseType outside CSLB|PL|OTHER
            "schema.fixedValue",         # projectName is declared fixed=""
            "ca.statementOfNP.noEmployees",
            "ca.name.idAttribute",
            "ca.name.idMatchesSsn",
            "ca.days.consecutive",
            "ca.totals.matchDays",
            "ca.deductions.totalMatchesItems",
            "ca.gross.projectNotAboveAll",
            "ca.filename.convention",
        ]:
            self.assertIn(expected, found)
        self.assertFalse(result["valid"])

    def test_every_finding_cites_a_resolvable_official_source(self):
        for f in validate_ca_ecpr(read("ca", "invalid.xml"))["findings"]:
            self.assertTrue(f["sources"], f["ruleId"])
            for source in f["sources"]:
                self.assertTrue(source["url"].startswith("http"))


class NewYork(unittest.TestCase):
    def test_valid_fixture_produces_no_findings(self):
        result = validate_ny_cert_payroll(read("ny", "valid.xml"), filename="week.xml")
        self.assertEqual(result["findings"], [])

    def test_invalid_fixture_catches_what_the_xsd_cannot(self):
        found = ids(validate_ny_cert_payroll(read("ny", "invalid.xml")))
        for expected in [
            "ny.employee.exactlyOneIdentifier",
            "ny.address.stateFullName",
            "ny.days.withinWeek",
            "schema.pattern",            # bare weekEndingDate, oversized deduction amount
            "schema.type",               # nysRegisteredApprentice sent as Y
            "schema.missingElement",     # country omitted
        ]:
            self.assertIn(expected, found)
        self.assertEqual(found.count("ny.employee.exactlyOneIdentifier"), 2,
                         "one for the employee carrying both, one for the employee carrying neither")

    def test_namespaced_instance_is_reported_once(self):
        result = validate_ny_cert_payroll(read("ny", "invalid-namespace.xml"))
        self.assertEqual(ids(result), ["ny.root.noNamespace"])


class Malformed(unittest.TestCase):
    def test_malformed_xml_yields_one_parse_finding(self):
        ca = validate_ca_ecpr("<CPR:eCPR><oops>")
        self.assertEqual([f["ruleId"] for f in ca["findings"]], ["ca.parse"])
        ny = validate_ny_cert_payroll("not xml at all")
        self.assertEqual(ny["findings"][0]["ruleId"], "ny.parse")

    def test_doctype_is_refused_not_expanded(self):
        result = validate_ny_cert_payroll('<!DOCTYPE ProjectRollup [<!ENTITY a "b">]><ProjectRollup/>')
        self.assertEqual(result["findings"][0]["ruleId"], "ny.parse")
        self.assertIn("DOCTYPE", result["findings"][0]["message"])


if __name__ == "__main__":
    unittest.main()
