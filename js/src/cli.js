#!/usr/bin/env node
// certified-payroll — query the dataset, or validate a file against a published format.

import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import {
  jurisdictions, jurisdiction, conflicts, rules, rule, elements, wh347Data,
} from './index.js';
import { validateCaEcpr } from './validate-ca.js';
import { validateNyCertPayroll } from './validate-ny.js';

const USAGE = `certified-payroll — US certified payroll formats, as data

  certified-payroll validate ca <file.xml>   validate against California's eCPR schema and guideline
  certified-payroll validate ny <file.xml>   validate against New York's bulk upload schema and guide
  certified-payroll jurisdictions            list the covered filing regimes
  certified-payroll show <id>                one jurisdiction (us, us-ca, us-ny, us-wa)
  certified-payroll rules <format>           documented rules (ca-ecpr, ny-certpayroll, wa-pwia)
  certified-payroll rule <id>                one rule, with its official sources
  certified-payroll elements <format>        the element tree extracted from the published XSD
  certified-payroll conflicts                where a schema and its own documentation disagree
  certified-payroll wh347                    the WH-347 field map

Options
  --json      machine-readable output
  --quiet     validate: suppress warnings and advisories

Exit codes: 0 clean, 1 errors found, 2 bad usage.
`;

const args = process.argv.slice(2);
const flags = new Set(args.filter((a) => a.startsWith('--')));
const positional = args.filter((a) => !a.startsWith('--'));
const asJson = flags.has('--json');
const out = (value) => console.log(asJson ? JSON.stringify(value, null, 2) : value);

function printFindings(result, filename) {
  if (asJson) { console.log(JSON.stringify({ file: filename, ...result }, null, 2)); return; }
  const shown = flags.has('--quiet')
    ? result.findings.filter((f) => f.severity === 'error')
    : result.findings;
  for (const f of shown) {
    const where = [f.line ? `line ${f.line}` : null, f.path].filter(Boolean).join(' · ');
    console.log(`${f.severity.toUpperCase()}  ${f.message}`);
    console.log(`      ${where}`);
    if (f.expected !== null) console.log(`      expected: ${f.expected}`);
    if (f.actual !== null) console.log(`      actual:   ${f.actual}`);
    console.log(`      rule ${f.ruleId} — ${f.sources.map((s) => s.url).join(' ')}`);
    console.log('');
  }
  const { error = 0, warning = 0, advisory = 0 } = result.counts;
  console.log(`${filename}: ${error} error(s), ${warning} warning(s), ${advisory} advisory`);
}

function main() {
  const [command, ...rest] = positional;
  switch (command) {
    case undefined:
    case 'help':
    case '-h':
      process.stdout.write(USAGE);
      return 0;

    case 'validate': {
      const [format, file] = rest;
      if (!file || !['ca', 'ny'].includes(format)) { process.stderr.write(USAGE); return 2; }
      let xml;
      try {
        xml = readFileSync(file, 'utf8');
      } catch (error) {
        process.stderr.write(`certified-payroll: cannot read ${file}: ${error.code ?? error.message}\n`);
        return 2;
      }
      const filename = basename(file);
      const result = format === 'ca'
        ? validateCaEcpr(xml, { filename })
        : validateNyCertPayroll(xml, { filename });
      printFindings(result, filename);
      return result.valid ? 0 : 1;
    }

    case 'jurisdictions':
      if (asJson) { out(jurisdictions()); return 0; }
      for (const j of jurisdictions()) {
        console.log(`${j.id.padEnd(6)}  ${j.name.padEnd(38)} ${j.filingFrequency.value}`);
      }
      return 0;

    case 'show': {
      const found = jurisdiction(rest[0]);
      if (!found) { process.stderr.write(`Unknown jurisdiction: ${rest[0]}\n`); return 2; }
      out(asJson ? found : JSON.stringify(found, null, 2));
      return 0;
    }

    case 'rules': {
      const list = rules(rest[0]);
      if (asJson) { out(list); return 0; }
      for (const r of list) {
        console.log(`${r.severity.padEnd(9)} ${r.id}`);
        console.log(`          ${r.statement}`);
        console.log(`          ${r.sources.map((s) => s.url).join(' ')}`);
        console.log('');
      }
      return 0;
    }

    case 'rule': {
      const found = rule(rest[0]);
      if (!found) { process.stderr.write(`Unknown rule: ${rest[0]}\n`); return 2; }
      out(asJson ? found : JSON.stringify(found, null, 2));
      return 0;
    }

    case 'elements': {
      const list = elements(rest[0]);
      if (asJson) { out(list); return 0; }
      for (const e of list) {
        const occurs = `[${e.minOccurs}..${e.maxOccurs}]`;
        console.log(`${occurs.padEnd(12)} ${e.path}${e.type ? `  ${e.type}` : ''}`);
      }
      return 0;
    }

    case 'conflicts': {
      const list = conflicts();
      if (asJson) { out(list); return 0; }
      for (const c of list) {
        console.log(`${c.id}  (${c.format}${c.element ? ` · ${c.element}` : ''})`);
        console.log(`  ${c.resolution}`);
        console.log('');
      }
      return 0;
    }

    case 'wh347':
      out(asJson ? wh347Data() : JSON.stringify(wh347Data(), null, 2));
      return 0;

    default:
      process.stderr.write(USAGE);
      return 2;
  }
}

// Setting exitCode rather than calling process.exit() lets Node flush stdout first;
// process.exit() truncates large piped output mid-write.
process.exitCode = main();
