"""XML reader behaviour. Mirrors js/test/xml.test.js."""

import unittest

from certified_payroll_formats.xml_reader import XmlError, at, kid, kids, parse_xml, text_at


class Reader(unittest.TestCase):
    def test_parses_elements_attributes_text_and_entities(self):
        root = parse_xml('<a xmlns="urn:x"><b id="1">Jones &amp; Co</b><b/></a>')
        self.assertEqual(root.name, "a")
        self.assertEqual(root.ns, "urn:x")
        self.assertEqual(len(kids(root, "b")), 2)
        self.assertEqual(kid(root, "b").attrs["id"], "1")
        self.assertEqual(text_at(root, "b"), "Jones & Co")

    def test_resolves_prefixed_namespaces(self):
        root = parse_xml('<CPR:eCPR xmlns:CPR="urn:ca"><CPR:payrollInfo/></CPR:eCPR>')
        self.assertEqual(root.ns, "urn:ca")
        self.assertEqual(root.name, "eCPR")
        self.assertEqual(root.qname, "CPR:eCPR")
        self.assertEqual(kid(root, "payrollInfo").ns, "urn:ca")

    def test_refuses_doctype(self):
        with self.assertRaises(XmlError) as caught:
            parse_xml('<!DOCTYPE a [<!ENTITY x "boom">]><a/>')
        self.assertIn("DOCTYPE", str(caught.exception))

    def test_reports_the_line_of_a_mismatched_end_tag(self):
        with self.assertRaises(XmlError) as caught:
            parse_xml("<a>\n  <b>\n</a>")
        self.assertEqual(caught.exception.line, 3)

    def test_handles_cdata_and_comments(self):
        root = parse_xml('<?xml version="1.0"?><a><!-- note --><b><![CDATA[a < b & c]]></b></a>')
        self.assertEqual(text_at(root, "b"), "a < b & c")

    def test_walks_new_york_day_day_nesting(self):
        root = parse_xml("<days><day><day>2026-08-02</day><h>8</h></day></days>")
        self.assertEqual(at(root, "day/day").text, "2026-08-02")
        self.assertEqual(text_at(root, "day/h"), "8")

    def test_rejects_unclosed_elements(self):
        with self.assertRaises(XmlError):
            parse_xml("<a><b></b>")


if __name__ == "__main__":
    unittest.main()
