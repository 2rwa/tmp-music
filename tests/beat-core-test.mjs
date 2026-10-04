import assert from 'node:assert/strict';
import { analyzeBeatGrid, alignCutRange, nearestGridTime } from '../docs/m6-status/structure-cutter-lab/beat-core.js';

const sr = 8000;
const seconds = 24;
const samples = new Float32Array(sr * seconds);
const bpm = 120;
const beatSec = 60 / bpm;
for (let beat = 0; beat * beatSec < seconds; beat++) {
  const t0 = beat * beatSec;
  const amp = beat % 4 === 0 ? 1 : .45;
  const start = Math.floor(t0 * sr);
  const length = Math.floor(.045 * sr);
  for (let i = 0; i < length && start + i < samples.length; i++) {
    const env = Math.exp(-i / (sr * .012));
    samples[start + i] += amp * env * Math.sin(2 * Math.PI * 900 * i / sr);
  }
}
const result = analyzeBeatGrid(samples, sr);
assert.ok(result.bpm, 'BPM should be estimated');
assert.ok(Math.abs(result.bpm - 120) < 4, `expected ~120 BPM, got ${result.bpm}`);
assert.ok(result.confidence > .3, 'tempo confidence should be useful');
assert.ok(result.beatTimes.length > 30, 'beat grid expected');
assert.ok(result.barTimes.length >= 8, 'bar grid expected');
assert.ok(result.boundaries.length >= 8, 'bar boundaries expected');

const beatHit = nearestGridTime(3.08, result.beatTimes, .3);
assert.ok(beatHit && Math.abs(beatHit.time - 3.0) < .08, 'nearest beat should land near 3.0 s');

const aligned = alignCutRange(3.08, 7.91, result, 'recommended');
assert.ok(Math.abs(aligned.start - 3.0) < .12, 'recommended start should use a nearby beat rather than jump almost a second to a bar');
assert.ok(aligned.end > aligned.start, 'aligned range must stay ordered');

console.log('Beat core regression: PASS', {
  bpm: result.bpm,
  confidence: result.confidence,
  beats: result.beatTimes.length,
  bars: result.barTimes.length,
  aligned
});
