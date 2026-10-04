const EPS = 1e-9;

export function median(values) {
  if (!values.length) return 0;
  const a = values.filter(Number.isFinite).slice().sort((x, y) => x - y);
  if (!a.length) return 0;
  const i = Math.floor(a.length / 2);
  return a.length % 2 ? a[i] : (a[i - 1] + a[i]) * .5;
}

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

export function extractRepetitionFrames(samples, sampleRate, stemFrames = [], options = {}) {
  const stepSec = options.stepSec || .55;
  const winSec = options.winSec || 1.1;
  const hop = Math.max(1, Math.floor(sampleRate * stepSec));
  const win = Math.max(hop, Math.floor(sampleRate * winSec));
  const frames = [];
  let previousDb = null;

  for (let start = 0; start + win <= samples.length; start += hop) {
    const end = start + win;
    const stride = Math.max(1, Math.floor(win / 520));
    let sum = 0, diffSum = 0, zc = 0, count = 0;
    let prev = samples[start] || 0;
    for (let i = start; i < end; i += stride) {
      const x = samples[i] || 0;
      sum += x * x;
      const d = x - prev;
      diffSum += d * d;
      if (count && ((x >= 0) !== (prev >= 0))) zc++;
      prev = x;
      count++;
    }
    const rms = Math.sqrt(sum / Math.max(1, count));
    const db = 20 * Math.log10(rms + 1e-8);
    const zcr = zc / Math.max(1, count);
    const brightness = Math.sqrt(diffSum / Math.max(EPS, sum));
    const deltaDb = previousDb == null ? 0 : db - previousDb;
    previousDb = db;
    const t = (start + win * .5) / sampleRate;
    const vector = [db / 20, zcr * 8, brightness, deltaDb / 12];

    if (stemFrames.length) {
      const stemIndex = clamp(Math.round(t / stepSec - .5), 0, stemFrames.length - 1);
      const stem = stemFrames[stemIndex];
      if (stem && stem.shares) {
        vector.push(
          stem.shares.vocals || 0,
          stem.shares.drums || 0,
          stem.shares.bass || 0,
          stem.shares.other || 0
        );
      }
    }
    frames.push({ t, vector });
  }
  return { stepSec, frames };
}

export function standardizeVectors(frames) {
  if (!frames.length) return [];
  const dims = frames[0].vector.length;
  const means = new Array(dims).fill(0);
  for (const frame of frames) for (let d = 0; d < dims; d++) means[d] += frame.vector[d] || 0;
  for (let d = 0; d < dims; d++) means[d] /= frames.length;
  const stds = new Array(dims).fill(0);
  for (const frame of frames) for (let d = 0; d < dims; d++) {
    const x = (frame.vector[d] || 0) - means[d];
    stds[d] += x * x;
  }
  for (let d = 0; d < dims; d++) stds[d] = Math.sqrt(stds[d] / frames.length) || 1;
  return frames.map(frame => ({
    t: frame.t,
    vector: frame.vector.map((x, d) => (x - means[d]) / stds[d])
  }));
}

export function cosineSimilarity(a, b) {
  let dot = 0, aa = 0, bb = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    dot += a[i] * b[i];
    aa += a[i] * a[i];
    bb += b[i] * b[i];
  }
  if (aa < EPS || bb < EPS) return 0;
  return clamp(dot / Math.sqrt(aa * bb), -1, 1);
}

export function lagSimilarityProfile(frames, minLag, maxLag) {
  const rows = [];
  for (let lag = minLag; lag <= maxLag; lag++) {
    let total = 0, support = 0;
    for (let i = 0; i + lag < frames.length; i++) {
      total += cosineSimilarity(frames[i].vector, frames[i + lag].vector);
      support++;
    }
    if (support) rows.push({ lagFrames: lag, similarity: total / support, support });
  }
  return rows;
}

export function periodCandidates(profile, topK = 5, separationFrames = 4) {
  const local = [];
  for (let i = 0; i < profile.length; i++) {
    const row = profile[i];
    const left = i ? profile[i - 1].similarity : -Infinity;
    const right = i + 1 < profile.length ? profile[i + 1].similarity : -Infinity;
    if (row.similarity >= left && row.similarity >= right) local.push(row);
  }
  local.sort((a, b) => b.similarity - a.similarity || a.lagFrames - b.lagFrames);
  const selected = [];
  for (const row of local) {
    if (selected.some(x => Math.abs(x.lagFrames - row.lagFrames) < separationFrames)) continue;
    selected.push(row);
    if (selected.length >= topK) break;
  }
  return selected;
}

function blockSimilarity(frames, a, b, length) {
  let sum = 0, count = 0;
  for (let k = 0; k < length && a + k < frames.length && b + k < frames.length; k++) {
    sum += cosineSimilarity(frames[a + k].vector, frames[b + k].vector);
    count++;
  }
  return count ? sum / count : -1;
}

