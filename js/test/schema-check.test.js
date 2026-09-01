import test from 'node:test';
import assert from 'node:assert/strict';
import { parseXml } from '../src/xml.js';
import { checkAgainstSchema, isCalendarDate } from '../src/schema-check.js';
import { validateCaEcpr, validateNyCertPayroll } from '../src/index.js';
import { fixture, mutate, ids, first } from './helpers.js';

const ca = (edits) => validateCaEcpr(mutate(fixture('ca', 'valid.xml'), edits));
const ny = (edits) => validateNyCertPayroll(mutate(fixture('ny', 'valid.xml'), edits));

test('isCalendarDate knows the length of every month and the leap rule', () => {
  assert.equal(isCalendarDate(2026, 1, 31), true);
  assert.equal(isCalendarDate(2026, 4, 31), false, 'April has 30 days');
  assert.equal(isCalendarDate(2026, 2, 29), false, '2026 is not a leap year');
  assert.equal(isCalendarDate(2024, 2, 29), true, '2024 is');
  assert.equal(isCalendarDate(1900, 2, 29), false, 'a century that is not a leap year');
  assert.equal(isCalendarDate(2000, 2, 29), true, 'a century that is');
  assert.equal(isCalendarDate(2026, 13, 1), false);
  assert.equal(isCalendarDate(2026, 0, 1), false);
  assert.equal(isCalendarDate(2026, 1, 0), false);
});

test('a date that matches the pattern but is not a real date is a type error', () => {
  const result = ca([['<CPR:forWeekEnding>2026-08-28</CPR:forWeekEnding>',
                      '<CPR:forWeekEnding>2026-13-45</CPR:forWeekEnding>']]);
  assert.deepEqual(ids(result), ['schema.type']);
  assert.match(first(result, 'schema.type').message, /xs:date/);
});

test('an impossible calendar date does not manufacture week-window findings', () => {
  // Rolling 2026-13-45 forward through the Date constructor lands in another month and
  // would report every day in the file as out of range.
  const result = ny([['2026-08-02T00:00:00.000Z', '2026-13-45T00:00:00.000Z']]);
  assert.deepEqual(ids(result), ['schema.type']);
});

test('an empty element is not a valid decimal or date', () => {
  for (const [from, to] of [
    ['<CPR:totHrsStraightTime>40.0</CPR:totHrsStraightTime>', '<CPR:totHrsStraightTime></CPR:totHrsStraightTime>'],
    ['<CPR:forWeekEnding>2026-08-28</CPR:forWeekEnding>', '<CPR:forWeekEnding></CPR:forWeekEnding>'],
  ]) {
    const result = ca([[from, to]]);
    assert.ok(ids(result).includes('schema.type'), `${to} should be a type error`);
    assert.match(first(result, 'schema.type').message, /empty/);
  }
});

test('an empty pattern-constrained string fails the pattern, not the type', () => {
  // California declares statementOfNP as xs:string with pattern true|false rather than
  // xs:boolean, so the empty value is a pattern failure. Both are errors; the rule id
  // should still say which facet was violated.
  const result = ca([['<CPR:statementOfNP>false</CPR:statementOfNP>',
                      '<CPR:statementOfNP></CPR:statementOfNP>']]);
  assert.deepEqual(ids(result), ['schema.pattern']);
});

test('an empty numeric element reports the type fault and not a phantom arithmetic one', () => {
  const result = ca([['<CPR:totHrsStraightTime>40.0</CPR:totHrsStraightTime>',
                      '<CPR:totHrsStraightTime></CPR:totHrsStraightTime>']]);
  assert.ok(!ids(result).includes('ca.totals.matchDays'),
    'reading the empty element as zero would produce a second, spurious finding');
});

test('an empty string element with minLength 0 is fine', () => {
  const result = ca([['<CPR:notes></CPR:notes>', '<CPR:notes></CPR:notes>']]);
  assert.deepEqual(ids(result), []);
});

test('enumerated values are enforced, and every enumerated value is accepted', () => {
  const bad = ny([['<type>Health/Welfare</type>', '<type>Health and Welfare</type>']]);
  assert.deepEqual(ids(bad), ['schema.enumeration']);
  assert.match(first(bad, 'schema.enumeration').expected, /Vacation\/Holiday/);

  for (const value of ['Health/Welfare', 'Vacation/Holiday', 'Apprenticeship/Training',
                       'Pension', 'Other Benefit (Type)']) {
    const result = ny([['<type>Health/Welfare</type>', `<type>${value}</type>`]]);
    assert.deepEqual(ids(result), [], `${value} is in the schema's enumeration`);
  }
});

