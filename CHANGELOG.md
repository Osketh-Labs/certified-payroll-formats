# Changelog

Dates are review dates: the day the facts were checked against the official sources
listed in `data/sources.json`.

## Unreleased

Verification pass over the first release. Nothing was published to npm or PyPI before
these were fixed.

**Data correction.** `data/ny-certpayroll.json` misstated the supplemental payment types.
The extractor kept only the last of an element's repeated `xs:enumeration` facets, so the
file claimed the sole legal value was `Other Benefit (Type)` when the schema enumerates
five. Repeated facets are now collected as lists, and the enumeration is enforced by the
validators under `schema.enumeration`.

**Correctness fixes.**

- `xs:date` and `xs:dateTime` now require a real calendar date. `2026-13-45` matched the
  lexical pattern and was accepted; downstream it rolled over into another month and
  either crashed the Python validator or flagged every day in the file.
- An empty element is no longer read as a valid decimal, date or boolean. A blank
  `<totHrsStraightTime/>` was read as zero in JavaScript, which turned one fault into a
  second, spurious arithmetic finding, and was skipped entirely in Python.
- `xmlns=""` now undeclares the default namespace instead of setting it to the empty
  string.
- A repeated attribute is now refused as the well-formedness error it is, rather than
  silently taking the last value.
- `rule()` in the JavaScript package searched only the WH-347 easy-to-miss list, not the
  checks; it now searches both, matching the Python loader.
- A worker with no entry number no longer reports a broken entry-number sequence.
- Both CLIs report an unreadable file as a message on stderr with exit code 2, instead of
  a stack trace.

**Testing.** 121 JavaScript and 113 Python tests, up from 41 and 39, covering the XML
readers, the structural checker facet by facet, every documented rule that a schema
cannot express, the WH-347 mapper, and both CLIs. `tools/differential.py` mutates every
element of every fixture four ways and asserts both implementations agree on all 400
mutants; it runs in CI.

## 0.1.0 — 2026-08-31

First release.

- `data/jurisdictions.json` — the federal DBRA baseline plus California, New York and
  Washington: filing cadence, accepted formats, portals, worker identifiers, fringe
  models, project keys, penalties and authority.
- `data/wh347.json` — WH-347 as revised January 2025: ten header fields, columns 1A–9,
  the page 2 Statement of Compliance and its six checkboxes, eight easy-to-miss rules
  from the WHD instructions, and sixteen checks the library applies.
- `data/ca-ecpr.json` — 83 elements extracted from DIR's `CPR.xsd` v1.3, 23 documented
  rules, the filename convention from the eCPR XML Guidelines v1.10.
- `data/ny-certpayroll.json` — 43 elements extracted from `NYDOL_CertPayroll.xsd` v2.0,
  23 documented rules, the three partitioning rules from the bulk upload guide.
- `data/wa-pwia.json` — 16 rules and the five-step upload validation from L&I's XML
  Payroll Upload Guide. No element tree: the schema is served from inside the PWIA
  portal and has no public URL.
- `data/conflicts.json` — 13 places where a schema and its own documentation disagree.
- Validators for California and New York in JavaScript and Python, each combining a
  structural check against the extracted schema with the rules the schema cannot express.
- WH-347 mapper and checker in both languages.
- `certified-payroll` CLI in both packages.
