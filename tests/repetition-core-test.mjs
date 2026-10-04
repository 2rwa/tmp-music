import assert from 'node:assert/strict';
import { analyzeRepetition, cosineSimilarity, periodCandidates } from '../docs/m6-status/structure-cutter-lab/repetition-core.js';

assert.ok(cosineSimilarity([1, 0], [1, 0]) > .999);
assert.ok(cosineSimilarity([1, 0], [-1, 0]) < -.999);
assert.equal(periodCandidates([
  {lagFrames:1, similarity:.1},
  {lagFrames:2, similarity:.9},
  {lagFrames:3, similarity:.2},
  {lagFrames:4, similarity:.8},
  {lagFrames:5, similarity:.1}
], 2, 1)[0].lagFrames, 2);

const sr = 4000;
const segmentSec = 8;
const totalSec = 32;
const samples = new Float32Array(sr * totalSec);
function fillSegment(startSec, frequency, amp, pulse) {
  const start = Math.floor(startSec * sr);
  const end = Math.floor((startSec + segmentSec) * sr);
  for (let i = start; i < end; i++) {
    const local = (i - start) / sr;
    const trem = 1 + .28 * Math.sin(2 * Math.PI * pulse * local);
    samples[i] = amp * trem * Math.sin(2 * Math.PI * frequency * local);
  }
}
fillSegment(0, 170, .25, 1.7);   // A
fillSegment(8, 330, .12, 3.1);  // B
fillSegment(16, 170, .25, 1.7); // A repeated
fillSegment(24, 520, .32, .8);  // C

const result = analyzeRepetition(samples, sr, [], {minPeriodSec:10, maxPeriodSec:22, blockSec:5.5});
assert.ok(result.candidates.length > 0, 'period candidate expected');
assert.ok(result.pairs.length > 0, 'repetition pair expected');
assert.ok(result.boundaries.length > 0, 'repetition boundaries expected');
assert.ok(result.pairs.some(p => Math.abs(p.lagSec - 16) < 2.0), 'A→A lag should be near 16 s');
assert.ok(result.boundaries.some(b => Math.abs(b.t - 16) < 3.0), 'repeated A start should become a boundary');

console.log('Repetition core regression: PASS', {
  selectedPeriodSec: result.selectedPeriodSec,
  pairs: result.pairs.length,
  boundaries: result.boundaries.length
});
