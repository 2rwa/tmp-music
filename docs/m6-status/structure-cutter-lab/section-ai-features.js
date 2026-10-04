import FFT from 'fft.js';

export const SECTION_AI_SAMPLE_RATE = 44100;
export const SECTION_AI_FRAME_SIZE = 2048;
export const SECTION_AI_HOP = 441;
export const SECTION_AI_FPS = 100;
export const SECTION_AI_STEM_ORDER = ['bass', 'drums', 'other', 'vocals'];

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

function roundTiesToEven(value) {
  const floor = Math.floor(value);
  const frac = value - floor;
  if (frac < 0.5) return floor;
  if (frac > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1;
}

export function quantizeStemToMadmomMonoInt16(interleavedStereo) {
  let peak = 0;
  for (let i = 0; i < interleavedStereo.length; i++) peak = Math.max(peak, Math.abs(interleavedStereo[i] || 0));
  const scale = Math.max(1.01 * peak, 1);
  const frames = Math.floor(interleavedStereo.length / 2);
  const mono = new Int16Array(frames);
  for (let i = 0; i < frames; i++) {
    const left = clamp((interleavedStereo[i * 2] || 0) / scale, -1, 1);
    const right = clamp((interleavedStereo[i * 2 + 1] || 0) / scale, -1, 1);
    const ql = clamp(roundTiesToEven(left * 32768), -32768, 32767);
    const qr = clamp(roundTiesToEven(right * 32768), -32768, 32767);
    mono[i] = Math.trunc((ql + qr) / 2);
  }
  return mono;
}

function hanning(length) {
  const out = new Float64Array(length);
  for (let i = 0; i < length; i++) out[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (length - 1));
  return out;
}

function logFrequencies(bandsPerOctave = 12, fmin = 30, fmax = 17000, fref = 440) {
  const left = Math.floor(Math.log2(fmin / fref) * bandsPerOctave);
  const right = Math.ceil(Math.log2(fmax / fref) * bandsPerOctave);
  const all = [];
  for (let n = left; n < right; n++) {
    const f = fref * Math.pow(2, n / bandsPerOctave);
    if (f >= fmin && f <= fmax) all.push(f);
  }
  return all;
}

function nearestUniqueBins(frequencies, binFrequencies) {
  const bins = [];
  for (const f of frequencies) {
    let lo = 1, hi = binFrequencies.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (binFrequencies[mid] < f) lo = mid + 1;
      else hi = mid;
    }
    const right = clamp(lo, 1, binFrequencies.length - 1);
    const left = right - 1;
    const index = (f - binFrequencies[left] < binFrequencies[right] - f) ? left : right;
    if (!bins.length || bins[bins.length - 1] !== index) bins.push(index);
  }
  return bins;
}

export function buildMadmomLogFilterbank(sampleRate = SECTION_AI_SAMPLE_RATE, frameSize = SECTION_AI_FRAME_SIZE) {
  const numBins = frameSize >> 1;
  const binFrequencies = new Float64Array(numBins);
  for (let i = 0; i < numBins; i++) binFrequencies[i] = i * sampleRate / frameSize;
  const bins = nearestUniqueBins(logFrequencies(), binFrequencies);
  const filters = [];
  for (let i = 0; i + 2 < bins.length; i++) {
    let [start, center, stop] = [bins[i], bins[i + 1], bins[i + 2]];
    if (stop - start < 2) { center = start; stop = start + 1; }
    const len = stop - start;
    const data = new Float32Array(len);
    const relCenter = center - start;
    for (let j = 0; j < relCenter; j++) data[j] = Math.fround(j / Math.max(1, relCenter));
    const fall = len - relCenter;
    for (let j = 0; j < fall; j++) data[relCenter + j] = Math.fround(1 - j / Math.max(1, fall));
    let sum = Math.fround(0);
    for (let j = 0; j < len; j++) sum = Math.fround(sum + data[j]);
    for (let j = 0; j < len; j++) data[j] = Math.fround(data[j] / sum);
    filters.push({start, data});
  }
  return {numBins, filters};
}

export function computeMadmomLogSpectrogram(monoInt16, sampleRate = SECTION_AI_SAMPLE_RATE) {
  const frameSize = SECTION_AI_FRAME_SIZE;
  const hop = sampleRate / SECTION_AI_FPS;
  const numFrames = Math.ceil(monoInt16.length / hop);
  const fft = new FFT(frameSize);
  const fftOut = fft.createComplexArray();
  const frame = new Float64Array(frameSize);
  const window = hanning(frameSize);
  const {numBins, filters} = buildMadmomLogFilterbank(sampleRate, frameSize);
  const bands = filters.length;
  const output = new Float32Array(numFrames * bands);

  for (let fi = 0; fi < numFrames; fi++) {
    const ref = Math.trunc(fi * hop);
    const start = ref - (frameSize >> 1);
    for (let j = 0; j < frameSize; j++) {
      const si = start + j;
      const sample = si >= 0 && si < monoInt16.length ? monoInt16[si] : 0;
      frame[j] = sample * window[j] / 32767;
    }
    fft.realTransform(fftOut, frame);
    for (let band = 0; band < bands; band++) {
      const filter = filters[band];
      let filtered = 0;
      for (let k = 0; k < filter.data.length; k++) {
        const bin = filter.start + k;
        if (bin < 0 || bin >= numBins) continue;
        const re = fftOut[bin * 2], im = fftOut[bin * 2 + 1];
        const magnitude = Math.fround(Math.sqrt(re * re + im * im));
        filtered += magnitude * filter.data[k];
      }
      output[fi * bands + band] = Math.fround(Math.log10(filtered + 1));
    }
  }
  return {data: output, frames: numFrames, bands};
}

export function computeSectionAISpectrograms(stemsInterleavedStereo, sampleRate = SECTION_AI_SAMPLE_RATE) {
  const chunks = [];
  let frames = null, bands = null;
  for (const name of SECTION_AI_STEM_ORDER) {
    const mono = quantizeStemToMadmomMonoInt16(stemsInterleavedStereo[name]);
    const spec = computeMadmomLogSpectrogram(mono, sampleRate);
    frames ??= spec.frames;
    bands ??= spec.bands;
    if (spec.frames !== frames || spec.bands !== bands) throw new Error('stem spectrogram shape mismatch');
    chunks.push(spec.data);
  }
  const data = new Float32Array(chunks.reduce((n, x) => n + x.length, 0));
  let offset = 0;
  for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.length; }
  return {data, shape: [1, SECTION_AI_STEM_ORDER.length, frames, bands]};
}
