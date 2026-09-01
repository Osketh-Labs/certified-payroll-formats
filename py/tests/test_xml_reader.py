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


class Edges(unittest.TestCase):
    def test_xmlns_empty_undeclares_the_default_namespace(self):
        root = parse_xml('<a xmlns="urn:x"><b xmlns=""><c/></b></a>')
        self.assertEqual(root.ns, "urn:x")
        self.assertIsNone(kid(root, "b").ns)
        self.assertIsNone(kid(kid(root, "b"), "c").ns)

    def test_attribute_value_may_contain_gt_and_trailing_slash(self):
        self.assertEqual(parse_xml('<a t="a&gt;b"><b/></a>').attrs["t"], "a>b")
        root = parse_xml('<a href="x/"><b/></a>')
        self.assertEqual(root.attrs["href"], "x/")
        self.assertEqual(len(root.children), 1)

    def test_self_closing_tags_may_carry_whitespace_and_attributes(self):
        root = parse_xml('<a><b x="1" /><c   /></a>')
        self.assertEqual(len(root.children), 2)
        self.assertEqual(kid(root, "b").attrs["x"], "1")

    def test_numeric_character_references(self):
        self.assertEqual(parse_xml("<a>&#65;&#x42;&#x2014;</a>").text, "AB—")

    def test_entities_inside_attribute_values(self):
        self.assertEqual(parse_xml('<a t="Jones &amp; Co &lt;x&gt;"/>').attrs["t"], "Jones & Co <x>")

    def test_byte_order_mark_is_tolerated(self):
        self.assertEqual(parse_xml("﻿<a/>").name, "a")

    def test_crlf_does_not_double_the_line_count(self):
        self.assertEqual(kid(parse_xml("<a>\r\n  <b/>\r\n</a>"), "b").line, 2)

    def test_a_repeated_attribute_is_refused(self):
        # XML forbids it, and accepting it would pass a document the agency's own
        # parser rejects.
        with self.assertRaises(XmlError):
            parse_xml('<a x="1" x="2"/>')

    def test_text_outside_the_document_element_is_refused(self):
        with self.assertRaises(XmlError):
            parse_xml("<a/>trailing")
        parse_xml("\n  <a/>\n  ")

    def test_an_empty_document_has_no_document_element(self):
        for source in ("", "   \n ", '<?xml version="1.0"?>'):
            with self.subTest(source=source), self.assertRaises(XmlError):
                parse_xml(source)

    def test_elements_may_nest_inside_the_same_name(self):
        root = parse_xml("<a><a><a>deep</a></a></a>")
        self.assertEqual(root.children[0].children[0].text, "deep")

    def test_missing_paths_return_none(self):
        root = parse_xml("<a><b/></a>")
        self.assertIsNone(at(root, "b/c"))
        self.assertIsNone(text_at(root, "nope"))
        self.assertEqual(kids(root, "nope"), [])
        self.assertEqual(kids(None, "b"), [])

    def test_path_of_names_the_route_from_the_document_element(self):
        from certified_payroll_formats.xml_reader import path_of
        root = parse_xml("<a><b><c/></b></a>")
        self.assertEqual(path_of(at(root, "b/c")), "a/b/c")

    def test_a_non_string_input_is_refused(self):
        for value in (None, 42, b"<a/>"):
            with self.subTest(value=value), self.assertRaises(XmlError):
                parse_xml(value)
