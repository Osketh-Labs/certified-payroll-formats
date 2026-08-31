#!/usr/bin/env python3
"""Regenerate data/ca-ecpr.json and data/ny-certpayroll.json from the official XSDs.

The element trees in those files are extracted mechanically so that types, lengths,
patterns and cardinalities are exactly what the agency published. Prose rules that the
schema cannot express live in tools/rules-*.json and are merged in here.

Usage:
    python3 tools/build_formats.py            # fetch the XSDs over the network
    python3 tools/build_formats.py --offline  # use tools/cache/*.xsd

Requires only the standard library.
"""
import argparse
import io
import json
import os
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

XS = "{http://www.w3.org/2001/XMLSchema}"
ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / "cache"

SCHEMAS = {
    "ca": {
        "url": "http://www.dir.ca.gov/dlse/CPR-Prod-Test/CPR.xsd",
        "cache": "CPR.xsd",
        "zipped": False,
    },
    "ny": {
        "url": "https://dol.ny.gov/certpayrollxsd",
        "cache": "NYDOL_CertPayroll.xsd",
        "zipped": True,  # NYSDOL serves the schema as a ZIP archive
    },
}


def fetch(key, offline):
    spec = SCHEMAS[key]
    path = CACHE / spec["cache"]
    if offline or path.exists():
        return path.read_bytes()
    CACHE.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(spec["url"]) as r:  # noqa: S310 - fixed official URLs
        raw = r.read()
    if spec["zipped"]:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".xsd"))
            raw = z.read(name)
    path.write_bytes(raw)
    return raw


def own_restriction(el):
    """The restriction belonging to this element, not to a descendant."""
    for st in el.findall(XS + "simpleType"):
        for r in st.findall(XS + "restriction"):
            return r
    return None


def describe(el):
    out = {}
    if el.get("type"):
        out["type"] = el.get("type")
    if el.get("fixed") is not None:
        out["fixed"] = el.get("fixed")
    r = own_restriction(el)
    if r is not None:
        out["type"] = r.get("base")
        for facet in r:
            if not facet.tag.startswith(XS):
                continue
            name = facet.tag[len(XS):]
            if name == "annotation":
                continue
            out.setdefault("facets", {})[name] = facet.get("value")
    doc = el.find(XS + "annotation/" + XS + "documentation")
    if doc is not None and doc.text:
        out["documentation"] = " ".join(doc.text.split())
    return out


def children(el):
    """Direct child element declarations, descending through complexType/sequence/choice/all."""
    out = []
    for node in el:
        if node.tag == XS + "element":
            out.append(node)
        elif node.tag in (XS + "complexType", XS + "sequence", XS + "choice", XS + "all"):
            out.extend(children(node))
    return out


def attributes(el):
    out = []
    for node in el:
        if node.tag == XS + "attribute":
            out.append(node)
        elif node.tag in (XS + "complexType", XS + "sequence", XS + "choice", XS + "all"):
            out.extend(attributes(node))
    return out


def walk(el, path=""):
    name = el.get("name")
    here = f"{path}/{name}" if path else name
    node = {"path": here, "name": name,
            "minOccurs": el.get("minOccurs", "1"),
            "maxOccurs": el.get("maxOccurs", "1")}
    node.update(describe(el))
    kids = children(el)
    attrs = [{"name": a.get("name"), "use": a.get("use", "optional"), **describe(a)}
             for a in attributes(el)]
    if attrs:
        node["attributes"] = attrs
    rows = [node]
    for k in kids:
        rows.extend(walk(k, here))
    return rows


def build(key, offline):
    raw = fetch(key, offline)
    root = ET.fromstring(raw)
    top = root.find(XS + "element")
    rows = walk(top)
    rules = json.loads((ROOT / "tools" / f"rules-{key}.json").read_text())
    rules["elements"] = rows
    rules["elementCount"] = len(rows)
    return rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    out = {"ca": "ca-ecpr.json", "ny": "ny-certpayroll.json"}
    for key, filename in out.items():
        doc = build(key, args.offline)
        dest = ROOT / "data" / filename
        dest.write_text(json.dumps(doc, indent=2) + "\n")
        print(f"{dest.relative_to(ROOT)}: {doc['elementCount']} elements")


if __name__ == "__main__":
    main()