test('patterns, lengths and ranges come from the published facets', () => {
  assert.deepEqual(ids(ca([['<CPR:contractorFEIN>123456789</CPR:contractorFEIN>',
                            '<CPR:contractorFEIN>12-3456789</CPR:contractorFEIN>']])), ['schema.pattern']);
  assert.deepEqual(ids(ca([['<CPR:licenseType>CSLB</CPR:licenseType>',
                            '<CPR:licenseType>cslb</CPR:licenseType>']])), ['schema.pattern'],
    'the pattern is case sensitive');
  assert.ok(ids(ca([['<CPR:city>Sacramento</CPR:city>', `<CPR:city>${'x'.repeat(26)}</CPR:city>`]]))
    .includes('schema.length'), 'contractorAddress/city is capped at 25');
  assert.ok(ids(ny([['<standardTimeHours>8.00</standardTimeHours>',
                     '<standardTimeHours>25.00</standardTimeHours>']]))
    .includes('schema.range'), 'a day cannot carry 25 hours');
  assert.ok(ids(ny([['<stHourlyRate>35.50</stHourlyRate>', '<stHourlyRate>35.505</stHourlyRate>']]))
    .includes('schema.fractionDigits'));
});

test('fixed="" elements must be present and empty', () => {
  assert.deepEqual(ids(ca([['<CPR:awardingBody></CPR:awardingBody>',
                            '<CPR:awardingBody>City of Example</CPR:awardingBody>']])), ['schema.fixedValue']);
  assert.deepEqual(ids(ca([['    <CPR:awardingBody></CPR:awardingBody>\n', '']])), ['schema.missingElement']);
});

test('occurrence limits are enforced in both directions', () => {
  const dayBlock = '<CPR:day id="7"><CPR:date>2026-08-28</CPR:date><CPR:straightTime>8.0</CPR:straightTime><CPR:overtime>0.0</CPR:overtime><CPR:doubletime>0.0</CPR:doubletime></CPR:day>';
  assert.ok(ids(ca([[dayBlock, '']])).includes('schema.missingElement'),
    'hrsWorkedEachDay requires exactly seven days');
  assert.ok(ids(ca([[dayBlock, dayBlock + dayBlock]])).includes('schema.tooManyElements'));
});

test('an element the schema does not declare is reported', () => {
  const result = ca([['<CPR:checkNum>1001</CPR:checkNum>',
                      '<CPR:checkNum>1001</CPR:checkNum><CPR:bonus>50.00</CPR:bonus>']]);
  assert.ok(ids(result).includes('schema.unexpectedElement'));
  assert.match(first(result, 'schema.unexpectedElement').message, /not declared under/);
});

test('elements out of sequence are reported once, not once per element', () => {
  const result = ca([['<CPR:netWagePaidWeek>946.06</CPR:netWagePaidWeek>\n          <CPR:checkNum>1001</CPR:checkNum>',
                      '<CPR:checkNum>1001</CPR:checkNum>\n          <CPR:netWagePaidWeek>946.06</CPR:netWagePaidWeek>']]);
  assert.deepEqual(ids(result), ['schema.elementOrder']);
});

test('a wrong document element short-circuits rather than reporting every child', () => {
  const { root } = parseXml('<CPR:notTheRoot xmlns:CPR="urn:x"><a/></CPR:notTheRoot>');
  const findings = checkAgainstSchema(root, 'ca-ecpr', 'urn:x');
  assert.equal(findings.length, 1);
  assert.match(findings[0].message, /document element must be <eCPR>/);
});

test('the namespace check can be delegated to the caller', () => {
  const { root } = parseXml('<eCPR xmlns="urn:wrong"/>');
  assert.ok(checkAgainstSchema(root, 'ca-ecpr', 'urn:right')
    .some((f) => f.ruleId === 'schema.namespace'));
  assert.ok(!checkAgainstSchema(root, 'ca-ecpr', 'urn:right', { reportNamespace: false })
    .some((f) => f.ruleId === 'schema.namespace'));
});

test('every schema finding carries the schema itself as its source', () => {
  const result = ca([['<CPR:contractorFEIN>123456789</CPR:contractorFEIN>',
                      '<CPR:contractorFEIN>x</CPR:contractorFEIN>']]);
  const finding = first(result, 'schema.pattern');
  assert.equal(finding.sources[0].id, 'ca-dir-xsd');
  assert.equal(finding.sources[0].kind, 'schema');
});
