export const HARMONIX_LABELS = [
  'start', 'end', 'intro', 'outro', 'break',
  'bridge', 'inst', 'solo', 'verse', 'chorus'
];

function sigmoid(x) {
  return 1 / (1 + Math.exp(-x));
}

function softmaxFrame(logits, classes, frames, frame) {
  let max = -Infinity;
  for (let c = 0; c < classes; c++) max = Math.max(max, logits[c * frames + frame]);
  let total = 0;
  const out = new Float32Array(classes);
  for (let c = 0; c < classes; c++) {
    const v = Math.exp(logits[c * frames + frame] - max);
    out[c] = v;
    total += v;
  }
  if (total <= 0) return out;
  for (let c = 0; c < classes; c++) out[c] /= total;
  return out;
}

export function localMaxima(values, filterSize = 97) {
  if (filterSize % 2 !== 1) throw new Error('filterSize must be odd');
  const radius = Math.floor(filterSize / 2);
  const out = new Float32Array(values.length);
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    let isMax = true;
    const a = Math.max(0, i - radius);
    const b = Math.min(values.length - 1, i + radius);
    for (let j = a; j <= b; j++) {
      if (values[j] > v) { isMax = false; break; }
    }
    if (isMax) out[i] = v;
  }
  return out;
}

function prefix(values) {
  const p = new Float64Array(values.length + 1);
  for (let i = 0; i < values.length; i++) p[i + 1] = p[i] + values[i];
  return p;
}

function rangeMean(p, start, end) {
  const a = Math.max(0, start);
  const b = Math.min(p.length - 1, end);
  if (b <= a) return 0;
  return (p[b] - p[a]) / (b - a);
}

export function peakPicking(values, windowPast = 1200, windowFuture = 1200) {
  if ((windowPast + windowFuture) % 2 !== 0) {
    throw new Error('windowPast + windowFuture must be even');
  }
  const p = prefix(values);
  const out = new Float32Array(values.length);
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!(v > 0)) continue;

    let isMax = true;
    const left = Math.max(0, i - windowPast);
    const right = Math.min(values.length - 1, i + windowFuture);
    for (let j = left; j <= right; j++) {
      if (values[j] > v) { isMax = false; break; }
    }
    if (!isMax) continue;

    // np.pad(..., mode='constant') means out-of-range samples count as zeros
    // in the upstream fixed-size mean windows.
    const pastSum = p[i] - p[Math.max(0, i - windowPast)];
    const futureSum = p[Math.min(values.length, i + 1 + windowFuture)] - p[i + 1];
    const pastMean = pastSum / Math.max(1, windowPast);
    const futureMean = futureSum / Math.max(1, windowFuture);
    out[i] = v - (pastMean + futureMean) * .5;
  }
  return out;
}

export function postprocessFunctionalStructure(
  sectionLogits,
  functionLogits,
  {
    fps = 100,
    hopSize = 441,
    sampleRate = 44100,
    minHopsPerBeat = 24,
    labels = HARMONIX_LABELS
  } = {}
) {
  const frames = sectionLogits.length;
  const classes = labels.length;
  if (functionLogits.length !== classes * frames) {
    throw new Error('function logits must be class-major [classes, frames]');
  }

  const sectionProb = new Float32Array(frames);
  for (let i = 0; i < frames; i++) sectionProb[i] = sigmoid(sectionLogits[i]);
  const maxima = localMaxima(sectionProb, 4 * minHopsPerBeat + 1);
  const strengths = peakPicking(maxima, 12 * fps, 12 * fps);

  const boundaryIndices = [];
  for (let i = 0; i < strengths.length; i++) if (strengths[i] > 0) boundaryIndices.push(i);
  const duration = frames * hopSize / sampleRate;
  const boundaryTimes = boundaryIndices.map(i => i * hopSize / sampleRate);
  if (!boundaryTimes.length || boundaryTimes[0] !== 0) boundaryTimes.unshift(0);
  if (boundaryTimes[boundaryTimes.length - 1] !== duration) boundaryTimes.push(duration);

  // Upstream splits label probabilities only at detected boundaries > frame 0.
  const splitIndices = boundaryIndices.filter(i => i > 0);
  const frameCuts = [0, ...splitIndices, frames];
  const segments = [];

  for (let s = 0; s < frameCuts.length - 1; s++) {
    const startFrame = frameCuts[s];
    const endFrame = frameCuts[s + 1];
    if (endFrame <= startFrame) continue;
    const mean = new Float64Array(classes);
    for (let f = startFrame; f < endFrame; f++) {
      const prob = softmaxFrame(functionLogits, classes, frames, f);
      for (let c = 0; c < classes; c++) mean[c] += prob[c];
    }
    let labelIndex = 0;
    for (let c = 1; c < classes; c++) if (mean[c] > mean[labelIndex]) labelIndex = c;
    segments.push({
      start: boundaryTimes[s] ?? startFrame * hopSize / sampleRate,
      end: boundaryTimes[s + 1] ?? endFrame * hopSize / sampleRate,
      label: labels[labelIndex],
      labelIndex
    });
  }

  return {
    segments,
    boundaryIndices,
    boundaryTimes,
    sectionProbability: sectionProb,
    sectionStrength: strengths
  };
}
