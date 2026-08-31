"""The dataset's own invariants: every claim resolves to a source that exists."""

import json
import unittest
from pathlib import Path

from certified_payroll_formats import data

DATA_DIR = data.DATA_DIR
FORMATS = ["ca-ecpr", "ny-certpayroll", "wa-pwia"]


def _collect_source_ids(node, found):
    if isinstance(node, list):
        for item in node:
            _collect_source_ids(item, found)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == "sources" and isinstance(value, list):
                found.update(v for v in value if isinstance(v, str))
            elif key.endswith("Says") and isinstance(value, dict) and isinstance(value.get("source"), str):
                found.add(value["source"])
            else:
                _collect_source_ids(value, found)


class DatasetIntegrity(unittest.TestCase):
    def test_every_data_file_is_valid_json(self):
        for path in DATA_DIR.glob("*.json"):
            with self.subTest(file=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_every_referenced_source_id_resolves(self):
        referenced = set()
        for path in DATA_DIR.glob("*.json"):
            if path.name == "sources.json":
                continue
            _collect_source_ids(json.loads(path.read_text(encoding="utf-8")), referenced)
        self.assertEqual(referenced - set(data.sources()), set())

    def test_sources_are_complete(self):
        for source_id, source in data.sources().items():
            with self.subTest(source=source_id):
                for field in ("title", "publisher", "kind", "url"):
                    self.assertTrue(source.get(field), f"{source_id} is missing {field}")
                self.assertTrue(source["url"].startswith("http"))

    def test_rules_are_well_formed(self):
        for format_id in FORMATS:
            for rule in data.rules(format_id):
                with self.subTest(rule=rule["id"]):
                    self.assertIn(rule["severity"], ("error", "warning", "advisory"))
                    self.assertGreater(len(rule["statement"]), 20)
                    self.assertTrue(rule["sources"])

    def test_rule_ids_are_unique_across_formats(self):
        seen = set()
        for format_id in FORMATS:
            for rule in data.rules(format_id):
                self.assertNotIn(rule["id"], seen, f"duplicate rule id {rule['id']}")
                seen.add(rule["id"])

    def test_jurisdictions_cover_the_documented_set(self):
        self.assertEqual([j["id"] for j in data.jurisdictions()], ["us", "us-ca", "us-ny", "us-wa"])
        self.assertEqual(data.jurisdiction("us-ny")["machineReadableFormat"]["rootElement"], "ProjectRollup")
        self.assertIsNone(data.jurisdiction("nope"))

    def test_the_four_regimes_disagree_about_the_worker_identifier(self):
        identifiers = {j["id"]: j["workerIdentifier"] for j in data.jurisdictions()}
        self.assertIn("ssn-full", identifiers["us"]["prohibits"])
        self.assertIn("ssn-full", identifiers["us-ca"]["accepts"])
        self.assertTrue(identifiers["us-ny"]["exactlyOne"])
        self.assertIn("ssn-full", identifiers["us-wa"]["accepts"])

    def test_extracted_element_trees_match_the_published_schemas(self):
        ca = data.elements("ca-ecpr")
        self.assertEqual(ca[0]["path"], "eCPR")
        employee = next(e for e in ca if e["path"].endswith("/employees/employee"))
        self.assertEqual(employee["maxOccurs"], "500")
        day = next(e for e in ca if e["path"].endswith("hrsWorkedEachDay/day"))
        self.assertEqual((day["minOccurs"], day["maxOccurs"]), ("7", "7"))

        ny = data.elements("ny-certpayroll")
        self.assertEqual(ny[0]["path"], "ProjectRollup")
        week = next(e for e in ny if e["path"].endswith("/employeeWorkWeek"))
        self.assertEqual(week["maxOccurs"], "500")
        # The schema cannot express "exactly one of these two", which is why the
        # validator has to.
        for name in ("dateOfBirth", "ssnLast4"):
            element = next(e for e in ny if e["path"].endswith("/" + name))
            self.assertEqual(element["minOccurs"], "0")

    def test_rule_lookup_resolves_sources(self):
        rule = data.rule("ny.employee.exactlyOneIdentifier")
        self.assertFalse(rule["expressibleInXsd"])
        self.assertEqual(rule["sources"][0]["publisher"], "New York State Department of Labor")
        self.assertEqual(data.rule("wh347.column1E.notFullSsn")["severity"], "error")

    def test_conflicts_name_a_format_and_a_resolution(self):
        for conflict in data.conflicts():
            with self.subTest(conflict=conflict["id"]):
                self.assertIn(conflict["format"], FORMATS)
                self.assertTrue(conflict["kind"])
                self.assertGreater(len(conflict["resolution"]), 20)

    def test_wh347_map_covers_the_2025_column_set(self):
        columns = [c["id"] for c in data.wh347_data()["columns"]]
        self.assertEqual(columns, ["1A", "1B", "1C", "1D", "1E", "2", "3", "4", "5",
                                   "6A", "6B", "6C", "7A", "7B", "8", "9"])
        self.assertEqual(data.wh347_data()["form"]["ombControlNumber"], "1235-0008")

    def test_packaged_data_matches_the_repository_root(self):
        root = Path(__file__).resolve().parents[2] / "data"
        if data.DATA_DIR == root:
            self.skipTest("running from a checkout with no packaged copy")
        for path in root.glob("*.json"):
            with self.subTest(file=path.name):
                self.assertEqual((data.DATA_DIR / path.name).read_text(encoding="utf-8"),
                                 path.read_text(encoding="utf-8"),
                                 f"{path.name} is out of sync; run python3 tools/sync_packages.py")


if __name__ == "__main__":
    unittest.main()
