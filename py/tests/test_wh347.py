"""WH-347 mapping and checks. Mirrors js/test/wh347.test.js."""

import copy
import unittest

from certified_payroll_formats import check_wh347, field_map, to_wh347, total_hours


def week(straight, overtime=(0, 0, 0, 0, 0, 0, 0)):
    return [{"date": f"2026-08-{24 + i:02d}", "straightTime": h, "overtime": overtime[i]}
            for i, h in enumerate(straight)]


def base():
    return {
        "project": {
            "name": "Example Overpass Rehabilitation",
            "number": "DTFH-2026-0001",
            "location": "Sacramento County, CA",
            "wageDeterminations": [{"number": "CA20260001", "revision": "3"}],
        },
        "contractor": {"name": "Example Mechanical Inc",
                       "address": "1 Example Way, Sacramento CA 95814",
                       "role": "subcontractor"},
        "payroll": {"number": 4, "weekEndingDate": "2026-08-28", "final": False},
        "workers": [{
            "entryNo": 1,
            "lastName": "Example", "firstName": "Jane", "middleInitial": "Q",
            "identifyingNumber": "3333",
            "status": "J",
            "classification": "Carrier Driver",
            "days": week([8, 8, 8, 8, 8, 0, 0]),
            "rate": {"straightTime": 30, "overtime": 45},
            "fringeCredit": 200, "hourlyFringeCredit": 5,
            "cashInLieu": 0,
            "grossThisProject": 1200, "grossAllWork": 1200,
            "deductions": {"taxWithholdings": 190, "fica": 91.8, "other": [], "total": 281.8},
            "netPay": 918.2,
        }],
    }


def ids(record):
    return [f["ruleId"] for f in check_wh347(record)["findings"]]


class Wh347(unittest.TestCase):
    def test_total_hours_is_the_sum_of_column_4(self):
        self.assertEqual(total_hours(base()["workers"][0]), 40)

    def test_a_clean_record_produces_no_findings(self):
        result = check_wh347(base())
        self.assertEqual(result["findings"], [])
        self.assertTrue(result["valid"])

    def test_column_values_follow_the_2025_numbering(self):
        rendered = to_wh347(base())
        self.assertEqual(rendered["header"]["wageDeterminationNumber"], "CA20260001 rev. 3")
        row = rendered["rows"][0]
        self.assertEqual(row["1B"], "Example")
        self.assertEqual(row["1C"], "Jane")
        self.assertEqual(row["1D"], "Q")
        self.assertEqual(row["1E"], "3333")
        self.assertEqual(row["5"], 40)
        self.assertEqual(row["6B"], 200)
        self.assertEqual(row["6C"], 0)
        self.assertEqual(row["9"], 918.2)
        self.assertTrue(rendered["pageTwo"]["checkboxes"][1])
        self.assertFalse(rendered["pageTwo"]["checkboxes"][4])
        self.assertEqual(rendered["pageTwo"]["box4"], "Not Applicable")

    def test_full_ssn_in_column_1e_is_an_error(self):
        record = base()
        record["workers"][0]["identifyingNumber"] = "111-22-3333"
        self.assertIn("wh347.column1E.notFullSsn", ids(record))

    def test_deduction_and_net_pay_arithmetic(self):
        record = base()
        record["workers"][0]["deductions"]["total"] = 250
        found = ids(record)
        self.assertIn("wh347.column8.totalMatchesItems", found)
        self.assertIn("wh347.column9.netMatchesGrossLessDeductions", found)

    def test_registered_apprentice_needs_a_level_of_progression(self):
        record = base()
        record["workers"][0]["status"] = "RA"
        self.assertIn("wh347.column2.apprenticeLevel", ids(record))
        self.assertEqual(to_wh347(record)["rows"][0]["2"], "RA")

    def test_split_classification_rows_share_one_entry_number(self):
        record = base()
        second = copy.deepcopy(record["workers"][0])
        second["entryNo"] = 2
        second["classification"] = "Laborer"
        second["days"] = week([0, 0, 0, 0, 0, 4, 0])
        record["workers"].append(second)
        self.assertIn("wh347.column1A.entryNoPerWorker", ids(record))

        record["workers"][1]["entryNo"] = 1
        self.assertNotIn("wh347.column1A.entryNoPerWorker", ids(record))

    def test_over_forty_straight_time_hours_with_no_overtime(self):
        record = base()
        worker = record["workers"][0]
        worker["days"] = week([10, 10, 10, 10, 8, 0, 0])
        worker["fringeCredit"] = 240
        worker["grossThisProject"] = 1440
        worker["grossAllWork"] = 1440
        worker["netPay"] = 1158.2
        self.assertIn("wh347.column4.overtimeThreshold", ids(record))

    def test_stated_weekly_total_is_checked_against_column_4(self):
        record = base()
        record["workers"][0]["statedTotalHours"] = 45
        self.assertIn("wh347.column5.matchesColumn4", ids(record))

    def test_wage_determination_without_a_revision_is_a_warning(self):
        record = base()
        del record["project"]["wageDeterminations"][0]["revision"]
        hit = next(f for f in check_wh347(record)["findings"]
                   if f["ruleId"] == "wh347.header.wageDeterminationRevision")
        self.assertEqual(hit["severity"], "warning")

    def test_fringe_credit_is_checked_against_the_page_two_rate(self):
        record = base()
        record["workers"][0]["fringeCredit"] = 175
        self.assertIn("wh347.column6B.matchesFringeTable", ids(record))

    def test_field_map_exposes_the_form_identity(self):
        form = field_map()["form"]
        self.assertEqual(form["expires"], "2028-01-31")
        self.assertFalse(form["required"])


if __name__ == "__main__":
    unittest.main()
