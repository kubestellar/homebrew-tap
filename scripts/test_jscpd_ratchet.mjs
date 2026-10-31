#!/usr/bin/env node
// test_jscpd_ratchet.mjs — end-to-end tests for scripts/jscpd-ratchet.mjs,
// the duplication ratchet gate added in #768 (.jscpd.json +
// jscpd-baseline.json). The script is top-level-side-effecting (reads
// jscpd-baseline.json from cwd, shells out to `npx jscpd`, calls
// process.exit), so like the project's shell helpers it is tested by
// spawning it as a subprocess rather than by import.
//
// Nothing previously covered this file. A regression that inverted the
// `clones > baseline` comparison, dropped the nonzero exit on regression,
// or stopped reading jscpd-baseline.json would land past CI unnoticed.
//
// This repo has no package.json/Node test runner wiring; run directly
// with Node's built-in test runner: node --test scripts/test_jscpd_ratchet.mjs
// (Node >= 18). A fake `npx` is placed first on PATH so these tests never
// depend on the real jscpd binary or network access.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync, chmodSync, readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCRIPT = resolve(__dirname, 'jscpd-ratchet.mjs');
const JSCPD_CONFIG = resolve(__dirname, '..', '.jscpd.json');

let fakeBinDir;

before(() => {
  // A fake `npx` that just writes a jscpd-style report.json containing
  // FAKE_CLONES clones into whatever --output dir it was given, instead of
  // actually running jscpd.
  fakeBinDir = mkdtempSync(join(tmpdir(), 'jscpd-fake-npx-'));
  const fakeNpx = join(fakeBinDir, 'npx');
  writeFileSync(
    fakeNpx,
    `#!/usr/bin/env node
const { writeFileSync } = require('fs')
const { join } = require('path')
const args = process.argv.slice(2)
const outDir = args[args.indexOf('--output') + 1]
const clones = Number(process.env.FAKE_CLONES || '0')
console.log(\`fake jscpd: emitting \${clones} clone(s)\`)
writeFileSync(join(outDir, 'jscpd-report.json'), JSON.stringify({ statistics: { total: { clones } } }))
`,
  );
  chmodSync(fakeNpx, 0o755);
});

after(() => {
  rmSync(fakeBinDir, { recursive: true, force: true });
});

function withTempRepo(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'jscpd-ratchet-'));
  try {
    // The script reads '.jscpd.json' and 'jscpd-baseline.json' relative to cwd.
    writeFileSync(join(dir, '.jscpd.json'), readFileSync(JSCPD_CONFIG, 'utf8'));
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function runScript(cwd, { baselineClones, fakeClones }) {
  writeFileSync(join(cwd, 'jscpd-baseline.json'), JSON.stringify({ clones: baselineClones }));
  return spawnSync(process.execPath, [SCRIPT], {
    cwd,
    encoding: 'utf8',
    env: {
      ...process.env,
      PATH: `${fakeBinDir}:${process.env.PATH}`,
      FAKE_CLONES: String(fakeClones),
      NO_COLOR: '1',
    },
  });
}

test('exits 0 and reports the clone count when clones stay at the baseline', () => {
  withTempRepo(dir => {
    const result = runScript(dir, { baselineClones: 5, fakeClones: 5 });
    assert.equal(result.status, 0);
    assert.match(result.stdout, /jscpd ratchet: 5 clone\(s\) found, baseline 5/);
    assert.doesNotMatch(result.stdout, /::notice::/);
  });
});

test('exits 1 and prints an ::error:: annotation when clones exceed the baseline', () => {
  withTempRepo(dir => {
    const result = runScript(dir, { baselineClones: 5, fakeClones: 8 });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /::error::Duplication increased: 8 clones > baseline 5/);
  });
});

test('exits 0 and prints a ::notice:: hint to ratchet down when clones drop below the baseline', () => {
  withTempRepo(dir => {
    const result = runScript(dir, { baselineClones: 5, fakeClones: 2 });
    assert.equal(result.status, 0);
    assert.match(result.stdout, /jscpd ratchet: 2 clone\(s\) found, baseline 5/);
    assert.match(
      result.stdout,
      /::notice::Duplication decreased; lower "clones" in jscpd-baseline\.json to 2 in this PR to ratchet\./,
    );
  });
});

test('exits non-zero when jscpd-baseline.json is missing from cwd', () => {
  const dir = mkdtempSync(join(tmpdir(), 'jscpd-ratchet-nobaseline-'));
  try {
    writeFileSync(join(dir, '.jscpd.json'), readFileSync(JSCPD_CONFIG, 'utf8'));
    const result = spawnSync(process.execPath, [SCRIPT], {
      cwd: dir,
      encoding: 'utf8',
      env: { ...process.env, PATH: `${fakeBinDir}:${process.env.PATH}`, FAKE_CLONES: '0' },
    });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /ENOENT|no such file/i);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
