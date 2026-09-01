"""One test per documented rule the schema cannot enforce.

Mirrors js/test/validate-rules.test.js. A file can pass XSD validation and fail every
one of these.
"""

import re
import unittest

from certified_payroll_formats import validate_ca_ecpr, validate_ny_cert_payroll
from helpers import count, first, fixture, ids, mutate


def ca(edits=(), **kwargs):
    return validate_ca_ecpr(mutate(fixture("ca", "valid.xml"), edits), **kwargs)


def ny(edits=(), **kwargs):
    return validate_ny_cert_payroll(mutate(fixture("ny", "valid.xml"), edits), **kwargs)


CA_EMPLOYEE = re.search(r" {6}<CPR:employee>.*?</CPR:employee>\n",
                        fixture("ca", "valid.xml"), re.S).group(0)
NY_WORK_WEEK = re.search(r" {4}<employeeWorkWeek>.*?</employeeWorkWeek>\n",
                         fixture("ny", "valid.xml"), re.S).group(0)


class California(unittest.TestCase):
    def test_contract_agency_may_not_be_empty(self):
        result = ca([("<CPR:contractAgency>CA-DIR</CPR:contractAgency>",
                      "<CPR:contractAgency></CPR:contractAgency>")])
        self.assertIn("ca.projectInfo.mandatory", ids(result))

    def test_empty_project_id_needs_the_full_lookup_fallback(self):
        without_id = [("<CPR:projectID>9</CPR:projectID>", "<CPR:projectID></CPR:projectID>")]
        self.assertIn("ca.projectInfo.mandatory", ids(ca(without_id)))
        with_fallback = ca(without_id + [
            ("<CPR:awardingBodyID></CPR:awardingBodyID>", "<CPR:awardingBodyID>123456789</CPR:awardingBodyID>"),
            ("<CPR:projectNum></CPR:projectNum>", "<CPR:projectNum>PN-1</CPR:projectNum>"),
            ("<CPR:contractID></CPR:contractID>", "<CPR:contractID>C-1</CPR:contractID>"),
        ])
        self.assertNotIn("ca.projectInfo.mandatory", ids(with_fallback))

    def test_statement_of_non_performance_carries_no_employees(self):
        clean = ca([("<CPR:statementOfNP>false</CPR:statementOfNP>",
                     "<CPR:statementOfNP>true</CPR:statementOfNP>"), (CA_EMPLOYEE, "")])
        self.assertEqual(ids(clean), [])
        self.assertEqual(ids(ca([(CA_EMPLOYEE, "")])), ["ca.statementOfNP.noEmployees"])

    def test_name_id_attribute_form(self):
        self.assertIn("ca.name.idAttribute", ids(ca([(' id="111223333::JANE EXAMPLE"', "")])))
        self.assertIn("ca.name.idAttribute",
                      ids(ca([('id="111223333::JANE EXAMPLE"', 'id="JANE EXAMPLE"')])))
        self.assertIn("ca.name.idAttribute",
                      ids(ca([('id="111223333::JANE EXAMPLE"', 'id="111223333::"')])))

    def test_name_id_ssn_must_match_the_ssn_element(self):
        result = ca([('id="111223333::JANE EXAMPLE"', 'id="999887777::JANE EXAMPLE"')])
        self.assertEqual(ids(result), ["ca.name.idMatchesSsn"])
        self.assertEqual(first(result, "ca.name.idMatchesSsn")["expected"], "111223333")

    def test_days_must_be_the_week_ending_on_for_week_ending(self):
        self.assertEqual(ids(ca([("<CPR:date>2026-08-22</CPR:date>",
                                  "<CPR:date>2026-08-15</CPR:date>")])), ["ca.days.consecutive"])
        self.assertEqual(ids(ca([("<CPR:date>2026-08-22</CPR:date>",
                                  "<CPR:date>2026-08-23</CPR:date>")])), ["ca.days.consecutive"])

    def test_each_weekly_total_is_checked_against_its_own_column(self):
        self.assertEqual(ids(ca([("<CPR:totHrsOvertime>1.0</CPR:totHrsOvertime>",
                                  "<CPR:totHrsOvertime>3.0</CPR:totHrsOvertime>")])),
                         ["ca.totals.matchDays"])
        self.assertEqual(ids(ca([("<CPR:totHrsDoubletime>0.0</CPR:totHrsDoubletime>",
                                  "<CPR:totHrsDoubletime>2.0</CPR:totHrsDoubletime>")])),
                         ["ca.totals.matchDays"])

    def test_deduction_total_is_the_sum_of_the_lines(self):
        result = ca([("<CPR:SDI>13.70</CPR:SDI>", "<CPR:SDI>20.00</CPR:SDI>")])
        self.assertEqual(ids(result), ["ca.deductions.totalMatchesItems"])
        self.assertEqual(first(result, "ca.deductions.totalMatchesItems")["expected"], "305.24")

    def test_this_project_cannot_exceed_all_work(self):
        self.assertEqual(ids(ca([("<CPR:allWork>1245.00</CPR:allWork>",
                                  "<CPR:allWork>1000.00</CPR:allWork>")])),
                         ["ca.gross.projectNotAboveAll"])
        self.assertEqual(ids(ca([("<CPR:allWork>1245.00</CPR:allWork>",
                                  "<CPR:allWork>2000.00</CPR:allWork>")])), [])

    def test_filename_convention(self):
        self.assertEqual(ids(ca(filename="6789_DIR001_010915.xml")), [])
        result = ca(filename="payroll.xml")
        self.assertEqual(ids(result), ["ca.filename.convention"])
        self.assertEqual(first(result, "ca.filename.convention")["severity"], "advisory")


