function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

export function localRms(samples, sampleRate, timeSec, frameSec = .025) {
  if (!samples || !samples.length || !sampleRate) return 0;
  const center = Math.round(timeSec * sampleRate);
  const half = Math.max(1, Math.round(frameSec * sampleRate * .5));
  const start = Math.max(0, center - half), end = Math.min(samples.length, center + half);
  let sum = 0, count = 0;
  const stride = Math.max(1, Math.floor((end - start) / 300));
  for (let i = start; i < end; i += stride) {
    const x = samples[i] || 0; sum += x * x; count++;
  }
  return Math.sqrt(sum / Math.max(1, count));
}

export function findLowEnergyTime(samples, sampleRate, timeSec, options = {}) {
  if (!samples || !samples.length || !sampleRate) return null;
  const duration = samples.length / sampleRate;
  const radiusSec = options.radiusSec ?? .35;
  const stepSec = options.stepSec ?? .01;
  const frameSec = options.frameSec ?? .025;
  const start = clamp(timeSec - radiusSec, 0, duration);
  const end = clamp(timeSec + radiusSec, 0, duration);
  const rawRms = localRms(samples, sampleRate, timeSec, frameSec);
  let bestTime = timeSec, bestRms = rawRms;
  for (let t = start; t <= end + 1e-9; t += stepSec) {
    const rms = localRms(samples, sampleRate, t, frameSec);
    if (rms < bestRms) { bestRms = rms; bestTime = t; }
  }
  const dropDb = 20 * Math.log10((rawRms + 1e-8) / (bestRms + 1e-8));
  return { time: bestTime, distance: Math.abs(bestTime - timeSec), rms: bestRms, rawRms, dropDb };
}

export function alignLowEnergyRange(startSec, endSec, samples, sampleRate, options = {}) {
  const a = findLowEnergyTime(samples, sampleRate, startSec, options);
  const b = findLowEnergyTime(samples, sampleRate, endSec, options);
  if (!a || !b || b.time <= a.time + .02) {
    return { start: startSec, end: endSec, startKind: 'exact', endKind: 'exact' };
  }
  return {
    start: a.time,
    end: b.time,
    startKind: a.distance > .005 ? 'low-energy' : 'exact',
    endKind: b.distance > .005 ? 'low-energy' : 'exact',
    startDropDb: a.dropDb,
    endDropDb: b.dropDb
  };
}
