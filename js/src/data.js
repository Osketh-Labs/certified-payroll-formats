import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

// `data/` at the repository root is canonical. `tools/sync_packages.py` copies it into
// this package before publishing, because npm cannot pack files above the package
// directory. Prefer the packaged copy; fall back to the root when running from a checkout.
const HERE = dirname(fileURLToPath(import.meta.url));
const PACKAGED = join(HERE, '..', 'data');
const REPO_ROOT = join(HERE, '..', '..', 'data');
const DATA_DIR = existsSync(join(PACKAGED, 'sources.json')) ? PACKAGED : REPO_ROOT;
const cache = new Map();

function load(name) {
  if (!cache.has(name)) cache.set(name, JSON.parse(readFileSync(join(DATA_DIR, name), 'utf8')));
  return cache.get(name);
}

export const sources = () => load('sources.json').sources;
export const jurisdictions = () => load('jurisdictions.json').jurisdictions;
export const wh347 = () => load('wh347.json');
export const caEcpr = () => load('ca-ecpr.json');
export const nyCertPayroll = () => load('ny-certpayroll.json');
export const waPwia = () => load('wa-pwia.json');
export const conflicts = () => load('conflicts.json').conflicts;

/** One jurisdiction by id (`us`, `us-ca`, `us-ny`, `us-wa`). */
export function jurisdiction(id) {
  return jurisdictions().find((j) => j.id === id) ?? null;
}

/** Resolve source ids to full `{id, title, publisher, kind, url}` records. */
export function resolveSources(ids = []) {
  const all = sources();
  return ids.map((id) => ({ id, ...(all[id] ?? { title: `unknown source: ${id}` }) }));
}

/** Every documented rule for a format id, with its sources resolved. */
export function rules(formatId) {
  const doc = { 'ca-ecpr': caEcpr, 'ny-certpayroll': nyCertPayroll, 'wa-pwia': waPwia }[formatId];
  if (!doc) throw new Error(`Unknown format: ${formatId}`);
  return doc().rules.map((r) => ({ ...r, sources: resolveSources(r.sources) }));
}

/** One rule by id, across every format and the WH-347 easy-to-miss list. */
export function rule(id) {
  for (const formatId of ['ca-ecpr', 'ny-certpayroll', 'wa-pwia']) {
    const found = rules(formatId).find((r) => r.id === id);
    if (found) return found;
  }
  const wh = wh347().easyToMiss.find((r) => r.id === id);
  return wh ? { ...wh, sources: resolveSources(wh.sources) } : null;
}

/** The element tree extracted from a published schema, as a flat list of paths. */
export function elements(formatId) {
  const doc = { 'ca-ecpr': caEcpr, 'ny-certpayroll': nyCertPayroll }[formatId];
  if (!doc) throw new Error(`No extracted element tree for format: ${formatId}`);
  return doc().elements;
}
