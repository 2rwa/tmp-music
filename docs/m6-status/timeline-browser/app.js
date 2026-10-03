(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const canvas = $('#timeline');
  const ctx = canvas.getContext('2d');
  const overviewCanvas = $('#overview-timeline');
  const overviewCtx = overviewCanvas.getContext('2d');
  const overviewPlayhead = $('#overview-playhead');
  const overviewPlayheadLabel = $('#overview-playhead-label');
  const overviewReadout = $('#overview-readout');
  const chronicleLog = $('#chronicle-log');
  const chronicleCount = $('#chronicle-count');
  const followLog = $('#follow-log');
  const jumpCurrentLog = $('#jump-current-log');
  const tooltip = $('#tooltip');
  const fileInput = $('#file-input');
  const chooseFile = $('#choose-file');
  const dropZone = $('#drop-zone');
  const audio = $('#audio');
  const statusEl = $('#status');
  const progressEl = $('#progress');
  const cancelBtn = $('#cancel-analysis');
  const exportBtn = $('#export-json');
  const syntheticBtn = $('#synthetic-test');
  const showLow = $('#show-low');
  const showSegments = $('#show-segments');
  const showMove = $('#show-movement');
  const showReg = $('#show-register');
  const playbackInsights = $('#playback-insights');
  const playbackState = $('#playback-state');
  const playbackTime = $('#playback-time');
  const playbackOverview = $('#playback-overview');
  const insightF0 = $('#insight-f0');
  const insightVoice = $('#insight-voice');
  const insightSpectrum = $('#insight-spectrum');
  const insightPitch = $('#insight-pitch');
  const playheadLine = $('#playhead-line');
  const playheadLabel = $('#playhead-label');
  const css = getComputedStyle(document.documentElement);
  const C = (n) => css.getPropertyValue(n).trim();
  const colors = {
    f0: C('--f0'), f0low: C('--f0low'), cpps: C('--cpps'), hnr: C('--hnr'),
    tilt: C('--tilt'), rms: C('--rms'), vib: C('--vib'), rate: C('--rate'),
    reg: C('--reg'), move: C('--move'), playhead: C('--playhead'),
    quiet: C('--state-quiet'), periodic: C('--state-periodic'), transient: C('--state-transient'), mixed: C('--state-mixed'),
    line: C('--line'), muted: C('--muted'), text: C('--text')
  };

  const state = {
    data: null,
    view: [0, 1],
    hover: null,
    drag: null,
    objectUrl: null,
    abortToken: 0,
    analyzing: false,
    playhead: 0,
    playRaf: 0,
    lastInsightAt: NaN,
    layout: null,
    overviewLayout: null,
    overviewHovering: false,
    chronicleEntries: [],
    currentChronicleId: null,
  };

  const fmt = (v, d = 2) => Number.isFinite(Number(v)) ? Number(v).toFixed(d) : '—';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const sleep = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
  const median = (arr) => percentile(arr, 0.5);
  function percentile(arr, p) {
    const v = arr.filter(Number.isFinite);
    if (!v.length) return NaN;
    const s = [...v].sort((a, b) => a - b);
    const i = (s.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
    return s[lo] + (s[hi] - s[lo]) * (i - lo);
  }
  function nearest(arr, t, key = 't') {
    if (!arr?.length) return null;
    let lo = 0, hi = arr.length - 1;
    while (lo < hi) {
      const m = (lo + hi) >> 1;
      if (arr[m][key] < t) lo = m + 1; else hi = m;
    }
    if (lo && Math.abs(arr[lo - 1][key] - t) < Math.abs(arr[lo][key] - t)) lo--;
    return arr[lo];
  }
  function nextPow2(n) { let p = 1; while (p < n) p <<= 1; return p; }

  function fft(re, im, inverse = false) {
    const n = re.length;
    for (let i = 1, j = 0; i < n; i++) {
      let bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) {
        [re[i], re[j]] = [re[j], re[i]];
        [im[i], im[j]] = [im[j], im[i]];
      }
    }
    for (let len = 2; len <= n; len <<= 1) {
      const ang = 2 * Math.PI / len * (inverse ? 1 : -1);
      const wLenR = Math.cos(ang), wLenI = Math.sin(ang);
      for (let i = 0; i < n; i += len) {
        let wr = 1, wi = 0;
        for (let j = 0; j < len / 2; j++) {
          const uR = re[i + j], uI = im[i + j];
          const k = i + j + len / 2;
          const vR = re[k] * wr - im[k] * wi;
          const vI = re[k] * wi + im[k] * wr;
          re[i + j] = uR + vR; im[i + j] = uI + vI;
          re[k] = uR - vR; im[k] = uI - vI;
          const nwr = wr * wLenR - wi * wLenI;
          wi = wr * wLenI + wi * wLenR; wr = nwr;
        }
      }
    }
    if (inverse) for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
  }

  function linearRegression(xs, ys) {
    const n = Math.min(xs.length, ys.length);
    if (n < 2) return { slope: 0, intercept: ys[0] || 0, r2: 0 };
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; sxx += xs[i] * xs[i]; sxy += xs[i] * ys[i]; }
    const den = n * sxx - sx * sx;
    const slope = Math.abs(den) < 1e-12 ? 0 : (n * sxy - sx * sy) / den;
    const intercept = (sy - slope * sx) / n;
    const mean = sy / n;
    let ssTot = 0, ssRes = 0;
    for (let i = 0; i < n; i++) {
      const pred = intercept + slope * xs[i];
      ssTot += (ys[i] - mean) ** 2; ssRes += (ys[i] - pred) ** 2;
    }
    return { slope, intercept, r2: ssTot > 1e-12 ? clamp(1 - ssRes / ssTot, 0, 1) : 0 };
  }

  function resampleLinear(input, srcRate, dstRate) {
    if (srcRate <= dstRate + 1) return { samples: input, rate: srcRate };
    const ratio = srcRate / dstRate;
    const out = new Float32Array(Math.floor(input.length / ratio));
    for (let i = 0; i < out.length; i++) {
      const pos = i * ratio;
      const i0 = Math.floor(pos), i1 = Math.min(input.length - 1, i0 + 1), a = pos - i0;
      out[i] = input[i0] * (1 - a) + input[i1] * a;
    }
    return { samples: out, rate: dstRate };
  }

  function downmix(buffer) {
    const n = buffer.length;
    const ch = buffer.numberOfChannels;
    const mono = new Float32Array(n);
    for (let c = 0; c < ch; c++) {
      const src = buffer.getChannelData(c);
      for (let i = 0; i < n; i++) mono[i] += src[i] / ch;
    }
    return mono;
  }

  function frameMetrics(samples, sr, start, fftSize, window, work) {
    const { re, im, pow, acR, acI, cepR, cepI } = work;
    let sumSq = 0, mean = 0;
    for (let i = 0; i < fftSize; i++) mean += samples[start + i] || 0;
    mean /= fftSize;
    for (let i = 0; i < fftSize; i++) {
      const x = (samples[start + i] || 0) - mean;
      sumSq += x * x;
      re[i] = x * window[i]; im[i] = 0;
    }
    const rms = Math.sqrt(sumSq / fftSize);
    const rmsDb = 20 * Math.log10(rms + 1e-12);
    fft(re, im, false);
    for (let i = 0; i < fftSize; i++) pow[i] = re[i] * re[i] + im[i] * im[i];

    for (let i = 0; i < fftSize; i++) { acR[i] = pow[i]; acI[i] = 0; }
    fft(acR, acI, true);
    const ac0 = Math.max(1e-12, acR[0]);
    const minLag = Math.max(2, Math.floor(sr / 1200));
    const maxLag = Math.min(Math.floor(sr / 55), Math.floor(fftSize / 2) - 2);
    let chosen = -1, bestVal = Infinity;
    let cumulative = 0;
    const cmnd = work.cmnd;
    cmnd[0] = 1;
    for (let lag = 1; lag <= maxLag; lag++) {
      const d = Math.max(0, 2 * (ac0 - acR[lag]));
      cumulative += d;
      cmnd[lag] = lag === 0 ? 1 : d * lag / Math.max(cumulative, 1e-12);
    }
    for (let lag = minLag + 1; lag < maxLag - 1; lag++) {
      if (cmnd[lag] < 0.18 && cmnd[lag] <= cmnd[lag - 1] && cmnd[lag] <= cmnd[lag + 1]) { chosen = lag; break; }
      if (cmnd[lag] < bestVal) { bestVal = cmnd[lag]; chosen = lag; }
    }
    let refinedLag = chosen;
    if (chosen > minLag && chosen < maxLag) {
      const a = cmnd[chosen - 1], b = cmnd[chosen], c = cmnd[chosen + 1];
      const den = a - 2 * b + c;
      if (Math.abs(den) > 1e-9) refinedLag = chosen + 0.5 * (a - c) / den;
    }
    let confidence = chosen > 0 ? clamp(1 - cmnd[chosen], 0, 1) : 0;
    if (rmsDb < -55) confidence *= clamp((rmsDb + 70) / 15, 0, 1);
    const f0 = confidence > 0.15 && refinedLag > 0 ? sr / refinedLag : NaN;
    const lagIdx = clamp(Math.round(refinedLag || 1), 1, maxLag);
    const corr = clamp(acR[lagIdx] / ac0, 0.0001, 0.9999);
    const hnr = 10 * Math.log10(corr / (1 - corr));

    const half = fftSize >> 1;
    const xs = [], ys = [];
    const minBin = Math.max(1, Math.ceil(200 * fftSize / sr));
    const maxHz = Math.min(5000, sr * 0.45);
    const maxBin = Math.min(half - 1, Math.floor(maxHz * fftSize / sr));
    for (let k = minBin; k <= maxBin; k++) {
      const hz = k * sr / fftSize;
      const db = 10 * Math.log10(pow[k] + 1e-18);
      xs.push(Math.log2(hz / 1000)); ys.push(db);
    }
    const tilt = linearRegression(xs, ys).slope;

    for (let i = 0; i < fftSize; i++) { cepR[i] = 0; cepI[i] = 0; }
    cepR[0] = Math.log(pow[0] + 1e-18);
    for (let k = 1; k < half; k++) {
      const lp = Math.log(pow[k] + 1e-18);
      cepR[k] = lp; cepR[fftSize - k] = lp;
    }
    cepR[half] = Math.log(pow[half] + 1e-18);
    fft(cepR, cepI, true);
    const qLo = Math.max(1, Math.floor(sr * 0.001));
    const qHi = Math.min(half - 2, Math.ceil(sr * 0.020));
    const pLo = Math.max(qLo + 1, Math.floor(sr / 500));
    const pHi = Math.min(qHi - 1, Math.ceil(sr / 60));
    const qx = [], qy = [];
    for (let q = qLo; q <= qHi; q++) { qx.push(q / sr); qy.push(cepR[q]); }
    const base = linearRegression(qx, qy);
    let peakQ = pLo, peak = -Infinity;
    for (let q = pLo; q <= pHi; q++) if (cepR[q] > peak) { peak = cepR[q]; peakQ = q; }
    const baseline = base.intercept + base.slope * (peakQ / sr);
    const cppsLike = Math.max(0, (peak - baseline) * (20 / Math.log(10)));

    return { rmsDb, f0, confidence, hnr, tilt, cppsLike };
  }

  async function localPitchMetrics(frames, token) {
    const radius = Math.round(0.4 / 0.02);
    for (let i = 0; i < frames.length; i++) {
      if (token !== state.abortToken) throw new Error('cancelled');
      if ((i & 63) === 0) { setProgress(0.76 + (frames.length ? i / frames.length : 0) * 0.12); setStatus(`local pitch modulation ${i.toLocaleString()} / ${frames.length.toLocaleString()}`); await sleep(); }
      const lo = Math.max(0, i - radius), hi = Math.min(frames.length - 1, i + radius);
      const pts = [];
      for (let j = lo; j <= hi; j++) if (frames[j].confidence >= 0.5 && Number.isFinite(frames[j].f0)) pts.push(frames[j]);
      if (pts.length < 14) { frames[i].vibExtent = NaN; frames[i].vibStd = NaN; frames[i].vibRate = NaN; continue; }
      const xs = pts.map((p) => p.t);
      const cents = pts.map((p) => 1200 * Math.log2(p.f0));
      const reg = linearRegression(xs, cents);
      const residual = cents.map((v, k) => v - (reg.intercept + reg.slope * xs[k]));
      frames[i].vibExtent = percentile(residual, 0.95) - percentile(residual, 0.05);
      frames[i].vibStd = Math.sqrt(residual.reduce((s, v) => s + v * v, 0) / residual.length);
      if (frames[i].vibStd < 2.5) { frames[i].vibRate = NaN; continue; }
      let bestF = NaN, bestAmp = 0;
      const t0 = xs[0];
      for (let f = 3; f <= 9.0001; f += 0.25) {
        let cs = 0, sn = 0;
        for (let k = 0; k < residual.length; k++) {
          const a = 2 * Math.PI * f * (xs[k] - t0);
          cs += residual[k] * Math.cos(a); sn += residual[k] * Math.sin(a);
        }
        const amp = 2 * Math.hypot(cs, sn) / residual.length;
        if (amp > bestAmp) { bestAmp = amp; bestF = f; }
      }
      frames[i].vibRate = bestAmp >= 2 ? bestF : NaN;
    }
  }

  function detectMovement(frames) {
    const events = [];
    const w = 9, step = 3;
    for (let i = 0; i + w <= frames.length; i += step) {
      const pts = frames.slice(i, i + w).filter((p) => p.confidence >= 0.55 && Number.isFinite(p.f0));
      if (pts.length < 7) continue;
      const xs = pts.map((p) => p.t);
      const ys = pts.map((p) => 1200 * Math.log2(p.f0));
      const reg = linearRegression(xs, ys);
      const change = reg.slope * (xs[xs.length - 1] - xs[0]);
      if (Math.abs(change) < 90 || reg.r2 < 0.72) continue;
      const e = { s: xs[0], e: xs[xs.length - 1], dir: change > 0 ? 'up' : 'down', change, r2: reg.r2 };
      const prev = events[events.length - 1];
      if (prev && prev.dir === e.dir && e.s <= prev.e + 0.12) {
        prev.e = Math.max(prev.e, e.e);
        if (Math.abs(e.change) > Math.abs(prev.change)) { prev.change = e.change; prev.r2 = e.r2; }
      } else events.push(e);
    }
    return events;
  }

  function medianAround(frames, i0, i1, key) {
    const vals = [];
    for (let i = Math.max(0, i0); i <= Math.min(frames.length - 1, i1); i++) {
      if (frames[i].confidence >= 0.5 && Number.isFinite(frames[i][key])) vals.push(frames[i][key]);
    }
    return median(vals);
  }

  function detectRegister(frames) {
    const out = [];
    for (let i = 4; i < frames.length - 4; i++) {
      const fA = medianAround(frames, i - 4, i - 1, 'f0');
      const fB = medianAround(frames, i + 1, i + 4, 'f0');
      if (!Number.isFinite(fA) || !Number.isFinite(fB)) continue;
      const jump = 1200 * Math.log2(fB / fA);
      if (Math.abs(jump) < 250) continue;
      const features = [];
      const checks = [
        ['CPPS-like', 'cppsLike', 1.5], ['HNR', 'hnr', 3.0], ['tilt', 'tilt', 1.5], ['RMS', 'rmsDb', 6.0]
      ];
      for (const [label, key, threshold] of checks) {
        const a = medianAround(frames, i - 4, i - 1, key), b = medianAround(frames, i + 1, i + 4, key);
        if (Number.isFinite(a) && Number.isFinite(b) && Math.abs(b - a) >= threshold) features.push(label);
      }
      if (features.length < 2) continue;
      const t = frames[i].t;
      const prev = out[out.length - 1];
      if (prev && t - prev.t < 0.35) {
        if (Math.abs(jump) > Math.abs(prev.jump)) Object.assign(prev, { t, jump, features });
      } else out.push({ t, jump, features });
    }
    return out;
  }

  function detectStableSegments(frames) {
    const segs = [];
    let start = null;
    for (let i = 0; i <= frames.length; i++) {
      const p = frames[i];
      const ok = p && p.confidence >= 0.55 && Number.isFinite(p.f0) && p.rmsDb > -55 && (!Number.isFinite(p.vibExtent) || p.vibExtent < 120);
      if (ok && start == null) start = i;
      if ((!ok || i === frames.length) && start != null) {
        const end = i - 1;
        if (end - start + 1 >= 12) {
          const slice = frames.slice(start, end + 1);
          segs.push({
            s: slice[0].t, e: slice[slice.length - 1].t,
            f0: median(slice.map((q) => q.f0)), cpps: median(slice.map((q) => q.cppsLike)),
            hnr: median(slice.map((q) => q.hnr)), tilt: median(slice.map((q) => q.tilt)),
            vib: median(slice.map((q) => q.vibExtent))
          });
        }
        start = null;
      }
    }
    return segs;
  }

  async function analyzePcm(samples, sr, meta, token) {
    const targetRate = Math.min(24000, sr);
    setStatus(`resampling / preparing ${fmt(sr, 0)} Hz → ${fmt(targetRate, 0)} Hz`);
    await sleep();
    const resampled = resampleLinear(samples, sr, targetRate);
    samples = resampled.samples; sr = resampled.rate;
    const fftSize = 1024;
    const hop = Math.max(1, Math.round(sr * 0.020));
    const duration = samples.length / sr;
    const frameCount = Math.max(0, Math.floor((samples.length - fftSize) / hop) + 1);
    const window = new Float64Array(fftSize);
    for (let i = 0; i < fftSize; i++) window[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (fftSize - 1));
    const work = {
      re: new Float64Array(fftSize), im: new Float64Array(fftSize), pow: new Float64Array(fftSize),
      acR: new Float64Array(fftSize), acI: new Float64Array(fftSize),
      cepR: new Float64Array(fftSize), cepI: new Float64Array(fftSize), cmnd: new Float64Array(fftSize)
    };
    const frames = [];
    for (let fi = 0; fi < frameCount; fi++) {
      if (token !== state.abortToken) throw new Error('cancelled');
      const start = fi * hop;
      const m = frameMetrics(samples, sr, start, fftSize, window, work);
      frames.push({ t: (start + fftSize / 2) / sr, ...m, vibExtent: NaN, vibStd: NaN, vibRate: NaN });
      if ((fi & 31) === 0) {
        setProgress(frameCount ? fi / frameCount * 0.72 : 0);
        setStatus(`frame analysis ${fi.toLocaleString()} / ${frameCount.toLocaleString()}`);
        await sleep();
      }
    }
    if (token !== state.abortToken) throw new Error('cancelled');
    setStatus('local pitch modulation'); setProgress(0.76); await sleep();
    await localPitchMetrics(frames, token);
    if (token !== state.abortToken) throw new Error('cancelled');
    setStatus('candidate events / stable guides'); setProgress(0.90); await sleep();
    const movement = detectMovement(frames);
    const register = detectRegister(frames);
    const segments = detectStableSegments(frames);
    const confident = frames.filter((q) => q.confidence >= 0.5 && Number.isFinite(q.f0));
    const summary = {
      medianF0: median(confident.map((q) => q.f0)),
      medianHnr: median(confident.map((q) => q.hnr)),
      medianCppsLike: median(confident.map((q) => q.cppsLike)),
      voicedFrames: confident.length,
    };
    setProgress(1);
    return {
      version: 1,
      browserAnalyzer: 'tmp-music timeline-browser',
      name: meta.name || 'synthetic',
      mime: meta.mime || 'audio/synthetic',
      duration_s: duration,
      source_sample_rate_hz: meta.sourceRate || sr,
      analysis_sample_rate_hz: sr,
      frame_hop_ms: hop / sr * 1000,
      fft_size: fftSize,
      frames, movement, register, segments, summary,
    };
  }

  async function analyzeFile(file) {
    const token = ++state.abortToken;
    setAnalyzing(true);
    setProgress(0.01);
    setStatus(`decoding ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`);
    try {
      const bytes = await file.arrayBuffer();
      if (token !== state.abortToken) throw new Error('cancelled');
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      let buffer;
      try { buffer = await ac.decodeAudioData(bytes.slice(0)); }
      finally { await ac.close().catch(() => {}); }
      if (token !== state.abortToken) throw new Error('cancelled');
      const mono = downmix(buffer);
      const d = await analyzePcm(mono, buffer.sampleRate, { name: file.name, mime: file.type, sourceRate: buffer.sampleRate }, token);
      if (token !== state.abortToken) throw new Error('cancelled');
      if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
      state.objectUrl = URL.createObjectURL(file);
      audio.src = state.objectUrl; audio.hidden = false;
      acceptAnalysis(d);
      setStatus(`done · ${d.frames.length.toLocaleString()} frames`);
    } catch (err) {
      if (String(err?.message || err) === 'cancelled') setStatus('cancelled');
      else { setStatus(`error: ${err?.message || err}`); console.error(err); }
    } finally {
      if (token === state.abortToken) setAnalyzing(false);
    }
  }

  function makeSynthetic() {
    const sr = 24000, duration = 2.8, n = Math.floor(sr * duration);
    const samples = new Float32Array(n);
    let phase = 0;
    for (let i = 0; i < n; i++) {
      const t = i / sr;
      const cents = 18 * Math.sin(2 * Math.PI * 5.2 * t);
      const f = 220 * 2 ** (cents / 1200);
      phase += 2 * Math.PI * f / sr;
      const env = Math.min(1, t / 0.08, (duration - t) / 0.08);
      samples[i] = 0.32 * Math.sin(phase) * Math.max(0, env) + 0.015 * Math.sin(2 * phase);
    }
    return { samples, sr, duration };
  }

  async function runSynthetic(selftest = false) {
    const token = ++state.abortToken;
    setAnalyzing(true); setProgress(0.01); setStatus(selftest ? 'selftest: synthetic 220 Hz' : 'synthetic 220 Hz analysis');
    if (selftest) document.documentElement.dataset.selftest = 'running';
    try {
      const s = makeSynthetic();
      const d = await analyzePcm(s.samples, s.sr, { name: 'synthetic-220Hz-vibrato.wav', mime: 'audio/synthetic', sourceRate: s.sr }, token);
      acceptAnalysis(d); audio.hidden = true;
      const ok = d.frames.length > 80 && d.summary.medianF0 > 210 && d.summary.medianF0 < 230 && Number.isFinite(d.summary.medianHnr);
      setStatus(`${selftest ? 'selftest ' : ''}${ok ? 'PASS' : 'WARN'} · median F0 ${fmt(d.summary.medianF0, 1)} Hz`);
      if (selftest) document.documentElement.dataset.selftest = ok ? 'pass' : 'fail';
    } catch (err) {
      setStatus(`error: ${err?.message || err}`);
      if (selftest) document.documentElement.dataset.selftest = 'fail';
    } finally { if (token === state.abortToken) setAnalyzing(false); }
  }

  function acceptAnalysis(d) {
    state.data = d; state.view = [0, d.duration_s]; state.hover = null; state.drag = null;
    state.playhead = 0; state.lastInsightAt = NaN;
    document.documentElement.dataset.playhead = '0.00';
    renderSummary(); renderProvenance(); renderPlaybackInsights(0, false); renderChronicle(); draw(); exportBtn.disabled = false;
  }

  function setAnalyzing(on) {
    state.analyzing = on;
    cancelBtn.disabled = !on; fileInput.disabled = on; chooseFile.disabled = on; syntheticBtn.disabled = on;
    if (!on && progressEl.style.width === '100%') setTimeout(() => { if (!state.analyzing) setProgress(0); }, 900);
  }
  function setStatus(s) { statusEl.textContent = s; }
  function setProgress(p) { progressEl.style.width = `${clamp(p, 0, 1) * 100}%`; }

  function renderSummary() {
    const d = state.data, s = d.summary;
    $('#summary').innerHTML = `
      <div class="stat"><b title="${escapeHtml(d.name)}">${escapeHtml(d.name)}</b><small>file</small></div>
      <div class="stat"><b>${fmt(d.duration_s, 1)} s</b><small>duration</small></div>
      <div class="stat"><b>${d.frames.length.toLocaleString()}</b><small>analysis frames</small></div>
      <div class="stat"><b>${fmt(s.medianF0, 1)} Hz</b><small>median F0</small></div>
      <div class="stat"><b>${fmt(s.medianHnr, 1)} dB</b><small>median HNR</small></div>
      <div class="stat"><b>${fmt(d.analysis_sample_rate_hz / 1000, 1)} kHz</b><small>analysis rate</small></div>`;
  }
  function renderProvenance() {
    const d = state.data;
    $('#provenance').innerHTML = `browser-local · source <code>${fmt(d.source_sample_rate_hz, 0)} Hz</code> · analysis <code>${fmt(d.analysis_sample_rate_hz, 0)} Hz</code> · FFT <code>${d.fft_size}</code> · hop <code>${fmt(d.frame_hop_ms, 1)} ms</code> · no upload`;
  }
  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  function currentSoundSummary(q) {
    if (!q) return 'この位置には解析フレームがありません。';
    const quiet = q.rmsDb < -55;
    const attackLike = q.rmsDb > -38 && q.confidence < .45 && q.hnr < 4;
    const periodic = Number.isFinite(q.f0) && q.confidence >= .6 && q.hnr >= 5;
    if (quiet) return 'かなり静かな区間です。RMSが低いため、F0やHNRなど他の値はノイズ床の影響を受けやすくなります。';
    if (attackLike) return '音量はある一方で周期性が弱い区間です。ドラム／パーカッションのアタック、子音、ノイズ成分などで値が動いている可能性があります。';
    if (periodic) return '明確な周期音が優勢な区間です。声の母音や歌声のほか、ベース・弦・管など持続する楽器音でも同じ傾向になります。';
    if (q.confidence < .45) return 'F0の周期検出が不安定な区間です。無声音、複雑な和音、ノイズ、打撃音、音の立ち上がりなどが候補です。';
    return '周期成分と非周期成分が混ざった区間です。単一の値では音源を断定せず、RMS・HNR・spectral tiltを合わせて見ます。';
  }

  function renderPlaybackInsights(t, playing = false) {
    if (!state.data) return;
    const q = nearest(state.data.frames, t);
    playbackInsights.hidden = audio.hidden;
    playbackState.textContent = playing ? '再生中' : (audio.ended ? '再生終了' : '一時停止 / 停止');
    playbackTime.textContent = `${fmt(t, 2)} s`;
    playbackOverview.textContent = currentSoundSummary(q);
    if (!q) return;

    let f0Text;
    if (q.rmsDb < -55) f0Text = '静かなためF0は信用しにくい状態です。';
    else if (Number.isFinite(q.f0) && q.confidence >= .6) f0Text = '周期がはっきりしています。母音・歌声・持続楽器で安定しやすい一方、音程のある打楽器でも反応します。';
    else if (q.confidence < .45) f0Text = '周期が曖昧です。子音、ノイズ、ドラムやパーカッションのアタックではF0が消えたり飛んだりしやすくなります。';
    else f0Text = '周期は拾えていますが確信度は中程度です。複数音やアタック直後では値が揺れます。';
    insightF0.innerHTML = `<h3>F0 / confidence</h3><div class="metric-value">F0 ${fmt(q.f0,1)} Hz · conf ${fmt(q.confidence,2)}</div><p>F0は周期音の高さ、confidenceは周期検出の確からしさ。 ${f0Text}</p>`;

    let voiceText;
    if (q.hnr >= 12 && q.cppsLike >= 8) voiceText = '周期・調波構造がかなり明瞭です。母音や持続音で上がりやすい状態です。';
    else if (q.hnr < 3 || q.cppsLike < 3) voiceText = '非周期成分が強めです。息、摩擦音、ノイズ、打撃音では低くなりやすい状態です。';
    else voiceText = '周期成分はありますが、ノイズ成分や複数音も混ざっている可能性があります。';
    insightVoice.innerHTML = `<h3>CPPS-like / HNR</h3><div class="metric-value">CPPS-like ${fmt(q.cppsLike,1)} dB · HNR ${fmt(q.hnr,1)} dB</div><p>高いほど周期構造が目立つ方向。 ${voiceText} CPPS-likeはPraat CPPSそのものではありません。</p>`;

    const levelText = q.rmsDb < -55 ? 'ほぼ静音寄り' : q.rmsDb < -38 ? '小さめ' : q.rmsDb < -20 ? '中程度' : '大きめ';
    let tiltText;
    if (q.tilt > -3) tiltText = '高域が比較的強く、シンバル／ハイハット、歯擦音、鋭いアタックで動きやすい傾向です。';
    else if (q.tilt < -9) tiltText = '高域の減衰が大きく、低域・中域寄りの柔らかい音色になりやすい傾向です。';
    else tiltText = '高域の減り方は中程度です。';
    insightSpectrum.innerHTML = `<h3>RMS / spectral tilt</h3><div class="metric-value">RMS ${fmt(q.rmsDb,1)} dBFS · tilt ${fmt(q.tilt,1)} dB/oct</div><p>RMSは現在の音量で「${levelText}」。ドラム等のアタックで瞬間的に跳ねます。spectral tiltは高域の減り方で、${tiltText}</p>`;

    let pitchText = 'F0が安定していないため、この区間のピッチ揺れは解釈を控えます。';
    if (q.confidence >= .55 && Number.isFinite(q.vibExtent)) {
      const extent = q.vibExtent < 30 ? '小さい' : q.vibExtent < 100 ? '中程度' : '大きい';
      pitchText = `短時間のピッチ揺れ幅は${extent}状態です。`;
      if (Number.isFinite(q.vibRate)) pitchText += ` ${fmt(q.vibRate,2)} Hz付近の周期変動がありますが、ビブラートとは断定しません。`;
      else pitchText += ' 明瞭な3–9 Hz周期は検出していません。';
    }
    const mov = state.data.movement.find((e) => t >= e.s && t <= e.e);
    const reg = state.data.register.find((e) => Math.abs(e.t - t) <= .25);
    if (mov) pitchText += ` pitch movement候補（${mov.dir}, ${fmt(mov.change,0)} cent）内です。`;
    if (reg) pitchText += ` register変化候補にも近接しています。`;
    insightPitch.innerHTML = `<h3>Local pitch modulation</h3><div class="metric-value">extent ${fmt(q.vibExtent,1)} cent · rate ${fmt(q.vibRate,2)} Hz</div><p>${pitchText}</p>`;
  }

  const SOUND_STATES = {
    quiet: { label: '静音', colorKey: 'quiet' },
    periodic: { label: '周期音', colorKey: 'periodic' },
    transient: { label: '打撃・ノイズ寄り', colorKey: 'transient' },
    mixed: { label: '混合', colorKey: 'mixed' },
  };

  function classifyFrame(q) {
    if (!q || q.rmsDb < -55) return 'quiet';
    if ((q.rmsDb > -38 && q.confidence < .45 && q.hnr < 4) || (q.tilt > -3 && q.confidence < .4 && q.rmsDb > -48)) return 'transient';
    if (Number.isFinite(q.f0) && q.confidence >= .6 && q.hnr >= 5) return 'periodic';
    return 'mixed';
  }

  function smoothedFrameKinds(frames) {
    const raw = frames.map(classifyFrame);
    if (raw.length < 5) return raw;
    const order = ['quiet','periodic','transient','mixed'];
    return raw.map((kind, i) => {
      const counts = new Map(order.map((k) => [k, 0]));
      for (let j = Math.max(0, i - 2); j <= Math.min(raw.length - 1, i + 2); j++) counts.set(raw[j], counts.get(raw[j]) + 1);
      let best = kind, bestN = -1;
      for (const k of order) {
        const n = counts.get(k);
        if (n > bestN || (n === bestN && k === kind)) { best = k; bestN = n; }
      }
      return best;
    });
  }

  function stateDescription(kind) {
    if (kind === 'quiet') return '静かな区間。RMSが低く、F0やHNRはノイズ床の影響を受けやすい。';
    if (kind === 'periodic') return '周期構造が優勢。母音・歌声・ベース・弦・管など持続する周期音で現れやすい。';
    if (kind === 'transient') return '音量はあるが周期性が弱い。ドラム／パーカッションのアタック、子音、ノイズなどの影響候補。';
    return '周期成分と非周期成分が混在。単独の指標では音源を特定しにくい状態。';
  }

  function buildChronicleEntries() {
    if (!state.data?.frames?.length) return [];
    const frames = state.data.frames, kinds = smoothedFrameKinds(frames), entries = [];
    let start = 0;
    for (let i = 1; i <= frames.length; i++) {
      if (i < frames.length && kinds[i] === kinds[start]) continue;
      const end = i - 1, slice = frames.slice(start, i), kind = kinds[start];
      const s = Math.max(0, frames[start].t - state.data.frame_hop_ms / 2000);
      const e = Math.min(state.data.duration_s, frames[end].t + state.data.frame_hop_ms / 2000);
      const f0s = slice.filter((q) => q.confidence >= .5 && Number.isFinite(q.f0)).map((q) => q.f0);
      entries.push({
        id: `state-${start}-${end}`, type:'state', kind, s, e, frameStart:start, frameEnd:end,
        title:SOUND_STATES[kind].label,
        text:stateDescription(kind),
        metrics:{
          rms:median(slice.map((q)=>q.rmsDb)),
          f0:median(f0s),
          conf:median(slice.map((q)=>q.confidence)),
          hnr:median(slice.map((q)=>q.hnr)),
          tilt:median(slice.map((q)=>q.tilt)),
        }
      });
      start = i;
    }
    for (let i = 0; i < state.data.movement.length; i++) {
      const m = state.data.movement[i];
      entries.push({
        id:`move-${i}`, type:'movement', kind:'movement', s:m.s, e:m.e,
        title:m.dir === 'up' ? 'ピッチ上昇' : 'ピッチ下降',
        text:`pitch movement候補。区間内で${m.dir === 'up' ? '上方向' : '下方向'}へ連続的な変化。`,
        metrics:{change:m.change,r2:m.r2}
      });
    }
    for (let i = 0; i < state.data.register.length; i++) {
      const r = state.data.register[i];
      entries.push({
        id:`register-${i}`, type:'register', kind:'register', s:r.t, e:r.t,
        title:'register変化候補',
        text:`F0のジャンプに加えて ${r.features.join(' / ')} が同時に変化。`,
        metrics:{jump:r.jump}
      });
    }
    entries.sort((a,b)=>a.s-b.s || (a.type==='state'?-1:1));
    return entries;
  }

  function chronicleMetricText(entry) {
    if (entry.type === 'state') {
      const m = entry.metrics;
      return `RMS ${fmt(m.rms,1)} dBFS · F0 ${fmt(m.f0,1)} Hz · conf ${fmt(m.conf,2)} · HNR ${fmt(m.hnr,1)} dB · tilt ${fmt(m.tilt,1)} dB/oct`;
    }
    if (entry.type === 'movement') return `${fmt(entry.metrics.change,0)} cent · r² ${fmt(entry.metrics.r2,2)}`;
    return `F0 jump ${fmt(entry.metrics.jump,0)} cent`;
  }

  function chronicleTimeText(entry) {
    const a = fmt(entry.s,2);
    if (entry.e - entry.s < .03) return `${a} s`;
    return `${a}–${fmt(entry.e,2)} s`;
  }

  function renderChronicle() {
    state.chronicleEntries = buildChronicleEntries();
    const entries = state.chronicleEntries;
    chronicleCount.textContent = `${entries.length.toLocaleString()} logs`;
    jumpCurrentLog.disabled = !entries.length;
    document.documentElement.dataset.chronicleEntries = String(entries.length);
    if (!entries.length) {
      chronicleLog.innerHTML = '<div class="chronicle-empty">解析ログはありません。</div>';
      return;
    }
    chronicleLog.innerHTML = entries.map((entry) => {
      const frameDetails = entry.type === 'state'
        ? `<details data-frame-start="${entry.frameStart}" data-frame-end="${entry.frameEnd}"><summary>生フレーム ${(entry.frameEnd-entry.frameStart+1).toLocaleString()}件</summary><div class="raw-frame-placeholder">開くと20ms解析値を読み込みます。</div></details>`
        : '';
      const cls = entry.type === 'state' ? `state-${entry.kind}` : `type-${entry.type}`;
      return `<article class="chronicle-item ${cls}" data-log-id="${entry.id}" data-s="${entry.s}" data-e="${entry.e}">
        <button class="chronicle-main" type="button" data-seek="${entry.s}">
          <span class="chronicle-time">${chronicleTimeText(entry)}</span>
          <span>
            <span class="chronicle-type">${entry.type === 'state' ? 'STATE' : entry.type.toUpperCase()}</span>
            <div class="chronicle-title">${escapeHtml(entry.title)}</div>
            <div class="chronicle-text">${escapeHtml(entry.text)}</div>
            <div class="chronicle-metrics">${escapeHtml(chronicleMetricText(entry))}</div>
          </span>
        </button>
        ${frameDetails}
      </article>`;
    }).join('');
    syncChronicle(state.playhead, false);
  }

  function rawFramesHtml(start, end) {
    const rows = [];
    for (let i = start; i <= end; i++) {
      const q = state.data.frames[i], kind = classifyFrame(q);
      rows.push(`<tr><td>${fmt(q.t,2)}s</td><td><span class="raw-state">${SOUND_STATES[kind].label}</span></td><td>${fmt(q.rmsDb,1)}</td><td>${fmt(q.f0,1)}</td><td>${fmt(q.confidence,2)}</td><td>${fmt(q.hnr,1)}</td><td>${fmt(q.cppsLike,1)}</td><td>${fmt(q.tilt,1)}</td><td>${fmt(q.vibExtent,1)}</td><td>${fmt(q.vibRate,2)}</td></tr>`);
    }
    return `<div class="raw-frame-wrap"><table class="raw-frame-table"><thead><tr><th>time</th><th>state</th><th>RMS</th><th>F0</th><th>conf</th><th>HNR</th><th>CPPS-like</th><th>tilt</th><th>extent</th><th>rate</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  }

  function syncChronicle(t, forceScroll = false) {
    if (!state.chronicleEntries.length) return;
    const active = state.chronicleEntries.filter((e) => {
      if (e.type === 'register') return Math.abs(e.s - t) <= .18;
      return t >= e.s && t <= e.e;
    });
    const primary = active.find((e)=>e.type==='state') || active[0] ||
      state.chronicleEntries.reduce((best,e)=>!best || Math.abs(e.s-t)<Math.abs(best.s-t)?e:best,null);
    const currentId = primary?.id || null;
    document.documentElement.dataset.chronicleCurrent = currentId || '';
    if (typeof chronicleLog.querySelectorAll === 'function') {
      for (const el of chronicleLog.querySelectorAll('.chronicle-item.is-current')) el.classList.remove('is-current');
      for (const e of active.length ? active : (primary ? [primary] : [])) {
        const el = chronicleLog.querySelector(`[data-log-id="${e.id}"]`);
        if (el) el.classList.add('is-current');
      }
    }
    const changed = currentId !== state.currentChronicleId;
    state.currentChronicleId = currentId;
    if ((forceScroll || (changed && followLog.checked)) && currentId && typeof chronicleLog.querySelector === 'function') {
      const el = chronicleLog.querySelector(`[data-log-id="${currentId}"]`);
      if (el?.scrollIntoView) el.scrollIntoView({block:'center',behavior:forceScroll?'smooth':'auto'});
    }
  }

  function overviewLayout() {
    const dpr = Math.max(1, devicePixelRatio || 1), r = overviewCanvas.getBoundingClientRect();
    const w = Math.max(320, Math.floor(r.width));
    const cssHeight = parseFloat(getComputedStyle(overviewCanvas).height);
    const h = Number.isFinite(cssHeight) && cssHeight > 0 ? Math.floor(cssHeight) : 188;
    if (overviewCanvas.width !== Math.floor(w * dpr) || overviewCanvas.height !== Math.floor(h * dpr)) {
      overviewCanvas.width = Math.floor(w * dpr); overviewCanvas.height = Math.floor(h * dpr);
    }
    overviewCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const left = w < 560 ? 46 : 58, right = 16, plotW = Math.max(1, w - left - right);
    return {
      w, h, left, right, plotW,
      level: { x:left, y:23, w:plotW, h:70 },
      state: { x:left, y:108, w:plotW, h:22 },
      events: { x:left, y:145, w:plotW, h:18 },
    };
  }

  function overviewX(t, L) {
    return L.left + clamp(t / Math.max(state.data?.duration_s || 1, 1e-6), 0, 1) * L.plotW;
  }

  function drawOverviewTimeline() {
    const L = overviewLayout(); state.overviewLayout = L;
    overviewCtx.clearRect(0, 0, L.w, L.h);
    overviewCtx.fillStyle = '#08111e'; overviewCtx.fillRect(0, 0, L.w, L.h);
    if (!state.data) {
      overviewCtx.fillStyle = colors.muted; overviewCtx.font = '14px system-ui'; overviewCtx.textAlign = 'center';
      overviewCtx.fillText('解析後に全尺タイムラインを表示します', L.w / 2, 82); overviewCtx.textAlign = 'start';
      overviewPlayhead.hidden = true;
      overviewCanvas.dataset.rendered = 'empty';
      return;
    }

    const d = state.data, duration = Math.max(d.duration_s, 0.001);
    overviewCtx.font = '10px system-ui'; overviewCtx.textAlign = 'right'; overviewCtx.fillStyle = colors.muted;
    overviewCtx.fillText('LEVEL', L.left - 7, L.level.y + 13);
    overviewCtx.fillText('STATE', L.left - 7, L.state.y + 14);
    overviewCtx.fillText('EVENT', L.left - 7, L.events.y + 13);
    overviewCtx.textAlign = 'start';

    // Time grid shared by all three lanes.
    const rough = duration / 7, steps = [.5,1,2,5,10,20,30,60,120,300,600,1200];
    const step = steps.find((s) => s >= rough) || Math.ceil(rough / 600) * 600;
    overviewCtx.strokeStyle = 'rgba(70,93,126,.26)'; overviewCtx.fillStyle = colors.muted; overviewCtx.font = '9px system-ui'; overviewCtx.textAlign = 'center';
    for (let t = 0; t <= duration + .001; t += step) {
      const x = overviewX(t, L);
      overviewCtx.beginPath(); overviewCtx.moveTo(x, L.level.y); overviewCtx.lineTo(x, L.events.y + L.events.h); overviewCtx.stroke();
      overviewCtx.fillText(t < 10 ? `${t.toFixed(1)}s` : `${Math.round(t)}s`, x, L.h - 7);
    }
    overviewCtx.textAlign = 'start';

    // RMS envelope: the more energetic the frame, the higher the line.
    overviewCtx.strokeStyle = colors.rms; overviewCtx.lineWidth = 1.2; overviewCtx.beginPath();
    let started = false;
    for (const q of d.frames) {
      const x = overviewX(q.t, L), norm = clamp((q.rmsDb + 80) / 80, 0, 1);
      const y = L.level.y + L.level.h - norm * L.level.h;
      if (!started) { overviewCtx.moveTo(x, y); started = true; } else overviewCtx.lineTo(x, y);
    }
    overviewCtx.stroke();
    overviewCtx.strokeStyle = colors.line;
    overviewCtx.strokeRect(L.level.x + .5, L.level.y + .5, L.level.w - 1, L.level.h - 1);

    // State lane, frame-by-frame. Narrow frames naturally coalesce visually.
    const counts = {quiet:0, periodic:0, transient:0, mixed:0};
    for (let i = 0; i < d.frames.length; i++) {
      const q = d.frames[i], kind = classifyFrame(q); counts[kind]++;
      const nextT = i + 1 < d.frames.length ? d.frames[i + 1].t : Math.min(duration, q.t + d.frame_hop_ms / 1000);
      const x1 = overviewX(Math.max(0, q.t - d.frame_hop_ms / 2000), L);
      const x2 = overviewX(nextT, L);
      overviewCtx.fillStyle = colors[SOUND_STATES[kind].colorKey];
      overviewCtx.fillRect(x1, L.state.y, Math.max(1, x2 - x1), L.state.h);
    }
    overviewCtx.strokeStyle = colors.line;
    overviewCtx.strokeRect(L.state.x + .5, L.state.y + .5, L.state.w - 1, L.state.h - 1);

    // Event lane: movement spans + register markers.
    overviewCtx.fillStyle = 'rgba(255,166,77,.62)';
    for (const e of d.movement) {
      const x1 = overviewX(e.s, L), x2 = overviewX(e.e, L);
      overviewCtx.fillRect(x1, L.events.y + 3, Math.max(1, x2 - x1), 6);
    }
    overviewCtx.strokeStyle = colors.reg; overviewCtx.lineWidth = 1.5;
    for (const r of d.register) {
      const x = overviewX(r.t, L); overviewCtx.beginPath(); overviewCtx.moveTo(x, L.events.y); overviewCtx.lineTo(x, L.events.y + L.events.h); overviewCtx.stroke();
    }
    overviewCtx.strokeStyle = colors.line;
    overviewCtx.strokeRect(L.events.x + .5, L.events.y + .5, L.events.w - 1, L.events.h - 1);

    // Current detailed-chart viewport.
    const vx1 = overviewX(state.view[0], L), vx2 = overviewX(state.view[1], L);
    overviewCtx.fillStyle = 'rgba(121,194,255,.065)';
    overviewCtx.fillRect(vx1, L.level.y, Math.max(1, vx2 - vx1), L.events.y + L.events.h - L.level.y);
    overviewCtx.strokeStyle = colors.f0; overviewCtx.lineWidth = 1;
    overviewCtx.strokeRect(vx1 + .5, L.level.y + .5, Math.max(1, vx2 - vx1) - 1, L.events.y + L.events.h - L.level.y - 1);

    overviewCanvas.dataset.rendered = 'ready';
    overviewCanvas.dataset.stateCounts = JSON.stringify(counts);
    document.documentElement.dataset.overviewTimeline = 'ready';
    updateOverviewPlayhead();
  }

  function overviewTimeAtEvent(ev) {
    if (!state.data || !state.overviewLayout) return null;
    const L = state.overviewLayout, r = overviewCanvas.getBoundingClientRect();
    const x = clamp(ev.clientX - r.left, L.left, L.left + L.plotW);
    return (x - L.left) / L.plotW * state.data.duration_s;
  }

  function renderOverviewReadout(t) {
    if (!state.data) return;
    const q = nearest(state.data.frames, t), kind = classifyFrame(q);
    const label = SOUND_STATES[kind].label;
    const mov = state.data.movement.find((e) => t >= e.s && t <= e.e);
    const reg = state.data.register.find((e) => Math.abs(e.t - t) <= .25);
    let s = `${fmt(t,2)} s · ${label}`;
    if (q) s += ` · RMS ${fmt(q.rmsDb,1)} dBFS · F0 ${fmt(q.f0,1)} Hz · conf ${fmt(q.confidence,2)}`;
    if (mov) s += ` · pitch ${mov.dir} ${fmt(mov.change,0)} cent`;
    if (reg) s += ' · register候補';
    overviewReadout.textContent = s;
  }

  function updateOverviewPlayhead() {
    if (!state.data || !state.overviewLayout || !Number.isFinite(state.playhead)) { overviewPlayhead.hidden = true; return; }
    const L = state.overviewLayout, x = overviewX(state.playhead, L);
    const canvasRect = overviewCanvas.getBoundingClientRect(), wrapRect = overviewCanvas.parentElement.getBoundingClientRect();
    overviewPlayhead.hidden = false;
    overviewPlayhead.style.left = `${canvasRect.left - wrapRect.left + x}px`;
    overviewPlayhead.style.top = `${canvasRect.top - wrapRect.top + L.level.y}px`;
    overviewPlayhead.style.height = `${L.events.y + L.events.h - L.level.y}px`;
    overviewPlayheadLabel.textContent = `${fmt(state.playhead,2)} s`;
    const flip = x > L.left + L.plotW - 82;
    overviewPlayheadLabel.style.left = flip ? '-6px' : '6px';
    overviewPlayheadLabel.style.transform = flip ? 'translateX(-100%)' : 'none';
  }

  function layout() {
    const dpr = Math.max(1, devicePixelRatio || 1), r = canvas.getBoundingClientRect();
    const w = Math.max(320, Math.floor(r.width)), h = Math.floor(parseFloat(getComputedStyle(canvas).height));
    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) { canvas.width = Math.floor(w * dpr); canvas.height = Math.floor(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const L = w < 560 ? 48 : 62, R = 48, top = 32, gap = 24;
    const f0 = { x: L, y: top, w: w - L - R, h: 210 };
    const voice = { x: L, y: f0.y + f0.h + gap, w: f0.w, h: 155 };
    const spectral = { x: L, y: voice.y + voice.h + gap, w: f0.w, h: 145 };
    const vib = { x: L, y: spectral.y + spectral.h + gap, w: f0.w, h: 130 };
    return { w, h, f0, voice, spectral, vib };
  }
  const mapX = (t, p) => p.x + (t - state.view[0]) / (state.view[1] - state.view[0]) * p.w;
  const timeAtX = (x, p) => state.view[0] + (x - p.x) / p.w * (state.view[1] - state.view[0]);
  const visible = (a, b) => b >= state.view[0] && a <= state.view[1];
  function base(p, title, sub) {
    ctx.fillStyle = '#091321'; ctx.fillRect(p.x, p.y, p.w, p.h);
    ctx.strokeStyle = colors.line; ctx.strokeRect(p.x + .5, p.y + .5, p.w - 1, p.h - 1);
    ctx.fillStyle = colors.text; ctx.font = '600 12px system-ui'; ctx.fillText(title, 8, p.y + 15);
    ctx.fillStyle = colors.muted; ctx.font = '10px system-ui'; ctx.fillText(sub, 8, p.y + 29);
  }
  function overlays(p) {
    if (!state.data) return;
    if (showMove.checked) {
      ctx.fillStyle = colors.move;
      for (const e of state.data.movement) if (visible(e.s, e.e)) ctx.fillRect(mapX(e.s, p), p.y, Math.max(1, mapX(e.e, p) - mapX(e.s, p)), p.h);
    }
    if (showReg.checked) {
      ctx.strokeStyle = colors.reg; ctx.lineWidth = 1.3;
      for (const r of state.data.register) if (r.t >= state.view[0] && r.t <= state.view[1]) {
        const x = mapX(r.t, p); ctx.beginPath(); ctx.moveTo(x, p.y); ctx.lineTo(x, p.y + p.h); ctx.stroke();
      }
    }
  }
  function timeGrid(p) {
    const [a, b] = state.view, rough = (b - a) / 8, steps = [.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600];
    const step = steps.find((s) => s >= rough) || 1200, first = Math.ceil(a / step) * step;
    ctx.font = '10px system-ui'; ctx.textAlign = 'center'; ctx.fillStyle = colors.muted; ctx.strokeStyle = 'rgba(70,93,126,.28)';
    for (let t = first; t <= b + .001; t += step) {
      const x = mapX(t, p); ctx.beginPath(); ctx.moveTo(x, p.y); ctx.lineTo(x, p.y + p.h); ctx.stroke();
      ctx.fillText(t < 10 ? `${t.toFixed(1)}s` : `${Math.round(t)}s`, x, p.y + p.h + 15);
    }
    ctx.textAlign = 'start';
  }
  function yGrid(p, lo, hi, step, right = false, suffix = '') {
    const yy = (v) => p.y + p.h - (v - lo) / (hi - lo) * p.h;
    ctx.font = '10px system-ui'; ctx.fillStyle = colors.muted; ctx.strokeStyle = 'rgba(70,93,126,.24)'; ctx.textAlign = right ? 'left' : 'right';
    for (let v = Math.ceil(lo / step) * step; v <= hi + .001; v += step) {
      const y = yy(v); ctx.beginPath(); ctx.moveTo(p.x, y); ctx.lineTo(p.x + p.w, y); ctx.stroke();
      ctx.fillText(`${v}${suffix}`, right ? p.x + p.w + 5 : p.x - 6, y + 3);
    }
    ctx.textAlign = 'start'; return yy;
  }
  function lineSeries(rows, p, key, yy, color, width = 1.3, predicate = null) {
    ctx.strokeStyle = color; ctx.lineWidth = width; let started = false, last = -99; ctx.beginPath();
    for (const q of rows) {
      const t = q.t, v = q[key];
      if (!Number.isFinite(t) || !Number.isFinite(v) || t < state.view[0] || t > state.view[1] || (predicate && !predicate(q))) { started = false; continue; }
      const x = mapX(t, p), y = yy(v);
      if (!started || t - last > .08) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      last = t;
    }
    ctx.stroke();
  }
  function segmentGuides(p, key, yy, color) {
    if (!showSegments.checked) return;
    ctx.strokeStyle = color; ctx.globalAlpha = .30; ctx.lineWidth = 3;
    for (const s of state.data.segments) if (visible(s.s, s.e) && Number.isFinite(s[key])) {
      const x1 = mapX(s.s, p), x2 = mapX(s.e, p), y = yy(s[key]);
      ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(Math.max(x1 + 1, x2), y); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function drawF0(p) {
    base(p, 'F0', 'browser selected-F0 · log-frequency axis'); overlays(p);
    const rows = state.data.frames, pts = rows.filter((q) => q.t >= state.view[0] && q.t <= state.view[1] && Number.isFinite(q.f0));
    const vals = pts.filter((q) => q.confidence >= .5).map((q) => q.f0);
    const fallback = pts.map((q) => q.f0);
    let lo = percentile(vals.length ? vals : fallback, .02), hi = percentile(vals.length ? vals : fallback, .98);
    if (!lo || !hi || lo === hi) { lo = 80; hi = 1000; }
    lo *= .88; hi *= 1.14;
    const yy = (v) => p.y + p.h - (Math.log2(v) - Math.log2(lo)) / (Math.log2(hi) - Math.log2(lo)) * p.h;
    ctx.font = '10px system-ui'; ctx.fillStyle = colors.muted; ctx.strokeStyle = 'rgba(70,93,126,.24)'; ctx.textAlign = 'right';
    for (const v of [55, 82.4, 110, 165, 220, 330, 440, 660, 880, 1320].filter((v) => v > lo && v < hi)) {
      const y = yy(v); ctx.beginPath(); ctx.moveTo(p.x, y); ctx.lineTo(p.x + p.w, y); ctx.stroke(); ctx.fillText(`${Math.round(v)}`, p.x - 6, y + 3);
    }
    ctx.textAlign = 'start';
    lineSeries(rows, p, 'f0', yy, colors.f0low, 1, (q) => showLow.checked && q.confidence < .5);
    lineSeries(rows, p, 'f0', yy, colors.f0, 1.35, (q) => q.confidence >= .5);
    segmentGuides(p, 'f0', yy, colors.f0);
  }
  function drawVoice(p) {
    base(p, 'Browser voice metrics', 'cepstral prominence proxy + autocorrelation HNR'); overlays(p);
    const rows = state.data.frames, vals = [];
    for (const q of rows) if (q.t >= state.view[0] && q.t <= state.view[1]) { if (Number.isFinite(q.cppsLike)) vals.push(q.cppsLike); if (Number.isFinite(q.hnr)) vals.push(q.hnr); }
    let vmin = 0, vmax = 25; for (const v of vals) { if (v < vmin) vmin = v; if (v > vmax) vmax = v; }
    let lo = Math.floor((vmin - 2) / 5) * 5, hi = Math.ceil((vmax + 2) / 5) * 5;
    if (hi - lo < 20) hi = lo + 20;
    const yy = yGrid(p, lo, hi, 5);
    segmentGuides(p, 'cpps', yy, colors.cpps); segmentGuides(p, 'hnr', yy, colors.hnr);
    lineSeries(rows, p, 'cppsLike', yy, colors.cpps, 1.35); lineSeries(rows, p, 'hnr', yy, colors.hnr, 1.25);
  }
  function drawSpectral(p) {
    base(p, 'Spectrum / level', 'spectral tilt (left) + RMS dBFS (right)'); overlays(p);
    const tiltY = yGrid(p, -18, 6, 6);
    const rmsY = (v) => p.y + p.h - (v + 80) / 80 * p.h;
    ctx.fillStyle = colors.muted; ctx.font = '10px system-ui'; ctx.textAlign = 'left';
    for (let v = -80; v <= 0; v += 20) ctx.fillText(`${v}`, p.x + p.w + 5, rmsY(v) + 3);
    ctx.textAlign = 'start';
    segmentGuides(p, 'tilt', tiltY, colors.tilt);
    lineSeries(state.data.frames, p, 'tilt', tiltY, colors.tilt, 1.15);
    lineSeries(state.data.frames, p, 'rmsDb', rmsY, colors.rms, 1.05);
  }
  function drawVib(p) {
    base(p, 'Local pitch modulation', '0.8 s detrended-F0 extent + dominant 3–9 Hz rate'); overlays(p);
    const vals = state.data.frames.filter((q) => q.t >= state.view[0] && q.t <= state.view[1] && Number.isFinite(q.vibExtent)).map((q) => q.vibExtent);
    const max = Math.max(50, Math.min(600, Math.ceil((percentile(vals, .98) || 50) / 25) * 25));
    const yy = yGrid(p, 0, max, max <= 100 ? 25 : 50);
    segmentGuides(p, 'vib', yy, colors.vib);
    lineSeries(state.data.frames, p, 'vibExtent', yy, colors.vib, 1.35);
    const rateY = (v) => p.y + p.h - (v - 3) / 6 * p.h;
    ctx.fillStyle = colors.rate; ctx.font = '10px system-ui'; ctx.textAlign = 'left';
    for (let v = 3; v <= 9; v += 2) ctx.fillText(`${v}Hz`, p.x + p.w + 5, rateY(v) + 3);
    ctx.textAlign = 'start'; lineSeries(state.data.frames, p, 'vibRate', rateY, colors.rate, 1.05);
  }
  function crosshair(L) {
    if (state.hover == null) return;
    const x = mapX(state.hover, L.f0); if (x < L.f0.x || x > L.f0.x + L.f0.w) return;
    ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(x, L.f0.y); ctx.lineTo(x, L.vib.y + L.vib.h); ctx.stroke(); ctx.setLineDash([]);
  }
  function selection(L) {
    if (!state.drag || state.drag.current == null) return;
    const x1 = mapX(Math.min(state.drag.start, state.drag.current), L.f0), x2 = mapX(Math.max(state.drag.start, state.drag.current), L.f0);
    ctx.fillStyle = 'rgba(121,194,255,.12)'; ctx.fillRect(x1, L.f0.y, x2 - x1, L.vib.y + L.vib.h - L.f0.y);
  }
  function draw() {
    drawOverviewTimeline();
    const L = layout(); state.layout = L; ctx.clearRect(0, 0, L.w, L.h);
    if (!state.data) {
      ctx.fillStyle = colors.muted; ctx.font = '16px system-ui'; ctx.textAlign = 'center'; ctx.fillText('音声を選択すると解析結果をここに表示します', L.w / 2, 80); ctx.textAlign = 'start'; return;
    }
    drawF0(L.f0); drawVoice(L.voice); drawSpectral(L.spectral); drawVib(L.vib); timeGrid(L.vib); crosshair(L); selection(L); updatePlayheadOverlay();
  }

  function updatePlayheadOverlay() {
    if (!state.data || audio.hidden || !state.layout || !Number.isFinite(state.playhead)) { playheadLine.hidden = true; return; }
    const L = state.layout;
    const x = mapX(state.playhead, L.f0);
    if (x < L.f0.x || x > L.f0.x + L.f0.w) { playheadLine.hidden = true; return; }
    const canvasRect = canvas.getBoundingClientRect(), shellRect = canvas.parentElement.getBoundingClientRect();
    playheadLine.hidden = false;
    playheadLine.style.left = `${canvasRect.left - shellRect.left + x}px`;
    playheadLine.style.top = `${canvasRect.top - shellRect.top + L.f0.y}px`;
    playheadLine.style.height = `${L.vib.y + L.vib.h - L.f0.y}px`;
    playheadLabel.textContent = `${fmt(state.playhead, 2)} s`;
    const flip = x > L.f0.x + L.f0.w - 90;
    playheadLabel.style.left = flip ? '-6px' : '6px';
    playheadLabel.style.transform = flip ? 'translateX(-100%)' : 'none';
  }

  function keepPlayheadInView(t) {
    if (!state.data) return false;
    const duration = state.data.duration_s, [a, b] = state.view, span = b - a;
    if (span >= duration - .001) return false;
    const left = a + span * .08, right = b - span * .08;
    if (t >= left && t <= right) return false;
    let na = t - span * .15;
    na = clamp(na, 0, Math.max(0, duration - span));
    state.view = [na, Math.min(duration, na + span)];
    return true;
  }

  function syncPlaybackUi(t = audio.currentTime, playing = !audio.paused && !audio.ended, forceInsight = false) {
    if (!state.data || !Number.isFinite(Number(t))) return;
    state.playhead = clamp(Number(t), 0, state.data.duration_s);
    document.documentElement.dataset.playhead = state.playhead.toFixed(2);
    const viewChanged = keepPlayheadInView(state.playhead);
    if (forceInsight || !Number.isFinite(state.lastInsightAt) || Math.abs(state.playhead - state.lastInsightAt) >= .08) {
      renderPlaybackInsights(state.playhead, playing);
      state.lastInsightAt = state.playhead;
    } else {
      playbackState.textContent = playing ? '再生中' : (audio.ended ? '再生終了' : '一時停止 / 停止');
      playbackTime.textContent = `${fmt(state.playhead, 2)} s`;
    }
    if (!state.overviewHovering) renderOverviewReadout(state.playhead);
    syncChronicle(state.playhead, false);
    if (viewChanged) draw(); else { updatePlayheadOverlay(); updateOverviewPlayhead(); }
  }

  function playbackTick() {
    state.playRaf = 0;
    if (audio.hidden || audio.paused || audio.ended) { syncPlaybackUi(audio.currentTime, false, true); return; }
    syncPlaybackUi(audio.currentTime, true, false);
    state.playRaf = requestAnimationFrame(playbackTick);
  }
  function startPlaybackLoop() {
    if (state.playRaf) cancelAnimationFrame(state.playRaf);
    syncPlaybackUi(audio.currentTime, true, true);
    state.playRaf = requestAnimationFrame(playbackTick);
  }
  function stopPlaybackLoop() {
    if (state.playRaf) cancelAnimationFrame(state.playRaf);
    state.playRaf = 0;
    syncPlaybackUi(audio.currentTime, false, true);
  }

  function tooltipAt(t, cx, cy) {
    const q = nearest(state.data.frames, t), mov = state.data.movement.find((e) => t >= e.s && t <= e.e);
    const reg = state.data.register.reduce((best, r) => !best || Math.abs(r.t - t) < Math.abs(best.t - t) ? r : best, null);
    const seg = state.data.segments.find((s) => t >= s.s && t <= s.e);
    let h = `<b>${escapeHtml(state.data.name)}</b> · ${fmt(t, 2)} s`;
    if (q && Math.abs(q.t - t) < .08) h += `<br>F0 <b>${fmt(q.f0, 1)} Hz</b> <span class="muted">conf ${fmt(q.confidence, 2)}</span><br>CPPS-like ${fmt(q.cppsLike)} dB · HNR ${fmt(q.hnr)} dB<br>tilt ${fmt(q.tilt)} dB/oct · RMS ${fmt(q.rmsDb, 1)} dBFS<br>local extent ${fmt(q.vibExtent, 1)} cent · rate ${fmt(q.vibRate, 2)} Hz`;
    if (seg) h += `<br><span class="muted">stable guide:</span> F0 ${fmt(seg.f0, 1)} / HNR ${fmt(seg.hnr, 1)}`;
    if (mov) h += `<br><span class="muted">movement:</span> ${mov.dir}, ${fmt(mov.change, 0)} cent`;
    if (reg && Math.abs(reg.t - t) <= .45) h += `<br><span class="muted">register candidate @ ${fmt(reg.t, 2)}s:</span> ${reg.features.join(', ')}`;
    tooltip.innerHTML = h; tooltip.hidden = false;
    const shell = tooltip.parentElement.getBoundingClientRect(); let x = cx - shell.left + 14, y = cy - shell.top + 14;
    const tw = tooltip.offsetWidth, th = tooltip.offsetHeight; if (x + tw > shell.width - 8) x -= tw + 28; if (y + th > shell.height - 8) y -= th + 28;
    tooltip.style.left = `${Math.max(8, x)}px`; tooltip.style.top = `${Math.max(8, y)}px`;
  }
  function pointTime(ev) {
    if (!state.data) return null;
    const L = layout(), r = canvas.getBoundingClientRect(), x = ev.clientX - r.left;
    if (x < L.f0.x || x > L.f0.x + L.f0.w) return null;
    return clamp(timeAtX(x, L.f0), state.view[0], state.view[1]);
  }
  function resetView() { if (state.data) { state.view = [0, state.data.duration_s]; draw(); } }

  chronicleLog.addEventListener('click', (ev) => {
    const button = ev.target.closest?.('.chronicle-main');
    if (!button || !state.data) return;
    const t = Number(button.dataset.seek);
    if (!Number.isFinite(t)) return;
    state.playhead = clamp(t,0,state.data.duration_s);
    document.documentElement.dataset.playhead = state.playhead.toFixed(2);
    if (!audio.hidden) { audio.currentTime = state.playhead; syncPlaybackUi(state.playhead, !audio.paused, true); }
    else { renderOverviewReadout(state.playhead); updateOverviewPlayhead(); syncChronicle(state.playhead,true); }
  });
  chronicleLog.addEventListener('toggle', (ev) => {
    const details = ev.target;
    if (details?.tagName !== 'DETAILS' || !details.open || details.dataset.loaded === '1' || !state.data) return;
    const start = Number(details.dataset.frameStart), end = Number(details.dataset.frameEnd);
    if (!Number.isInteger(start) || !Number.isInteger(end)) return;
    details.innerHTML = `<summary>生フレーム ${(end-start+1).toLocaleString()}件</summary>${rawFramesHtml(start,end)}`;
    details.dataset.loaded = '1';
  }, true);
  jumpCurrentLog.addEventListener('click', () => syncChronicle(state.playhead,true));
  followLog.addEventListener('change', () => { if (followLog.checked) syncChronicle(state.playhead,true); });

  overviewCanvas.addEventListener('pointermove', (ev) => {
    const t = overviewTimeAtEvent(ev); if (t == null) return;
    state.overviewHovering = true; renderOverviewReadout(t);
  });
  overviewCanvas.addEventListener('pointerleave', () => {
    state.overviewHovering = false;
    if (state.data) renderOverviewReadout(state.playhead);
  });
  overviewCanvas.addEventListener('pointerdown', (ev) => {
    const t = overviewTimeAtEvent(ev); if (t == null) return;
    state.playhead = t;
    document.documentElement.dataset.playhead = t.toFixed(2);
    if (!audio.hidden) {
      audio.currentTime = t; syncPlaybackUi(t, !audio.paused, true);
    } else {
      renderOverviewReadout(t); updateOverviewPlayhead();
    }
  });

  canvas.addEventListener('pointermove', (ev) => {
    const t = pointTime(ev); if (t == null) return;
    if (state.drag) state.drag.current = t; state.hover = t; tooltipAt(t, ev.clientX, ev.clientY); draw();
  });
  canvas.addEventListener('pointerleave', () => { if (!state.drag) { state.hover = null; tooltip.hidden = true; draw(); } });
  canvas.addEventListener('pointerdown', (ev) => { const t = pointTime(ev); if (t == null) return; state.drag = { start: t, current: t }; canvas.setPointerCapture(ev.pointerId); });
  canvas.addEventListener('pointerup', (ev) => {
    if (!state.drag) return; const a = state.drag.start, b = state.drag.current; state.drag = null;
    if (Math.abs(a - b) > .35) state.view = [Math.min(a, b), Math.max(a, b)];
    else if (!audio.hidden) { const t = pointTime(ev); if (Number.isFinite(t)) { audio.currentTime = t; syncPlaybackUi(t, !audio.paused, true); } }
    draw();
  });
  canvas.addEventListener('dblclick', resetView);
  canvas.addEventListener('wheel', (ev) => {
    if (!state.data) return; ev.preventDefault(); const t = pointTime(ev); if (t == null) return;
    const [a, b] = state.view, span = b - a, f = ev.deltaY > 0 ? 1.35 : .74, minSpan = Math.min(2, state.data.duration_s), ns = clamp(span * f, minSpan, state.data.duration_s), rel = (t - a) / span;
    let na = t - rel * ns, nb = na + ns; if (na < 0) { nb -= na; na = 0; } if (nb > state.data.duration_s) { na -= nb - state.data.duration_s; nb = state.data.duration_s; }
    state.view = [Math.max(0, na), Math.min(state.data.duration_s, nb)]; draw();
  }, { passive: false });

  audio.addEventListener('play', startPlaybackLoop);
  audio.addEventListener('pause', stopPlaybackLoop);
  audio.addEventListener('ended', stopPlaybackLoop);
  audio.addEventListener('seeking', () => syncPlaybackUi(audio.currentTime, !audio.paused, true));
  audio.addEventListener('timeupdate', () => { if (audio.paused || audio.ended) syncPlaybackUi(audio.currentTime, false, false); });

  chooseFile.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => { const f = fileInput.files?.[0]; if (f) analyzeFile(f); });
  dropZone.addEventListener('dragover', (ev) => { ev.preventDefault(); dropZone.classList.add('drag'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag'));
  dropZone.addEventListener('drop', (ev) => { ev.preventDefault(); dropZone.classList.remove('drag'); const f = ev.dataTransfer?.files?.[0]; if (f) analyzeFile(f); });
  dropZone.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); fileInput.click(); } });
  cancelBtn.addEventListener('click', () => { state.abortToken++; setAnalyzing(false); setStatus('cancelled'); });
  syntheticBtn.addEventListener('click', () => runSynthetic(false));
  $('#reset-view').addEventListener('click', resetView);
  [showLow, showSegments, showMove, showReg].forEach((x) => x.addEventListener('change', draw));
  exportBtn.addEventListener('click', () => {
    if (!state.data) return;
    const payload = JSON.stringify(state.data);
    const blob = new Blob([payload], { type: 'application/json' });
    const u = URL.createObjectURL(blob), a = document.createElement('a'); a.href = u; a.download = `${state.data.name.replace(/\.[^.]+$/, '') || 'audio'}-browser-analysis.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(u), 1000);
  });
  addEventListener('resize', () => { draw(); updatePlayheadOverlay(); updateOverviewPlayhead(); });

  draw();
  if (new URLSearchParams(location.search).get('selftest') === '1') runSynthetic(true);
})();