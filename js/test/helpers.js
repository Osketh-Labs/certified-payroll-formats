import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const FIXTURES = join(ROOT, 'fixtures');

/** The text of a fixture. */
export function fixture(...parts) {
  return readFileSync(join(FIXTURES, ...parts), 'utf8');
}

/**
 * A fixture with one edit applied. Tests read as "this fault produces this finding",
 * which is the only thing about a validator worth asserting.
 */
export function mutate(source, replacements) {
  let out = source;
  for (const [from, to] of replacements) {
    if (!out.includes(from)) throw new Error(`mutation target not present: ${from}`);
    out = out.replace(from, to);
  }
  return out;
}

/** Rule ids from a result, in the order reported. */
export const ids = (result) => result.findings.map((f) => f.ruleId);

/** Count of a given rule id in a result. */
export const count = (result, ruleId) => ids(result).filter((id) => id === ruleId).length;

/** The first finding with a given rule id. */
export const first = (result, ruleId) => result.findings.find((f) => f.ruleId === ruleId);
