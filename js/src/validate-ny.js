// New York certified payroll bulk upload: the checks the published schema cannot express.
//
// The interesting ones are the identifier choice and the state-name rule. Both are
// stated in NYSDOL's bulk upload guide, neither is expressible in — or expressed by —
// NYDOL_CertPayroll.xsd, and a file that gets them wrong passes local XSD validation
// and is rejected on upload.

import { parseXml, kid, kids, textAt, pathOf } from './xml.js';
import { checkAgainstSchema } from './schema-check.js';
import { nyCertPayroll } from './data.js';
import { finding, summarize } from './finding.js';

const ruleIndex = () => Object.fromEntries(nyCertPayroll().rules.map((r) => [r.id, r]));

const US_STATE_ABBREVIATIONS = new Set(['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT',
  'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN',
  'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC', 'PR', 'VI', 'GU', 'AS', 'MP']);

function addDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d) + n * 86400000).toISOString().slice(0, 10);
}

/**
 * Validate a New York certified payroll XML document.
 *
 * @param {string} xml         the file contents
 * @param {object} [options]
 * @param {string} [options.filename]
 * @returns {{valid: boolean, counts: object, findings: Array}}
 */
export function validateNyCertPayroll(xml, options = {}) {
  const R = ruleIndex();
  const out = [];

  let root;
  try {
    ({ root } = parseXml(xml));
  } catch (error) {
    return summarize([finding(
      { id: 'ny.parse', severity: 'error', statement: 'The file must be well-formed XML.', sources: ['ny-dol-buf'] },
      { message: error.message, line: error.line },
    )]);
  }

  // The schema declares no targetNamespace, so the instance must carry none.
  if (root.ns) {
    out.push(finding(R['ny.root.noNamespace'], {
      path: root.qname, line: root.line,
      message: 'the document is in a namespace; NYDOL_CertPayroll.xsd declares none, so a namespaced instance does not validate',
      expected: '(no namespace)', actual: root.ns,
    }));
  }

  out.push(...checkAgainstSchema(root, 'ny-certpayroll', null, { reportNamespace: !root.ns }));

  const weekEndingRaw = textAt(root, 'weekEndingDate') ?? '';
  const weekEnding = weekEndingRaw.slice(0, 10);
  const workWeeks = kids(kid(root, 'employeeWorkWeeks'), 'employeeWorkWeek');

  const seen = new Map();

  for (const eww of workWeeks) {
    const employee = kid(eww, 'employee');
    if (!employee) continue;
    const base = pathOf(employee);

    const ssnLast4 = textAt(employee, 'ssnLast4');
    const dateOfBirth = textAt(employee, 'dateOfBirth');
    if (Boolean(ssnLast4) === Boolean(dateOfBirth)) {
      out.push(finding(R['ny.employee.exactlyOneIdentifier'], {
        path: base, line: employee.line,
        message: ssnLast4
          ? 'the employee carries both ssnLast4 and dateOfBirth'
          : 'the employee carries neither ssnLast4 nor dateOfBirth',
        expected: 'exactly one of ssnLast4 or dateOfBirth',
        actual: ssnLast4 ? 'both present' : 'neither present',
      }));
    }

    const state = textAt(employee, 'address/state');
    if (state && state.length === 2 && US_STATE_ABBREVIATIONS.has(state.toUpperCase())) {
      out.push(finding(R['ny.address.stateFullName'], {
        path: `${base}/address/state`, line: kid(kid(employee, 'address'), 'state').line,
        message: 'address/state carries a two-letter abbreviation; the portal requires the full state name',
        expected: 'the full state name, e.g. New York', actual: state,
      }));
    }

    const key = [
      (textAt(employee, 'firstName') ?? '').toLowerCase(),
      (textAt(employee, 'lastName') ?? '').toLowerCase(),
      ssnLast4 ?? dateOfBirth ?? '',
    ].join('|');
    if (seen.has(key)) {
      out.push(finding(R['ny.employee.noDuplicates'], {
        path: base, line: employee.line,
        message: `this employee already appears in the file at line ${seen.get(key)}`,
        expected: 'one employeeWorkWeek per employee per file', actual: 'a duplicate entry',
      }));
    } else {
      seen.set(key, employee.line);
    }

    for (const workWeek of kids(kid(eww, 'workWeeks'), 'workWeek')) {
      const dayNodes = kids(kid(workWeek, 'days'), 'day');
      const dates = [];
      for (const dayNode of dayNodes) {
        const date = textAt(dayNode, 'day');
        if (!date) continue;
        dates.push(date);
        if (weekEnding && /^\d{4}-\d{2}-\d{2}$/.test(weekEnding)) {
          const window = Array.from({ length: 7 }, (_, k) => addDays(weekEnding, k - 6));
          if (!window.includes(date)) {
            out.push(finding(R['ny.days.withinWeek'], {
              path: `${pathOf(workWeek)}/days/day`, line: dayNode.line,
              message: 'the day date falls outside the seven-day window ending on weekEndingDate',
              expected: `${window[0]} … ${window[6]}`, actual: date,
            }));
          }
        }
      }
      const duplicates = dates.filter((d, k) => dates.indexOf(d) !== k);
      for (const duplicate of new Set(duplicates)) {
        out.push(finding(R['ny.days.withinWeek'], {
          path: `${pathOf(workWeek)}/days`, line: workWeek.line,
          message: 'a day date repeats within one workWeek',
          expected: 'distinct dates', actual: duplicate,
        }));
      }
    }
  }

  if (options.filename && !/\.xml$/i.test(options.filename)) {
    out.push(finding({ ...R['ny.root.noNamespace'], id: 'ny.filename.extension', severity: 'error', statement: 'The file extension must be .xml.', sources: ['ny-dol-buf'] }, {
      path: null, line: null, message: 'the filename does not end in .xml',
      expected: '.xml', actual: options.filename,
    }));
  }

  return summarize(out);
}
