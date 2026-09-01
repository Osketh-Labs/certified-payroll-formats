// Inputs that are legal but awkward: the largest file each format permits, names that
// are not ASCII, and structures deep enough to break a naive parser.

import test from 'node:test';
import assert from 'node:assert/strict';
import { parseXml, at, pathOf, textAt } from '../src/xml.js';
import { validateCaEcpr, validateNyCertPayroll, elements, rules, resolveSources } from '../src/index.js';
import { summarize } from '../src/finding.js';
import { fixture, ids } from './helpers.js';

/** A New York file carrying `n` distinct employee work weeks. */
function nyWithRecords(n) {
  const source = fixture('ny', 'valid.xml');
  const block = source.match(/ {4}<employeeWorkWeek>[\s\S]*?<\/employeeWorkWeek>\n/)[0];
  const body = Array.from({ length: n }, (_, i) => block
    .replace('<ssnLast4>0323</ssnLast4>', `<ssnLast4>${String(i % 10000).padStart(4, '0')}</ssnLast4>`)
    .replace('<firstName>Steven</firstName>', `<firstName>Worker${i}</firstName>`)).join('');
  return source.replace(/ {4}<employeeWorkWeek>[\s\S]*<\/employeeWorkWeek>\n/, body);
}

test('the largest file New York permits validates cleanly', () => {
  const xml = nyWithRecords(500);
  assert.ok(xml.length > 900_000, 'a 500-record file is about a megabyte');
  const result = validateNyCertPayroll(xml);
  assert.deepEqual(result.findings, [], 'five hundred distinct workers is legal');
});

test('parsing is linear in file size, not quadratic', () => {
  // Recomputing each node's line number by counting newlines from the start of the
  // document made this quadratic: the 500-record file took seconds rather than
  // milliseconds. The ratio is the guard, because it survives a slow CI machine.
  const time = (xml) => { const t = process.hrtime.bigint(); validateNyCertPayroll(xml); return Number(process.hrtime.bigint() - t); };
  const small = nyWithRecords(100);
  const large = nyWithRecords(500);
  time(small); // warm up, so the first run does not pay for lazy compilation
  const ratio = time(large) / time(small);
  assert.ok(ratio < 12, `five times the input should not cost ${ratio.toFixed(1)}x (quadratic would be ~25x)`);
});

test('deep nesting does not exhaust the stack', () => {
  const depth = 2000;
  const xml = `${'<a>'.repeat(depth)}deep${'</a>'.repeat(depth)}`;
  const { root } = parseXml(xml);
  let node = root;
  let counted = 1;
  while (node.children.length) { node = node.children[0]; counted += 1; }
  assert.equal(counted, depth);
  assert.equal(node.text, 'deep');
  assert.equal(pathOf(node).split('/').length, depth);
});

test('length facets count characters, not UTF-16 code units', () => {
  // contractorAddress/city is capped at 25 characters. An astral-plane character is one
  // character and two code units; measuring code units rejects a legal name.
  const city = (n) => fixture('ca', 'valid.xml')
    .replace('<CPR:city>Sacramento</CPR:city>', `<CPR:city>${'\u{1d54f}'.repeat(n)}</CPR:city>`);
  assert.deepEqual(ids(validateCaEcpr(city(25))), [], '25 characters is at the limit');
  assert.deepEqual(ids(validateCaEcpr(city(26))), ['schema.length'], '26 is over it');
});

test('non-ASCII text and attributes survive parsing intact', () => {
  const { root } = parseXml('<a n="Ünïcødé"><b>Zoë Ñuñez 中文 \u{1f600}</b></a>');
  assert.equal(root.attrs.n, 'Ünïcødé');
  assert.equal(textAt(root, 'b'), 'Zoë Ñuñez 中文 \u{1f600}');
});

test('a worker name with non-ASCII characters validates normally', () => {
  const xml = fixture('ny', 'valid.xml').replace('<lastName>Bradley</lastName>', '<lastName>Ñuñez-Öztürk</lastName>');
  assert.deepEqual(ids(validateNyCertPayroll(xml)), []);
});

test('a very long single text node is handled', () => {
  const { root } = parseXml(`<a>${'x'.repeat(500_000)}</a>`);
  assert.equal(root.text.length, 500_000);
});

test('an element with many attributes is handled', () => {
  const attrs = Array.from({ length: 500 }, (_, i) => `a${i}="${i}"`).join(' ');
  const { root } = parseXml(`<e ${attrs}/>`);
  assert.equal(Object.keys(root.attrs).length, 500);
  assert.equal(root.attrs.a499, '499');
});

// ------------------------------------------------------------------- loaders

test('the data loaders refuse a format they do not have', () => {
  assert.throws(() => rules('us-tx'), /Unknown format/);
  assert.throws(() => elements('wa-pwia'), /No extracted element tree/,
    'Washington publishes no reachable schema, so there is nothing to extract');
});

test('an unknown source id resolves to a marker rather than undefined', () => {
  const [resolved] = resolveSources(['not-a-source']);
  assert.equal(resolved.id, 'not-a-source');
  assert.match(resolved.title, /unknown source/);
  assert.deepEqual(resolveSources(), []);
});

// ------------------------------------------------------------------ findings

test('summarize counts by severity and reports validity from errors alone', () => {
  const make = (severity, line) => ({ severity, line, ruleId: `r.${severity}${line}` });
  const summary = summarize([
    make('advisory', 3), make('error', 9), make('warning', 1), make('error', 2),
  ]);
  assert.deepEqual(summary.counts, { error: 2, warning: 1, advisory: 1 });
  assert.equal(summary.valid, false);
  assert.deepEqual(summary.findings.map((f) => f.ruleId),
    ['r.error2', 'r.error9', 'r.warning1', 'r.advisory3'],
    'errors first, then by line within a severity');
});

test('summarize treats a file with only warnings as valid', () => {
  const summary = summarize([{ severity: 'warning', line: 1, ruleId: 'w' }]);
  assert.equal(summary.valid, true);
  assert.deepEqual(summary.counts, { error: 0, warning: 1, advisory: 0 });
});

test('summarize handles an empty finding list', () => {
  const summary = summarize([]);
  assert.equal(summary.valid, true);
  assert.deepEqual(summary.counts, { error: 0, warning: 0, advisory: 0 });
  assert.deepEqual(summary.findings, []);
});

test('a finding with no line still sorts without throwing', () => {
  const summary = summarize([
    { severity: 'error', line: null, ruleId: 'a' }, { severity: 'error', line: 5, ruleId: 'b' },
  ]);
  assert.deepEqual(summary.findings.map((f) => f.ruleId), ['a', 'b']);
});
