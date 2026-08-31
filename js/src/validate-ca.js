// California eCPR: the checks that the published schema cannot express.
//
// Everything the XSD *can* express is handled by checkAgainstSchema and reported
// under schema.* rule ids. What follows is the layer above that — cross-field
// arithmetic, conditional structure, and the conventions DIR states in prose.

import { parseXml, kid, kids, textAt, pathOf } from './xml.js';
import { checkAgainstSchema } from './schema-check.js';
import { caEcpr } from './data.js';
import { finding, summarize } from './finding.js';

export const CA_NAMESPACE = 'http://www.dir.ca.gov/dlse/CPR-Prod-Test/CPR.xsd';

const ruleIndex = () => Object.fromEntries(caEcpr().rules.map((r) => [r.id, r]));

const num = (node) => {
  if (!node) return null;
  const v = Number(node.text.trim());
  return Number.isFinite(v) ? v : null;
};
const close = (a, b) => Math.abs(a - b) < 0.005;
const money = (n) => n.toFixed(2);

function addDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  const t = Date.UTC(y, m - 1, d) + n * 86400000;
  return new Date(t).toISOString().slice(0, 10);
}

/**
 * Validate a California eCPR XML document.
 *
 * @param {string} xml         the file contents
 * @param {object} [options]
 * @param {string} [options.filename]  checked against DIR's naming convention when given
 * @returns {{valid: boolean, counts: object, findings: Array}}
 */
