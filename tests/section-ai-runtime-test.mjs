import assert from 'node:assert/strict';

const STEMS = 4, BANDS = 81, originalFrames = 120;
const data = new Float32Array(STEMS * originalFrames * BANDS);
for (let i = 0; i < data.length; i++) data[i] = i + 1;

function prepareInput(features) {
  const MIN_FRAMES = 10240, MAX_FRAMES = 66000;
  const shape = features.shape, originalFrames = shape[2];
  if (originalFrames > MAX_FRAMES) throw new Error('Section AI supports tracks up to 660 seconds');
  const frames = Math.max(MIN_FRAMES, originalFrames);
  if (frames === originalFrames) return {data: features.data, frames, originalFrames};
  const padded = new Float32Array(STEMS * frames * BANDS);
  for (let stem = 0; stem < STEMS; stem++) {
    const srcStart = stem * originalFrames * BANDS;
    const dstStart = stem * frames * BANDS;
    padded.set(features.data.subarray(srcStart, srcStart + originalFrames * BANDS), dstStart);
  }
  return {data: padded, frames, originalFrames};
}

const padded = prepareInput({data, shape:[1,4,originalFrames,81]});
assert.equal(padded.frames, 10240);
assert.equal(padded.originalFrames, originalFrames);
for (let stem = 0; stem < STEMS; stem++) {
  const src = stem * originalFrames * BANDS;
  const dst = stem * padded.frames * BANDS;
  assert.equal(padded.data[dst], data[src]);
  assert.equal(padded.data[dst + originalFrames * BANDS - 1], data[src + originalFrames * BANDS - 1]);
  assert.equal(padded.data[dst + originalFrames * BANDS], 0);
}
console.log('Section AI runtime padding regression: PASS');
