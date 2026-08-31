# Fixtures

Synthetic files. Every name, number, address and identifier is invented; none of these is
a copy of an agency sample. The structure follows each agency's published schema and
guide, so a fixture is also a worked example of a well-formed file.

| File | What it is |
|---|---|
| `ca/valid.xml` | A California eCPR file that produces zero findings. Week ending Friday 28 August 2026 |
| `ca/invalid.xml` | The same file with nine seeded faults, one per documented rule |
| `ny/valid.xml` | A New York bulk upload file that produces zero findings. Week ending Sunday 2 August 2026 |
| `ny/invalid.xml` | The same file with six seeded faults |
| `ny/invalid-namespace.xml` | `ny/valid.xml` with a default namespace added — `NYDOL_CertPayroll.xsd` declares none, so this fails |

## Seeded faults

`ca/invalid.xml`

| Fault | Rule |
|---|---|
| `licenseType` of `STATE` | `schema.pattern` |
| `projectName` carries a value | `schema.fixedValue` — it is declared `fixed=""` |
| `statementOfNP` is `true` with an employee present | `ca.statementOfNP.noEmployees` |
| name `id` of `999887777::Jane Example` | `ca.name.idAttribute` (not upper-case) and `ca.name.idMatchesSsn` (does not match `<ssn>`) |
| first day dated a week early | `ca.days.consecutive` |
| `totHrsStraightTime` of 32 against 40 daily hours | `ca.totals.matchDays` |
| deductions `total` of 250.00 against items summing to 298.94 | `ca.deductions.totalMatchesItems` |
| `thisProject` above `allWork` | `ca.gross.projectNotAboveAll` |
| the filename itself | `ca.filename.convention` |

`ny/invalid.xml`

| Fault | Rule |
|---|---|
| `weekEndingDate` as a bare date | `schema.pattern` — the schema demands `…T00:00:00.000Z` |
| first employee carries both `ssnLast4` and `dateOfBirth` | `ny.employee.exactlyOneIdentifier` |
| second employee carries neither | `ny.employee.exactlyOneIdentifier` |
| `state` of `NY` | `ny.address.stateFullName` |
| a day dated outside the week | `ny.days.withinWeek` |
| a deduction `amount` of 12000.00 | `schema.pattern` — at most four digits before the point |
| `nysRegisteredApprentice` of `Y` | `schema.type` — the element is `xs:boolean` |
| `country` omitted | `schema.missingElement` |

Both test suites assert that the same rule ids fire for the same file, which is what
keeps the JavaScript and Python implementations from drifting apart.