export function validateCaEcpr(xml, options = {}) {
  const R = ruleIndex();
  const out = [];

  let root;
  try {
    ({ root } = parseXml(xml));
  } catch (error) {
    return summarize([finding(
      { id: 'ca.parse', severity: 'error', statement: 'The file must be well-formed XML.', sources: ['ca-dir-guideline'] },
      { message: error.message, line: error.line },
    )]);
  }

  out.push(...checkAgainstSchema(root, 'ca-ecpr', CA_NAMESPACE));

  // projectInfo: contractAgency and projectID, or the documented lookup fallback.
  const project = kid(root, 'projectInfo');
  if (project) {
    const agency = textAt(project, 'contractAgency');
    const projectId = textAt(project, 'projectID');
    const fallback = ['awardingBodyID', 'projectNum', 'contractID'].map((n) => textAt(project, n));
    if (!agency) {
      out.push(finding(R['ca.projectInfo.mandatory'], {
        path: 'eCPR/projectInfo/contractAgency', line: project.line,
        message: 'contractAgency is empty; the guideline lists it as one of the two fields to fill in',
        expected: 'a contract agency, e.g. CA-DIR', actual: '(empty)',
      }));
    }
    if (!projectId && fallback.some((v) => !v)) {
      out.push(finding(R['ca.projectInfo.mandatory'], {
        path: 'eCPR/projectInfo/projectID', line: project.line,
        message: 'projectID is empty and the documented fallback is incomplete',
        expected: 'a projectID, or all three of awardingBodyID, projectNum and contractID',
        actual: `projectID=(empty), awardingBodyID=${fallback[0] || '(empty)'}, projectNum=${fallback[1] || '(empty)'}, contractID=${fallback[2] || '(empty)'}`,
      }));
    }
  }

  const payrollInfo = kid(root, 'payrollInfo');
  if (!payrollInfo) return summarize(out);

  const weekEnding = textAt(payrollInfo, 'forWeekEnding');
  const nonPerformance = textAt(payrollInfo, 'statementOfNP') === 'true';
  const employees = kids(kid(payrollInfo, 'employees'), 'employee');

  if (nonPerformance && employees.length > 0) {
    out.push(finding(R['ca.statementOfNP.noEmployees'], {
      path: 'eCPR/payrollInfo/employees', line: employees[0].line,
      message: `statementOfNP is true but ${employees.length} employee element(s) are present`,
      expected: 'an empty <employees> element', actual: `${employees.length} employees`,
    }));
  }
  if (!nonPerformance && employees.length === 0) {
    out.push(finding(R['ca.statementOfNP.noEmployees'], {
      path: 'eCPR/payrollInfo/employees', line: payrollInfo.line,
      message: 'statementOfNP is false but no employee elements are present',
      expected: 'at least one employee', actual: 'none',
    }));
  }

  for (const employee of employees) {
    const base = pathOf(employee);
    const ssn = textAt(employee, 'ssn');
    const nameNode = kid(employee, 'name');

    if (nameNode) {
      const id = nameNode.attrs.id;
      if (!id) {
        out.push(finding(R['ca.name.idAttribute'], {
          path: `${base}/name@id`, line: nameNode.line,
          message: 'the name element carries no id attribute',
          expected: 'id="SSN::NAME"', actual: '(absent)',
        }));
      } else {
        const parts = id.split('::');
        if (parts.length !== 2 || !parts[0] || !parts[1]) {
          out.push(finding(R['ca.name.idAttribute'], {
            path: `${base}/name@id`, line: nameNode.line,
            message: 'the name id attribute is not in SSN::NAME form',
            expected: 'id="SSN::NAME"', actual: id,
          }));
        } else {
          if (parts[1] !== parts[1].toUpperCase()) {
            out.push(finding(R['ca.name.idAttribute'], {
              path: `${base}/name@id`, line: nameNode.line,
              message: 'the NAME portion of the id attribute is not upper-case',
              expected: parts[1].toUpperCase(), actual: parts[1],
            }));
          }
          if (ssn && parts[0] !== ssn) {
            out.push(finding(R['ca.name.idMatchesSsn'], {
              path: `${base}/name@id`, line: nameNode.line,
              message: 'the SSN portion of the id attribute does not match the ssn element',
              expected: ssn, actual: parts[0],
            }));
          }
        }
      }
    }

    const payroll = kid(employee, 'payroll');
    if (!payroll) continue;

    const days = kids(kid(payroll, 'hrsWorkedEachDay'), 'day');
    const dates = days.map((d) => textAt(d, 'date')).filter(Boolean);
    if (weekEnding && dates.length === 7) {
      const expected = Array.from({ length: 7 }, (_, k) => addDays(weekEnding, k - 6));
      const sorted = [...dates].sort();
      if (sorted.join(',') !== expected.join(',')) {
        out.push(finding(R['ca.days.consecutive'], {
          path: `${base}/payroll/hrsWorkedEachDay`, line: days[0].line,
          message: 'the seven day dates are not the seven consecutive days ending on forWeekEnding',
          expected: expected.join(', '), actual: sorted.join(', '),
        }));
      }
    }

    const totals = kid(payroll, 'totHrs');
    const pairs = [
      ['straightTime', 'totHrsStraightTime'],
      ['overtime', 'totHrsOvertime'],
      ['doubletime', 'totHrsDoubletime'],
    ];
    for (const [dayField, totalField] of pairs) {
      const sum = days.reduce((acc, d) => acc + (num(kid(d, dayField)) ?? 0), 0);
      const stated = num(kid(totals, totalField));
      if (stated !== null && !close(sum, stated)) {
        out.push(finding(R['ca.totals.matchDays'], {
          path: `${base}/payroll/totHrs/${totalField}`, line: kid(totals, totalField).line,
          message: `${totalField} does not equal the sum of the per-day ${dayField} values`,
          expected: String(sum), actual: String(stated),
        }));
      }
    }

    const deductions = kid(payroll, 'deductionsContribPay');
    if (deductions) {
      const items = ['fedTax', 'FICA', 'stateTax', 'SDI', 'vacationHoliday', 'healthWelfare',
        'pension', 'training', 'fundAdmin', 'dues', 'travelSubs', 'savings', 'other'];
      const sum = items.reduce((acc, n) => acc + (num(kid(deductions, n)) ?? 0), 0);
      const stated = num(kid(deductions, 'total'));
      if (stated !== null && !close(sum, stated)) {
        out.push(finding(R['ca.deductions.totalMatchesItems'], {
          path: `${base}/payroll/deductionsContribPay/total`, line: kid(deductions, 'total').line,
          message: 'total does not equal the sum of the itemised deductions and contributions',
          expected: money(sum), actual: money(stated),
        }));
      }
    }

    const gross = kid(payroll, 'grossAmountEarned');
    const thisProject = num(kid(gross, 'thisProject'));
    const allWork = num(kid(gross, 'allWork'));
    if (thisProject !== null && allWork !== null && thisProject > allWork + 0.005) {
      out.push(finding(R['ca.gross.projectNotAboveAll'], {
        path: `${base}/payroll/grossAmountEarned`, line: gross.line,
        message: 'thisProject exceeds allWork',
        expected: `at most ${money(allWork)}`, actual: money(thisProject),
      }));
    }
  }

  if (options.filename) {
    const naming = caEcpr().fileNaming;
    if (!new RegExp(naming.regex).test(options.filename)) {
      out.push(finding(R['ca.filename.convention'], {
        path: null, line: null,
        message: 'the filename does not follow the convention in the eCPR XML guideline',
        expected: naming.example, actual: options.filename,
      }));
    }
  }

  return summarize(out);
}
