// One test per documented rule that the published schema cannot enforce. These are the
// rules that make the validators worth having: a file can pass XSD validation and fail
// every one of them.

import test from 'node:test';
import assert from 'node:assert/strict';
import { validateCaEcpr, validateNyCertPayroll } from '../src/index.js';
import { fixture, mutate, ids, count, first } from './helpers.js';

const ca = (edits = [], options) => validateCaEcpr(mutate(fixture('ca', 'valid.xml'), edits), options);
const ny = (edits = [], options) => validateNyCertPayroll(mutate(fixture('ny', 'valid.xml'), edits), options);

// ---------------------------------------------------------------- California

test('ca.projectInfo.mandatory: contractAgency may not be empty', () => {
  const result = ca([['<CPR:contractAgency>CA-DIR</CPR:contractAgency>',
                      '<CPR:contractAgency></CPR:contractAgency>']]);
  assert.ok(ids(result).includes('ca.projectInfo.mandatory'));
  assert.match(first(result, 'ca.projectInfo.mandatory').message, /contractAgency/);
});

test('ca.projectInfo.mandatory: an empty projectID needs the full lookup fallback', () => {
  const withoutId = [['<CPR:projectID>9</CPR:projectID>', '<CPR:projectID></CPR:projectID>']];
  assert.ok(ids(ca(withoutId)).includes('ca.projectInfo.mandatory'),
    'no projectID and no fallback');

  // The schema's own projectID annotation documents this fallback, and the three
  // elements are not fixed="", so supplying all of them is legitimate.
  const withFallback = ca([
    ...withoutId,
    ['<CPR:awardingBodyID></CPR:awardingBodyID>', '<CPR:awardingBodyID>123456789</CPR:awardingBodyID>'],
    ['<CPR:projectNum></CPR:projectNum>', '<CPR:projectNum>PN-1</CPR:projectNum>'],
    ['<CPR:contractID></CPR:contractID>', '<CPR:contractID>C-1</CPR:contractID>'],
  ]);
  assert.ok(!ids(withFallback).includes('ca.projectInfo.mandatory'));
});

test('ca.statementOfNP.noEmployees: true with an empty employees element is correct', () => {
  const employee = fixture('ca', 'valid.xml').match(/ {6}<CPR:employee>[\s\S]*?<\/CPR:employee>\n/)[0];
  const result = ca([
    ['<CPR:statementOfNP>false</CPR:statementOfNP>', '<CPR:statementOfNP>true</CPR:statementOfNP>'],
    [employee, ''],
  ]);
  assert.deepEqual(ids(result), [], 'a statement of non-performance carries no employees');
});

test('ca.statementOfNP.noEmployees: false with no employees is a fault', () => {
  const employee = fixture('ca', 'valid.xml').match(/ {6}<CPR:employee>[\s\S]*?<\/CPR:employee>\n/)[0];
  const result = ca([[employee, '']]);
  assert.deepEqual(ids(result), ['ca.statementOfNP.noEmployees']);
  assert.match(first(result, 'ca.statementOfNP.noEmployees').message, /no employee elements/);
});

test('ca.name.idAttribute: the id must be present and in SSN::NAME form', () => {
  assert.ok(ids(ca([[' id="111223333::JANE EXAMPLE"', '']])).includes('ca.name.idAttribute'));
  assert.ok(ids(ca([['id="111223333::JANE EXAMPLE"', 'id="JANE EXAMPLE"']])).includes('ca.name.idAttribute'));
  assert.ok(ids(ca([['id="111223333::JANE EXAMPLE"', 'id="111223333::"']])).includes('ca.name.idAttribute'));
});

test('ca.name.idMatchesSsn: the SSN half must match the ssn element', () => {
  const result = ca([['id="111223333::JANE EXAMPLE"', 'id="999887777::JANE EXAMPLE"']]);
  assert.deepEqual(ids(result), ['ca.name.idMatchesSsn']);
  assert.equal(first(result, 'ca.name.idMatchesSsn').expected, '111223333');
});

