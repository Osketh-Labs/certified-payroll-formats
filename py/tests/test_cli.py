"""CLI behaviour: exit codes, clean failure, machine-readable output.

Mirrors js/test/cli.test.js.
"""

import json
import subprocess
import sys
import unittest

from helpers import ROOT

ENV_SRC = str(ROOT / "py" / "src")


def run(*args):
    result = subprocess.run(
        [sys.executable, "-m", "certified_payroll_formats.cli", *args],
        capture_output=True, text=True, cwd=ROOT,
        env={"PYTHONPATH": ENV_SRC, "PATH": "/usr/bin:/bin"},
    )
    return result.returncode, result.stdout, result.stderr


class ExitCodes(unittest.TestCase):
    def test_clean_file_exits_zero_and_errors_exit_one(self):
        self.assertEqual(run("validate", "ny", "fixtures/ny/valid.xml")[0], 0)
        self.assertEqual(run("validate", "ny", "fixtures/ny/invalid.xml")[0], 1)

    def test_warnings_alone_do_not_fail_the_exit_code(self):
        code, out, _ = run("validate", "ca", "fixtures/ca/valid.xml")
        self.assertEqual(code, 0)
        self.assertIn("1 advisory", out)

    def test_missing_file_is_a_clean_message_and_exit_two(self):
        code, out, err = run("validate", "ca", "does-not-exist.xml")
        self.assertEqual(code, 2)
        self.assertIn("cannot read does-not-exist.xml", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out, "")

    def test_bad_usage_exits_two(self):
        for args in (("validate",), ("validate", "tx", "x.xml"), ("nonsense",)):
            with self.subTest(args=args):
                self.assertEqual(run(*args)[0], 2)

    def test_unknown_jurisdiction_or_rule_exits_two(self):
        self.assertEqual(run("show", "us-zz")[0], 2)
        self.assertEqual(run("rule", "nope")[0], 2)


class Output(unittest.TestCase):
    def test_json_is_parseable_and_complete(self):
        code, out, _ = run("--json", "validate", "ny", "fixtures/ny/invalid.xml")
        self.assertEqual(code, 1)
        parsed = json.loads(out)
        self.assertEqual(parsed["file"], "invalid.xml")
        self.assertFalse(parsed["valid"])
        self.assertTrue(parsed["findings"])
        for f in parsed["findings"]:
            self.assertTrue(f["ruleId"] and f["severity"] and f["message"])
            self.assertTrue(all(s["url"].startswith("http") for s in f["sources"]))

    def test_quiet_drops_warnings_but_keeps_the_summary(self):
        _, noisy, _ = run("validate", "ca", "fixtures/ca/invalid.xml")
        _, quiet, _ = run("validate", "ca", "fixtures/ca/invalid.xml", "--quiet")
        self.assertIn("WARNING", noisy)
        self.assertNotIn("WARNING", quiet)
        self.assertNotIn("ADVISORY", quiet)
        self.assertIn("error(s)", quiet)

    def test_human_output_names_the_rule_and_links_its_source(self):
        _, out, _ = run("validate", "ny", "fixtures/ny/invalid.xml")
        self.assertIn("rule ny.employee.exactlyOneIdentifier", out)
        self.assertIn("https://dol.ny.gov", out)

    def test_every_query_subcommand_produces_output(self):
        for args in (("jurisdictions",), ("show", "us-ny"), ("rules", "ca-ecpr"),
                     ("rule", "ny.employee.exactlyOneIdentifier"), ("elements", "ca-ecpr"),
                     ("conflicts",), ("wh347",)):
            with self.subTest(args=args):
                code, out, _ = run(*args)
                self.assertEqual(code, 0)
                self.assertGreater(len(out), 40)

    def test_query_subcommands_emit_valid_json(self):
        for args in (("jurisdictions",), ("rules", "wa-pwia"), ("elements", "ny-certpayroll"),
                     ("conflicts",), ("show", "us-ca"), ("wh347",)):
            with self.subTest(args=args):
                json.loads(run("--json", *args)[1])


if __name__ == "__main__":
    unittest.main()
