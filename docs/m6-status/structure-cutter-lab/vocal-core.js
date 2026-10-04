const EPS = 1e-12;

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

function percentile(values, q) {
  if (!values.length) return 0;
  const a = values.slice().sort((x, y) => x - y);
  const pos = clamp(q, 0, 1) * (a.length - 1);
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return a[lo] + (a[hi] - a[lo]) * (pos - lo);
}

export function analyzeVocalPhrases(interleaved, sampleRate = 44100, options = {}) {
  if (!(interleaved instanceof Float32Array) || interleaved.length < 4) {
    return { phrases: [], boundaries: [], thresholdDb: null, frames: [] };
  }
  const channels = options.channels || 2;
  const totalFrames = Math.floor(interleaved.length / channels);
  const frameSec = options.frameSec || .10;
  const hopSec = options.hopSec || .05;
  const frame = Math.max(1, Math.round(sampleRate * frameSec));
  const hop = Math.max(1, Math.round(sampleRate * hopSec));
  const rows = [];

  for (let start = 0; start + frame <= totalFrames; start += hop) {
    const end = start + frame;
    const stride = Math.max(1, Math.floor(frame / 300));
    let sum = 0, count = 0;
    for (let i = start; i < end; i += stride) {
      let x = 0;
      for (let ch = 0; ch < channels; ch++) x += interleaved[i * channels + ch] || 0;
      x /= channels;
      sum += x * x; count++;
    }
    const rms = Math.sqrt(sum / Math.max(1, count));
    rows.push({ t: (start + frame * .5) / sampleRate, db: 20 * Math.log10(rms + 1e-8), active: false });
  }
  if (!rows.length) return { phrases: [], boundaries: [], thresholdDb: null, frames: [] };

  const dbs = rows.map(x => x.db);
  const noise = percentile(dbs, .2);
  const peak = percentile(dbs, .95);
  const thresholdDb = Math.max(noise + (options.noiseMarginDb || 10), peak - (options.dynamicRangeDb || 28));
  const onThreshold = thresholdDb + (options.onHysteresisDb || 1.5);
  const offThreshold = thresholdDb - (options.offHysteresisDb || 2.5);

  let on = false;
  for (const row of rows) {
    if (!on && row.db >= onThreshold) on = true;
    else if (on && row.db < offThreshold) on = false;
    row.active = on;
  }

  const fillGapFrames = Math.max(1, Math.round((options.fillGapSec || .22) / hopSec));
  let i = 0;
  while (i < rows.length) {
    if (rows[i].active) { i++; continue; }
    const start = i;
    while (i < rows.length && !rows[i].active) i++;
    const end = i;
    if (start > 0 && end < rows.length && end - start <= fillGapFrames) {
      for (let j = start; j < end; j++) rows[j].active = true;
    }
  }

  const minPhraseSec = options.minPhraseSec || .35;
  const minGapSec = options.minGapSec || .38;
  const raw = [];
  i = 0;
  while (i < rows.length) {
    if (!rows[i].active) { i++; continue; }
    const start = i;
    while (i < rows.length && rows[i].active) i++;
    const end = i;
    const startSec = Math.max(0, rows[start].t - frameSec * .5);
    const endSec = Math.min(totalFrames / sampleRate, rows[end - 1].t + frameSec * .5);
    if (endSec - startSec >= minPhraseSec) raw.push({ start: startSec, end: endSec, startFrame: start, endFrame: end - 1 });
  }

  const phrases = [];
  for (const phrase of raw) {
    const prev = phrases[phrases.length - 1];
    if (prev && phrase.start - prev.end < minGapSec) {
      prev.end = phrase.end;
      prev.endFrame = phrase.endFrame;
    } else phrases.push({ ...phrase });
  }

  const boundaries = [];
  phrases.forEach((phrase, index) => {
    const inside = rows.slice(phrase.startFrame, phrase.endFrame + 1).map(x => x.db);
    const localPeak = inside.length ? Math.max(...inside) : peak;
    const confidence = clamp((localPeak - thresholdDb) / 18, .25, 1);
    phrase.id = index + 1;
    phrase.duration = phrase.end - phrase.start;
    phrase.confidence = confidence;
    boundaries.push({ t: phrase.start, confidence, score: confidence, source: 'vocal', evidence: { vocal: confidence }, edge: 'start', phraseId: phrase.id });
    boundaries.push({ t: phrase.end, confidence, score: confidence, source: 'vocal', evidence: { vocal: confidence }, edge: 'end', phraseId: phrase.id });
  });

  return { phrases, boundaries, thresholdDb, noiseDb: noise, peakDb: peak, frames: rows };
}

export function nearestPhraseBoundary(timeSec, boundaries, maxDistanceSec = .8) {
  if (!boundaries || !boundaries.length) return null;
  let best = boundaries[0], distance = Math.abs(best.t - timeSec);
  for (let i = 1; i < boundaries.length; i++) {
    const d = Math.abs(boundaries[i].t - timeSec);
    if (d < distance) { distance = d; best = boundaries[i]; }
  }
  return distance <= maxDistanceSec ? { time: best.t, distance, edge: best.edge, phraseId: best.phraseId } : null;
}
