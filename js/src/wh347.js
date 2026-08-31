// WH-347 (revised January 2025): map a canonical weekly payroll record onto the
// form's columns, and check the record against the rules in WHD's instructions.
//
// The form is optional; the weekly submission is not. This module produces the
// column values, not a PDF — the point is to get the arithmetic and the 2025
// column numbering right before anything is rendered or filed.

import { wh347 as wh347Data } from './data.js';
import { finding, summarize } from './finding.js';

/**
 * @typedef {object} Wh347Worker
 * @property {number} entryNo
 * @property {string} lastName
 * @property {string} firstName
 * @property {string} [middleInitial]
 * @property {string} identifyingNumber  last four of the SSN, or a worker-specific number
 * @property {'J'|'RA'} status
 * @property {string} [apprenticeLevel]  required when status is RA
 * @property {string} classification
 * @property {Array<{date: string, straightTime: number, overtime: number}>} days
 * @property {{straightTime: number, overtime: number}} rate
 * @property {number} [fringeCredit]     column 6B
 * @property {number} [cashInLieu]       column 6C
 * @property {number} grossThisProject   column 7A
 * @property {number} grossAllWork       column 7B
 * @property {{taxWithholdings?: number, fica?: number, other?: Array<{name: string, amount: number}>, total: number}} deductions
 * @property {number} netPay             column 9
 * @property {number} [statedTotalHours]    a total from an upstream system, checked against column 4
 * @property {number} [hourlyFringeCredit]  the page 2 table rate, used to check 6B
 * @property {number} [hourlyCashInLieu]    the cash-in-lieu rate, used to check 6C
 */

/**
 * @typedef {object} Wh347Record
 * @property {{name: string, number?: string, location: string, wageDeterminations: Array<{number: string, revision?: string}>}} project
 * @property {{name: string, address: string, role: 'prime'|'subcontractor'}} contractor
 * @property {{number: number, weekEndingDate: string, final?: boolean}} payroll
 * @property {Wh347Worker[]} workers
 * @property {Array<{name: string, type?: string, number?: string, funded?: boolean}>} [fringePlans]
 * @property {Array<{program: string, classification: string, registeredWith?: string}>} [apprenticePrograms]
 */

const check = (id) => checkIndex()[id];
let _checks = null;
function checkIndex() {
  if (!_checks) _checks = Object.fromEntries(wh347Data().checks.map((c) => [c.id, c]));
  return _checks;
}

const round2 = (n) => Math.round(n * 100) / 100;
const close = (a, b) => Math.abs(a - b) < 0.005;
const sum = (xs) => xs.reduce((a, b) => a + b, 0);

/** The published field map: header fields, columns 1A–9, page 2, and the rule lists. */
export function fieldMap() {
  return wh347Data();
}

/** Total hours for a worker row — column 5. */
export function totalHours(worker) {
  return round2(sum((worker.days ?? []).map((d) => (d.straightTime ?? 0) + (d.overtime ?? 0))));
}

/**
 * Render a canonical record as WH-347 column values.
 * @param {Wh347Record} record
 * @returns {{header: object, rows: object[], pageTwo: object}}
 */
export function toWH347(record) {
  const header = {
    finalPayroll: Boolean(record.payroll?.final),
    role: record.contractor?.role ?? null,
    projectName: record.project?.name ?? null,
    projectOrContractNumber: record.project?.number ?? null,
    payrollNumber: record.payroll?.number ?? null,
    businessName: record.contractor?.name ?? null,
    projectLocation: record.project?.location ?? null,
    wageDeterminationNumber: (record.project?.wageDeterminations ?? [])
      .map((wd) => (wd.revision ? `${wd.number} rev. ${wd.revision}` : wd.number))
      .join('; ') || null,
    weekEndingDate: record.payroll?.weekEndingDate ?? null,
    businessAddress: record.contractor?.address ?? null,
  };

  const rows = (record.workers ?? []).map((w) => {
    const st = sum((w.days ?? []).map((d) => d.straightTime ?? 0));
    const ot = sum((w.days ?? []).map((d) => d.overtime ?? 0));
    return {
      '1A': w.entryNo ?? null,
      '1B': w.lastName ?? null,
      '1C': w.firstName ?? null,
      '1D': w.middleInitial ?? null,
      '1E': w.identifyingNumber ?? null,
      '2': w.status === 'RA' && w.apprenticeLevel ? `RA (${w.apprenticeLevel})` : (w.status ?? null),
      '3': w.classification ?? null,
      '4': (w.days ?? []).map((d) => ({ date: d.date, ST: d.straightTime ?? 0, OT: d.overtime ?? 0 })),
      '5': round2(st + ot),
      '6A': { straightTime: w.rate?.straightTime ?? null, overtime: w.rate?.overtime ?? null },
      '6B': w.fringeCredit ?? 0,
      '6C': w.cashInLieu ?? 0,
      '7A': w.grossThisProject ?? null,
      '7B': w.grossAllWork ?? null,
      '8': {
        taxWithholdings: w.deductions?.taxWithholdings ?? 0,
        fica: w.deductions?.fica ?? 0,
        other: w.deductions?.other ?? [],
        total: w.deductions?.total ?? 0,
      },
      '9': w.netPay ?? null,
    };
  });

  const fringePlans = record.fringePlans ?? [];
  const apprenticePrograms = record.apprenticePrograms ?? [];
  const anyApprentice = (record.workers ?? []).some((w) => w.status === 'RA');
  const anyCredit = (record.workers ?? []).some((w) => (w.fringeCredit ?? 0) > 0);

  return {
    header,
    rows,
    pageTwo: {
      identifiers: {
        projectName: header.projectName,
        projectOrContractNumber: header.projectOrContractNumber,
        payrollNumber: header.payrollNumber,
        businessName: header.businessName,
        projectLocation: header.projectLocation,
        weekEndingDate: header.weekEndingDate,
      },
      checkboxes: {
        1: true, 2: true, 3: true, 6: true,
        4: anyApprentice,
        5: anyCredit || (record.workers ?? []).some((w) => (w.cashInLieu ?? 0) > 0),
      },
      box4: anyApprentice ? apprenticePrograms : 'Not Applicable',
      box5Table: anyCredit
        ? (record.workers ?? []).filter((w) => (w.fringeCredit ?? 0) > 0).map((w) => ({
          workerEntryNumber: w.entryNo,
          workerName: [w.lastName, w.firstName].filter(Boolean).join(', '),
          plans: fringePlans,
          hourlyCredit: w.hourlyFringeCredit ?? null,
        }))
        : [],
      addenda: {
        box4Required: apprenticePrograms.length > 3,
        box5Required: fringePlans.length > 6,
      },
    },
  };
}

