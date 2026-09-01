// The CLI is the surface most people will meet first. Exit codes and clean failure
// matter as much as the findings themselves.

import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { ROOT } from './helpers.js';

const CLI = join(ROOT, 'js', 'src', 'cli.js');

function run(...args) {
  const result = spawnSync(process.execPath, [CLI, ...args], { encoding: 'utf8', cwd: ROOT });
  return { code: result.status, out: result.stdout, err: result.stderr };
}

test('a clean file exits 0 and a file with errors exits 1', () => {
  assert.equal(run('validate', 'ny', 'fixtures/ny/valid.xml').code, 0);
  assert.equal(run('validate', 'ny', 'fixtures/ny/invalid.xml').code, 1);
});

test('warnings and advisories alone do not fail the exit code', () => {
  // The California fixture is clean but its filename does not follow the convention.
  const result = run('validate', 'ca', 'fixtures/ca/valid.xml');
  assert.equal(result.code, 0);
  assert.match(result.out, /1 advisory/);
});

test('a missing file is a clean message on stderr and exit 2, not a stack trace', () => {
  const result = run('validate', 'ca', 'does-not-exist.xml');
  assert.equal(result.code, 2);
  assert.match(result.err, /cannot read does-not-exist\.xml/);
  assert.doesNotMatch(result.err, /at Object|node:internal/, 'no stack trace');
  assert.equal(result.out, '');
});

test('bad usage exits 2 and prints the usage text', () => {
  for (const args of [['validate'], ['validate', 'tx', 'x.xml'], ['nonsense']]) {
    const result = run(...args);
    assert.equal(result.code, 2, args.join(' '));
    assert.match(result.err, /certified-payroll validate/);
  }
});

test('no arguments prints usage on stdout and exits 0', () => {
  const result = run();
  assert.equal(result.code, 0);
  assert.match(result.out, /US certified payroll formats, as data/);
});

test('--json emits parseable output that survives a pipe', () => {
  const result = run('validate', 'ny', 'fixtures/ny/invalid.xml', '--json');
  const parsed = JSON.parse(result.out);
  assert.equal(parsed.file, 'invalid.xml');
  assert.equal(parsed.valid, false);
  assert.ok(parsed.findings.length > 0);
  for (const f of parsed.findings) {
    assert.ok(f.ruleId && f.severity && f.message);
    assert.ok(f.sources.every((s) => s.url.startsWith('http')));
  }
});

test('--json output is complete even when the process exits non-zero', () => {
  // process.exit() truncates a large piped write; the CLI sets exitCode instead.
  const result = run('validate', 'ny', 'fixtures/ny/invalid-namespace.xml', '--json');
  assert.equal(result.code, 1);
  assert.doesNotThrow(() => JSON.parse(result.out));
});

test('--quiet drops warnings and advisories but keeps the summary', () => {
  const noisy = run('validate', 'ca', 'fixtures/ca/invalid.xml');
  const quiet = run('validate', 'ca', 'fixtures/ca/invalid.xml', '--quiet');
  assert.match(noisy.out, /WARNING/);
  assert.doesNotMatch(quiet.out, /WARNING|ADVISORY/);
  assert.match(quiet.out, /error\(s\)/);
});

test('human output names the rule and links its source', () => {
  const result = run('validate', 'ny', 'fixtures/ny/invalid.xml');
  assert.match(result.out, /rule ny\.employee\.exactlyOneIdentifier/);
  assert.match(result.out, /https:\/\/dol\.ny\.gov/);
});

test('every query subcommand produces output and exits 0', () => {
  const commands = [
    ['jurisdictions'], ['show', 'us-ny'], ['rules', 'ca-ecpr'],
    ['rule', 'ny.employee.exactlyOneIdentifier'], ['elements', 'ca-ecpr'],
    ['conflicts'], ['wh347'],
  ];
  for (const args of commands) {
    const result = run(...args);
    assert.equal(result.code, 0, args.join(' '));
    assert.ok(result.out.length > 40, args.join(' '));
  }
});

test('query subcommands emit valid JSON under --json', () => {
  for (const args of [['jurisdictions'], ['rules', 'wa-pwia'], ['elements', 'ny-certpayroll'],
                      ['conflicts'], ['show', 'us-ca'], ['wh347']]) {
    const result = run(...args, '--json');
    assert.doesNotThrow(() => JSON.parse(result.out), args.join(' '));
  }
});

test('an unknown jurisdiction or rule exits 2', () => {
  assert.equal(run('show', 'us-zz').code, 2);
  assert.equal(run('rule', 'nope').code, 2);
});
