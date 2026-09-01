"""The XSD extractor in tools/build_formats.py.

Its output is heavily tested through data/*.json, but the code that produces that output
had no tests of its own — and it is where the one factual error in the published dataset
came from: repeated xs:enumeration facets were collapsed to the last value, so the
dataset claimed one legal supplemental payment type where the schema enumerates five.
These tests pin the extraction rules directly.
"""

import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))

import build_formats as bf  # noqa: E402

XS = "http://www.w3.org/2001/XMLSchema"


def parse(body: str):
    """Wrap an element declaration in a schema and return the declaration."""
    doc = ET.fromstring(f'<xs:schema xmlns:xs="{XS}">{body}</xs:schema>')
    return doc.find(f"{{{XS}}}element")


class Describe(unittest.TestCase):
    def test_a_named_type_is_recorded(self):
        self.assertEqual(bf.describe(parse('<xs:element name="a" type="xs:date"/>')),
                         {"type": "xs:date"})

    def test_an_element_with_no_type_and_no_facets_records_nothing(self):
        self.assertEqual(bf.describe(parse('<xs:element name="a"/>')), {})

    def test_a_restriction_supplies_the_base_type_and_its_facets(self):
        described = bf.describe(parse("""
            <xs:element name="a">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:minLength value="1"/><xs:maxLength value="56"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:element>"""))
        self.assertEqual(described, {"type": "xs:string",
                                     "facets": {"minLength": "1", "maxLength": "56"}})

    def test_repeated_enumerations_become_a_list(self):
        # The bug. Keeping only the last value misstated the schema in the published data.
        described = bf.describe(parse("""
            <xs:element name="a">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:enumeration value="Health/Welfare"/>
                  <xs:enumeration value="Pension"/>
                  <xs:enumeration value="Other Benefit (Type)"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:element>"""))
        self.assertEqual(described["facets"]["enumeration"],
                         ["Health/Welfare", "Pension", "Other Benefit (Type)"])

    def test_a_single_enumeration_is_still_a_list(self):
        # Consumers should not have to branch on whether the schema happened to
        # enumerate one value or several.
        described = bf.describe(parse("""
            <xs:element name="a">
              <xs:simpleType>
                <xs:restriction base="xs:string"><xs:enumeration value="only"/></xs:restriction>
              </xs:simpleType>
            </xs:element>"""))
        self.assertEqual(described["facets"]["enumeration"], ["only"])

    def test_any_other_repeated_facet_also_becomes_a_list(self):
        described = bf.describe(parse("""
            <xs:element name="a">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:pattern value="[0-9]{4}"/><xs:pattern value="NA"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:element>"""))
        self.assertEqual(described["facets"]["pattern"], ["[0-9]{4}", "NA"])

    def test_a_facet_that_appears_once_stays_scalar(self):
        described = bf.describe(parse("""
            <xs:element name="a">
              <xs:simpleType>
                <xs:restriction base="xs:string"><xs:pattern value="CSLB|PL|OTHER"/></xs:restriction>
              </xs:simpleType>
            </xs:element>"""))
        self.assertEqual(described["facets"]["pattern"], "CSLB|PL|OTHER")

    def test_a_fixed_value_is_recorded_including_the_empty_one(self):
        self.assertEqual(bf.describe(parse('<xs:element name="a" fixed=""/>'))["fixed"], "")
        self.assertEqual(bf.describe(parse('<xs:element name="a" fixed="CA-DIR"/>'))["fixed"],
                         "CA-DIR")

    def test_documentation_is_captured_with_whitespace_collapsed(self):
        described = bf.describe(parse("""
            <xs:element name="a">
              <xs:annotation>
                <xs:documentation>
                  This element   contains
                  a worker's name.
                </xs:documentation>
              </xs:annotation>
            </xs:element>"""))
        self.assertEqual(described["documentation"], "This element contains a worker's name.")

    def test_an_annotation_is_not_mistaken_for_a_facet(self):
        described = bf.describe(parse("""
            <xs:element name="a">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:annotation><xs:documentation>ignore me</xs:documentation></xs:annotation>
                  <xs:maxLength value="4"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:element>"""))
        self.assertEqual(described["facets"], {"maxLength": "4"})

    def test_a_complex_parent_does_not_inherit_a_descendant_restriction(self):
        # The subtle one. Searching the whole subtree for a restriction would give a
        # container element the type and facets of its first typed grandchild, which is
        # wrong and silently plausible.
        element = parse("""
            <xs:element name="parent">
              <xs:complexType><xs:sequence>
                <xs:element name="child">
                  <xs:simpleType>
                    <xs:restriction base="xs:decimal"><xs:fractionDigits value="2"/></xs:restriction>
                  </xs:simpleType>
                </xs:element>
              </xs:sequence></xs:complexType>
            </xs:element>""")
        described = bf.describe(element)
        self.assertNotIn("type", described)
        self.assertNotIn("facets", described)


