import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateCaEcpr, validateNyCertPayroll } from '../src/index.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'fixtures');
const read = (...p) => readFileSync(join(FIXTURES, ...p), 'utf8');
const ids = (result) => result.findings.map((f) => f.ruleId);

test('California: the valid fixture produces no errors', () => {
  const result = validateCaEcpr(read('ca', 'valid.xml'), { filename: '6789_9_082826.xml' });
  assert.deepEqual(result.findings, [], 'unexpected findings');
  assert.equal(result.valid, true);
});

test('California: the invalid fixture produces one finding per seeded fault', () => {
  const result = validateCaEcpr(read('ca', 'invalid.xml'), { filename: 'invalid.xml' });
  const found = ids(result);
  for (const expected of [
    'schema.pattern',                     // licenseType outside CSLB|PL|OTHER
    'schema.fixedValue',                  // projectName is declared fixed=""
    'ca.statementOfNP.noEmployees',
    'ca.name.idAttribute',
    'ca.name.idMatchesSsn',
    'ca.days.consecutive',
    'ca.totals.matchDays',
    'ca.deductions.totalMatchesItems',
    'ca.gross.projectNotAboveAll',
    'ca.filename.convention',
  ]) {
    assert.ok(found.includes(expected), `missing ${expected}`);
  }
  assert.equal(result.valid, false);
});

test('California: every finding cites a resolvable official source', () => {
  const result = validateCaEcpr(read('ca', 'invalid.xml'));
  for (const f of result.findings) {
    assert.ok(f.sources.length > 0, f.ruleId);
    for (const s of f.sources) assert.match(s.url, /^https?:\/\//);
  }
});

test('New York: the valid fixture produces no findings at all', () => {
  const result = validateNyCertPayroll(read('ny', 'valid.xml'), { filename: 'week.xml' });
  assert.deepEqual(result.findings, []);
});

test('New York: the invalid fixture catches what the XSD cannot', () => {
  const result = validateNyCertPayroll(read('ny', 'invalid.xml'));
  const found = ids(result);
  for (const expected of [
    'ny.employee.exactlyOneIdentifier',   // both, then neither
    'ny.address.stateFullName',
    'ny.days.withinWeek',
    'schema.pattern',                     // bare weekEndingDate, oversized deduction amount
    'schema.type',                        // nysRegisteredApprentice sent as Y
    'schema.missingElement',              // country omitted
  ]) {
    assert.ok(found.includes(expected), `missing ${expected}`);
  }
  assert.equal(found.filter((i) => i === 'ny.employee.exactlyOneIdentifier').length, 2,
    'one for the employee carrying both, one for the employee carrying neither');
});

test('New York: a namespaced instance is reported once, not per element', () => {
  const result = validateNyCertPayroll(read('ny', 'invalid-namespace.xml'));
  assert.deepEqual(ids(result), ['ny.root.noNamespace']);
});

test('malformed XML yields one parse finding rather than an exception', () => {
  const ca = validateCaEcpr('<CPR:eCPR><oops>');
  assert.equal(ca.findings.length, 1);
  assert.equal(ca.findings[0].ruleId, 'ca.parse');
  const ny = validateNyCertPayroll('not xml at all');
  assert.equal(ny.findings[0].ruleId, 'ny.parse');
});

test('a DOCTYPE in a submitted file is refused, not expanded', () => {
  const result = validateNyCertPayroll('<!DOCTYPE ProjectRollup [<!ENTITY a "b">]><ProjectRollup/>');
  assert.equal(result.findings[0].ruleId, 'ny.parse');
  assert.match(result.findings[0].message, /DOCTYPE/);
});
