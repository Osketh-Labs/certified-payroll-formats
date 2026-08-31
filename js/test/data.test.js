import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { sources, jurisdictions, jurisdiction, conflicts, rules, rule, elements, wh347Data } from '../src/index.js';

const DATA = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'data');

test('every data file is valid JSON', () => {
  for (const name of readdirSync(DATA).filter((f) => f.endsWith('.json'))) {
    assert.doesNotThrow(() => JSON.parse(readFileSync(join(DATA, name), 'utf8')), name);
  }
});

test('every source id referenced anywhere resolves', () => {
  const known = new Set(Object.keys(sources()));
  const missing = new Set();
  const walk = (node) => {
    if (Array.isArray(node)) { node.forEach(walk); return; }
    if (!node || typeof node !== 'object') return;
    for (const [key, value] of Object.entries(node)) {
      if (key === 'sources' && Array.isArray(value)) {
        for (const id of value) if (typeof id === 'string' && !known.has(id)) missing.add(id);
      } else if (key.endsWith('Says') && value && typeof value === 'object' && typeof value.source === 'string') {
        if (!known.has(value.source)) missing.add(value.source);
      } else {
        walk(value);
      }
    }
  };
  for (const name of readdirSync(DATA).filter((f) => f.endsWith('.json') && f !== 'sources.json')) {
    walk(JSON.parse(readFileSync(join(DATA, name), 'utf8')));
  }
  assert.deepEqual([...missing], [], 'unresolved source ids');
});

test('every source carries a title, publisher, kind and url', () => {
  for (const [id, s] of Object.entries(sources())) {
    for (const field of ['title', 'publisher', 'kind', 'url']) {
      assert.ok(s[field], `${id} is missing ${field}`);
    }
    assert.match(s.url, /^https?:\/\//, `${id} url`);
  }
});

test('every rule has an id, a severity and a statement', () => {
  for (const formatId of ['ca-ecpr', 'ny-certpayroll', 'wa-pwia']) {
    for (const r of rules(formatId)) {
      assert.ok(r.id.startsWith(formatId.split('-')[0]), `${r.id} should be namespaced by jurisdiction`);
      assert.ok(['error', 'warning', 'advisory'].includes(r.severity), `${r.id} severity`);
      assert.ok(r.statement.length > 20, `${r.id} statement`);
      assert.ok(r.sources.length > 0, `${r.id} sources`);
    }
  }
});

test('rule ids are unique across formats', () => {
  const seen = new Set();
  for (const formatId of ['ca-ecpr', 'ny-certpayroll', 'wa-pwia']) {
    for (const r of rules(formatId)) {
      assert.ok(!seen.has(r.id), `duplicate rule id ${r.id}`);
      seen.add(r.id);
    }
  }
});

test('jurisdictions are addressable and cover the documented set', () => {
  assert.deepEqual(jurisdictions().map((j) => j.id), ['us', 'us-ca', 'us-ny', 'us-wa']);
  assert.equal(jurisdiction('us-ny').machineReadableFormat.rootElement, 'ProjectRollup');
  assert.equal(jurisdiction('nope'), null);
});

test('the four regimes disagree about the worker identifier, and the data says so', () => {
  const identifiers = Object.fromEntries(jurisdictions().map((j) => [j.id, j.workerIdentifier]));
  assert.ok(identifiers.us.prohibits.includes('ssn-full'));
  assert.ok(identifiers['us-ca'].accepts.includes('ssn-full'));
  assert.equal(identifiers['us-ny'].exactlyOne, true);
  assert.ok(identifiers['us-wa'].accepts.includes('ssn-full'));
});

test('extracted element trees match the published schemas', () => {
  const ca = elements('ca-ecpr');
  assert.equal(ca[0].path, 'eCPR');
  const employee = ca.find((e) => e.path.endsWith('/employees/employee'));
  assert.equal(employee.maxOccurs, '500');
  const day = ca.find((e) => e.path.endsWith('hrsWorkedEachDay/day'));
  assert.equal(day.minOccurs, '7');
  assert.equal(day.maxOccurs, '7');

  const ny = elements('ny-certpayroll');
  assert.equal(ny[0].path, 'ProjectRollup');
  const week = ny.find((e) => e.path.endsWith('/employeeWorkWeek'));
  assert.equal(week.maxOccurs, '500');
  const dob = ny.find((e) => e.path.endsWith('/dateOfBirth'));
  const ssn4 = ny.find((e) => e.path.endsWith('/ssnLast4'));
  assert.equal(dob.minOccurs, '0');
  assert.equal(ssn4.minOccurs, '0', 'the schema cannot express the exactly-one rule');
});

test('rule lookup resolves sources to full records', () => {
  const r = rule('ny.employee.exactlyOneIdentifier');
  assert.equal(r.severity, 'error');
  assert.equal(r.expressibleInXsd, false);
  assert.equal(r.sources[0].publisher, 'New York State Department of Labor');
});

test('conflicts each name a format and a resolution', () => {
  const formats = new Set(['ca-ecpr', 'ny-certpayroll', 'wa-pwia']);
  for (const c of conflicts()) {
    assert.ok(formats.has(c.format), `${c.id} format`);
    assert.ok(c.resolution.length > 20, `${c.id} resolution`);
    assert.ok(c.kind, `${c.id} kind`);
  }
});

test('the WH-347 map covers the 2025 column set', () => {
  const ids = wh347Data().columns.map((c) => c.id);
  assert.deepEqual(ids, ['1A', '1B', '1C', '1D', '1E', '2', '3', '4', '5', '6A', '6B', '6C', '7A', '7B', '8', '9']);
  assert.equal(wh347Data().form.ombControlNumber, '1235-0008');
});

test('the README\'s stated counts match the data', () => {
  const readme = readFileSync(join(DATA, '..', 'README.md'), 'utf8');
  const expectations = [
    [/(\d+) elements extracted from DIR's `CPR\.xsd`/, elements('ca-ecpr').length],
    [/plus (\d+) documented rules and the filename convention/, rules('ca-ecpr').length],
    [/(\d+) elements extracted from `NYDOL_CertPayroll\.xsd`/, elements('ny-certpayroll').length],
    [/plus (\d+) documented rules and the partitioning rules/, rules('ny-certpayroll').length],
    [/(\d+) rules from L&I's upload guide/, rules('wa-pwia').length],
  ];
  for (const [pattern, expected] of expectations) {
    const match = readme.match(pattern);
    assert.ok(match, `README no longer states a count for ${pattern}`);
    assert.equal(Number(match[1]), expected, `README count for ${pattern}`);
  }
});

test('every conflict in the data is mentioned in the README', () => {
  const readme = readFileSync(join(DATA, '..', 'README.md'), 'utf8');
  // The README summarises conflicts in prose, so match on the element rather than the id.
  const unmentioned = conflicts().filter((c) => {
    const needle = (c.element ?? '').split(',')[0].trim().split('/').pop();
    return needle && !readme.includes(needle);
  });
  assert.deepEqual(unmentioned.map((c) => c.id), []);
});
