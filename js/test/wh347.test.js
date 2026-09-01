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

test('a sparse or empty record is handled rather than thrown at', () => {
  for (const record of [{}, { workers: [] }, { workers: [{}] }, { project: {}, workers: [{ entryNo: 1 }] }]) {
    assert.doesNotThrow(() => checkWH347(record));
    assert.doesNotThrow(() => toWH347(record));
  }
  assert.deepEqual(checkWH347({ workers: [{}] }).findings, [],
    'a worker with no entry number is not a broken sequence');
  assert.equal(totalHours({}), 0);
});

test('two different workers may not share an entry number', () => {
  const record = base();
  record.workers.push({
    ...base().workers[0], entryNo: 1, lastName: 'Other', firstName: 'Sam', identifyingNumber: '4444',
  });
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column1A.entryNoPerWorker'));
});

test('entry numbers must run from 1 without gaps', () => {
  const record = base();
  record.workers[0].entryNo = 2;
  const found = checkWH347(record).findings;
  const hit = found.find((f) => f.ruleId === 'wh347.column1A.sequential');
  assert.ok(hit);
  assert.equal(hit.severity, 'warning');
  assert.equal(hit.expected, '1');
});

test('a payroll number below 1 is rejected — the sequence starts at 1, per project', () => {
  const record = base();
  record.payroll.number = 0;
  assert.ok(checkWH347(record).findings.map((f) => f.ruleId).includes('wh347.header.payrollNumber'));
});

test('column 7A may not exceed 7B', () => {
  const record = base();
  record.workers[0].grossThisProject = 1500;
  assert.ok(checkWH347(record).findings.map((f) => f.ruleId).includes('wh347.column7.projectNotAboveAll'));
});

test('the cash-in-lieu rate drives column 6C', () => {
  const record = base();
  record.workers[0].fringeCredit = 0;
  record.workers[0].hourlyFringeCredit = 0;
  record.workers[0].cashInLieu = 150;
  record.workers[0].hourlyCashInLieu = 5;
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.column6C.matchesCashRate'), '40 hours × 5 is 200, not 150');
});

test('fringe met entirely in cash means box 5 with a blank table', () => {
  const record = base();
  record.workers[0].fringeCredit = 0;
  record.workers[0].hourlyFringeCredit = 0;
  record.workers[0].cashInLieu = 200;
  record.workers[0].hourlyCashInLieu = 5;
  record.fringePlans = [{ name: 'Example Health Trust', type: 'health', funded: true }];
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.pageTwo.box5CashOnly'));

  const rendered = toWH347(record);
  assert.equal(rendered.pageTwo.checkboxes[5], true, 'box 5 is still checked');
  assert.deepEqual(rendered.pageTwo.box5Table, [], 'and the table stays blank');
});

test('an apprentice populates box 4 and the level appears in column 2', () => {
  const record = base();
  record.workers[0].status = 'RA';
  record.workers[0].apprenticeLevel = '3rd period';
  record.apprenticePrograms = [{ program: 'Example JATC', classification: 'Carrier Driver' }];
  const rendered = toWH347(record);
  assert.equal(rendered.rows[0]['2'], 'RA (3rd period)');
  assert.equal(rendered.pageTwo.checkboxes[4], true);
  assert.deepEqual(rendered.pageTwo.box4, record.apprenticePrograms);
  assert.deepEqual(checkWH347(record).findings, []);
});

test('addendum thresholds are three apprentice programs and six fringe plans', () => {
  const record = base();
  record.apprenticePrograms = Array.from({ length: 4 }, (_, i) => ({ program: `P${i}`, classification: 'x' }));
  record.fringePlans = Array.from({ length: 7 }, (_, i) => ({ name: `Plan ${i}` }));
  const found = checkWH347(record).findings.map((f) => f.ruleId);
  assert.ok(found.includes('wh347.pageTwo.box4Addendum'));
  assert.ok(found.includes('wh347.pageTwo.box5Addendum'));
  const { addenda } = toWH347(record).pageTwo;
  assert.equal(addenda.box4Required, true);
  assert.equal(addenda.box5Required, true);
});

test('several wage determinations are all listed, each with its revision', () => {
  const record = base();
  record.project.wageDeterminations = [
    { number: 'CA20260001', revision: '3' },
    { number: 'CA20260002', revision: '1' },
  ];
  assert.equal(toWH347(record).header.wageDeterminationNumber, 'CA20260001 rev. 3; CA20260002 rev. 1');
  assert.deepEqual(checkWH347(record).findings, []);
});

test('an identifying number of exactly nine digits is caught however it is punctuated', () => {
  for (const value of ['111223333', '111-22-3333', '111 22 3333']) {
    const record = base();
    record.workers[0].identifyingNumber = value;
    assert.ok(checkWH347(record).findings.map((f) => f.ruleId).includes('wh347.column1E.notFullSsn'), value);
  }
  for (const value of ['3333', 'EMP-00042', '12345678']) {
    const record = base();
    record.workers[0].identifyingNumber = value;
    assert.ok(!checkWH347(record).findings.map((f) => f.ruleId).includes('wh347.column1E.notFullSsn'), value);
  }
});

test('deduction arithmetic includes itemised Other lines', () => {
  const record = base();
  record.workers[0].deductions = {
    taxWithholdings: 190, fica: 91.8,
    other: [{ name: 'Union dues', amount: 25 }, { name: 'Garnishment', amount: 30 }],
    total: 336.8,
  };
  record.workers[0].netPay = 863.2;
  assert.deepEqual(checkWH347(record).findings, []);

  record.workers[0].deductions.total = 281.8;
  assert.ok(checkWH347(record).findings.map((f) => f.ruleId).includes('wh347.column8.totalMatchesItems'));
});

test('every finding cites the WHD instructions', () => {
  const record = base();
  record.workers[0].identifyingNumber = '111223333';
  for (const f of checkWH347(record).findings) {
    assert.ok(f.sources.length > 0, f.ruleId);
    assert.ok(f.sources.some((s) => s.url.includes('dol.gov') || s.url.includes('ecfr.gov')), f.ruleId);
  }
});
