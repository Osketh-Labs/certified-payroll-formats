"""Legal but awkward inputs: the largest file each format permits, non-ASCII names, and
structures deep enough to break a naive parser. Mirrors js/test/robustness.test.js.
"""

import re
import time
import unittest

from certified_payroll_formats import (
    data, elements, resolve_sources, rules, validate_ca_ecpr, validate_ny_cert_payroll,
)
from certified_payroll_formats.finding import summarize
from certified_payroll_formats.xml_reader import parse_xml, path_of, text_at
from helpers import fixture, ids


def ny_with_records(n: int) -> str:
    source = fixture("ny", "valid.xml")
    block = re.search(r" {4}<employeeWorkWeek>.*?</employeeWorkWeek>\n", source, re.S).group(0)
    body = "".join(
        block.replace("<ssnLast4>0323</ssnLast4>", f"<ssnLast4>{i % 10000:04d}</ssnLast4>")
             .replace("<firstName>Steven</firstName>", f"<firstName>Worker{i}</firstName>")
        for i in range(n)
    )
    return re.sub(r" {4}<employeeWorkWeek>.*</employeeWorkWeek>\n", body, source, flags=re.S)


class LargeInputs(unittest.TestCase):
    def test_the_largest_file_new_york_permits_validates_cleanly(self):
        xml = ny_with_records(500)
        self.assertGreater(len(xml), 900_000, "a 500-record file is about a megabyte")
        self.assertEqual(validate_ny_cert_payroll(xml)["findings"], [])

    def test_parsing_is_linear_in_file_size(self):
        # The JavaScript reader was quadratic here, taking seconds on this file. The
        # ratio is the guard, because it survives a slow CI machine.
        def timed(xml):
            start = time.perf_counter()
            validate_ny_cert_payroll(xml)
            return time.perf_counter() - start

        small, large = ny_with_records(100), ny_with_records(500)
        timed(small)
        ratio = timed(large) / max(timed(small), 1e-6)
        self.assertLess(ratio, 12, f"five times the input should not cost {ratio:.1f}x")

    def test_deep_nesting_does_not_exhaust_the_stack(self):
        depth = 2000
        root = parse_xml("<a>" * depth + "deep" + "</a>" * depth)
        node, counted = root, 1
        while node.children:
            node = node.children[0]
            counted += 1
        self.assertEqual(counted, depth)
        self.assertEqual(node.text, "deep")
        self.assertEqual(len(path_of(node).split("/")), depth)

    def test_a_very_long_text_node(self):
        self.assertEqual(len(parse_xml("<a>" + "x" * 500_000 + "</a>").text), 500_000)

    def test_an_element_with_many_attributes(self):
        attrs = " ".join(f'a{i}="{i}"' for i in range(500))
        root = parse_xml(f"<e {attrs}/>")
        self.assertEqual(len(root.attrs), 500)
        self.assertEqual(root.attrs["a499"], "499")


class Unicode(unittest.TestCase):
    def test_length_facets_count_characters(self):
        # contractorAddress/city is capped at 25 characters. An astral-plane character
        # is one character; counting UTF-16 code units would reject a legal name.
        def city(n):
            return fixture("ca", "valid.xml").replace(
                "<CPR:city>Sacramento</CPR:city>", "<CPR:city>" + "\U0001d54f" * n + "</CPR:city>", 1)

        self.assertEqual(ids(validate_ca_ecpr(city(25))), [])
        self.assertEqual(ids(validate_ca_ecpr(city(26))), ["schema.length"])

    def test_non_ascii_text_and_attributes_survive_parsing(self):
        root = parse_xml('<a n="Ünïcødé"><b>Zoë Ñuñez 中文 \U0001f600</b></a>')
        self.assertEqual(root.attrs["n"], "Ünïcødé")
        self.assertEqual(text_at(root, "b"), "Zoë Ñuñez 中文 \U0001f600")

    def test_a_non_ascii_worker_name_validates_normally(self):
        xml = fixture("ny", "valid.xml").replace("<lastName>Bradley</lastName>",
                                                 "<lastName>Ñuñez-Öztürk</lastName>")
        self.assertEqual(ids(validate_ny_cert_payroll(xml)), [])


class Loaders(unittest.TestCase):
    def test_an_unknown_format_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unknown format"):
            rules("us-tx")
        with self.assertRaisesRegex(ValueError, "No extracted element tree"):
            elements("wa-pwia")

    def test_an_unknown_source_id_resolves_to_a_marker(self):
        resolved = resolve_sources(["not-a-source"])[0]
        self.assertEqual(resolved["id"], "not-a-source")
        self.assertIn("unknown source", resolved["title"])
        self.assertEqual(resolve_sources(None), [])

    def test_an_unknown_rule_id_returns_none(self):
        self.assertIsNone(data.rule("no.such.rule"))


class Findings(unittest.TestCase):
    @staticmethod
    def make(severity, line):
        return {"severity": severity, "line": line, "ruleId": f"r.{severity}{line}"}

    def test_summarize_counts_and_orders(self):
        summary = summarize([self.make("advisory", 3), self.make("error", 9),
                             self.make("warning", 1), self.make("error", 2)])
        self.assertEqual(summary["counts"], {"error": 2, "warning": 1, "advisory": 1})
        self.assertFalse(summary["valid"])
        self.assertEqual([f["ruleId"] for f in summary["findings"]],
                         ["r.error2", "r.error9", "r.warning1", "r.advisory3"])

    def test_warnings_only_is_valid(self):
        summary = summarize([self.make("warning", 1)])
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["counts"], {"error": 0, "warning": 1, "advisory": 0})

    def test_an_empty_finding_list(self):
        summary = summarize([])
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["counts"], {"error": 0, "warning": 0, "advisory": 0})

    def test_a_finding_with_no_line_sorts_without_raising(self):
        summary = summarize([{"severity": "error", "line": None, "ruleId": "a"},
                             {"severity": "error", "line": 5, "ruleId": "b"}])
        self.assertEqual([f["ruleId"] for f in summary["findings"]], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