function clusterBoundaries(raw, toleranceSec = 1.2) {
  const sorted = raw.slice().sort((a, b) => a.t - b.t);
  const clusters = [];
  for (const item of sorted) {
    const prev = clusters[clusters.length - 1];
    if (prev && item.t - prev.last <= toleranceSec) {
      prev.items.push(item);
      prev.last = item.t;
    } else {
      clusters.push({ items: [item], last: item.t });
    }
  }
  return clusters.map(cluster => {
    const weight = cluster.items.reduce((s, x) => s + Math.max(.05, x.confidence), 0);
    const t = cluster.items.reduce((s, x) => s + x.t * Math.max(.05, x.confidence), 0) / weight;
    const confidence = Math.max(...cluster.items.map(x => x.confidence));
    return { t, score: confidence, confidence, source: 'repetition', evidence: { repetition: confidence } };
  });
}

export function analyzeRepetition(samples, sampleRate, stemFrames = [], options = {}) {
  const extracted = extractRepetitionFrames(samples, sampleRate, stemFrames, options);
  const frames = standardizeVectors(extracted.frames);
  const stepSec = extracted.stepSec;
  const durationSec = samples.length / sampleRate;
  if (frames.length < 24) return { stepSec, frames, profile: [], candidates: [], pairs: [], boundaries: [], selectedPeriodSec: null };

  const minLag = Math.max(2, Math.round((options.minPeriodSec || 6) / stepSec));
  const maxLag = Math.min(
    frames.length - 8,
    Math.round(Math.min(options.maxPeriodSec || 70, durationSec * .68) / stepSec)
  );
  if (maxLag <= minLag) return { stepSec, frames, profile: [], candidates: [], pairs: [], boundaries: [], selectedPeriodSec: null };

  const profile = lagSimilarityProfile(frames, minLag, maxLag);
  const candidates = periodCandidates(profile, options.topPeriods || 5, Math.max(2, Math.round(2.5 / stepSec)));
  const blockFrames = Math.max(4, Math.round((options.blockSec || 5.5) / stepSec));
  const pairs = [];

  for (const candidate of candidates.slice(0, 4)) {
    const lag = candidate.lagFrames;
    const sims = [];
    for (let i = 0; i + lag + blockFrames < frames.length; i++) {
      sims.push({ i, similarity: blockSimilarity(frames, i, i + lag, blockFrames) });
    }
    const med = median(sims.map(x => x.similarity));
    const mad = median(sims.map(x => Math.abs(x.similarity - med))) || .03;
    const threshold = Math.min(.92, Math.max(.5, med + Math.max(.08, mad * 1.7)));
    const peaks = sims.filter((row, index) => {
      if (row.similarity < threshold) return false;
      const left = index ? sims[index - 1].similarity : -Infinity;
      const right = index + 1 < sims.length ? sims[index + 1].similarity : -Infinity;
      return row.similarity >= left && row.similarity >= right;
    }).sort((a, b) => b.similarity - a.similarity);

    const chosen = [];
    for (const peak of peaks) {
      if (chosen.some(x => Math.abs(x.i - peak.i) < blockFrames)) continue;
      chosen.push(peak);
      if (chosen.length >= 3) break;
    }

    for (const peak of chosen) {
      const aStart = frames[peak.i].t - stepSec * .5;
      const bStart = frames[peak.i + lag].t - stepSec * .5;
      const duration = blockFrames * stepSec;
      const rawConfidence = (peak.similarity - threshold) / Math.max(.08, 1 - threshold);
      const confidence = clamp(.42 + rawConfidence * .5 + Math.max(0, candidate.similarity) * .12, .25, 1);
      pairs.push({
        aStart: Math.max(0, aStart),
        aEnd: Math.min(durationSec, aStart + duration),
        bStart: Math.max(0, bStart),
        bEnd: Math.min(durationSec, bStart + duration),
        lagSec: lag * stepSec,
        similarity: peak.similarity,
        periodSimilarity: candidate.similarity,
        confidence
      });
    }
  }

  pairs.sort((a, b) => b.confidence - a.confidence || b.similarity - a.similarity);
  const selectedPairs = [];
  for (const pair of pairs) {
    const duplicate = selectedPairs.some(x =>
      Math.abs(x.aStart - pair.aStart) < 2 &&
      Math.abs(x.bStart - pair.bStart) < 2
    );
    if (!duplicate) selectedPairs.push(pair);
    if (selectedPairs.length >= 8) break;
  }
  selectedPairs.sort((a, b) => a.aStart - b.aStart || a.bStart - b.bStart);

  const rawBoundaries = [];
  for (const pair of selectedPairs) {
    for (const t of [pair.aStart, pair.aEnd, pair.bStart, pair.bEnd]) {
      if (t >= 2 && t <= durationSec - 2) rawBoundaries.push({ t, confidence: pair.confidence });
    }
  }
  const boundaries = clusterBoundaries(rawBoundaries);
  const selectedPeriodSec = candidates.length ? candidates[0].lagFrames * stepSec : null;
  return { stepSec, frames, profile, candidates, pairs: selectedPairs, boundaries, selectedPeriodSec };
}
