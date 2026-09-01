// Structural validation against the element tree extracted from an agency's own XSD.
//
// This is not a general XSD processor. It checks the constructs the two certified
// payroll schemas actually use — sequences of named elements with occurrence limits
// and simple-type facets — which is enough to reproduce the errors XML Notepad would
// report, with no dependency and no schema download at run time.

import { elements } from './data.js';
import { finding } from './finding.js';
import { pathOf } from './xml.js';

const SCHEMA_SOURCE = { 'ca-ecpr': ['ca-dir-xsd'], 'ny-certpayroll': ['ny-dol-xsd'] };

const RULES = {
  namespace: { id: 'schema.namespace', severity: 'error', statement: 'Every element must be in the namespace the schema declares — or in no namespace, where the schema declares none.' },
  unexpected: { id: 'schema.unexpectedElement', severity: 'error', statement: 'The schema declares no element with this name at this position.' },
  missing: { id: 'schema.missingElement', severity: 'error', statement: 'A required element declared by the schema is absent.' },
  tooMany: { id: 'schema.tooManyElements', severity: 'error', statement: 'More occurrences of an element than the schema permits.' },
  order: { id: 'schema.elementOrder', severity: 'error', statement: 'Elements in an xs:sequence must appear in the order the schema declares.' },
  fixed: { id: 'schema.fixedValue', severity: 'error', statement: 'An element declared with a fixed value must carry exactly that value.' },
  pattern: { id: 'schema.pattern', severity: 'error', statement: 'The value does not match the pattern the schema declares.' },
  length: { id: 'schema.length', severity: 'error', statement: 'The value violates a minLength or maxLength facet.' },
  range: { id: 'schema.range', severity: 'error', statement: 'The value violates a maxInclusive or maxExclusive facet.' },
  fraction: { id: 'schema.fractionDigits', severity: 'error', statement: 'The value carries more fraction digits than the schema permits.' },
  type: { id: 'schema.type', severity: 'error', statement: 'The value is not a valid lexical form for its declared type.' },
  enumeration: { id: 'schema.enumeration', severity: 'error', statement: 'The value is not one of the values the schema enumerates.' },
};

function ruleFor(kind, formatId) {
  return { ...RULES[kind], sources: SCHEMA_SOURCE[formatId] ?? [] };
}

function index(formatId) {
  const defs = elements(formatId);
  const byPath = new Map(defs.map((d) => [d.path, d]));
  const childrenOf = new Map();
  for (const d of defs) {
    const cut = d.path.lastIndexOf('/');
    if (cut === -1) continue;
    const parent = d.path.slice(0, cut);
    if (!childrenOf.has(parent)) childrenOf.set(parent, []);
    childrenOf.get(parent).push(d);
  }
  return { root: defs[0], byPath, childrenOf };
}

