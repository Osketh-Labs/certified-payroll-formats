# certified-payroll-formats

Machine-readable reference data and zero-dependency validators for US certified payroll
filing: the federal **WH-347** baseline, **California eCPR** XML, **New York**'s bulk
upload XML, and **Washington**'s PWIA upload.

Every fact in `data/` traces to a statute, a regulation, a published schema, or an
agency's own instructions, and carries the link. The element trees are extracted
mechanically from the agencies' XSDs rather than transcribed, so the types, lengths,
patterns and occurrence limits are exactly what was published.

Nothing here is legal advice. The linked official sources govern, and they change.

```bash
npx certified-payroll validate ny payroll.xml     # Node
pipx run certified-payroll-formats validate ca payroll.xml   # Python
```

---

## Why this exists

Certified payroll is one obligation implemented four different ways. The same worker,
the same week, the same hours produce four incompatible files, and the incompatibility
is not cosmetic — the regimes disagree about what identifies a worker, what an hour is,
and what a payment is.

| | Federal (DBRA) | California | New York | Washington |
|---|---|---|---|---|
| **Filed** | weekly | at least monthly | at least every 30 days | at least monthly |
| **Format** | WH-347, or any form carrying an identical Statement of Compliance | online entry or eCPR XML | online entry or XML — **XML only** for bulk, no CSV, no API | online entry or PWIA XML |
| **Root element** | — | `eCPR` | `ProjectRollup` | not public |
| **Namespace** | — | `http://www.dir.ca.gov/dlse/CPR-Prod-Test/CPR.xsd` | **none** | not public |
| **Per-file cap** | — | 500 employees | 500 employee work weeks | — |
| **Worker identifier** | last 4 of SSN or a worker-specific number; **full SSNs prohibited** | **full 9-digit SSN required** | `ssnLast4` **or** `dateOfBirth` — exactly one, never both | full SSN required, unique within the file |
| **Hours** | ST + OT | ST + OT + **double time** | ST + OT | ST + OT |
| **Fringe** | credit (6B) vs cash (6C), never combined | itemised by fund type | typed `supplementalPayments` | hourly usual benefits |
| **Project key** | agency contract number | `projectID` + contractor registration | `prcNumber` (Prevailing Rate Case) | PWIA intent/project |
| **Authority** | [40 U.S.C. § 3145](https://www.law.cornell.edu/uscode/text/40/3145), [29 CFR 5.5](https://www.ecfr.gov/current/title-29/subtitle-A/part-5/subpart-A/section-5.5) | [Labor Code §§ 1771.4](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=LAB&sectionNum=1771.4), [1776](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=LAB&sectionNum=1776) | [Labor Law § 220-j](https://www.nysenate.gov/legislation/laws/LAB/220-J) | [RCW 39.12.120](https://app.leg.wa.gov/rcw/default.aspx?cite=39.12.120) |

The payroll itself is always weekly. Only the filing cadence differs — a state that
collects monthly is collecting a month of weekly records.

A canonical weekly record can be *derived* into each format. No format is a superset of
the others, and the mapping is per-jurisdiction.

---

## Where a schema and its own documentation disagree

The part you cannot get from reading either document alone. Each of these is a file that
passes local XSD validation and is rejected by the portal, or the reverse. Full detail,
with quotes and resolutions, in [`data/conflicts.json`](data/conflicts.json).

| Element | The schema says | The documentation says | What actually works |
|---|---|---|---|
| NY `nysRegisteredApprentice` | `type="xs:boolean"` | its own annotation: `"Y"` or `"N"` | `true` / `false` — `Y` is not a valid boolean |
| NY `address/state` | `xs:string`, 1–50 chars, no pattern | its own annotation: "two uppercase letters… For example: CA" | the **full state name**; the bulk upload guide lists abbreviations as an upload error |
| NY `ssnLast4` / `dateOfBirth` | both `minOccurs="0"`, independent | guide: a value in either, "you cannot include a value in both" | exactly one. An `xs:choice` would have expressed this; the schema does not use one |
| NY `address/country` | required (no `minOccurs`, defaults to 1) | guide lists it as optional | send it |
| NY `ssnLast4` annotation | — | "must match name id attribute SSN of `SSN::NAME`" | there is no `name` element or `id` attribute anywhere in v2.0 — the sentence describes nothing |
| NY `days/day/day` | a `day` element whose first child is also named `day` | not mentioned | legal XML, and the official sample does it — note it before writing XPath or generating bindings |
| NY `deduction/amount` | `([0-9]{1,4})(\.[0-9]{1,2})?` | not mentioned | no single deduction of 10000.00 or more, and no sign |
| CA `notes` | `minOccurs` defaults to 1, `minLength` 0 | guide: "isn't mandatory and can be left blank" | send the element, empty. The content is optional; the element is not |
| CA `projectInfo` | `awardingBodyID`, `projectNum`, `contractID` are **not** `fixed=""` | guide: "All other fields must be empty" | the schema's own `projectID` annotation documents those three as the lookup fallback |
| CA `employee` | `maxOccurs="500"` | guide states no limit | split at 500 |
| CA versioning | schema comment: Version 1.3 | guideline PDF: Version 1.10, release notes headed 1.5 | there is no single version number — pin by content hash |
| WA seven elements | still declared in the schema | guide: remove them, or send them null | omit `amendedFlag`, `amendedDate`, `amendReason`, `WageID`, `apprenticePgmOccpnID`, `apprenticePgmName`, `apprenticePgmOccpnStepCalcID` |

And one that is nobody's mistake: California **requires** the full nine-digit SSN and
still collects `numWithholdingExemp`, while the January 2025 WH-347 revision **prohibits**
full SSNs and removed the withholding-exemptions column entirely. The same worker record
must carry the number in one file and must not in the other.

---

## Install

```bash
npm install certified-payroll-formats
```

```bash
pip install certified-payroll-formats
```

Both packages have **zero runtime dependencies**. Node 18+, Python 3.9+.

The JSON in `data/` is the product; the two libraries are thin readers over it. If you
work in another language, vendor the JSON and skip the packages.

---

## Validating a file

The validators do two things. First they check the document against the element tree
extracted from the agency's own XSD — occurrence limits, sequence order, patterns,
lengths, ranges, fraction digits, fixed values — which reproduces what XML Notepad would
report, with no schema download and no XML library. Then they apply the rules the schema
*cannot* express: the identifier choice, cross-field arithmetic, date windows, duplicate
detection, and the conventions each agency states only in prose.

```bash
$ certified-payroll validate ny payroll.xml
ERROR  the employee carries both ssnLast4 and dateOfBirth
      line 12 · ProjectRollup/employeeWorkWeeks/employeeWorkWeek/employee
      expected: exactly one of ssnLast4 or dateOfBirth
      actual:   both present
      rule ny.employee.exactlyOneIdentifier — https://dol.ny.gov/bizserve/ep/guide/buf

payroll.xml: 1 error(s), 0 warning(s), 0 advisory
```

Every finding names the rule it came from and links the official source behind that rule.
Exit code is 0 when there are no errors, 1 when there are, 2 on bad usage. `--json` gives
you the whole thing as data; `--quiet` suppresses warnings and advisories.

```js
import { validateNyCertPayroll, validateCaEcpr } from 'certified-payroll-formats';

const { valid, counts, findings } = validateNyCertPayroll(xml, { filename: 'week.xml' });
for (const f of findings) {
  console.log(f.severity, f.ruleId, f.message, f.sources.map((s) => s.url));
}
```

```python
from certified_payroll_formats import validate_ny_cert_payroll, validate_ca_ecpr

result = validate_ny_cert_payroll(xml, filename="week.xml")
for f in result["findings"]:
    print(f["severity"], f["ruleId"], f["message"])
```

Severity means what it says: `error` blocks the filing, `warning` is a mismatch worth a
human look, `advisory` is a convention rather than a constraint. Rules the schema can
enforce are reported under `schema.*` ids; the rest under their documented id
(`ca.*`, `ny.*`, `wa.*`). `data/*.json` records which is which in `expressibleInXsd`.

### XML handling

Both readers refuse `DOCTYPE` declarations outright. No certified payroll format uses
one, and accepting them is how entity expansion attacks (XXE, billion laughs) get in.
The Node reader is hand-written and dependency-free; the Python reader is built on the
standard library's expat with external entity resolution disabled. Line numbers on every
node, so findings point at a place in the file.

---

## WH-347

`data/wh347.json` maps the form as revised **January 2025** — worker names split into
three fields, the withholding-exemptions column removed, the old single rate-of-pay
column split into 6A, 6B and 6C. Guidance written against the older layout does not line
up with the current form. Check the OMB expiration date: a current form reads
**OMB 1235-0008, expires 01/31/2028**.

```js
import { toWH347, checkWH347 } from 'certified-payroll-formats/wh347';

const { header, rows, pageTwo } = toWH347(record);
const { findings } = checkWH347(record);
```

```python
from certified_payroll_formats import to_wh347, check_wh347
```

The canonical record is a plain object — project, contractor, payroll, and a list of
workers each carrying days, rates, fringe, gross, deductions and net pay. `toWH347`
renders it as column values (`1A` … `9`) plus the page 2 checkbox state and fringe
table. `checkWH347` applies sixteen documented checks, including:

- **column 1E is not a full SSN** — the rule filers break most often
- column 5 equals the sum of column 4, column 8's total equals the sum of its parts, and
  column 9 equals 7B less that total — net pay is for **all work**, never pro-rated
- 6B equals hours × the page 2 hourly credit; 6C equals hours × the cash-in-lieu rate;
  the two are separate obligations and are never combined
- a worker in two classifications gets two rows and **one** entry number
- more than 40 straight-time hours with no overtime, since CWHSSA counts hours worked
  **off** the site of the covered contract toward the threshold
- a registered apprentice row without a level of progression
- wage determinations listed without their revision number

The form is optional. The weekly submission is not — 29 CFR 5.5(a)(3)(ii) requires a
certified payroll every week, and any format satisfies it provided each payroll carries a
Statement of Compliance with wording identical to WH-347 page 2.

---

## The dataset

| File | What it holds |
|---|---|
| [`data/sources.json`](data/sources.json) | The source registry. Every claim elsewhere cites an id from here |
| [`data/jurisdictions.json`](data/jurisdictions.json) | Filing cadence, accepted formats, portals, worker identifiers, fringe models, penalties, authority — federal, CA, NY, WA |
| [`data/wh347.json`](data/wh347.json) | Header fields, columns 1A–9, page 2 and its six checkboxes, the easy-to-miss rules, and the checks the library applies |
| [`data/ca-ecpr.json`](data/ca-ecpr.json) | 83 elements extracted from DIR's `CPR.xsd` v1.3, plus 23 documented rules and the filename convention |
| [`data/ny-certpayroll.json`](data/ny-certpayroll.json) | 43 elements extracted from `NYDOL_CertPayroll.xsd` v2.0, plus 23 documented rules and the partitioning rules |
| [`data/wa-pwia.json`](data/wa-pwia.json) | 16 rules from L&I's upload guide, the statutory record contents, the optional demographic fields, and the five-step upload validation |
| [`data/conflicts.json`](data/conflicts.json) | Where a schema and its own documentation disagree, with both positions quoted |

Query it without writing code:

```bash
certified-payroll jurisdictions
certified-payroll show us-ny
certified-payroll rules ny-certpayroll
certified-payroll rule ny.employee.exactlyOneIdentifier
certified-payroll elements ca-ecpr
certified-payroll conflicts
certified-payroll wh347
```

Or in Node and Python:

```js
import { jurisdiction, rules, rule, elements, conflicts } from 'certified-payroll-formats';
jurisdiction('us-ny').machineReadableFormat.maxRecordsPerFile;  // 500
rule('ca.name.idAttribute').sources[0].url;
```

```python
from certified_payroll_formats import jurisdiction, rules, rule, elements, conflicts
jurisdiction("us-ny")["machineReadableFormat"]["maxRecordsPerFile"]  # 500
```

---

## How the data is produced, and how to check it

`data/ca-ecpr.json` and `data/ny-certpayroll.json` are generated. `tools/build_formats.py`
fetches each agency's XSD, extracts every element with its cardinality and facets, and
merges in the prose rules from `tools/rules-ca.json` and `tools/rules-ny.json`. Regenerate
and diff:

```bash
python3 tools/build_formats.py
git diff data/
```

A clean diff means the published schemas have not changed since the review date. A dirty
one is the signal to re-read the guides.

Every other file is hand-maintained and every entry carries `sources`. Test suites in
both languages assert that no claim cites a source id that does not exist, and that no
source lacks a title, publisher, kind and URL.

Facts are dated, not evergreen. Each data file carries `reviewed`; the current review is
**31 August 2026**. Filing rules change and agencies revise their schemas without
announcing it. Check the source before you rely on the copy.

### Sourcing rules

1. Primary artifacts only — the schema, the XSD, the statute, the agency's own
   instructions. No commentary, no vendor documentation, no secondary summaries.
2. Where something was determined by reading a published sample file rather than prose,
   the entry says so.
3. Discretionary or as-of positions are labelled as such and dated, never stated as
   settled law. New York's current non-enforcement posture on late payrolls is recorded
   this way in `jurisdictions.json` — it is a posture, not a change in the statute.
4. Nothing is inferred silently. The two entries that reason from element naming rather
   than a stated rule are marked `"inferred": true`.

---

## Scope

Covered: the federal baseline, and the three states that publish a machine-readable
format and a schema you can build against.

Not covered: the other forty-seven states, city and county programs that apply on top of
a state one, wage determination data, classification lists (New York validates
`workCategory` against an approved list that is not published as a machine-readable
file), and rate calculation. Washington's schema is served from inside the PWIA portal
and has no public URL, so its entry records the published upload guide only and carries
no extracted element tree.

This library does not file anything, does not talk to any portal — none of the three
offers an API for bulk certified payroll — and does not render a PDF.

---

## Development

```bash
cd js && npm test                                            # 135 tests
cd py && PYTHONPATH=src python3 -m unittest discover -s tests # 146 tests
python3 tools/differential.py                                # both, on 485 mutants
```

No dependencies and no network in any of them.

Fixtures live in [`fixtures/`](fixtures/). Each format has a valid file that must produce
zero findings and an invalid file carrying one seeded fault per documented rule, and both
suites assert the same rule fires for the same fault.

Unit tests only catch what someone thought to test, so `tools/differential.py` walks every
element of every fixture and mutates it five ways — drop it, duplicate it, blank it,
corrupt it, replace it with non-ASCII — then checks that both implementations report an
identical set of rule ids for all 485 mutants. It is a CI job. Two implementations that
disagree about a file are worse than one, and this is what stops them drifting.

The suites also cover the inputs these formats actually permit at their limits: the
largest file New York accepts is 500 employee work weeks, about a megabyte, and parsing
it must stay linear.

`data/` at the repository root is the single source of truth. `tools/sync_packages.py`
copies it into each package before publishing, because neither npm nor a Python wheel can
reference files above the package directory; the loaders fall back to the root when you
run from a checkout.

Corrections are the most valuable contribution here — see [CONTRIBUTING.md](CONTRIBUTING.md).
If a rule is wrong, or an agency has changed something, open an issue with the official
source and it will be fixed and dated.

---

## Licence and provenance

MIT. See [LICENSE](LICENSE).

Statutes, regulations, agency instructions and published schemas are quoted and cited,
not redistributed: this repository links to each source rather than vendoring it, and
the fixtures are synthetic files written for this project, not copies of agency samples.

Maintained by [Osketh](https://osketh.com), which builds quiet software for regulated
back offices — systems that read a document, check every value against the rules that
govern it, and file the result. This repository is reference material, not a product.

**Not legal advice.** Verify against the official source before relying on anything here.
