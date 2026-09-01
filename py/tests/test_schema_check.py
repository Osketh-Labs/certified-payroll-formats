"""Structural validation against the extracted schemas. Mirrors js/test/schema-check.test.js."""

import unittest

from certified_payroll_formats import validate_ca_ecpr, validate_ny_cert_payroll
from certified_payroll_formats.schema_check import check_against_schema, is_calendar_date
from certified_payroll_formats.xml_reader import parse_xml
from helpers import first, fixture, ids, mutate


def ca(edits=(), **kwargs):
    return validate_ca_ecpr(mutate(fixture("ca", "valid.xml"), edits), **kwargs)


def ny(edits=(), **kwargs):
    return validate_ny_cert_payroll(mutate(fixture("ny", "valid.xml"), edits), **kwargs)


class CalendarDates(unittest.TestCase):
    def test_month_lengths_and_the_leap_rule(self):
        self.assertTrue(is_calendar_date(2026, 1, 31))
        self.assertFalse(is_calendar_date(2026, 4, 31), "April has 30 days")
        self.assertFalse(is_calendar_date(2026, 2, 29), "2026 is not a leap year")
        self.assertTrue(is_calendar_date(2024, 2, 29), "2024 is")
        self.assertFalse(is_calendar_date(1900, 2, 29), "a century that is not a leap year")
        self.assertTrue(is_calendar_date(2000, 2, 29), "a century that is")
        self.assertFalse(is_calendar_date(2026, 13, 1))
        self.assertFalse(is_calendar_date(2026, 0, 1))
        self.assertFalse(is_calendar_date(2026, 1, 0))

    def test_pattern_shaped_non_date_is_a_type_error(self):
        result = ca([("<CPR:forWeekEnding>2026-08-28</CPR:forWeekEnding>",
                      "<CPR:forWeekEnding>2026-13-45</CPR:forWeekEnding>")])
        self.assertEqual(ids(result), ["schema.type"])
        self.assertIn("xs:date", first(result, "schema.type")["message"])

    def test_impossible_date_does_not_manufacture_window_findings(self):
        result = ny([("2026-08-02T00:00:00.000Z", "2026-13-45T00:00:00.000Z")])
        self.assertEqual(ids(result), ["schema.type"])


class Facets(unittest.TestCase):
    def test_empty_element_is_not_a_valid_decimal_or_date(self):
        for old, new in [
            ("<CPR:totHrsStraightTime>40.0</CPR:totHrsStraightTime>",
             "<CPR:totHrsStraightTime></CPR:totHrsStraightTime>"),
            ("<CPR:forWeekEnding>2026-08-28</CPR:forWeekEnding>",
             "<CPR:forWeekEnding></CPR:forWeekEnding>"),
        ]:
            with self.subTest(element=old):
                result = ca([(old, new)])
                self.assertIn("schema.type", ids(result))
                self.assertIn("empty", first(result, "schema.type")["message"])

    def test_empty_pattern_constrained_string_fails_the_pattern(self):
        # California declares statementOfNP as xs:string with pattern true|false rather
        # than xs:boolean, so an empty value is a pattern failure.
        result = ca([("<CPR:statementOfNP>false</CPR:statementOfNP>",
                      "<CPR:statementOfNP></CPR:statementOfNP>")])
        self.assertEqual(ids(result), ["schema.pattern"])

    def test_empty_numeric_does_not_produce_a_phantom_arithmetic_finding(self):
        result = ca([("<CPR:totHrsStraightTime>40.0</CPR:totHrsStraightTime>",
                      "<CPR:totHrsStraightTime></CPR:totHrsStraightTime>")])
        self.assertNotIn("ca.totals.matchDays", ids(result))

    def test_enumerated_values(self):
        bad = ny([("<type>Health/Welfare</type>", "<type>Health and Welfare</type>")])
        self.assertEqual(ids(bad), ["schema.enumeration"])
        self.assertIn("Vacation/Holiday", first(bad, "schema.enumeration")["expected"])
        for value in ["Health/Welfare", "Vacation/Holiday", "Apprenticeship/Training",
                      "Pension", "Other Benefit (Type)"]:
            with self.subTest(value=value):
                self.assertEqual(ids(ny([("<type>Health/Welfare</type>", f"<type>{value}</type>")])), [])

    def test_patterns_lengths_and_ranges(self):
        self.assertEqual(ids(ca([("<CPR:contractorFEIN>123456789</CPR:contractorFEIN>",
                                  "<CPR:contractorFEIN>12-3456789</CPR:contractorFEIN>")])),
                         ["schema.pattern"])
        self.assertEqual(ids(ca([("<CPR:licenseType>CSLB</CPR:licenseType>",
                                  "<CPR:licenseType>cslb</CPR:licenseType>")])),
                         ["schema.pattern"], "the pattern is case sensitive")
        self.assertIn("schema.length", ids(ca([("<CPR:city>Sacramento</CPR:city>",
                                                f"<CPR:city>{'x' * 26}</CPR:city>")])))
        self.assertIn("schema.range", ids(ny([("<standardTimeHours>8.00</standardTimeHours>",
                                               "<standardTimeHours>25.00</standardTimeHours>")])))
        self.assertIn("schema.fractionDigits", ids(ny([("<stHourlyRate>35.50</stHourlyRate>",
                                                        "<stHourlyRate>35.505</stHourlyRate>")])))

    def test_fixed_elements_must_be_present_and_empty(self):
        self.assertEqual(ids(ca([("<CPR:awardingBody></CPR:awardingBody>",
                                  "<CPR:awardingBody>City of Example</CPR:awardingBody>")])),
                         ["schema.fixedValue"])
        self.assertEqual(ids(ca([("    <CPR:awardingBody></CPR:awardingBody>\n", "")])),
                         ["schema.missingElement"])