/**
 * Check a canonical record against the WH-347 instructions.
 * @param {Wh347Record} record
 * @returns {{valid: boolean, counts: object, findings: Array}}
 */
export function checkWH347(record) {
  const out = [];
  const workers = record.workers ?? [];

  const payrollNumber = record.payroll?.number;
  if (payrollNumber !== undefined && !(Number(payrollNumber) >= 1)) {
    out.push(finding(check('wh347.header.payrollNumber'), {
      path: 'payroll.number', message: 'the certified payroll number must be 1 or greater',
      expected: '>= 1', actual: String(payrollNumber),
    }));
  }
  for (const [i, wd] of (record.project?.wageDeterminations ?? []).entries()) {
    if (!wd.revision) {
      out.push(finding(check('wh347.header.wageDeterminationRevision'), {
        path: `project.wageDeterminations[${i}]`,
        message: `wage determination ${wd.number} carries no revision number`,
        expected: 'a revision number', actual: '(absent)',
      }));
    }
  }

  const entryToWorker = new Map();
  const workerToEntry = new Map();
  const seenEntryNos = [];

  workers.forEach((w, i) => {
    const at = `workers[${i}]`;
    const id = String(w.identifyingNumber ?? '');
    if (/^\d{9}$/.test(id.replace(/[-\s]/g, ''))) {
      out.push(finding(check('wh347.column1E.notFullSsn'), {
        path: `${at}.identifyingNumber`,
        message: 'column 1E looks like a full Social Security number',
        expected: 'the last four digits, or a worker-specific number', actual: id,
      }));
    }
    if (w.status === 'RA' && !w.apprenticeLevel) {
      out.push(finding(check('wh347.column2.apprenticeLevel'), {
        path: `${at}.apprenticeLevel`,
        message: 'a registered apprentice row carries no level of progression',
        expected: 'the level of progression in the approved program', actual: '(absent)',
      }));
    }

    const identity = [w.lastName, w.firstName, w.identifyingNumber].join('|').toLowerCase();
    seenEntryNos.push(w.entryNo);
    if (workerToEntry.has(identity) && workerToEntry.get(identity) !== w.entryNo) {
      out.push(finding(check('wh347.column1A.entryNoPerWorker'), {
        path: `${at}.entryNo`,
        message: 'the same worker appears under two different entry numbers; classification rows share one entry number',
        expected: String(workerToEntry.get(identity)), actual: String(w.entryNo),
      }));
    }
    workerToEntry.set(identity, w.entryNo);
    if (entryToWorker.has(w.entryNo) && entryToWorker.get(w.entryNo) !== identity) {
      out.push(finding(check('wh347.column1A.entryNoPerWorker'), {
        path: `${at}.entryNo`,
        message: 'two different workers share one entry number',
        expected: 'a distinct entry number per worker', actual: String(w.entryNo),
      }));
    }
    entryToWorker.set(w.entryNo, identity);

    const hours = totalHours(w);
    if (w.statedTotalHours !== undefined && !close(hours, w.statedTotalHours)) {
      out.push(finding(check('wh347.column5.matchesColumn4'), {
        path: `${at}.statedTotalHours`,
        message: 'the stated weekly total does not equal the sum of the daily hours in column 4',
        expected: hours.toFixed(2), actual: Number(w.statedTotalHours).toFixed(2),
      }));
    }
    const st = sum((w.days ?? []).map((d) => d.straightTime ?? 0));
    const ot = sum((w.days ?? []).map((d) => d.overtime ?? 0));
    if (st > 40 && ot === 0) {
      out.push(finding(check('wh347.column4.overtimeThreshold'), {
        path: `${at}.days`,
        message: `${st} straight-time hours with no overtime recorded`,
        expected: 'overtime beyond 40 hours in the week, counting hours worked off site',
        actual: `${st} ST / ${ot} OT`,
      }));
    }

    if (w.hourlyFringeCredit !== undefined && w.fringeCredit !== undefined) {
      const expected = round2(hours * w.hourlyFringeCredit);
      if (!close(expected, w.fringeCredit)) {
        out.push(finding(check('wh347.column6B.matchesFringeTable'), {
          path: `${at}.fringeCredit`,
          message: 'column 6B does not equal total hours × the page 2 hourly credit',
          expected: expected.toFixed(2), actual: Number(w.fringeCredit).toFixed(2),
        }));
      }
    }
    if (w.hourlyCashInLieu !== undefined && w.cashInLieu !== undefined) {
      const expected = round2(hours * w.hourlyCashInLieu);
      if (!close(expected, w.cashInLieu)) {
        out.push(finding(check('wh347.column6C.matchesCashRate'), {
          path: `${at}.cashInLieu`,
          message: 'column 6C does not equal total hours × the hourly cash-in-lieu rate',
          expected: expected.toFixed(2), actual: Number(w.cashInLieu).toFixed(2),
        }));
      }
    }

    if (w.grossThisProject !== undefined && w.grossAllWork !== undefined
        && w.grossThisProject > w.grossAllWork + 0.005) {
      out.push(finding(check('wh347.column7.projectNotAboveAll'), {
        path: `${at}.grossThisProject`,
        message: 'column 7A exceeds column 7B',
        expected: `at most ${Number(w.grossAllWork).toFixed(2)}`,
        actual: Number(w.grossThisProject).toFixed(2),
      }));
    }

    const d = w.deductions;
    if (d && d.total !== undefined) {
      const items = round2((d.taxWithholdings ?? 0) + (d.fica ?? 0)
        + sum((d.other ?? []).map((o) => o.amount ?? 0)));
      if (!close(items, d.total)) {
        out.push(finding(check('wh347.column8.totalMatchesItems'), {
          path: `${at}.deductions.total`,
          message: 'the column 8 total does not equal the sum of its parts',
          expected: items.toFixed(2), actual: Number(d.total).toFixed(2),
        }));
      }
      if (w.grossAllWork !== undefined && w.netPay !== undefined) {
        const expected = round2(w.grossAllWork - d.total);
        if (!close(expected, w.netPay)) {
          out.push(finding(check('wh347.column9.netMatchesGrossLessDeductions'), {
            path: `${at}.netPay`,
            message: 'column 9 does not equal column 7B less the column 8 total',
            expected: expected.toFixed(2), actual: Number(w.netPay).toFixed(2),
          }));
        }
      }
    }

    if ((w.fringeCredit ?? 0) === 0 && (w.cashInLieu ?? 0) > 0 && (record.fringePlans ?? []).length > 0) {
      out.push(finding(check('wh347.pageTwo.box5CashOnly'), {
        path: `${at}.cashInLieu`,
        message: 'fringe obligations are met entirely in cash for this worker, yet fringe plans are listed for the box 5 table',
        expected: 'box 5 checked with the table left blank', actual: `${(record.fringePlans ?? []).length} plan(s) listed`,
      }));
    }
  });

  const unique = [...new Set(seenEntryNos)].sort((a, b) => a - b);
  const expectedSequence = unique.map((_, k) => k + 1);
  if (unique.length && unique.join(',') !== expectedSequence.join(',')) {
    out.push(finding(check('wh347.column1A.sequential'), {
      path: 'workers[].entryNo',
      message: 'worker entry numbers are not sequential from 1',
      expected: expectedSequence.join(', '), actual: unique.join(', '),
    }));
  }

  if ((record.apprenticePrograms ?? []).length > 3) {
    out.push(finding(check('wh347.pageTwo.box4Addendum'), {
      path: 'apprenticePrograms',
      message: 'more than three apprenticeship programs require an addendum to box 4',
      expected: 'at most 3 on the form itself', actual: String(record.apprenticePrograms.length),
    }));
  }
  if ((record.fringePlans ?? []).length > 6) {
    out.push(finding(check('wh347.pageTwo.box5Addendum'), {
      path: 'fringePlans',
      message: 'more than six fringe benefit plans require an addendum to the box 5 table',
      expected: 'at most 6 on the form itself', actual: String(record.fringePlans.length),
    }));
  }

  return summarize(out);
}
