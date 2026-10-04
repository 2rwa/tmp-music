import assert from 'node:assert/strict';
import { analyzeVocalPhrases, nearestPhraseBoundary } from '../docs/m6-status/structure-cutter-lab/vocal-core.js';

const sr = 8000;
const seconds = 18;
const channels = 2;
const data = new Float32Array(sr * seconds * channels);
const phrases = [[1.0, 3.8], [5.0, 7.4], [10.2, 14.1]];
for (const [startSec, endSec] of phrases) {
  const start = Math.floor(startSec * sr), end = Math.floor(endSec * sr);
  for (let i = start; i < end; i++) {
    const local = (i - start) / sr;
    const env = Math.min(1, local / .08, (endSec - startSec - local) / .10);
    const value = .48 * Math.max(0, env) * Math.sin(2 * Math.PI * (210 + 18 * Math.sin(local * 2)) * local);
    data[i * 2] = value;
    data[i * 2 + 1] = value;
  }
}
const result = analyzeVocalPhrases(data, sr);
assert.equal(result.phrases.length, 3, `expected 3 phrases, got ${result.phrases.length}`);
assert.equal(result.boundaries.length, 6);
assert.ok(Math.abs(result.phrases[0].start - 1.0) < .2);
assert.ok(Math.abs(result.phrases[2].end - 14.1) < .2);
const hit = nearestPhraseBoundary(5.18, result.boundaries, .5);
assert.ok(hit && Math.abs(hit.time - 5.0) < .2, 'nearest phrase start expected');
console.log('Vocal phrase regression: PASS', {
  phrases: result.phrases.map(p => [p.start, p.end]),
  thresholdDb: result.thresholdDb,
  hit
});
