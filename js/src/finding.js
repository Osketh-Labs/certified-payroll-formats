import { resolveSources } from './data.js';

export const SEVERITY_ORDER = { error: 0, warning: 1, advisory: 2 };

/**
 * A single validation finding. Every finding cites the rule it came from and the
 * official source behind that rule — the point of the exercise is that you can
 * check the claim, not take our word for it.
 */
export function finding(ruleDoc, { path, line, message, expected, actual }) {
  return {
    ruleId: ruleDoc.id,
    severity: ruleDoc.severity,
    path: path ?? null,
    line: line ?? null,
    message,
    expected: expected ?? null,
    actual: actual ?? null,
    statement: ruleDoc.statement,
    sources: Array.isArray(ruleDoc.sources) && typeof ruleDoc.sources[0] === 'string'
      ? resolveSources(ruleDoc.sources)
      : ruleDoc.sources,
  };
}

export function sortFindings(findings) {
  return [...findings].sort((a, b) => {
    const s = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
    return s !== 0 ? s : (a.line ?? 0) - (b.line ?? 0);
  });
}

export function summarize(findings) {
  const counts = { error: 0, warning: 0, advisory: 0 };
  for (const f of findings) counts[f.severity] = (counts[f.severity] ?? 0) + 1;
  return { valid: counts.error === 0, counts, findings: sortFindings(findings) };
}
