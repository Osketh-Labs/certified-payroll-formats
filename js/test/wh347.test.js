import test from 'node:test';
import assert from 'node:assert/strict';
import { toWH347, checkWH347, totalHours, fieldMap } from '../src/wh347.js';

const week = (st, ot = [0, 0, 0, 0, 0, 0, 0]) => st.map((h, i) => ({
  date: `2026-08-${String(24 + i).padStart(2, '0')}`, straightTime: h, overtime: ot[i],
}));

const base = () => ({
  project: {
    name: 'Example Overpass Rehabilitation',
    number: 'DTFH-2026-0001',
    location: 'Sacramento County, CA',
    wageDeterminations: [{ number: 'CA20260001', revision: '3' }],
  },
  contractor: { name: 'Example Mechanical Inc', address: '1 Example Way, Sacramento CA 95814', role: 'subcontractor' },
  payroll: { number: 4, weekEndingDate: '2026-08-28', final: false },
  workers: [{
    entryNo: 1,
    lastName: 'Example', firstName: 'Jane', middleInitial: 'Q',
    identifyingNumber: '3333',
    status: 'J',
    classification: 'Carrier Driver',
    days: week([8, 8, 8, 8, 8, 0, 0]),
    rate: { straightTime: 30, overtime: 45 },
    fringeCredit: 200, hourlyFringeCredit: 5,
    cashInLieu: 0,
    grossThisProject: 1200, grossAllWork: 1200,
    deductions: { taxWithholdings: 190, fica: 91.8, other: [], total: 281.8 },
    netPay: 918.2,
  }],
});

test('total hours is the sum of column 4', () => {
  assert.equal(totalHours(base().workers[0]), 40);
});

test('a clean record produces no findings', () => {
  const result = checkWH347(base());
  assert.deepEqual(result.findings, []);
  assert.equal(result.valid, true);
});

test('column values follow the January 2025 numbering', () => {
  const { header, rows, pageTwo } = toWH347(base());
  assert.equal(header.wageDeterminationNumber, 'CA20260001 rev. 3');
  const row = rows[0];
  assert.equal(row['1B'], 'Example');
  assert.equal(row['1C'], 'Jane');
  assert.equal(row['1D'], 'Q');
  assert.equal(row['1E'], '3333');
  assert.equal(row['5'], 40);
  assert.deepEqual(row['6A'], { straightTime: 30, overtime: 45 });
  assert.equal(row['6B'], 200);
  assert.equal(row['6C'], 0);
  assert.equal(row['9'], 918.2);
  assert.equal(pageTwo.checkboxes[1], true);
  assert.equal(pageTwo.checkboxes[4], false, 'no apprentices, so box 4 stays unchecked');
  assert.equal(pageTwo.box4, 'Not Applicable');
});

test('a full Social Security number in column 1E is an error', () => {
  const record = base();
  record.workers[0].identifyingNumber = '111-22-3333';
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column1E.notFullSsn'));
});

test('deduction and net-pay arithmetic is checked against column 7B', () => {
  const record = base();
  record.workers[0].deductions.total = 250;
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column8.totalMatchesItems'));
  assert.ok(found.includes('wh347.column9.netMatchesGrossLessDeductions'));
});

test('a registered apprentice without a level of progression is an error', () => {
  const record = base();
  record.workers[0].status = 'RA';
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column2.apprenticeLevel'));
  assert.equal(toWH347(record).rows[0]['2'], 'RA');
});

test('split-classification rows share one entry number', () => {
  const record = base();
  const second = structuredClone(record.workers[0]);
  second.entryNo = 2;
  second.classification = 'Laborer';
  second.days = week([0, 0, 0, 0, 0, 4, 0]);
  record.workers.push(second);
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column1A.entryNoPerWorker'));

  record.workers[1].entryNo = 1;
  assert.ok(!checkWH347(record).findings.map((f) => f.ruleId).includes('wh347.column1A.entryNoPerWorker'));
});

test('more than 40 straight-time hours with no overtime is flagged under CWHSSA', () => {
  const record = base();
  record.workers[0].days = week([10, 10, 10, 10, 8, 0, 0]);
  record.workers[0].fringeCredit = 240;
  record.workers[0].grossThisProject = 1440;
  record.workers[0].grossAllWork = 1440;
  record.workers[0].deductions = { taxWithholdings: 190, fica: 91.8, other: [], total: 281.8 };
  record.workers[0].netPay = 1158.2;
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column4.overtimeThreshold'));
});

test('a stated weekly total that disagrees with column 4 is caught', () => {
  const record = base();
  record.workers[0].statedTotalHours = 45;
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column5.matchesColumn4'));
});

test('a wage determination without a revision number is a warning', () => {
  const record = base();
  delete record.project.wageDeterminations[0].revision;
  const found = checkWH347(record).findings;
  const hit = found.find((f) => f.ruleId === 'wh347.header.wageDeterminationRevision');
  assert.ok(hit);
  assert.equal(hit.severity, 'warning');
});

test('the fringe credit is checked against the page 2 hourly rate', () => {
  const record = base();
  record.workers[0].fringeCredit = 175;
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column6B.matchesFringeTable'));
});

test('the field map exposes the form identity used to spot a stale PDF', () => {
  const form = fieldMap().form;
  assert.equal(form.expires, '2028-01-31');
  assert.equal(form.required, false);
});