test('ca.days.consecutive: the seven dates must be the week ending on forWeekEnding', () => {
  assert.deepEqual(ids(ca([['<CPR:date>2026-08-22</CPR:date>', '<CPR:date>2026-08-15</CPR:date>']])),
    ['ca.days.consecutive'], 'a date outside the week');
  assert.deepEqual(ids(ca([['<CPR:date>2026-08-22</CPR:date>', '<CPR:date>2026-08-23</CPR:date>']])),
    ['ca.days.consecutive'], 'a duplicated date leaves the week incomplete');
});

test('ca.totals.matchDays: each weekly total is checked against its own daily column', () => {
  assert.deepEqual(ids(ca([['<CPR:totHrsOvertime>1.0</CPR:totHrsOvertime>',
                            '<CPR:totHrsOvertime>3.0</CPR:totHrsOvertime>']])), ['ca.totals.matchDays']);
  assert.deepEqual(ids(ca([['<CPR:totHrsDoubletime>0.0</CPR:totHrsDoubletime>',
                            '<CPR:totHrsDoubletime>2.0</CPR:totHrsDoubletime>']])), ['ca.totals.matchDays']);
});

test('ca.deductions.totalMatchesItems: the total is the sum of the itemised lines', () => {
  const result = ca([['<CPR:SDI>13.70</CPR:SDI>', '<CPR:SDI>20.00</CPR:SDI>']]);
  assert.deepEqual(ids(result), ['ca.deductions.totalMatchesItems']);
  assert.equal(first(result, 'ca.deductions.totalMatchesItems').expected, '305.24');
});

test('ca.gross.projectNotAboveAll: this project cannot exceed all work', () => {
  assert.deepEqual(ids(ca([['<CPR:allWork>1245.00</CPR:allWork>', '<CPR:allWork>1000.00</CPR:allWork>']])),
    ['ca.gross.projectNotAboveAll']);
  assert.deepEqual(ids(ca([['<CPR:allWork>1245.00</CPR:allWork>', '<CPR:allWork>2000.00</CPR:allWork>']])),
    [], 'earning more elsewhere in the week is normal');
});

test('ca.filename.convention: the guideline pattern is accepted, anything else is advisory', () => {
  assert.deepEqual(ids(ca([], { filename: '6789_DIR001_010915.xml' })), []);
  assert.deepEqual(ids(ca([], { filename: 'payroll.xml' })), ['ca.filename.convention']);
  assert.equal(first(ca([], { filename: 'payroll.xml' }), 'ca.filename.convention').severity, 'advisory');
});

// ------------------------------------------------------------------ New York

test('ny.employee.exactlyOneIdentifier: neither, both, and each alone', () => {
  assert.deepEqual(ids(ny([['        <ssnLast4>0323</ssnLast4>\n', '']])),
    ['ny.employee.exactlyOneIdentifier'], 'neither');
  assert.deepEqual(ids(ny([['<ssnLast4>0323</ssnLast4>',
                            '<dateOfBirth>1984-02-09</dateOfBirth>\n        <ssnLast4>0323</ssnLast4>']])),
    ['ny.employee.exactlyOneIdentifier'], 'both');
  assert.deepEqual(ids(ny([['<ssnLast4>0323</ssnLast4>', '<dateOfBirth>1984-02-09</dateOfBirth>']])),
    [], 'date of birth alone is valid');
});

test('ny.address.stateFullName: abbreviations are rejected, full names accepted', () => {
  assert.deepEqual(ids(ny([['<state>New York</state>', '<state>NY</state>']])),
    ['ny.address.stateFullName']);
  for (const value of ['New York', 'California', 'Puerto Rico']) {
    assert.deepEqual(ids(ny([['<state>New York</state>', `<state>${value}</state>`]])), []);
  }
});

test('ny.address.stateFullName: a two-letter string that is not a state code is left alone', () => {
  // The rule exists to catch the documented abbreviation mistake, not to police strings.
  assert.deepEqual(ids(ny([['<state>New York</state>', '<state>Ox</state>']])), []);
});

test('ny.employee.noDuplicates: the same worker twice in one file', () => {
  const block = fixture('ny', 'valid.xml').match(/ {4}<employeeWorkWeek>[\s\S]*?<\/employeeWorkWeek>\n/)[0];
  const result = ny([[block, block + block]]);
  assert.equal(count(result, 'ny.employee.noDuplicates'), 1);
  assert.match(first(result, 'ny.employee.noDuplicates').message, /already appears in the file at line/);
});