class Traversal(unittest.TestCase):
    SCHEMA = """
        <xs:element name="root">
          <xs:complexType>
            <xs:attribute name="id" type="xs:string"/>
            <xs:sequence>
              <xs:element name="one" type="xs:string"/>
              <xs:element name="group">
                <xs:complexType><xs:sequence>
                  <xs:element name="item" minOccurs="0" maxOccurs="500">
                    <xs:complexType>
                      <xs:attribute name="seq" type="xs:integer" use="required"/>
                      <xs:sequence><xs:element name="leaf" type="xs:date"/></xs:sequence>
                    </xs:complexType>
                  </xs:element>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="many" type="xs:string" maxOccurs="unbounded"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>"""

    def setUp(self):
        self.rows = bf.walk(parse(self.SCHEMA))
        self.by_path = {r["path"]: r for r in self.rows}

    def test_paths_are_built_from_the_document_element_down(self):
        self.assertEqual([r["path"] for r in self.rows], [
            "root", "root/one", "root/group", "root/group/item",
            "root/group/item/leaf", "root/many",
        ])

    def test_occurrence_defaults_are_recorded_explicitly(self):
        self.assertEqual((self.by_path["root/one"]["minOccurs"],
                          self.by_path["root/one"]["maxOccurs"]), ("1", "1"))
        self.assertEqual((self.by_path["root/group/item"]["minOccurs"],
                          self.by_path["root/group/item"]["maxOccurs"]), ("0", "500"))
        self.assertEqual(self.by_path["root/many"]["maxOccurs"], "unbounded")

    def test_attributes_are_attached_to_their_own_element(self):
        self.assertEqual(self.by_path["root"]["attributes"],
                         [{"name": "id", "use": "optional", "type": "xs:string"}])
        self.assertEqual(self.by_path["root/group/item"]["attributes"],
                         [{"name": "seq", "use": "required", "type": "xs:integer"}])
        self.assertNotIn("attributes", self.by_path["root/one"])

    def test_children_descends_through_complex_type_and_sequence(self):
        names = [c.get("name") for c in bf.children(parse(self.SCHEMA))]
        self.assertEqual(names, ["one", "group", "many"], "direct children only")

    def test_a_choice_is_traversed_like_a_sequence(self):
        element = parse("""
            <xs:element name="root"><xs:complexType><xs:choice>
              <xs:element name="a" type="xs:string"/><xs:element name="b" type="xs:string"/>
            </xs:choice></xs:complexType></xs:element>""")
        self.assertEqual([r["path"] for r in bf.walk(element)], ["root", "root/a", "root/b"])


class Fetching(unittest.TestCase):
    def test_the_offline_path_reads_the_cache_and_never_touches_the_network(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            cache = pathlib.Path(directory)
            (cache / "fake.xsd").write_bytes(b"<xs:schema/>")
            original_cache, original_schemas = bf.CACHE, bf.SCHEMAS
            try:
                bf.CACHE = cache
                bf.SCHEMAS = {"fake": {"url": "http://invalid.invalid/x.xsd",
                                       "cache": "fake.xsd", "zipped": False}}
                self.assertEqual(bf.fetch("fake", offline=True), b"<xs:schema/>")
            finally:
                bf.CACHE, bf.SCHEMAS = original_cache, original_schemas

    def test_a_user_agent_is_sent(self):
        # dol.ny.gov answers 403 to the default Python-urllib user agent, so the tool
        # must identify itself. This only ever ran from cache before, which is how the
        # weekly drift job failed on its first live run.
        self.assertIn("certified-payroll-formats", bf.USER_AGENT)
        self.assertIn("github.com", bf.USER_AGENT)


if __name__ == "__main__":
    unittest.main()