class Structure(unittest.TestCase):
    DAY = ('<CPR:day id="7"><CPR:date>2026-08-28</CPR:date><CPR:straightTime>8.0</CPR:straightTime>'
           "<CPR:overtime>0.0</CPR:overtime><CPR:doubletime>0.0</CPR:doubletime></CPR:day>")

    def test_occurrence_limits_in_both_directions(self):
        self.assertIn("schema.missingElement", ids(ca([(self.DAY, "")])))
        self.assertIn("schema.tooManyElements", ids(ca([(self.DAY, self.DAY + self.DAY)])))

    def test_undeclared_element_is_reported(self):
        result = ca([("<CPR:checkNum>1001</CPR:checkNum>",
                      "<CPR:checkNum>1001</CPR:checkNum><CPR:bonus>50.00</CPR:bonus>")])
        self.assertIn("schema.unexpectedElement", ids(result))

    def test_out_of_sequence_is_reported_once(self):
        result = ca([("<CPR:netWagePaidWeek>946.06</CPR:netWagePaidWeek>\n          "
                      "<CPR:checkNum>1001</CPR:checkNum>",
                      "<CPR:checkNum>1001</CPR:checkNum>\n          "
                      "<CPR:netWagePaidWeek>946.06</CPR:netWagePaidWeek>")])
        self.assertEqual(ids(result), ["schema.elementOrder"])

    def test_wrong_document_element_short_circuits(self):
        root = parse_xml('<CPR:notTheRoot xmlns:CPR="urn:x"><a/></CPR:notTheRoot>')
        findings = check_against_schema(root, "ca-ecpr", "urn:x")
        self.assertEqual(len(findings), 1)
        self.assertIn("document element must be <eCPR>", findings[0]["message"])

    def test_namespace_check_can_be_delegated(self):
        root = parse_xml('<eCPR xmlns="urn:wrong"/>')
        self.assertTrue(any(f["ruleId"] == "schema.namespace"
                            for f in check_against_schema(root, "ca-ecpr", "urn:right")))
        self.assertFalse(any(f["ruleId"] == "schema.namespace"
                             for f in check_against_schema(root, "ca-ecpr", "urn:right",
                                                           report_namespace=False)))

    def test_schema_findings_cite_the_schema(self):
        result = ca([("<CPR:contractorFEIN>123456789</CPR:contractorFEIN>",
                      "<CPR:contractorFEIN>x</CPR:contractorFEIN>")])
        source = first(result, "schema.pattern")["sources"][0]
        self.assertEqual(source["id"], "ca-dir-xsd")
        self.assertEqual(source["kind"], "schema")


if __name__ == "__main__":
    unittest.main()
