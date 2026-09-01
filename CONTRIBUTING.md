# Contributing

The value of this repository is that it is right. Corrections are the most useful thing
you can send, and they are held to the same standard as everything already here.

## Corrections and additions

Open an issue or a pull request with **the official source**. Primary artifacts only:
the statute, the regulation, the published schema, the agency's own instructions, or an
agency sample file. Commentary, vendor documentation, blog posts and secondary summaries
are not sources, however accurate they may be.

A correction needs three things:

1. What the data currently says.
2. What it should say.
3. The URL of the official source, and where in it the claim appears — a section number,
   a step in a guide, an element name in a schema.

If a claim came from reading a published sample file rather than from prose, say so; the
entry will record it that way.

## Adding a jurisdiction

Worth doing only where the state publishes a machine-readable format and a schema you
can build against. A new entry in `data/jurisdictions.json` needs the filing cadence,
accepted formats, the portal, the worker identifier, the fringe model, the project key,
the authority, and source ids for each. If the state publishes an XSD at a public URL,
add it to `SCHEMAS` in `tools/build_formats.py` and write a `tools/rules-<id>.json` for
the rules the schema cannot express, so the element tree is extracted rather than typed.

## Rules

A rule in `data/*.json` carries:

- `id` — namespaced by jurisdiction (`ca.`, `ny.`, `wa.`) or `wh347.`
- `severity` — `error` blocks the filing, `warning` is a mismatch worth a human look,
  `advisory` is a convention rather than a constraint
- `statement` — what the rule is, in a sentence a filer would understand
- `expressibleInXsd` — whether the published schema can enforce it. This is what divides
  the structural check from the format-specific pass
- `sources` — ids that resolve in `data/sources.json`
- `inferred: true` if the rule reasons from element naming rather than a stated rule.
  Prefer not to add these

Anything the schema already enforces is reported by the structural checker under a
`schema.*` id; document it as a rule anyway, so the data describes the format completely.

## Changing behaviour

Both implementations must agree. A rule that fires in JavaScript and not in Python is a
bug, and the fixtures exist to catch it: `fixtures/*/valid.xml` must produce zero
findings, and `fixtures/*/invalid.xml` carries one seeded fault per documented rule with
both test suites asserting the same rule ids.

```bash
cd js && npm test
cd py && PYTHONPATH=src python3 -m unittest discover -s tests
python3 tools/differential.py
```

The last one is the important one for a behaviour change. It mutates every element of
every fixture four ways and fails if the two implementations report different rule ids for
any mutant, which is how a change made in one language and forgotten in the other gets
caught.

Neither package may take a runtime dependency. The test suites use `node:test` and
`unittest` for the same reason. If a change seems to need a library, it probably needs a
smaller change instead.

Regenerate the extracted element trees and review the diff whenever an agency may have
revised a schema:

```bash
python3 tools/build_formats.py
git diff data/
```

When you change a fact, update the `reviewed` date on that file in the same commit.

## What this repository will not become

A filing client, a PDF renderer, a rate calculator, or a wrapper around a portal. None of
the three states offers an API for bulk certified payroll, and pretending otherwise would
make the repository less useful, not more.
