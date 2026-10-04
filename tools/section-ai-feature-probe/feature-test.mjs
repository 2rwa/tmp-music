import fs from 'node:fs';
import assert from 'node:assert/strict';
import { computeSectionAISpectrograms } from './feature-core.mjs';

const referenceDir = process.argv[2];
if (!referenceDir) throw new Error('usage: node feature-test.mjs <reference-dir>');
const meta = JSON.parse(fs.readFileSync(referenceDir + '/reference.json', 'utf8'));
const raw = fs.readFileSync(referenceDir + '/reference.f32');
const ref = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);

const sr = 44100, seconds = 2, samples = Math.floor(sr * seconds);
const cfg = {
  bass: [82.41, .31, 1.2],
  drums: [913, .19, 4.0],
  other: [329.63, .22, .7],
  vocals: [220, .27, 2.1]
};
const stems = {};
for (const [name, [freq, amp, trem]] of Object.entries(cfg)) {
  const interleaved = new Float32Array(samples * 2);
  for (let i = 0; i < samples; i++) {
    const t = i / sr;
    const envelope = .82 + .18 * Math.sin(2 * Math.PI * trem * t);
    let left = amp * envelope * Math.sin(2 * Math.PI * freq * t);
    let right = amp * envelope * Math.sin(2 * Math.PI * (freq * 1.003) * t + .17);
    if (name === 'drums') {
      const clickPhase = t % .25;
      const click = Math.exp(-clickPhase / .018) * Math.sin(2 * Math.PI * 1400 * clickPhase);
      left += .22 * click;
      right += .18 * click;
    }
    interleaved[i * 2] = left;
    interleaved[i * 2 + 1] = right;
  }
  stems[name] = interleaved;
}

const got = computeSectionAISpectrograms(stems, sr);
assert.deepEqual(got.shape.slice(1), meta.shape);
assert.equal(got.data.length, ref.length);

let maxAbs = 0, sumAbs = 0, over1e4 = 0;
for (let i = 0; i < ref.length; i++) {
  const d = Math.abs(got.data[i] - ref[i]);
  maxAbs = Math.max(maxAbs, d);
  sumAbs += d;
  if (d > 1e-4) over1e4++;
}
const meanAbs = sumAbs / ref.length;
console.log(JSON.stringify({shape: got.shape, maxAbs, meanAbs, over1e4, values: ref.length}, null, 2));
assert.ok(maxAbs < 3e-4, 'max feature error too high: ' + maxAbs);
assert.ok(meanAbs < 2e-5, 'mean feature error too high: ' + meanAbs);
console.log('Section AI feature parity: PASS');
