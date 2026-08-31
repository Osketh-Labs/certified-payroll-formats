# Changelog

Dates are review dates: the day the facts were checked against the official sources
listed in `data/sources.json`.

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