test('ny.days.withinWeek: outside the window, and repeated inside it', () => {
  assert.deepEqual(ids(ny([['<day>2026-07-27</day>', '<day>2026-07-20</day>']])),
    ['ny.days.withinWeek'], 'a week early');
  const repeated = ny([['<day>2026-07-27</day>', '<day>2026-07-28</day>']]);
  assert.equal(count(repeated, 'ny.days.withinWeek'), 1, 'the repeat is reported once');
  assert.match(first(repeated, 'ny.days.withinWeek').message, /repeats/);
});

test('ny.days.withinWeek: the window is inclusive of both ends', () => {
  // The fixture already starts on 2026-07-27, the first day of the window, and passes
  // clean. The other end is the week ending date itself, which must also be accepted.
  assert.deepEqual(ids(ny()), []);
  assert.deepEqual(ids(ny([['<day>2026-07-29</day>', '<day>2026-08-02</day>']])), [],
    'the week ending date is inside its own window');
  assert.deepEqual(ids(ny([['<day>2026-07-29</day>', '<day>2026-08-03</day>']])),
    ['ny.days.withinWeek'], 'the day after it is not');
});

test('schema facets carry the New York limits the guide does not spell out', () => {
  assert.ok(ids(ny([['<amount>150.00</amount>', '<amount>12000.00</amount>']])).includes('schema.pattern'),
    'a deduction line is capped at four digits before the point');
  assert.ok(ids(ny([['<postalCode>12207</postalCode>', '<postalCode>1220</postalCode>']])).includes('schema.pattern'));
  assert.ok(ids(ny([['        <country>United States</country>\n', '']])).includes('schema.missingElement'),
    'country is required by the schema even though the guide calls it optional');
});

test('the 500-record cap is enforced', () => {
  const many = `<employeeWorkWeeks>${'<employeeWorkWeek/>'.repeat(501)}</employeeWorkWeeks>`;
  const source = fixture('ny', 'valid.xml').replace(/<employeeWorkWeeks>[\s\S]*<\/employeeWorkWeeks>/, many);
  assert.ok(ids(validateNyCertPayroll(source)).includes('schema.tooManyElements'));
});

test('ny filename must end in .xml', () => {
  assert.deepEqual(ids(ny([], { filename: 'week.txt' })), ['ny.filename.extension']);
  assert.deepEqual(ids(ny([], { filename: 'WEEK.XML' })), [], 'the check is case insensitive');
});

// -------------------------------------------------------------------- shared

test('findings are ordered by severity and then by line', () => {
  const result = ca([
    ['<CPR:licenseType>CSLB</CPR:licenseType>', '<CPR:licenseType>STATE</CPR:licenseType>'],
    ['<CPR:allWork>1245.00</CPR:allWork>', '<CPR:allWork>1000.00</CPR:allWork>'],
  ], { filename: 'payroll.xml' });
  const severities = result.findings.map((f) => f.severity);
  assert.deepEqual(severities, [...severities].sort(
    (a, b) => ({ error: 0, warning: 1, advisory: 2 })[a] - ({ error: 0, warning: 1, advisory: 2 })[b]));
  assert.equal(result.counts.error, 1);
  assert.equal(result.counts.warning, 1);
  assert.equal(result.counts.advisory, 1);
  assert.equal(result.valid, false, 'valid tracks errors only');
});

test('warnings and advisories alone leave the file valid', () => {
  const result = ca([], { filename: 'payroll.xml' });
  assert.equal(result.counts.advisory, 1);
  assert.equal(result.valid, true);
});

test('every finding carries a line number except the whole-file ones', () => {
  for (const f of ca([['<CPR:licenseType>CSLB</CPR:licenseType>',
                       '<CPR:licenseType>STATE</CPR:licenseType>']]).findings) {
    assert.equal(typeof f.line, 'number', `${f.ruleId} should point at a line`);
    assert.ok(f.line > 0);
  }
  assert.equal(first(ca([], { filename: 'x.xml' }), 'ca.filename.convention').line, null);
});
