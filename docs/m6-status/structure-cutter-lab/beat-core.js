const EPS = 1e-12;

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

export function extractOnsetEnvelope(samples, sampleRate, options = {}) {
  const hopSec = options.hopSec || .02;
  const winSec = options.winSec || .04;
  const hop = Math.max(1, Math.round(sampleRate * hopSec));
  const win = Math.max(hop, Math.round(sampleRate * winSec));
  const envelope = [];
  let previousRms = 0;

  for (let start = 0; start + win <= samples.length; start += hop) {
    let energy = 0, diffEnergy = 0, prev = samples[start] || 0, count = 0;
    const stride = Math.max(1, Math.floor(win / 220));
    for (let i = start; i < start + win; i += stride) {
      const x = samples[i] || 0;
      const d = x - prev;
      energy += x * x;
      diffEnergy += d * d;
      prev = x;
      count++;
    }
    const rms = Math.sqrt(energy / Math.max(1, count));
    const hf = Math.sqrt(diffEnergy / Math.max(1, count));
    const rise = Math.max(0, rms - previousRms);
    previousRms = rms;
    envelope.push(rise * 3.5 + hf * .8);
  }

  const sorted = envelope.slice().sort((a, b) => a - b);
  const floor = sorted.length ? sorted[Math.floor(sorted.length * .5)] : 0;
  const peak = Math.max(EPS, ...envelope.map(x => Math.max(0, x - floor)));
  return {
    hopSec,
    values: envelope.map(x => clamp((x - floor) / peak, 0, 1))
  };
}

function autocorrelationScore(values, lag) {
  let dot = 0, aa = 0, bb = 0;
  for (let i = 0; i + lag < values.length; i++) {
    const a = values[i], b = values[i + lag];
    dot += a * b; aa += a * a; bb += b * b;
  }
  return aa > EPS && bb > EPS ? dot / Math.sqrt(aa * bb) : 0;
}

export function tempoCandidates(envelope, options = {}) {
  const { values, hopSec } = envelope;
  const minBpm = options.minBpm || 60;
  const maxBpm = options.maxBpm || 200;
  const minLag = Math.max(1, Math.floor(60 / maxBpm / hopSec));
  const maxLag = Math.min(values.length - 2, Math.ceil(60 / minBpm / hopSec));
  const rows = [];
  for (let lag = minLag; lag <= maxLag; lag++) {
    const base = autocorrelationScore(values, lag);
    const half = lag * 2 <= maxLag ? autocorrelationScore(values, lag * 2) : 0;
    const doubleLag = Math.round(lag / 2);
    const harmonic = doubleLag >= minLag ? autocorrelationScore(values, doubleLag) : 0;
    const bpm = 60 / (lag * hopSec);
    const centerPreference = Math.exp(-Math.pow((bpm - 120) / 95, 2));
    const score = base + half * .16 + harmonic * .06 + centerPreference * .025;
    rows.push({ lagFrames: lag, bpm, autocorrelation: base, score });
  }
  rows.sort((a, b) => b.score - a.score || Math.abs(a.bpm - 120) - Math.abs(b.bpm - 120));
  const picked = [];
  for (const row of rows) {
    if (picked.some(x => Math.abs(x.bpm - row.bpm) < 3)) continue;
    picked.push(row);
    if (picked.length >= (options.topK || 5)) break;
  }
  return picked;
}

function sampleStrength(values, position, radius = 1) {
  let best = 0;
  const center = Math.round(position);
  for (let d = -radius; d <= radius; d++) {
    const i = center + d;
    if (i >= 0 && i < values.length) best = Math.max(best, values[i] || 0);
  }
  return best;
}

export function estimateBeatPhase(envelope, periodFrames) {
  const { values, hopSec } = envelope;
  const period = Math.max(1, periodFrames);
  let best = { offset: 0, score: -Infinity };
  for (let offset = 0; offset < period; offset++) {
    let total = 0, count = 0;
    for (let p = offset; p < values.length; p += period) {
      total += sampleStrength(values, p, 1);
      count++;
    }
    const score = count ? total / Math.sqrt(count) : 0;
    if (score > best.score) best = { offset, score };
  }
  const times = [];
  for (let p = best.offset; p < values.length; p += period) times.push(p * hopSec);
  return { offsetFrames: best.offset, score: best.score, times };
}