class NewYork(unittest.TestCase):
    def test_exactly_one_identifier(self):
        self.assertEqual(ids(ny([("        <ssnLast4>0323</ssnLast4>\n", "")])),
                         ["ny.employee.exactlyOneIdentifier"])
        self.assertEqual(ids(ny([("<ssnLast4>0323</ssnLast4>",
                                  "<dateOfBirth>1984-02-09</dateOfBirth>\n        "
                                  "<ssnLast4>0323</ssnLast4>")])),
                         ["ny.employee.exactlyOneIdentifier"])
        self.assertEqual(ids(ny([("<ssnLast4>0323</ssnLast4>",
                                  "<dateOfBirth>1984-02-09</dateOfBirth>")])), [])

    def test_state_must_be_a_full_name(self):
        self.assertEqual(ids(ny([("<state>New York</state>", "<state>NY</state>")])),
                         ["ny.address.stateFullName"])
        for value in ["New York", "California", "Puerto Rico"]:
            with self.subTest(value=value):
                self.assertEqual(ids(ny([("<state>New York</state>", f"<state>{value}</state>")])), [])

    def test_a_two_letter_non_state_is_left_alone(self):
        self.assertEqual(ids(ny([("<state>New York</state>", "<state>Ox</state>")])), [])

    def test_duplicate_employee(self):
        result = ny([(NY_WORK_WEEK, NY_WORK_WEEK + NY_WORK_WEEK)])
        self.assertEqual(count(result, "ny.employee.noDuplicates"), 1)
        self.assertIn("already appears in the file at line",
                      first(result, "ny.employee.noDuplicates")["message"])

    def test_day_outside_the_window_and_repeated_inside_it(self):
        self.assertEqual(ids(ny([("<day>2026-07-27</day>", "<day>2026-07-20</day>")])),
                         ["ny.days.withinWeek"])
        repeated = ny([("<day>2026-07-27</day>", "<day>2026-07-28</day>")])
        self.assertEqual(count(repeated, "ny.days.withinWeek"), 1)
        self.assertIn("repeats", first(repeated, "ny.days.withinWeek")["message"])

    def test_the_window_is_inclusive_of_both_ends(self):
        self.assertEqual(ids(ny()), [])
        self.assertEqual(ids(ny([("<day>2026-07-29</day>", "<day>2026-08-02</day>")])), [])
        self.assertEqual(ids(ny([("<day>2026-07-29</day>", "<day>2026-08-03</day>")])),
                         ["ny.days.withinWeek"])

    def test_schema_facets_carry_the_undocumented_limits(self):
        self.assertIn("schema.pattern", ids(ny([("<amount>150.00</amount>",
                                                 "<amount>12000.00</amount>")])))
        self.assertIn("schema.pattern", ids(ny([("<postalCode>12207</postalCode>",
                                                 "<postalCode>1220</postalCode>")])))
        self.assertIn("schema.missingElement",
                      ids(ny([("        <country>United States</country>\n", "")])))

    def test_the_five_hundred_record_cap(self):
        many = "<employeeWorkWeeks>" + "<employeeWorkWeek/>" * 501 + "</employeeWorkWeeks>"
        source = re.sub(r"<employeeWorkWeeks>.*</employeeWorkWeeks>", many,
                        fixture("ny", "valid.xml"), flags=re.S)
        self.assertIn("schema.tooManyElements", ids(validate_ny_cert_payroll(source)))

    def test_filename_must_end_in_xml(self):
        self.assertEqual(ids(ny(filename="week.txt")), ["ny.filename.extension"])
        self.assertEqual(ids(ny(filename="WEEK.XML")), [])


class Shared(unittest.TestCase):
    def test_findings_are_ordered_by_severity(self):
        result = ca([("<CPR:licenseType>CSLB</CPR:licenseType>",
                      "<CPR:licenseType>STATE</CPR:licenseType>"),
                     ("<CPR:allWork>1245.00</CPR:allWork>", "<CPR:allWork>1000.00</CPR:allWork>")],
                    filename="payroll.xml")
        order = {"error": 0, "warning": 1, "advisory": 2}
        severities = [f["severity"] for f in result["findings"]]
        self.assertEqual(severities, sorted(severities, key=lambda s: order[s]))
        self.assertEqual(result["counts"], {"error": 1, "warning": 1, "advisory": 1})
        self.assertFalse(result["valid"], "valid tracks errors only")

    def test_warnings_alone_leave_the_file_valid(self):
        result = ca(filename="payroll.xml")
        self.assertEqual(result["counts"]["advisory"], 1)
        self.assertTrue(result["valid"])

    def test_findings_carry_line_numbers(self):
        for f in ca([("<CPR:licenseType>CSLB</CPR:licenseType>",
                      "<CPR:licenseType>STATE</CPR:licenseType>")])["findings"]:
            self.assertIsInstance(f["line"], int)
            self.assertGreater(f["line"], 0)
        self.assertIsNone(first(ca(filename="x.xml"), "ca.filename.convention")["line"])


if __name__ == "__main__":
    unittest.main()