const DATE = /^-?(\d{4})-(\d{2})-(\d{2})(Z|[+-]\d{2}:\d{2})?$/;
const DATETIME = /^-?(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/;

/**
 * xs:date and xs:dateTime require a real calendar date, not merely the right shape.
 * `2026-13-45` matches the lexical pattern and is still not a date, and letting it
 * through produces nonsense downstream when the week window is computed from it.
 */
export function isCalendarDate(year, month, day) {
  if (month < 1 || month > 12 || day < 1) return false;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  return day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}

function validDate(value) {
  const m = DATE.exec(value);
  return Boolean(m) && isCalendarDate(Number(m[1]), Number(m[2]), Number(m[3]));
}

function validDateTime(value) {
  const m = DATETIME.exec(value);
  if (!m) return false;
  if (!isCalendarDate(Number(m[1]), Number(m[2]), Number(m[3]))) return false;
  const [hour, minute, second] = [Number(m[4]), Number(m[5]), Number(m[6])];
  if (minute > 59 || second > 59) return false;
  return hour < 24 || (hour === 24 && minute === 0 && second === 0);
}

function checkValue(def, node, out, formatId) {
  const raw = node.text;
  const value = raw.trim();
  const path = pathOf(node);
  const where = { path, line: node.line, actual: value };

  if (def.fixed !== undefined) {
    if (value !== def.fixed) {
      out.push(finding(ruleFor('fixed', formatId), {
        ...where,
        message: `<${node.qname}> is declared fixed=${JSON.stringify(def.fixed)} and must be sent empty`,
        expected: def.fixed === '' ? '(empty)' : def.fixed,
      }));
    }
    return;
  }

  const facets = def.facets ?? {};
  const type = def.type ?? 'xs:string';

  if (facets.enumeration !== undefined) {
    const allowed = [].concat(facets.enumeration);
    if (!allowed.includes(value)) {
      out.push(finding(ruleFor('enumeration', formatId), {
        ...where, message: `<${node.qname}> is not one of the enumerated values`,
        expected: allowed.join(' | '),
      }));
      return;
    }
  }

  if (facets.pattern !== undefined) {
    let re;
    try { re = new RegExp(`^(?:${facets.pattern})$`); } catch { re = null; }
    if (re && !re.test(value)) {
      out.push(finding(ruleFor('pattern', formatId), {
        ...where, message: `<${node.qname}> does not match the schema pattern`, expected: facets.pattern,
      }));
      return;
    }
  }
  if (facets.minLength !== undefined && value.length < Number(facets.minLength)) {
    out.push(finding(ruleFor('length', formatId), { ...where, message: `<${node.qname}> is shorter than minLength`, expected: `at least ${facets.minLength} characters` }));
  }
  if (facets.maxLength !== undefined && value.length > Number(facets.maxLength)) {
    out.push(finding(ruleFor('length', formatId), { ...where, message: `<${node.qname}> is longer than maxLength`, expected: `at most ${facets.maxLength} characters` }));
  }

  // An empty element is a valid xs:string with minLength 0, and is not a valid anything
  // else. Without this, a blank <totHrsStraightTime/> reads as zero and the real fault
  // is never reported.
  const TYPED = ['xs:date', 'xs:dateTime', 'xs:boolean', 'xs:decimal', 'xs:integer'];
  if (value === '' && TYPED.includes(type)) {
    out.push(finding(ruleFor('type', formatId), {
      ...where, message: `<${node.qname}> is empty, which is not a valid ${type}`,
      expected: type, actual: '(empty)',
    }));
    return;
  }

  if (type === 'xs:date' && value && !validDate(value)) {
    out.push(finding(ruleFor('type', formatId), { ...where, message: `<${node.qname}> is not a valid xs:date`, expected: 'a real calendar date, yyyy-mm-dd' }));
  } else if (type === 'xs:dateTime' && value && !validDateTime(value)) {
    out.push(finding(ruleFor('type', formatId), { ...where, message: `<${node.qname}> is not a valid xs:dateTime`, expected: 'yyyy-mm-ddThh:mm:ss[.sss][Z]' }));
  } else if (type === 'xs:boolean' && value && !['true', 'false', '1', '0'].includes(value)) {
    out.push(finding(ruleFor('type', formatId), { ...where, message: `<${node.qname}> is not a valid xs:boolean`, expected: 'true or false' }));
  } else if ((type === 'xs:decimal' || type === 'xs:integer') && value !== '') {
    const numeric = type === 'xs:integer' ? /^[+-]?\d+$/ : /^[+-]?(\d+(\.\d*)?|\.\d+)$/;
    if (!numeric.test(value)) {
      out.push(finding(ruleFor('type', formatId), { ...where, message: `<${node.qname}> is not a valid ${type}`, expected: type }));
      return;
    }
    const n = Number(value);
    if (facets.maxInclusive !== undefined && n > Number(facets.maxInclusive)) {
      out.push(finding(ruleFor('range', formatId), { ...where, message: `<${node.qname}> exceeds maxInclusive`, expected: `at most ${facets.maxInclusive}` }));
    }
    if (facets.maxExclusive !== undefined && n >= Number(facets.maxExclusive)) {
      out.push(finding(ruleFor('range', formatId), { ...where, message: `<${node.qname}> is not below maxExclusive`, expected: `less than ${facets.maxExclusive}` }));
    }
    if (facets.minInclusive !== undefined && n < Number(facets.minInclusive)) {
      out.push(finding(ruleFor('range', formatId), { ...where, message: `<${node.qname}> is below minInclusive`, expected: `at least ${facets.minInclusive}` }));
    }
    if (facets.fractionDigits !== undefined) {
      const dot = value.indexOf('.');
      const digits = dot === -1 ? 0 : value.length - dot - 1;
      if (digits > Number(facets.fractionDigits)) {
        out.push(finding(ruleFor('fraction', formatId), { ...where, message: `<${node.qname}> carries ${digits} fraction digits`, expected: `at most ${facets.fractionDigits}` }));
      }
    }
  }
}

function checkNode(def, node, idx, out, formatId, expectedNs, reportNs = true) {
  // A wrong namespace is inherited by every descendant, so report it once at the
  // highest element that has it and stay quiet below — one finding, not hundreds.
  if ((node.ns ?? null) !== expectedNs) {
    if (reportNs) {
      out.push(finding(ruleFor('namespace', formatId), {
        path: pathOf(node), line: node.line, actual: node.ns ?? '(no namespace)',
        expected: expectedNs ?? '(no namespace)',
        message: `<${node.qname}> and its descendants are in the wrong namespace`,
      }));
    }
    reportNs = false;
  }

  const childDefs = idx.childrenOf.get(def.path) ?? [];
  if (childDefs.length === 0) {
    checkValue(def, node, out, formatId);
    return;
  }

  const allowed = new Map(childDefs.map((d) => [d.name, d]));
  for (const child of node.children) {
    if (!allowed.has(child.name)) {
      out.push(finding(ruleFor('unexpected', formatId), {
        path: pathOf(child), line: child.line, actual: child.qname,
        expected: childDefs.map((d) => d.name).join(', '),
        message: `<${child.qname}> is not declared under <${node.qname}>`,
      }));
    }
  }

  let lastIndex = -1;
  let outOfOrderReported = false;
  for (const child of node.children) {
    const position = childDefs.findIndex((d) => d.name === child.name);
    if (position === -1) continue;
    if (position < lastIndex && !outOfOrderReported) {
      outOfOrderReported = true;
      out.push(finding(ruleFor('order', formatId), {
        path: pathOf(child), line: child.line, actual: child.name,
        expected: childDefs.map((d) => d.name).join(' → '),
        message: `<${child.qname}> appears out of sequence under <${node.qname}>`,
      }));
    }
    lastIndex = Math.max(lastIndex, position);
  }

  for (const childDef of childDefs) {
    const matches = node.children.filter((c) => c.name === childDef.name);
    const min = Number(childDef.minOccurs ?? '1');
    const max = childDef.maxOccurs === 'unbounded' ? Infinity : Number(childDef.maxOccurs ?? '1');
    if (matches.length < min) {
      out.push(finding(ruleFor('missing', formatId), {
        path: `${pathOf(node)}/${childDef.name}`, line: node.line,
        actual: `${matches.length} present`, expected: `at least ${min}`,
        message: `<${childDef.name}> is required under <${node.qname}>`,
      }));
    }
    if (matches.length > max) {
      out.push(finding(ruleFor('tooMany', formatId), {
        path: `${pathOf(node)}/${childDef.name}`, line: matches[max]?.line ?? node.line,
        actual: `${matches.length} present`, expected: `at most ${max}`,
        message: `too many <${childDef.name}> elements under <${node.qname}>`,
      }));
    }
    for (const match of matches) checkNode(childDef, match, idx, out, formatId, expectedNs, reportNs);
  }
}

/**
 * Validate a parsed document against the extracted schema for `formatId`.
 *
 * @param {object} root                    the document element from parseXml
 * @param {string} formatId                'ca-ecpr' or 'ny-certpayroll'
 * @param {string|null} expectedNs         the namespace every element must be in
 * @param {{reportNamespace?: boolean}} [options]  set reportNamespace false when the
 *        caller has already reported the namespace itself with a better message
 * @returns {Array} findings
 */
export function checkAgainstSchema(root, formatId, expectedNs, options = {}) {
  const idx = index(formatId);
  const out = [];
  if (root.name !== idx.root.name) {
    out.push(finding(ruleFor('unexpected', formatId), {
      path: root.name, line: root.line, actual: root.qname, expected: idx.root.name,
      message: `the document element must be <${idx.root.name}>`,
    }));
    return out;
  }
  checkNode(idx.root, root, idx, out, formatId, expectedNs ?? null, options.reportNamespace !== false);
  return out;
}
