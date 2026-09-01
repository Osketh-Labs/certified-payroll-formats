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


class Edges(unittest.TestCase):
    def test_sparse_or_empty_records_are_handled(self):
        for record in ({}, {"workers": []}, {"workers": [{}]},
                       {"project": {}, "workers": [{"entryNo": 1}]}):
            with self.subTest(record=record):
                check_wh347(record)
                to_wh347(record)
        self.assertEqual(check_wh347({"workers": [{}]})["findings"], [],
                         "a worker with no entry number is not a broken sequence")
        self.assertEqual(total_hours({}), 0)

    def test_two_workers_may_not_share_an_entry_number(self):
        record = base()
        second = dict(record["workers"][0])
        second.update({"entryNo": 1, "lastName": "Other", "firstName": "Sam",
                       "identifyingNumber": "4444"})
        record["workers"].append(second)
        self.assertIn("wh347.column1A.entryNoPerWorker", ids(record))

    def test_entry_numbers_run_from_one(self):
        record = base()
        record["workers"][0]["entryNo"] = 2
        hit = next(f for f in check_wh347(record)["findings"]
                   if f["ruleId"] == "wh347.column1A.sequential")
        self.assertEqual(hit["severity"], "warning")
        self.assertEqual(hit["expected"], "1")

    def test_payroll_number_below_one(self):
        record = base()
        record["payroll"]["number"] = 0
        self.assertIn("wh347.header.payrollNumber", ids(record))

    def test_column_7a_may_not_exceed_7b(self):
        record = base()
        record["workers"][0]["grossThisProject"] = 1500
        self.assertIn("wh347.column7.projectNotAboveAll", ids(record))

    def test_cash_in_lieu_rate_drives_column_6c(self):
        record = base()
        record["workers"][0].update({"fringeCredit": 0, "hourlyFringeCredit": 0,
                                     "cashInLieu": 150, "hourlyCashInLieu": 5})
        self.assertIn("wh347.column6C.matchesCashRate", ids(record))

    def test_fringe_met_entirely_in_cash_means_box_five_with_a_blank_table(self):
        record = base()
        record["workers"][0].update({"fringeCredit": 0, "hourlyFringeCredit": 0,
                                     "cashInLieu": 200, "hourlyCashInLieu": 5})
        record["fringePlans"] = [{"name": "Example Health Trust", "type": "health", "funded": True}]
        self.assertIn("wh347.pageTwo.box5CashOnly", ids(record))
        page_two = to_wh347(record)["pageTwo"]
        self.assertTrue(page_two["checkboxes"][5])
        self.assertEqual(page_two["box5Table"], [])

    def test_an_apprentice_populates_box_four(self):
        record = base()
        record["workers"][0].update({"status": "RA", "apprenticeLevel": "3rd period"})
        record["apprenticePrograms"] = [{"program": "Example JATC", "classification": "Carrier Driver"}]
        rendered = to_wh347(record)
        self.assertEqual(rendered["rows"][0]["2"], "RA (3rd period)")
        self.assertTrue(rendered["pageTwo"]["checkboxes"][4])
        self.assertEqual(rendered["pageTwo"]["box4"], record["apprenticePrograms"])
        self.assertEqual(check_wh347(record)["findings"], [])

    def test_addendum_thresholds(self):
        record = base()
        record["apprenticePrograms"] = [{"program": f"P{i}", "classification": "x"} for i in range(4)]
        record["fringePlans"] = [{"name": f"Plan {i}"} for i in range(7)]
        found = ids(record)
        self.assertIn("wh347.pageTwo.box4Addendum", found)
        self.assertIn("wh347.pageTwo.box5Addendum", found)
        addenda = to_wh347(record)["pageTwo"]["addenda"]
        self.assertTrue(addenda["box4Required"])
        self.assertTrue(addenda["box5Required"])

    def test_several_wage_determinations_are_all_listed(self):
        record = base()
        record["project"]["wageDeterminations"] = [
            {"number": "CA20260001", "revision": "3"},
            {"number": "CA20260002", "revision": "1"},
        ]
        self.assertEqual(to_wh347(record)["header"]["wageDeterminationNumber"],
                         "CA20260001 rev. 3; CA20260002 rev. 1")
        self.assertEqual(check_wh347(record)["findings"], [])

    def test_nine_digit_identifier_however_punctuated(self):
        for value in ("111223333", "111-22-3333", "111 22 3333"):
            record = base()
            record["workers"][0]["identifyingNumber"] = value
            with self.subTest(value=value):
                self.assertIn("wh347.column1E.notFullSsn", ids(record))
        for value in ("3333", "EMP-00042", "12345678"):
            record = base()
            record["workers"][0]["identifyingNumber"] = value
            with self.subTest(value=value):
                self.assertNotIn("wh347.column1E.notFullSsn", ids(record))

    def test_deduction_arithmetic_includes_itemised_other_lines(self):
        record = base()
        record["workers"][0]["deductions"] = {
            "taxWithholdings": 190, "fica": 91.8,
            "other": [{"name": "Union dues", "amount": 25}, {"name": "Garnishment", "amount": 30}],
            "total": 336.8,
        }
        record["workers"][0]["netPay"] = 863.2
        self.assertEqual(check_wh347(record)["findings"], [])
        record["workers"][0]["deductions"]["total"] = 281.8
        self.assertIn("wh347.column8.totalMatchesItems", ids(record))

    def test_every_finding_cites_the_whd_instructions(self):
        record = base()
        record["workers"][0]["identifyingNumber"] = "111223333"
        for f in check_wh347(record)["findings"]:
            self.assertTrue(f["sources"])
            self.assertTrue(any("dol.gov" in s["url"] or "ecfr.gov" in s["url"] for s in f["sources"]))
