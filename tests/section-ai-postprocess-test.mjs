import assert from 'node:assert/strict';
import { HARMONIX_LABELS, localMaxima, peakPicking, postprocessFunctionalStructure } from '../docs/m6-status/structure-cutter-lab/section-ai-postprocess.js';

assert.equal(HARMONIX_LABELS[8], 'verse');
assert.equal(HARMONIX_LABELS[9], 'chorus');

const maxima = localMaxima(Float32Array.from([0, 1, .2, 2, .1]), 3);
assert.deepEqual(Array.from(maxima), [0, 1, 0, 2, 0]);
const peaks = peakPicking(maxima, 2, 2);
assert.ok(peaks[3] > 0);

const frames = 4500;
const section = new Float32Array(frames).fill(-8);
section[1500] = 9;
section[3000] = 10;

const classes = HARMONIX_LABELS.length;
const fn = new Float32Array(classes * frames).fill(-5);
function setLabel(start, end, labelIndex) {
  for (let f = start; f < end; f++) fn[labelIndex * frames + f] = 5;
}
setLabel(0, 1500, 2);       // intro
setLabel(1500, 3000, 8);    // verse
setLabel(3000, frames, 9);  // chorus

const result = postprocessFunctionalStructure(section, fn);
assert.deepEqual(result.boundaryIndices, [1500, 3000]);
assert.equal(result.segments.length, 3);
assert.deepEqual(result.segments.map(x => x.label), ['intro', 'verse', 'chorus']);
assert.ok(Math.abs(result.segments[0].end - 15) < .001);
assert.ok(Math.abs(result.segments[2].start - 30) < .001);
assert.ok(Math.abs(result.segments[2].end - 45) < .001);

console.log('Section AI postprocess regression: PASS', result.segments);
