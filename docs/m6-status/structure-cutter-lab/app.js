import { Separator } from 'unblend';
import { analyzeRepetition } from './repetition-core.js';
import { analyzeBeatGrid, alignCutRange, nearestGridTime } from './beat-core.js';
import { analyzeVocalPhrases, nearestPhraseBoundary } from './vocal-core.js';
import { alignLowEnergyRange } from './cut-core.js';
import { computeSectionAISpectrograms } from './section-ai-features.js';
import { postprocessFunctionalStructure } from './section-ai-postprocess.js';
import { runSectionAIInference } from './section-ai-runtime.js';

(() => {
  'use strict';

  const DEMUCS_MODEL = 'htdemucs';
  const DEMUCS_RATE = 44100;
  const ORT_WASM_PATHS = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.26.0/dist/';
  const STEM_NAMES = ['vocals', 'drums', 'bass', 'other'];
  const STEM_COLORS = { vocals: '#dc72c8', drums: '#e4a64f', bass: '#69bfc8', other: '#9b87d6' };
  let separatorLoader = (model, options) => Separator.load(model, options);

  const REPO_SAMPLES = {
    'whisper-ao': {
      title: 'Whisper AO',
      path: 'samples/whisper-ao/source/whisper-ao.mp3',
      url: 'https://raw.githubusercontent.com/2rwa/tmp-music/main/samples/whisper-ao/source/whisper-ao.mp3'
    },
    jugemu: {
      title: 'Jugemu',
      path: 'samples/jugemu/source/jugemu.mp3',
      url: 'https://raw.githubusercontent.com/2rwa/tmp-music/main/samples/jugemu/source/jugemu.mp3'
    },
    'chichinu-fiija': {
      title: 'Chichinu Fiija',
      path: 'samples/chichinu-fiija/source/chichinu-fiija.mp3',
      url: 'https://raw.githubusercontent.com/2rwa/tmp-music/main/samples/chichinu-fiija/source/chichinu-fiija.mp3'
    }
  };

  const $ = id => document.getElementById(id);
  const el = {
    gpuBadge: $('gpu-badge'), openFile: $('open-file'), fileInput: $('file-input'), sampleSelect: $('sample-select'), loadSample: $('load-sample'),
    trackName: $('track-name'), trackMeta: $('track-meta'), progressPanel: $('progress-panel'), progressTitle: $('progress-title'), progressPercent: $('progress-percent'), progressFill: $('progress-fill'), cancelProcessing: $('cancel-processing'),
    play: $('play-toggle'), stop: $('stop-playback'), seek: $('seek'), current: $('time-current'), duration: $('time-duration'), volume: $('volume'), playbackSourceButtons: $('playback-source-buttons'), playbackSourceStatus: $('playback-source-status'),
    modeTabs: $('mode-tabs'), engineNotice: $('engine-notice'), toggleCompare: $('toggle-compare'), comparePanel: $('compare-panel'), compareGrid: $('compare-grid'),
    ruler: $('timeline-ruler'), sectionTrack: $('section-track'), mixTrack: $('mix-track'), waveform: $('waveform'), selectionOverlay: $('selection-overlay'), playhead: $('playhead'), boundaryLayer: $('boundary-layer'),
    selectionTitle: $('selection-title'), selectionTime: $('selection-time'), cutAlignment: $('cut-alignment'), alignmentNote: $('alignment-note'), loop: $('loop-toggle'), clearSelection: $('clear-selection'), extract: $('extract-selection'),
    inspector: $('boundary-inspector'), closeInspector: $('close-inspector'), boundaryTime: $('boundary-time'), boundaryConfidence: $('boundary-confidence'), evidenceChange: $('evidence-change'), evidenceStem: $('evidence-stem'), evidenceRepetition: $('evidence-repetition'), evidenceSection: $('evidence-section'), evidenceVocal: $('evidence-vocal'), evidenceBeat: $('evidence-beat'),
    stemCanvases: { vocals: $('stem-vocals'), drums: $('stem-drums'), bass: $('stem-bass'), other: $('stem-other') }
  };

  const state = {
    audioBuffer: null,
    objectUrl: '',
    name: '',
    sourcePath: '',
    duration: 0,
    envelope: [],
    boundaries: [],
    mixBoundaries: [],
    stemBoundaries: [],
    repetitionBoundaries: [],
    repetitionPairs: [],
    repetitionPeriodSec: null,
    beatAnalysis: { bpm: null, confidence: 0, beatTimes: [], barTimes: [], boundaries: [] },
    vocalPhrases: [],
    vocalPhraseBoundaries: [],
    sectionAI: { status: 'idle', provider: '', error: '', segments: [], boundaries: [], inferenceMs: 0, frames: 0 },
    consensusBoundaries: [],
    stemProfiles: {},
    stems: {},
    stemFrames: [],
    mono: null,
    sections: [],
    selection: null,
    dragStart: null,
    dragMoved: false,
    loop: false,
    mode: 'consensus',
    gpuAvailable: false,
    demucs: { runId: 0, controller: null, busy: false },
    playback: { ctx: null, gain: null, node: null, sourceName: 'mix', buffers: {}, startedAtCtx: 0, startedAtOffset: 0, pausedAt: 0, playing: false, token: 0, raf: 0 }
  };

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function fmt(sec) {
    const s = Math.max(0, Number(sec) || 0), m = Math.floor(s / 60), r = s - m * 60;
    return `${String(m).padStart(2, '0')}:${r.toFixed(1).padStart(4, '0')}`;
  }
  function pct(sec) { return state.duration > 0 ? clamp(sec / state.duration * 100, 0, 100) : 0; }
  function median(values) {
    if (!values.length) return 0;
    const a = [...values].sort((x, y) => x - y), i = Math.floor(a.length / 2);
    return a.length % 2 ? a[i] : (a[i - 1] + a[i]) / 2;
  }
  function mean(values) { return values.length ? values.reduce((s, v) => s + v, 0) / values.length : 0; }

  function setProgress(value, title) {
    const v = clamp(value, 0, 1);
    el.progressPanel.hidden = false;
    el.progressFill.style.width = `${v * 100}%`;
    el.progressPercent.textContent = `${Math.round(v * 100)}%`;
    if (title) el.progressTitle.textContent = title;
  }
  function stepState(name, cls) {
    const n = document.querySelector(`[data-step="${name}"]`);
    if (!n) return;
    n.classList.remove('done', 'active');
    if (cls) n.classList.add(cls);
  }

  async function decodeArrayBuffer(bytes) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    try { return await ctx.decodeAudioData(bytes.slice(0)); }
    finally { await ctx.close().catch(() => {}); }
  }

  function monoFromBuffer(buffer) {
    const out = new Float32Array(buffer.length), channels = buffer.numberOfChannels;
    for (let c = 0; c < channels; c++) {
      const src = buffer.getChannelData(c);
      for (let i = 0; i < out.length; i++) out[i] += src[i] / channels;
    }
    return out;
  }

  function buildEnvelope(samples, bins = 1500) {
    const out = new Array(bins).fill(0), stride = Math.max(1, Math.floor(samples.length / bins));
    for (let b = 0; b < bins; b++) {
      const s = b * stride, e = Math.min(samples.length, s + stride); let peak = 0;
      const step = Math.max(1, Math.floor((e - s) / 96));
      for (let i = s; i < e; i += step) peak = Math.max(peak, Math.abs(samples[i] || 0));
      out[b] = peak;
    }
    return out;
  }

  function analyzeChangePoints(samples, sampleRate) {
    const winSec = 1.2, hopSec = 0.55, win = Math.max(1, Math.floor(sampleRate * winSec)), hop = Math.max(1, Math.floor(sampleRate * hopSec));
    const frames = [];
    for (let s = 0; s + win <= samples.length; s += hop) {
      let sum = 0, zc = 0, prev = samples[s] || 0;
      const stride = Math.max(1, Math.floor(win / 500));
      let n = 0;
      for (let i = s; i < s + win; i += stride) {
        const x = samples[i] || 0; sum += x * x; n++;
        if ((x >= 0) !== (prev >= 0)) zc++;
        prev = x;
      }
      const rms = Math.sqrt(sum / Math.max(1, n));
      frames.push({ t: (s + win / 2) / sampleRate, db: 20 * Math.log10(rms + 1e-8), zcr: zc / Math.max(1, n) });
    }
    const raw = [];
    for (let i = 1; i < frames.length; i++) {
      const a = frames[i - 1], b = frames[i];
      const score = Math.abs(b.db - a.db) / 9 + Math.abs(b.zcr - a.zcr) * 5;
      raw.push({ t: b.t, score });
    }
    const values = raw.map(x => x.score), med = median(values), mad = median(values.map(x => Math.abs(x - med))) || 0.05;
    const threshold = med + Math.max(0.38, mad * 2.4);
    const picked = raw.filter(x => x.score >= threshold).sort((a, b) => b.score - a.score);
    const chosen = [];
    for (const c of picked) {
      if (c.t < 3 || c.t > state.duration - 3) continue;
      if (chosen.every(x => Math.abs(x.t - c.t) >= 5.5)) chosen.push(c);
      if (chosen.length >= 11) break;
    }
    chosen.sort((a, b) => a.t - b.t);
    const max = Math.max(0.001, ...chosen.map(x => x.score));
    return chosen.map(x => { const confidence = clamp(x.score / max, 0.25, 1); return { ...x, confidence, source: 'mix', evidence: { mix: confidence } }; });
  }


  function clearStemVisuals() {
    for (const name of STEM_NAMES) {
      const canvas = el.stemCanvases[name];
      if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, canvas.width || 1, canvas.height || 1);
        const track = canvas.closest('[data-stem-track]');
        if (track) track.classList.remove('is-ready');
      }
    }
  }

  function currentPlaybackTime() {
    const p = state.playback;
    if (!p.playing || !p.ctx) return clamp(p.pausedAt || 0, 0, state.duration || 0);
    const elapsed = Math.max(0, p.ctx.currentTime - p.startedAtCtx);
    let t = p.startedAtOffset + elapsed;
    if (state.loop && state.selection) {
      const span = Math.max(.02, state.selection.e - state.selection.s);
      if (t >= state.selection.e) t = state.selection.s + ((t - state.selection.s) % span);
    }
    return clamp(t, 0, state.duration || 0);
  }

  async function ensurePlaybackContext() {
    const p = state.playback;
    if (!p.ctx) {
      p.ctx = new (window.AudioContext || window.webkitAudioContext)();
      p.gain = p.ctx.createGain();
      p.gain.gain.value = clamp(Number(el.volume.value) / 100, 0, 1);
      p.gain.connect(p.ctx.destination);
    }
    if (p.ctx.state === 'suspended') await p.ctx.resume();
    return p.ctx;
  }

  function playbackBufferFor(name) {
    if (name === 'mix') return state.audioBuffer;
    if (state.playback.buffers[name]) return state.playback.buffers[name];
    const data = state.stems[name];
    if (!(data instanceof Float32Array) || !state.playback.ctx) return null;
    const frames = Math.floor(data.length / 2);
    const buffer = state.playback.ctx.createBuffer(2, frames, DEMUCS_RATE);
    const left = buffer.getChannelData(0), right = buffer.getChannelData(1);
    for (let i = 0; i < frames; i++) {
      left[i] = data[i * 2] || 0;
      right[i] = data[i * 2 + 1] || 0;
    }
    state.playback.buffers[name] = buffer;
    return buffer;
  }

  function stopPlayback({ preservePosition = true } = {}) {
    const p = state.playback;
    const t = preservePosition ? currentPlaybackTime() : 0;
    p.token += 1;
    if (p.node) {
      try { p.node.onended = null; p.node.stop(); } catch {}
      try { p.node.disconnect(); } catch {}
    }
    p.node = null;
    p.playing = false;
    p.pausedAt = clamp(t, 0, state.duration || 0);
    if (p.raf) cancelAnimationFrame(p.raf);
    p.raf = 0;
    el.play.textContent = '▶';
  }

  function renderPlaybackSourceUi() {
    const name = state.playback.sourceName;
    document.querySelectorAll('button[data-playback-source]').forEach(button => {
      const active = button.dataset.playbackSource === name;
      button.classList.toggle('is-active', active);
      button.classList.toggle('is-playback-source', active);
      if (button.dataset.playbackSource !== 'mix') button.disabled = !(state.stems[button.dataset.playbackSource] instanceof Float32Array);
    });
    const label = name === 'mix' ? 'MIX · original audio' : name.toUpperCase() + ' · HTDemucs stem';
    if (el.playbackSourceStatus) el.playbackSourceStatus.textContent = label;
    document.documentElement.dataset.playbackSource = name;
  }

  async function startPlayback(offset = state.playback.pausedAt) {
    if (!state.audioBuffer) return false;
    const p = state.playback;
    await ensurePlaybackContext();
    stopPlayback({ preservePosition: true });
    const buffer = playbackBufferFor(p.sourceName);
    if (!buffer) return false;
    let start = clamp(Number(offset) || 0, 0, Math.max(0, buffer.duration - .005));
    if (state.loop && state.selection && (start < state.selection.s || start >= state.selection.e)) start = state.selection.s;
    const node = p.ctx.createBufferSource();
    node.buffer = buffer;
    node.connect(p.gain);
    if (state.loop && state.selection) {
      node.loop = true;
      node.loopStart = state.selection.s;
      node.loopEnd = state.selection.e;
    }
    const token = ++p.token;
    p.node = node;
    p.startedAtCtx = p.ctx.currentTime;
    p.startedAtOffset = start;
    p.pausedAt = start;
    p.playing = true;
    node.onended = () => {
      if (token !== p.token || node.loop) return;
      p.node = null;
      p.playing = false;
      p.pausedAt = Math.min(state.duration, buffer.duration);
      el.play.textContent = '▶';
      updatePlayhead();
    };
    node.start(0, start);
    el.play.textContent = '❚❚';
    updatePlayhead();
    return true;
  }

  function pausePlayback() {
    if (!state.playback.playing) return;
    stopPlayback({ preservePosition: true });
    updatePlayhead();
  }

  async function seekPlayback(time) {
    const t = clamp(Number(time) || 0, 0, state.duration || 0);
    const wasPlaying = state.playback.playing;
    stopPlayback({ preservePosition: false });
    state.playback.pausedAt = t;
    if (wasPlaying) await startPlayback(t);
    else updatePlayhead();
  }

  async function setPlaybackSource(name) {
    if (!['mix', ...STEM_NAMES].includes(name)) return false;
    if (name !== 'mix' && !(state.stems[name] instanceof Float32Array)) return false;
    const t = currentPlaybackTime();
    const wasPlaying = state.playback.playing;
    stopPlayback({ preservePosition: true });
    state.playback.sourceName = name;
    state.playback.pausedAt = t;
    renderPlaybackSourceUi();
    if (wasPlaying) await startPlayback(t);
    else updatePlayhead();
    return true;
  }

  function resetPlaybackState() {
    stopPlayback({ preservePosition: false });
    state.playback.sourceName = 'mix';
    state.playback.buffers = {};
    state.playback.pausedAt = 0;
    renderPlaybackSourceUi();
    updatePlayhead();
  }

  function resetStemState(abort = true) {
    if (abort && state.demucs.controller && !state.demucs.controller.signal.aborted) {
      try { state.demucs.controller.abort(new DOMException('new source', 'AbortError')); } catch {}
    }
    state.demucs.runId += 1;
    state.demucs.controller = null;
    state.demucs.busy = false;
    state.stems = {};
    state.stemProfiles = {};
    state.stemFrames = [];
    state.stemBoundaries = [];
    state.vocalPhrases = [];
    state.vocalPhraseBoundaries = [];
    state.sectionAI = { status: 'idle', provider: '', error: '', segments: [], boundaries: [], inferenceMs: 0, frames: 0 };
    state.consensusBoundaries = buildConsensusBoundaries(state.mixBoundaries, [], state.repetitionBoundaries, []);
    stopPlayback({ preservePosition: false });
    state.playback.sourceName = 'mix';
    state.playback.buffers = {};
    renderPlaybackSourceUi();
    clearStemVisuals();
    document.documentElement.dataset.demucsReady = 'false';
    document.documentElement.dataset.sectionAiReady = 'false';
  }

  async function prepareWholeTrackForDemucs(buffer) {
    const targetFrames = Math.max(1, Math.round(buffer.duration * DEMUCS_RATE));
    const offline = new OfflineAudioContext(2, targetFrames, DEMUCS_RATE);
    const source = offline.createBufferSource();
    source.buffer = buffer;
    source.connect(offline.destination);
    source.start();
    return await offline.startRendering();
  }

  function buildStemProfile(data, bins = 1400) {
    const frames = Math.floor(data.length / 2), out = new Array(bins).fill(0);
    for (let b = 0; b < bins; b++) {
      const s = Math.floor(b * frames / bins), e = Math.max(s + 1, Math.floor((b + 1) * frames / bins));
      const stride = Math.max(1, Math.floor((e - s) / 90));
      let sum = 0, n = 0;
      for (let i = s; i < e; i += stride) {
        const l = data[i * 2] || 0, rr = data[i * 2 + 1] || 0;
        sum += (l * l + rr * rr) * .5; n++;
      }
      out[b] = Math.sqrt(sum / Math.max(1, n));
    }
    const peak = Math.max(1e-6, ...out);
    return out.map(v => Math.sqrt(clamp(v / peak, 0, 1)));
  }

  function analyzeStemActivity(stems) {
    const names = STEM_NAMES.filter(n => stems[n] instanceof Float32Array);
    if (!names.length) return { frames: [], boundaries: [] };
    const totalFrames = Math.min(...names.map(n => Math.floor(stems[n].length / 2)));
    const win = Math.max(1, Math.floor(DEMUCS_RATE * .55)), frames = [];
    for (let start = 0; start < totalFrames; start += win) {
      const end = Math.min(totalFrames, start + win), energies = {}, rms = {};
      let totalEnergy = 0;
      for (const name of names) {
        const a = stems[name], stride = Math.max(1, Math.floor((end - start) / 420));
        let sum = 0, count = 0;
        for (let i = start; i < end; i += stride) {
          const l = a[i * 2] || 0, rr = a[i * 2 + 1] || 0;
          sum += (l * l + rr * rr) * .5; count++;
        }
        energies[name] = sum / Math.max(1, count);
        rms[name] = Math.sqrt(energies[name]);
        totalEnergy += energies[name];
      }
      const shares = {};
      for (const name of names) shares[name] = totalEnergy > 1e-12 ? energies[name] / totalEnergy : 0;
      frames.push({ t: (start + end) * .5 / DEMUCS_RATE, shares, rms, db: 10 * Math.log10(totalEnergy + 1e-12) });
    }
    const raw = [];
    for (let i = 1; i < frames.length; i++) {
      const a = frames[i - 1], b = frames[i];
      let shareDelta = 0;
      for (const name of names) shareDelta += Math.abs((b.shares[name] || 0) - (a.shares[name] || 0));
      const score = shareDelta * 1.35 + Math.abs(b.db - a.db) / 13;
      raw.push({ t: b.t, score });
    }
    const vals = raw.map(x => x.score), med = median(vals), mad = median(vals.map(x => Math.abs(x - med))) || .03;
    const threshold = med + Math.max(.22, mad * 2.25);
    const picked = raw.filter(x => x.score >= threshold).sort((a, b) => b.score - a.score), chosen = [];
    for (const item of picked) {
      if (item.t < 3 || item.t > state.duration - 3) continue;
      if (chosen.every(x => Math.abs(x.t - item.t) >= 4.5)) chosen.push(item);
      if (chosen.length >= 14) break;
    }
    chosen.sort((a, b) => a.t - b.t);
    const max = Math.max(.001, ...chosen.map(x => x.score));
    return {
      frames,
      boundaries: chosen.map(x => {
        const confidence = clamp(x.score / max, .25, 1);
        return { ...x, confidence, source: 'stem', evidence: { stem: confidence } };
      })
    };
  }

  function buildConsensusBoundaries(mix, stem, repetition = [], sectionAI = []) {
    const events = [
      ...mix.map(x => ({ ...x, kind: 'mix' })),
      ...stem.map(x => ({ ...x, kind: 'stem' })),
      ...repetition.map(x => ({ ...x, kind: 'repetition' })),
      ...sectionAI.map(x => ({ ...x, kind: 'section' }))
    ].sort((a, b) => a.t - b.t);
    const clusters = [];
    for (const event of events) {
      const prev = clusters[clusters.length - 1];
      if (prev && event.t - prev.lastT <= 1.5) {
        prev.events.push(event); prev.lastT = event.t;
      } else {
        clusters.push({ events: [event], lastT: event.t });
      }
    }
    return clusters.map(cluster => {
      const evidence = { mix: 0, stem: 0, repetition: 0, section: 0 };
      for (const kind of Object.keys(evidence)) {
        const matches = cluster.events.filter(x => x.kind === kind);
        evidence[kind] = matches.length ? Math.max(...matches.map(x => x.confidence)) : 0;
      }
      const weightSum = cluster.events.reduce((s, x) => s + Math.max(.1, x.confidence), 0);
      const t = cluster.events.reduce((s, x) => s + x.t * Math.max(.1, x.confidence), 0) / weightSum;
      const active = Object.values(evidence).filter(x => x > 0);
      const avg = active.length ? mean(active) : 0;
      const confidence = clamp(avg * (.58 + .14 * Math.max(0, active.length - 1)) + .08 * Math.max(0, active.length - 1), .18, 1);
      return { t, score: confidence, confidence, source: 'consensus', evidence };
    }).filter(x => x.t >= 3 && x.t <= state.duration - 3);
  }

  function boundariesForMode(mode = state.mode) {
    if (mode === 'change-point') return state.mixBoundaries;
    if (mode === 'stem-activity') return state.stemBoundaries.length ? state.stemBoundaries : state.mixBoundaries;
    if (mode === 'repetition') return state.repetitionBoundaries.length ? state.repetitionBoundaries : state.mixBoundaries;
    if (mode === 'beat-bars') return state.beatAnalysis.boundaries.length ? state.beatAnalysis.boundaries : state.mixBoundaries;
    if (mode === 'vocal-phrase') return state.vocalPhraseBoundaries.length ? state.vocalPhraseBoundaries : state.mixBoundaries;
    if (mode === 'section-ai') return state.sectionAI.boundaries.length ? state.sectionAI.boundaries : state.consensusBoundaries;
    return state.consensusBoundaries.length ? state.consensusBoundaries : state.mixBoundaries;
  }

  function refreshModeView() {
    state.boundaries = boundariesForMode();
    state.sections = state.mode === 'section-ai' && state.sectionAI.segments.length
      ? state.sectionAI.segments.map(x => ({ s: x.start, e: x.end, label: String(x.label || 'section').toUpperCase() }))
      : buildSections(state.boundaries);
    if (state.mode === 'beat-bars') {
      state.sections.forEach((section, i) => { section.label = 'Bar ' + (i + 1); });
    }
    renderSections();
    renderBoundaries();
    renderCompare();
  }

  function drawStemProfile(name) {
    const canvas = el.stemCanvases[name], profile = state.stemProfiles[name];
    if (!canvas || !profile || !profile.length) return;
    const rect = canvas.getBoundingClientRect(), dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    canvas.width = Math.max(2, Math.round(rect.width * dpr)); canvas.height = Math.max(2, Math.round(rect.height * dpr));
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = '#0d1015'; ctx.fillRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = STEM_COLORS[name] || '#999';
    const step = rect.width / profile.length;
    for (let i = 0; i < profile.length; i++) {
      const h = Math.max(1, profile[i] * rect.height * .88);
      ctx.globalAlpha = .22 + profile[i] * .68;
      ctx.fillRect(i * step, rect.height - h, Math.max(1, step + .2), h);
    }
    ctx.globalAlpha = 1;
    const track = canvas.closest('[data-stem-track]');
    if (track) track.classList.add('is-ready');
  }

  function drawAllStemProfiles() { for (const name of STEM_NAMES) drawStemProfile(name); }

  function sectionAIBoundariesFromPostprocess(post) {
    const strengths = post.boundaryIndices.map(i => post.sectionStrength[i] || 0);
    const maxStrength = Math.max(1e-6, ...strengths);
    return post.boundaryIndices.map((frame, i) => {
      const t = frame / 100;
      const raw = strengths[i] || 0;
      const confidence = clamp(raw / maxStrength, .25, 1);
      const next = post.segments.find(segment => Math.abs(segment.start - t) < .02);
      return {
        t,
        score: raw,
        confidence,
        source: 'section-ai',
        label: next?.label || '',
        evidence: { section: confidence }
      };
    }).filter(x => x.t >= 1 && x.t <= state.duration - 1);
  }

  async function runSectionAIAnalysis(stems) {
    state.sectionAI = { status: 'running', provider: '', error: '', segments: [], boundaries: [], inferenceMs: 0, frames: 0 };
    document.documentElement.dataset.sectionAiReady = 'false';
    stepState('section-ai', 'active');
    try {
      setProgress(.945, 'Section AI · building 81-bin stem features');
      await new Promise(resolve => setTimeout(resolve, 0));
      const features = computeSectionAISpectrograms(stems, DEMUCS_RATE);
      state.sectionAI.frames = features.shape[2];
      setProgress(.965, 'Section AI · running All-In-One fold0');
      await new Promise(resolve => setTimeout(resolve, 0));
      const inferred = await runSectionAIInference(features, { preferWebGPU: state.gpuAvailable });
      const post = postprocessFunctionalStructure(inferred.sectionLogits, inferred.functionLogits);
      const segments = post.segments
        .map(segment => ({
          ...segment,
          start: clamp(segment.start, 0, state.duration),
          end: clamp(segment.end, 0, state.duration)
        }))
        .filter(segment => segment.end > segment.start + .01);
      const boundaries = sectionAIBoundariesFromPostprocess(post);
      state.sectionAI = {
        status: 'ready',
        provider: inferred.provider,
        error: '',
        segments,
        boundaries,
        inferenceMs: inferred.inferenceMs,
        frames: inferred.originalFrames
      };
      state.consensusBoundaries = buildConsensusBoundaries(
        state.mixBoundaries,
        state.stemBoundaries,
        state.repetitionBoundaries,
        boundaries
      );
      document.documentElement.dataset.sectionAiReady = 'true';
      document.documentElement.dataset.sectionAiProvider = inferred.provider;
      document.documentElement.dataset.consensusSources = boundaries.length ? '4' : '3';
      stepState('section-ai', 'done');
      refreshModeView();
      return true;
    } catch (err) {
      console.error('Section AI failed', err);
      state.sectionAI = {
        status: 'error',
        provider: '',
        error: String(err?.message || err),
        segments: [],
        boundaries: [],
        inferenceMs: 0,
        frames: state.sectionAI.frames || 0
      };
      document.documentElement.dataset.sectionAiReady = 'error';
      document.documentElement.dataset.sectionAiError = state.sectionAI.error.slice(0, 300);
      stepState('section-ai', '');
      state.consensusBoundaries = buildConsensusBoundaries(
        state.mixBoundaries,
        state.stemBoundaries,
        state.repetitionBoundaries,
        []
      );
      document.documentElement.dataset.consensusSources = '3';
      refreshModeView();
      return false;
    }
  }

  async function installStemResult(result) {
    const stems = result && result.stems ? result.stems : (result || {});
    const valid = Object.fromEntries(STEM_NAMES.filter(name => stems[name] instanceof Float32Array).map(name => [name, stems[name]]));
    if (Object.keys(valid).length !== 4) throw new Error('HTDemucs did not return all four stems');
    state.stems = valid;
    state.stemProfiles = Object.fromEntries(STEM_NAMES.map(name => [name, buildStemProfile(valid[name])]));
    const activity = analyzeStemActivity(valid);
    state.stemFrames = activity.frames;
    state.stemBoundaries = activity.boundaries;
    const vocal = analyzeVocalPhrases(valid.vocals, DEMUCS_RATE);
    state.vocalPhrases = vocal.phrases;
    state.vocalPhraseBoundaries = vocal.boundaries;
    document.documentElement.dataset.vocalPhraseReady = state.vocalPhraseBoundaries.length ? 'true' : 'false';
    if (state.mono && state.audioBuffer) {
      const recurrence = analyzeRepetition(state.mono, state.audioBuffer.sampleRate, state.stemFrames);
      state.repetitionBoundaries = recurrence.boundaries;
      state.repetitionPairs = recurrence.pairs;
      state.repetitionPeriodSec = recurrence.selectedPeriodSec;
    }
    state.consensusBoundaries = buildConsensusBoundaries(state.mixBoundaries, state.stemBoundaries, state.repetitionBoundaries, []);
    drawAllStemProfiles();
    renderPlaybackSourceUi();
    refreshModeView();
    document.documentElement.dataset.demucsReady = 'true';
    document.documentElement.dataset.consensusSources = '3';
  }

  async function runWholeTrackDemucs(buffer) {
    if (!state.gpuAvailable) {
      setProgress(.72, 'WebGPU required for HTDemucs; mix analysis remains usable');
      el.progressPercent.textContent = 'GPU required';
      return false;
    }
    const runId = ++state.demucs.runId, controller = new AbortController();
    state.demucs.controller = controller; state.demucs.busy = true; el.cancelProcessing.hidden = false;
    stepState('demucs', 'active'); setProgress(.68, 'Preparing full track for HTDemucs');
    let separator = null;
    try {
      const input = await prepareWholeTrackForDemucs(buffer);
      if (runId !== state.demucs.runId) return false;
      setProgress(.70, 'Loading HTDemucs WebGPU model');
      separator = await separatorLoader(DEMUCS_MODEL, {
        backend: 'webgpu', precision: 'fp16', wasmPaths: ORT_WASM_PATHS,
        numThreads: crossOriginIsolated ? 4 : 1, cache: true, signal: controller.signal,
        onProgress: (phase, loaded, total) => {
          if (runId !== state.demucs.runId) return;
          const f = total > 0 ? loaded / total : 0;
          setProgress(phase === 'download' ? .70 + f * .08 : .78, phase === 'download' ? 'HTDemucs model ' + Math.round(f * 100) + '%' : 'Compiling HTDemucs');
        }
      });
      if (runId !== state.demucs.runId) return false;
      const started = performance.now();
      const result = await separator.separate(input, {
        signal: controller.signal, shifts: 0,
        onProgress: p => {
          if (runId !== state.demucs.runId) return;
          const f = clamp(Number(p.fraction) || 0, 0, 1);
          setProgress(.79 + f * .15, 'HTDemucs ' + (p.stage || 'inference') + ' ' + Math.round(f * 100) + '%');
        }
      });
      if (runId !== state.demucs.runId) return false;
      await installStemResult(result);
      stepState('demucs', 'done');

      // Release the large separator before loading the structure model so the
      // two GPU models do not have to coexist.
      try { if (separator && separator.unload) await separator.unload(); } catch {}
      separator = null;

      await runSectionAIAnalysis(state.stems);

      stepState('structure', 'active'); setProgress(.99, 'Building multi-engine consensus');
      await new Promise(resolve => setTimeout(resolve, 0));
      stepState('structure', 'done');
      const elapsed = (performance.now() - started) / 1000;
      const aiText = state.sectionAI.status === 'ready' ? ' · Section AI ' + state.sectionAI.provider : ' · Section AI unavailable';
      setProgress(1, 'Ready · HTDemucs ' + (elapsed < 1 ? '<1' : elapsed.toFixed(1)) + ' s' + aiText + ' · ' + state.consensusBoundaries.length + ' consensus boundaries');
      el.progressPercent.textContent = 'ready';
      return true;
    } catch (err) {
      if (err && err.name === 'AbortError') {
        setProgress(.70, 'HTDemucs cancelled; mix analysis remains usable');
        el.progressPercent.textContent = 'cancelled';
      } else {
        console.error(err);
        setProgress(.70, 'HTDemucs error: ' + (err && err.message ? err.message : err));
        el.progressPercent.textContent = 'error';
        document.documentElement.dataset.demucsError = String(err && err.message ? err.message : err);
      }
      return false;
    } finally {
      try { if (separator && separator.unload) await separator.unload(); } catch {}
      if (runId === state.demucs.runId) {
        state.demucs.controller = null; state.demucs.busy = false; el.cancelProcessing.hidden = true;
      }
    }
  }

  function buildSections(boundaries) {
    const points = [0, ...boundaries.map(x => x.t), state.duration];
    return points.slice(0, -1).map((s, i) => ({
      s,
      e: points[i + 1],
      label: i === 0 && points[i + 1] < 24 ? 'Opening' : (i === points.length - 2 && points[i + 1] - s < 28 ? 'Ending' : `Section ${i + 1}`)
    }));
  }

  function drawWaveform() {
    const canvas = el.waveform, rect = canvas.getBoundingClientRect(), dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    canvas.width = Math.max(2, Math.round(rect.width * dpr)); canvas.height = Math.max(2, Math.round(rect.height * dpr));
    const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = '#0d1015'; ctx.fillRect(0, 0, rect.width, rect.height);
    if (!state.envelope.length) return;
    ctx.strokeStyle = '#7d8794'; ctx.lineWidth = 1; ctx.beginPath();
    const mid = rect.height / 2, scale = rect.height * .42;
    for (let x = 0; x < rect.width; x++) {
      const i = Math.min(state.envelope.length - 1, Math.floor(x / Math.max(1, rect.width - 1) * state.envelope.length));
      const amp = state.envelope[i] * scale;
      ctx.moveTo(x + .5, mid - amp); ctx.lineTo(x + .5, mid + amp);
    }
    ctx.stroke();
  }

  function renderRuler() {
    el.ruler.innerHTML = '';
    if (!state.duration) return;
    const target = state.duration > 360 ? 60 : state.duration > 160 ? 30 : state.duration > 80 ? 15 : 10;
    for (let t = 0; t <= state.duration + .01; t += target) {
      const s = document.createElement('span'); s.className = 'ruler-tick'; s.style.left = `${pct(t)}%`; s.textContent = fmt(t); el.ruler.appendChild(s);
    }
  }

  function renderSections() {
    el.sectionTrack.innerHTML = '';
    if (!state.sections.length) { el.sectionTrack.innerHTML = '<div class="empty-lane">Load audio to build sections</div>'; return; }
    for (const [i, section] of state.sections.entries()) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'section-block';
      b.style.left = `${pct(section.s)}%`; b.style.width = `${pct(section.e) - pct(section.s)}%`; b.dataset.section = String(i);
      b.innerHTML = `${section.label}<small>${fmt(section.s)}–${fmt(section.e)}</small>`; el.sectionTrack.appendChild(b);
    }
  }

  function renderBoundaries() {
    el.boundaryLayer.innerHTML = '';
    for (const [i, b] of state.boundaries.entries()) {
      const n = document.createElement('button'); n.type = 'button'; n.className = 'boundary-marker'; n.dataset.boundary = String(i); n.style.left = `${pct(b.t)}%`;
      n.style.setProperty('--height', `${35 + b.confidence * 58}%`); n.style.setProperty('--opacity', String(.35 + b.confidence * .6));
      n.setAttribute('aria-label', `Boundary ${fmt(b.t)} confidence ${b.confidence.toFixed(2)}`); el.boundaryLayer.appendChild(n);
    }
  }

  function renderCompare() {
    const rows = [
      ['Consensus', state.consensusBoundaries, 'live'],
      ['Section AI', state.sectionAI.boundaries, state.sectionAI.status === 'ready' ? 'live' : 'pending'],
      ['Repetition', state.repetitionBoundaries, state.repetitionBoundaries.length ? 'live' : 'pending'],
      ['Change Point', state.mixBoundaries, 'live'],
      ['Stem Activity', state.stemBoundaries, state.stems.vocals ? 'live' : 'pending'],
      ['Vocal Phrase', state.vocalPhraseBoundaries, state.vocalPhraseBoundaries.length ? 'live' : 'pending'],
      ['Beat / Bars', state.beatAnalysis.boundaries, state.beatAnalysis.boundaries.length ? 'live' : 'pending']
    ];
    el.compareGrid.innerHTML = rows.map(([name, boundaries, status]) => {
      const marks = status === 'live'
        ? boundaries.map(b => '<span class="compare-dot" style="left:' + pct(b.t) + '%"></span>').join('')
        : '<span class="compare-pending">engine pending</span>';
      return '<div class="compare-row"><div class="compare-name">' + name + '</div><div class="compare-track">' + marks + '</div></div>';
    }).join('');
  }

  function setSelection(s, e, title = 'Manual selection') {
    if (!state.duration) return;
    const rawS = clamp(Math.min(s, e), 0, state.duration);
    const rawE = clamp(Math.max(s, e), 0, state.duration);
    const minRawE = rawE - rawS < .02 ? Math.min(state.duration, rawS + .02) : rawE;
    const mode = el.cutAlignment ? el.cutAlignment.value : 'recommended';
    let aligned;
    if (mode === 'vocal') {
      const startHit = nearestPhraseBoundary(rawS, state.vocalPhraseBoundaries, .9);
      const endHit = nearestPhraseBoundary(minRawE, state.vocalPhraseBoundaries, .9);
      const start = startHit ? startHit.time : rawS;
      const end = endHit ? endHit.time : minRawE;
      aligned = end > start + .02
        ? { start, end, startKind: startHit ? 'vocal' : 'exact', endKind: endHit ? 'vocal' : 'exact' }
        : { start: rawS, end: minRawE, startKind: 'exact', endKind: 'exact' };
    } else if (mode === 'low-energy') {
      aligned = alignLowEnergyRange(rawS, minRawE, state.mono, state.audioBuffer?.sampleRate || 0, { radiusSec: .35 });
    } else {
      aligned = alignCutRange(rawS, minRawE, state.beatAnalysis, mode);
      if (mode === 'recommended' && state.mono && state.audioBuffer) {
        const low = alignLowEnergyRange(rawS, minRawE, state.mono, state.audioBuffer.sampleRate, { radiusSec: .28 });
        let start = aligned.start, end = aligned.end, startKind = aligned.startKind, endKind = aligned.endKind;
        if (startKind === 'exact' && low.startKind === 'low-energy' && (low.startDropDb || 0) >= 4) {
          start = low.start; startKind = 'low-energy';
        }
        if (endKind === 'exact' && low.endKind === 'low-energy' && (low.endDropDb || 0) >= 4) {
          end = low.end; endKind = 'low-energy';
        }
        if (end > start + .02) aligned = { ...aligned, start, end, startKind, endKind };
      }
    }
    s = clamp(aligned.start, 0, state.duration);
    e = clamp(aligned.end, 0, state.duration);
    if (e - s < .02) { s = rawS; e = minRawE; }
    state.selection = { rawS, rawE: minRawE, s, e, title, alignmentMode: mode, startKind: aligned.startKind, endKind: aligned.endKind };
    el.selectionOverlay.hidden = false; el.selectionOverlay.style.left = `${pct(s)}%`; el.selectionOverlay.style.width = `${pct(e) - pct(s)}%`;
    const changed = Math.abs(s - rawS) > .015 || Math.abs(e - minRawE) > .015;
    el.selectionTitle.textContent = title;
    el.selectionTime.textContent = changed
      ? `cut ${fmt(s)} → ${fmt(e)} · raw ${fmt(rawS)} → ${fmt(minRawE)} · ${(e - s).toFixed(2)} sec`
      : `${fmt(s)} → ${fmt(e)} · ${(e - s).toFixed(2)} sec`;
    if (el.alignmentNote) {
      const bpm = state.beatAnalysis.bpm ? state.beatAnalysis.bpm.toFixed(1) + ' BPM' : 'no beat grid';
      el.alignmentNote.textContent = changed
        ? `${aligned.startKind} → ${aligned.endKind} · ${bpm}`
        : `${mode === 'exact' ? 'Exact' : 'No nearby snap'} · ${bpm}`;
    }
    el.loop.disabled = false; el.clearSelection.disabled = false; el.extract.disabled = !state.audioBuffer;
    el.sectionTrack.querySelectorAll('.section-block').forEach((n, i) => n.classList.toggle('is-selected', state.sections[i] && Math.abs(state.sections[i].s - rawS) < .03 && Math.abs(state.sections[i].e - minRawE) < .03));
    if (state.loop && state.playback.playing) startPlayback(s).catch(err => console.error('loop restart failed', err));
  }

  function clearSelection() {
    const resumeAt = currentPlaybackTime();
    const restartWithoutLoop = state.loop && state.playback.playing;
    state.selection = null; el.selectionOverlay.hidden = true; el.selectionTitle.textContent = 'No range selected'; el.selectionTime.textContent = 'Drag the waveform or click a section.';
    el.loop.disabled = true; el.clearSelection.disabled = true; el.extract.disabled = true; state.loop = false; el.loop.textContent = 'Loop'; if (el.alignmentNote) el.alignmentNote.textContent = state.beatAnalysis.bpm ? state.beatAnalysis.bpm.toFixed(1) + ' BPM · choose a range to snap' : 'Beat grid appears after analysis.';
    el.sectionTrack.querySelectorAll('.section-block').forEach(n => n.classList.remove('is-selected'));
    if (restartWithoutLoop) startPlayback(resumeAt).catch(err => console.error('clear selection restart failed', err));
  }

  function showBoundary(index) {
    const b = state.boundaries[index]; if (!b) return;
    el.boundaryTime.textContent = fmt(b.t);
    el.boundaryConfidence.textContent = b.confidence.toFixed(2);
    const mixEvidence = b.evidence && Number.isFinite(b.evidence.mix) ? b.evidence.mix : (b.source === 'mix' ? b.confidence : 0);
    const stemEvidence = b.evidence && Number.isFinite(b.evidence.stem) ? b.evidence.stem : (b.source === 'stem' ? b.confidence : 0);
    const repetitionEvidence = b.evidence && Number.isFinite(b.evidence.repetition) ? b.evidence.repetition : (b.source === 'repetition' ? b.confidence : 0);
    const sectionEvidence = b.evidence && Number.isFinite(b.evidence.section) ? b.evidence.section : (b.source === 'section-ai' ? b.confidence : 0);
    el.evidenceChange.textContent = mixEvidence ? mixEvidence.toFixed(2) : '—';
    el.evidenceStem.textContent = stemEvidence ? stemEvidence.toFixed(2) : (state.stems.vocals ? '0.00' : 'pending');
    el.evidenceRepetition.textContent = repetitionEvidence ? repetitionEvidence.toFixed(2) : (state.repetitionBoundaries.length ? '0.00' : 'pending');
    el.evidenceSection.textContent = sectionEvidence ? sectionEvidence.toFixed(2) : (state.sectionAI.status === 'ready' ? '0.00' : 'pending');
    const nearestVocal = nearestPhraseBoundary(b.t, state.vocalPhraseBoundaries, Infinity);
    el.evidenceVocal.textContent = nearestVocal ? 'Δ' + nearestVocal.distance.toFixed(2) + 's' : 'pending';
    const nearestBar = nearestGridTime(b.t, state.beatAnalysis.barTimes || [], Infinity);
    el.evidenceBeat.textContent = nearestBar ? 'Δ' + nearestBar.distance.toFixed(2) + 's' : 'pending';
    el.inspector.hidden = false;
  }

  function updatePlayhead() {
    const t = currentPlaybackTime();
    el.current.textContent = fmt(t);
    el.seek.value = String(t);
    if (state.duration) {
      el.playhead.hidden = false;
      el.playhead.style.left = `${pct(t)}%`;
    }
    if (state.playback.playing && !state.playback.raf) {
      state.playback.raf = requestAnimationFrame(() => {
        state.playback.raf = 0;
        updatePlayhead();
      });
    }
  }

  function setLoadedAudio(buffer, name, url, sourcePath) {
    resetStemState(true);
    state.mixBoundaries = [];
    state.repetitionBoundaries = [];
    state.repetitionPairs = [];
    state.repetitionPeriodSec = null;
    state.beatAnalysis = { bpm: null, confidence: 0, beatTimes: [], barTimes: [], boundaries: [] };
    state.consensusBoundaries = [];
    state.boundaries = [];
    if (state.objectUrl && state.objectUrl.startsWith('blob:')) URL.revokeObjectURL(state.objectUrl);
    state.audioBuffer = buffer; state.name = name; state.objectUrl = url; state.sourcePath = sourcePath || ''; state.duration = buffer.duration; state.mono = null;
    state.playback.sourceName = 'mix'; state.playback.buffers = {}; state.playback.pausedAt = 0;
    el.trackName.textContent = name; el.trackMeta.textContent = sourcePath ? 'Repository source · ' + sourcePath : 'Local audio file';
    el.seek.max = String(buffer.duration); el.seek.value = '0'; el.seek.disabled = false; el.play.disabled = false; el.stop.disabled = false; el.duration.textContent = fmt(buffer.duration); clearSelection(); renderPlaybackSourceUi(); updatePlayhead();
  }

  async function processBytes(bytes, name, audioUrl, sourcePath = '') {
    for (const step of ['decode', 'waveform', 'change', 'repetition', 'beat', 'demucs', 'section-ai', 'structure']) stepState(step, '');
    setProgress(.08, 'Decoding audio'); stepState('decode', 'active');
    const buffer = await decodeArrayBuffer(bytes); stepState('decode', 'done'); setLoadedAudio(buffer, name, audioUrl, sourcePath);
    setProgress(.35, 'Building waveform'); stepState('waveform', 'active');
    const mono = monoFromBuffer(buffer); state.mono = mono; state.envelope = buildEnvelope(mono); stepState('waveform', 'done'); drawWaveform(); renderRuler();
    setProgress(.50, 'Finding mix change points'); stepState('change', 'active');
    await new Promise(r => setTimeout(r, 0));
    state.mixBoundaries = analyzeChangePoints(mono, buffer.sampleRate);
    stepState('change', 'done');
    setProgress(.60, 'Finding repeated structure'); stepState('repetition', 'active');
    const recurrence = analyzeRepetition(mono, buffer.sampleRate);
    state.repetitionBoundaries = recurrence.boundaries;
    state.repetitionPairs = recurrence.pairs;
    state.repetitionPeriodSec = recurrence.selectedPeriodSec;
    stepState('repetition', 'done');
    setProgress(.66, 'Estimating beat / bar grid'); stepState('beat', 'active');
    state.beatAnalysis = analyzeBeatGrid(mono, buffer.sampleRate);
    stepState('beat', 'done');
    document.documentElement.dataset.beatGridReady = state.beatAnalysis.boundaries.length ? 'true' : 'false';
    if (el.alignmentNote) el.alignmentNote.textContent = state.beatAnalysis.bpm
      ? state.beatAnalysis.bpm.toFixed(1) + ' BPM · ' + state.beatAnalysis.barTimes.length + ' estimated bars'
      : 'Beat grid unavailable for this track.';
    state.consensusBoundaries = buildConsensusBoundaries(state.mixBoundaries, [], state.repetitionBoundaries);
    document.documentElement.dataset.consensusSources = state.repetitionBoundaries.length ? '2' : '1';
    refreshModeView();
    document.documentElement.dataset.structureCutterReady = 'true';
    await runWholeTrackDemucs(buffer);
  }

  async function loadRepositorySample(key) {
    const sample = REPO_SAMPLES[key]; if (!sample) return;
    el.loadSample.disabled = true; el.trackName.textContent = `Loading ${sample.title}…`; el.trackMeta.textContent = sample.path;
    try {
      const response = await fetch(sample.url); if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const bytes = await response.arrayBuffer(); await processBytes(bytes, sample.title, sample.url, sample.path);
    } catch (err) {
      console.error(err); el.trackName.textContent = 'Sample load failed'; el.trackMeta.textContent = String(err?.message || err); setProgress(0, 'Load failed');
    } finally { el.loadSample.disabled = !el.sampleSelect.value; }
  }

  function wavBlob(buffer, s, e) {
    const rate = buffer.sampleRate, channels = buffer.numberOfChannels, start = Math.floor(s * rate), end = Math.min(buffer.length, Math.ceil(e * rate)), frames = Math.max(0, end - start), bytes = 44 + frames * channels * 2;
    const ab = new ArrayBuffer(bytes), v = new DataView(ab); let p = 0;
    const str = x => { for (let i = 0; i < x.length; i++) v.setUint8(p++, x.charCodeAt(i)); };
    str('RIFF'); v.setUint32(p, bytes - 8, true); p += 4; str('WAVEfmt '); v.setUint32(p, 16, true); p += 4; v.setUint16(p, 1, true); p += 2; v.setUint16(p, channels, true); p += 2; v.setUint32(p, rate, true); p += 4; v.setUint32(p, rate * channels * 2, true); p += 4; v.setUint16(p, channels * 2, true); p += 2; v.setUint16(p, 16, true); p += 2; str('data'); v.setUint32(p, frames * channels * 2, true); p += 4;
    for (let i = start; i < end; i++) for (let c = 0; c < channels; c++) { const x = clamp(buffer.getChannelData(c)[i] || 0, -1, 1); v.setInt16(p, x < 0 ? x * 32768 : x * 32767, true); p += 2; }
    return new Blob([ab], { type: 'audio/wav' });
  }

  function extractSelection() {
    if (!state.audioBuffer || !state.selection) return;
    const blob = wavBlob(state.audioBuffer, state.selection.s, state.selection.e), a = document.createElement('a'), safe = (state.name || 'audio').replace(/\.[^.]+$/, '').replace(/[^\w.-]+/g, '_');
    a.href = URL.createObjectURL(blob); a.download = `${safe}_${state.selection.s.toFixed(2)}-${state.selection.e.toFixed(2)}.wav`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1500);
  }

  async function loadLocal(file) {
    const bytes = await file.arrayBuffer(), url = URL.createObjectURL(file); await processBytes(bytes, file.name, url, '');
  }

  function timeFromPointer(e) { const r = el.mixTrack.getBoundingClientRect(); return clamp((e.clientX - r.left) / Math.max(1, r.width), 0, 1) * state.duration; }

  async function runSelfTest() {
    const sr = 4000, seconds = 32, segmentSec = 8, frames = sr * seconds, x = new Float32Array(frames);
    const specs = [
      { freq: 170, amp: .25, pulse: 1.7 },
      { freq: 330, amp: .12, pulse: 3.1 },
      { freq: 170, amp: .25, pulse: 1.7 },
      { freq: 520, amp: .32, pulse: .8 }
    ];
    for (let i = 0; i < frames; i++) {
      const t = i / sr, region = Math.min(3, Math.floor(t / segmentSec)), local = t - region * segmentSec, spec = specs[region];
      const trem = 1 + .28 * Math.sin(2 * Math.PI * spec.pulse * local);
      x[i] = spec.amp * trem * Math.sin(2 * Math.PI * spec.freq * local);
    }
    for (let beat = 0; beat * .5 < seconds; beat++) {
      const start = Math.floor(beat * .5 * sr), amp = beat % 4 === 0 ? .8 : .32, clickFrames = Math.floor(.035 * sr);
      for (let i = 0; i < clickFrames && start + i < x.length; i++) {
        x[start + i] += amp * Math.exp(-i / (sr * .01)) * Math.sin(2 * Math.PI * 900 * i / sr);
      }
    }
    const buffer = { sampleRate: sr, numberOfChannels: 1, length: frames, duration: seconds, getChannelData: () => x };
    state.duration = buffer.duration; state.audioBuffer = buffer; state.name = 'selftest.wav'; state.mono = x; state.envelope = buildEnvelope(x);
    state.mixBoundaries = analyzeChangePoints(x, sr);
    state.beatAnalysis = analyzeBeatGrid(x, sr);
    const recurrence = analyzeRepetition(x, sr, [], { minPeriodSec: 10, maxPeriodSec: 22, blockSec: 5.5 });
    state.repetitionBoundaries = recurrence.boundaries;
    state.repetitionPairs = recurrence.pairs;
    state.repetitionPeriodSec = recurrence.selectedPeriodSec;

    const demucsFrames = Math.floor(seconds * DEMUCS_RATE), fake = {};
    for (const name of STEM_NAMES) {
      const a = new Float32Array(demucsFrames * 2);
      for (let i = 0; i < demucsFrames; i++) {
        const t = i / DEMUCS_RATE, region = Math.min(3, Math.floor(t / segmentSec));
        const pattern = region === 2 ? 0 : region;
        const amp = name === 'vocals' ? [.18, .48, .18, .24][pattern]
          : name === 'drums' ? [.34, .18, .34, .64][pattern]
          : name === 'bass' ? [.28, .12, .28, .2][pattern]
          : [.18, .42, .18, .24][pattern];
        const local = t % segmentSec;
        const phraseGate = name === 'vocals' && !(local > 1.0 && local < 5.2) ? 0 : 1;
        const v = amp * phraseGate * Math.sin(i * .047);
        a[i * 2] = v; a[i * 2 + 1] = v;
      }
      fake[name] = a;
    }
    await installStemResult(fake);

    await setPlaybackSource('vocals');
    const vocalSourceUiOk = state.playback.sourceName === 'vocals' &&
      document.querySelector('button[data-playback-source="vocals"]')?.classList.contains('is-active') &&
      document.documentElement.dataset.playbackSource === 'vocals';
    setSelection(2, 6, 'Playback source self-test');
    const selectionKeepsSource = state.playback.sourceName === 'vocals';
    clearSelection();
    const clearKeepsSource = state.playback.sourceName === 'vocals' && !state.loop;
    await setPlaybackSource('mix');
    const mixSourceUiOk = state.playback.sourceName === 'mix' &&
      document.querySelector('button[data-playback-source="mix"]')?.classList.contains('is-active');
    const playbackSourceUiOk = vocalSourceUiOk && selectionKeepsSource && clearKeepsSource && mixSourceUiOk;
    document.documentElement.dataset.playbackSourceVocalUi = vocalSourceUiOk ? 'PASS' : 'FAIL';
    document.documentElement.dataset.playbackSourceSelection = selectionKeepsSource ? 'PASS' : 'FAIL';
    document.documentElement.dataset.playbackSourceClear = clearKeepsSource ? 'PASS' : 'FAIL';
    document.documentElement.dataset.playbackSourceMixUi = mixSourceUiOk ? 'PASS' : 'FAIL';
    document.documentElement.dataset.playbackSourceSelftest = playbackSourceUiOk ? 'PASS' : 'FAIL';

    // Section AI browser regression uses deterministic logits rather than
    // downloading/running the real ONNX model in this cheap UI self-test.
    const aiFrames = seconds * 100;
    const aiSection = new Float32Array(aiFrames).fill(-Infinity);
    // Boundaries are >12 seconds apart because upstream functional
    // postprocessing uses a ±12 s peak-picking window.
    aiSection[600] = 9; aiSection[2200] = 10;
    const aiClasses = 10;
    const aiFunction = new Float32Array(aiClasses * aiFrames).fill(-5);
    const setAILabel = (start, end, label) => {
      for (let f = start; f < end; f++) aiFunction[label * aiFrames + f] = 5;
    };
    setAILabel(0, 600, 2);
    setAILabel(600, 2200, 8);
    setAILabel(2200, aiFrames, 9);
    const aiPost = postprocessFunctionalStructure(aiSection, aiFunction);
    const aiBoundaries = sectionAIBoundariesFromPostprocess(aiPost);
    state.sectionAI = {
      status: 'ready',
      provider: 'selftest',
      error: '',
      segments: aiPost.segments,
      boundaries: aiBoundaries,
      inferenceMs: 1,
      frames: aiFrames
    };
    state.consensusBoundaries = buildConsensusBoundaries(
      state.mixBoundaries,
      state.stemBoundaries,
      state.repetitionBoundaries,
      aiBoundaries
    );
    document.documentElement.dataset.sectionAiReady = 'true';
    document.documentElement.dataset.consensusSources = '4';

    state.mode = 'section-ai';
    refreshModeView();
    const sectionAiUiOk = state.sections.length === 3 &&
      state.sections.map(x => x.label).join(',') === 'INTRO,VERSE,CHORUS';
    document.documentElement.dataset.sectionAiSelftest = sectionAiUiOk ? 'PASS' : 'FAIL';
    state.mode = 'consensus';
    refreshModeView();

    renderRuler(); drawWaveform(); setSelection(2, 6, 'Self-test selection');
    const ok = state.sections.length >= 2 &&
      state.mixBoundaries.length >= 1 &&
      state.repetitionBoundaries.length >= 1 &&
      state.repetitionPairs.length >= 1 &&
      state.beatAnalysis.bpm && Math.abs(state.beatAnalysis.bpm - 120) < 4 &&
      state.beatAnalysis.boundaries.length >= 4 &&
      state.stemBoundaries.length >= 1 &&
      state.vocalPhrases.length >= 3 &&
      state.vocalPhraseBoundaries.length >= 6 &&
      state.sectionAI.boundaries.length === 2 &&
      state.sectionAI.segments.length === 3 &&
      state.consensusBoundaries.length >= 1 &&
      document.documentElement.dataset.consensusSources === '4' &&
      document.documentElement.dataset.sectionAiSelftest === 'PASS' &&
      document.documentElement.dataset.playbackSourceSelftest === 'PASS' &&
      !el.selectionOverlay.hidden &&
      STEM_NAMES.every(name => state.stemProfiles[name] && state.stemProfiles[name].length);
    document.documentElement.dataset.repetitionReady = state.repetitionBoundaries.length ? 'true' : 'false';
    document.documentElement.dataset.beatGridReady = state.beatAnalysis.boundaries.length ? 'true' : 'false';
    document.documentElement.dataset.vocalPhraseReady = state.vocalPhraseBoundaries.length ? 'true' : 'false';
    el.cutAlignment.value = 'low-energy';
    setSelection(7.72, 8.28, 'Low-energy UI self-test');
    const lowEnergyUiOk = state.selection && state.selection.alignmentMode === 'low-energy';
    document.documentElement.dataset.lowEnergyUiSelftest = lowEnergyUiOk ? 'PASS' : 'FAIL';
    el.cutAlignment.value = 'vocal';
    setSelection(1.18, 5.08, 'Vocal snap self-test');
    const vocalSnapOk = state.selection && state.selection.startKind === 'vocal' && state.selection.endKind === 'vocal';
    document.documentElement.dataset.vocalSnapSelftest = vocalSnapOk ? 'PASS' : 'FAIL';
    document.documentElement.dataset.structureCutterSelftest = ok && sectionAiUiOk && playbackSourceUiOk && vocalSnapOk && lowEnergyUiOk ? 'PASS' : 'FAIL';
    el.engineNotice.textContent = 'structure cutter self-test: ' + (ok && sectionAiUiOk && playbackSourceUiOk && vocalSnapOk && lowEnergyUiOk ? 'PASS' : 'FAIL');
  }

  el.sampleSelect.addEventListener('change', () => { el.loadSample.disabled = !el.sampleSelect.value; const s = REPO_SAMPLES[el.sampleSelect.value]; if (s) { el.trackName.textContent = s.title; el.trackMeta.textContent = `Repository source · ${s.path}`; } });
  el.loadSample.addEventListener('click', () => loadRepositorySample(el.sampleSelect.value));
  el.openFile.addEventListener('click', () => el.fileInput.click()); el.fileInput.addEventListener('change', () => { const f = el.fileInput.files?.[0]; if (f) loadLocal(f); });
  el.play.addEventListener('click', async () => { if (!state.audioBuffer) return; if (state.playback.playing) pausePlayback(); else await startPlayback(); });
  el.stop.addEventListener('click', () => { stopPlayback({ preservePosition: false }); state.playback.pausedAt = 0; updatePlayhead(); });
  el.seek.addEventListener('input', () => { seekPlayback(Number(el.seek.value) || 0).catch(err => console.error('seek failed', err)); });
  el.volume.addEventListener('input', () => { if (state.playback.gain) state.playback.gain.gain.value = clamp(Number(el.volume.value) / 100, 0, 1); });
  el.sectionTrack.addEventListener('click', e => { const b = e.target.closest('[data-section]'); if (!b) return; const s = state.sections[Number(b.dataset.section)]; if (s) setSelection(s.s, s.e, s.label); });
  el.boundaryLayer.addEventListener('click', e => { const b = e.target.closest('[data-boundary]'); if (b) showBoundary(Number(b.dataset.boundary)); }); el.closeInspector.addEventListener('click', () => el.inspector.hidden = true);
  el.modeTabs.addEventListener('click', e => {
    const b = e.target.closest('[data-mode]'); if (!b) return;
    state.mode = b.dataset.mode;
    el.modeTabs.querySelectorAll('.mode-tab').forEach(n => n.classList.toggle('is-active', n === b));
    if (b.dataset.pending === 'true') {
      el.engineNotice.textContent = b.textContent.trim() + ' engine is not connected yet; showing the current consensus while keeping this engine visibly pending.';
    } else if (state.mode === 'section-ai') {
      if (state.sectionAI.status === 'ready') {
        el.engineNotice.textContent = 'All-In-One Harmonix fold0 · ' + state.sectionAI.provider + ' · ' + state.sectionAI.segments.length + ' labeled sections · ' + state.sectionAI.inferenceMs.toFixed(0) + ' ms inference.';
      } else if (state.sectionAI.status === 'error') {
        el.engineNotice.textContent = 'Section AI unavailable: ' + state.sectionAI.error;
      } else {
        el.engineNotice.textContent = 'Section AI runs after HTDemucs because it consumes all four stems.';
      }
    } else if (state.mode === 'change-point') {
      el.engineNotice.textContent = 'Showing the live mix energy/ZCR change-point track.';
    } else if (state.mode === 'stem-activity') {
      el.engineNotice.textContent = state.stems.vocals ? 'Showing boundaries from HTDemucs stem energy-share changes.' : 'Stem Activity becomes available after HTDemucs finishes.';
    } else if (state.mode === 'repetition') {
      const periodText = state.repetitionPeriodSec ? ' Strongest recurrence lag: ' + state.repetitionPeriodSec.toFixed(1) + ' s.' : '';
      el.engineNotice.textContent = 'Showing M3-style recurrence boundaries from non-local repeated audio patterns.' + periodText;
    } else if (state.mode === 'beat-bars') {
      el.engineNotice.textContent = state.beatAnalysis.bpm
        ? 'Estimated beat/bar grid · ' + state.beatAnalysis.bpm.toFixed(1) + ' BPM · autocorrelation ' + state.beatAnalysis.confidence.toFixed(2) + '. Bars assume 4 beats and are editing aids, not semantic structure.'
        : 'Beat/bar grid could not be estimated reliably.';
    } else if (state.mode === 'vocal-phrase') {
      el.engineNotice.textContent = state.vocalPhrases.length
        ? 'Showing ' + state.vocalPhrases.length + ' vocal phrases from adaptive energy hysteresis on the HTDemucs vocals stem.'
        : 'Vocal Phrase becomes available after HTDemucs finishes.';
    } else {
      const sources = [state.mixBoundaries.length, state.repetitionBoundaries.length, state.stemBoundaries.length, state.sectionAI.boundaries.length].filter(Boolean).length;
      el.engineNotice.textContent = 'Consensus fuses ' + sources + ' live structural evidence tracks: mix change point, repetition, stem activity, and Section AI when available.';
    }
    refreshModeView();
  });
  el.toggleCompare.addEventListener('click', () => { el.comparePanel.hidden = !el.comparePanel.hidden; el.toggleCompare.textContent = el.comparePanel.hidden ? 'Compare engines' : 'Hide comparison'; });
  el.mixTrack.addEventListener('pointerdown', e => { if (!state.duration) return; state.dragStart = timeFromPointer(e); state.dragMoved = false; el.mixTrack.setPointerCapture?.(e.pointerId); });
  el.mixTrack.addEventListener('pointermove', e => { if (state.dragStart == null) return; const t = timeFromPointer(e); if (Math.abs(t - state.dragStart) > .06) state.dragMoved = true; setSelection(state.dragStart, t, 'Manual selection'); });
  el.mixTrack.addEventListener('pointerup', e => { if (state.dragStart == null) return; const t = timeFromPointer(e); if (!state.dragMoved) { seekPlayback(t).catch(err => console.error('waveform seek failed', err)); } else setSelection(state.dragStart, t, 'Manual selection'); state.dragStart = null; state.dragMoved = false; el.mixTrack.releasePointerCapture?.(e.pointerId); });
  el.mixTrack.addEventListener('pointercancel', () => { state.dragStart = null; state.dragMoved = false; });
  el.loop.addEventListener('click', async () => { if (!state.selection) return; const wasPlaying = state.playback.playing; const resumeAt = currentPlaybackTime(); state.loop = !state.loop; el.loop.textContent = state.loop ? 'Loop on' : 'Loop'; if (state.loop) await startPlayback(state.selection.s); else if (wasPlaying) await startPlayback(resumeAt); else updatePlayhead(); });
  el.clearSelection.addEventListener('click', clearSelection); el.extract.addEventListener('click', extractSelection);
  el.cutAlignment.addEventListener('change', () => {
    if (state.selection) setSelection(state.selection.rawS, state.selection.rawE, state.selection.title);
  });
  el.cancelProcessing.addEventListener('click', () => {
    if (state.demucs.controller && !state.demucs.controller.signal.aborted) state.demucs.controller.abort(new DOMException('cancel button', 'AbortError'));
  });
  document.querySelectorAll('button[data-playback-source]').forEach(button => button.addEventListener('click', () => { if (!button.disabled) setPlaybackSource(button.dataset.playbackSource).catch(err => console.error('source switch failed', err)); }));
  window.addEventListener('resize', () => { drawWaveform(); drawAllStemProfiles(); });

  state.gpuAvailable = !!navigator.gpu;
  el.gpuBadge.textContent = state.gpuAvailable ? 'WebGPU available · HTDemucs ready' : 'WebGPU unavailable · mix only';
  el.gpuBadge.classList.add(state.gpuAvailable ? 'good' : 'warn');
  renderPlaybackSourceUi();
  drawWaveform();
  window.__structureCutterLab = { state, REPO_SAMPLES, computeSectionAISpectrograms, postprocessFunctionalStructure, runSectionAIAnalysis, analyzeBeatGrid, analyzeChangePoints, analyzeRepetition, analyzeStemActivity, analyzeVocalPhrases, alignCutRange, alignLowEnergyRange, buildConsensusBoundaries, buildSections, nearestPhraseBoundary, currentPlaybackTime, setPlaybackSource, startPlayback, pausePlayback, seekPlayback, setSelection, clearSelection, installStemResult, runSelfTest };
  if (new URLSearchParams(location.search).get('selftest') === '1') setTimeout(() => runSelfTest(), 0);
})();