export function estimateBarPhase(beatTimes, envelope, beatsPerBar = 4) {
  if (!beatTimes.length) return { phase: 0, barTimes: [] };
  const { values, hopSec } = envelope;
  const phaseScores = new Array(beatsPerBar).fill(0);
  const phaseCounts = new Array(beatsPerBar).fill(0);
  for (let i = 0; i < beatTimes.length; i++) {
    const phase = i % beatsPerBar;
    phaseScores[phase] += sampleStrength(values, beatTimes[i] / hopSec, 2);
    phaseCounts[phase]++;
  }
  let phase = 0, best = -Infinity;
  for (let p = 0; p < beatsPerBar; p++) {
    const score = phaseCounts[p] ? phaseScores[p] / phaseCounts[p] : 0;
    if (score > best) { best = score; phase = p; }
  }
  return { phase, barTimes: beatTimes.filter((_, i) => i % beatsPerBar === phase) };
}

export function analyzeBeatGrid(samples, sampleRate, options = {}) {
  const envelope = extractOnsetEnvelope(samples, sampleRate, options);
  const candidates = tempoCandidates(envelope, options);
  if (!candidates.length) {
    return { bpm: null, confidence: 0, beatTimes: [], barTimes: [], boundaries: [], candidates, envelope };
  }
  const best = candidates[0];
  const phase = estimateBeatPhase(envelope, best.lagFrames);
  const bars = estimateBarPhase(phase.times, envelope, options.beatsPerBar || 4);
  const confidence = clamp(best.autocorrelation, 0, 1);
  const duration = samples.length / sampleRate;
  const boundaries = bars.barTimes
    .filter(t => t >= 1 && t <= duration - 1)
    .map(t => ({ t, score: confidence, confidence, source: 'beat', evidence: { beat: confidence } }));
  return {
    bpm: best.bpm,
    confidence,
    beatTimes: phase.times,
    barTimes: bars.barTimes,
    barPhase: bars.phase,
    boundaries,
    candidates,
    envelope
  };
}

export function nearestGridTime(timeSec, times, maxDistanceSec = Infinity) {
  if (!times || !times.length) return null;
  let best = times[0], distance = Math.abs(best - timeSec);
  for (let i = 1; i < times.length; i++) {
    const d = Math.abs(times[i] - timeSec);
    if (d < distance) { distance = d; best = times[i]; }
  }
  return distance <= maxDistanceSec ? { time: best, distance } : null;
}

export function alignCutRange(startSec, endSec, beatAnalysis, mode = 'recommended') {
  if (!beatAnalysis || !beatAnalysis.beatTimes || !beatAnalysis.beatTimes.length || mode === 'exact') {
    return { start: startSec, end: endSec, startKind: 'exact', endKind: 'exact' };
  }
  const beatPeriod = beatAnalysis.bpm ? 60 / beatAnalysis.bpm : .5;
  const barMax = Math.max(.35, beatPeriod * 1.4);
  const beatMax = Math.max(.12, beatPeriod * .42);
  const pick = (time, whichMode) => {
    if (whichMode === 'bar') {
      const hit = nearestGridTime(time, beatAnalysis.barTimes, barMax);
      return hit ? { time: hit.time, kind: 'bar', distance: hit.distance } : { time, kind: 'exact', distance: 0 };
    }
    if (whichMode === 'beat') {
      const hit = nearestGridTime(time, beatAnalysis.beatTimes, beatMax);
      return hit ? { time: hit.time, kind: 'beat', distance: hit.distance } : { time, kind: 'exact', distance: 0 };
    }
    const bar = nearestGridTime(time, beatAnalysis.barTimes, barMax);
    if (bar) return { time: bar.time, kind: 'bar', distance: bar.distance };
    const beat = nearestGridTime(time, beatAnalysis.beatTimes, beatMax);
    if (beat) return { time: beat.time, kind: 'beat', distance: beat.distance };
    return { time, kind: 'exact', distance: 0 };
  };
  const a = pick(startSec, mode), b = pick(endSec, mode);
  if (b.time <= a.time + .02) return { start: startSec, end: endSec, startKind: 'exact', endKind: 'exact' };
  return { start: a.time, end: b.time, startKind: a.kind, endKind: b.kind, startDistance: a.distance, endDistance: b.distance };
}
