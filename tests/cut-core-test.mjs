import assert from 'node:assert/strict';
import { findLowEnergyTime, alignLowEnergyRange } from '../docs/m6-status/structure-cutter-lab/cut-core.js';

const sr = 8000;
const seconds = 6;
const samples = new Float32Array(sr * seconds);
for (let i = 0; i < samples.length; i++) {
  const t = i / sr;
  let amp = .45;
  if (t > 1.92 && t < 2.08) amp = .015;
  if (t > 4.02 && t < 4.18) amp = .02;
  samples[i] = amp * Math.sin(2 * Math.PI * 220 * t);
}
const start = findLowEnergyTime(samples, sr, 1.8, { radiusSec: .35 });
const end = findLowEnergyTime(samples, sr, 3.9, { radiusSec: .35 });
assert.ok(start && Math.abs(start.time - 2.0) < .12, `start trough expected near 2.0, got ${start?.time}`);
assert.ok(end && Math.abs(end.time - 4.1) < .12, `end trough expected near 4.1, got ${end?.time}`);
assert.ok(start.dropDb > 10 && end.dropDb > 10, 'energy drop should be substantial');
const range = alignLowEnergyRange(1.8, 3.9, samples, sr, { radiusSec: .35 });
assert.ok(range.end > range.start);
assert.equal(range.startKind, 'low-energy');
assert.equal(range.endKind, 'low-energy');
console.log('Cut core regression: PASS', {start, end, range});
