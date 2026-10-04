(() => {
  'use strict';

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
    trackName: $('track-name'), trackMeta: $('track-meta'), progressPanel: $('progress-panel'), progressTitle: $('progress-title'), progressPercent: $('progress-percent'), progressFill: $('progress-fill'),
    audio: $('audio'), play: $('play-toggle'), seek: $('seek'), current: $('time-current'), duration: $('time-duration'), volume: $('volume'),
    modeTabs: $('mode-tabs'), engineNotice: $('engine-notice'), toggleCompare: $('toggle-compare'), comparePanel: $('compare-panel'), compareGrid: $('compare-grid'),
    ruler: $('timeline-ruler'), sectionTrack: $('section-track'), mixTrack: $('mix-track'), waveform: $('waveform'), selectionOverlay: $('selection-overlay'), playhead: $('playhead'), boundaryLayer: $('boundary-layer'),
    selectionTitle: $('selection-title'), selectionTime: $('selection-time'), loop: $('loop-toggle'), clearSelection: $('clear-selection'), extract: $('extract-selection'),
    inspector: $('boundary-inspector'), closeInspector: $('close-inspector'), boundaryTime: $('boundary-time'), boundaryConfidence: $('boundary-confidence'), evidenceChange: $('evidence-change')
  };

  const state = {
    audioBuffer: null,
    objectUrl: '',
    name: '',
    sourcePath: '',
    duration: 0,
    envelope: [],
    boundaries: [],
    sections: [],
    selection: null,
    dragStart: null,
    dragMoved: false,
    loop: false,
    mode: 'consensus'
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
    return chosen.map(x => ({ ...x, confidence: clamp(x.score / max, 0.25, 1) }));
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
      ['Consensus', 'live'], ['Section AI', 'pending'], ['Repetition', 'pending'], ['Change Point', 'live'], ['Stem Activity', 'pending'], ['Beat / Downbeat', 'pending']
    ];
    el.compareGrid.innerHTML = rows.map(([name, status]) => {
      const marks = status === 'live' ? state.boundaries.map(b => `<span class="compare-dot" style="left:${pct(b.t)}%"></span>`).join('') : '<span class="compare-pending">engine pending</span>';
      return `<div class="compare-row"><div class="compare-name">${name}</div><div class="compare-track">${marks}</div></div>`;
    }).join('');
  }

  function setSelection(s, e, title = 'Manual selection') {
    if (!state.duration) return;
    s = clamp(Math.min(s, e), 0, state.duration); e = clamp(Math.max(s, e), 0, state.duration);
    if (e - s < .02) e = Math.min(state.duration, s + .02);
    state.selection = { s, e, title };
    el.selectionOverlay.hidden = false; el.selectionOverlay.style.left = `${pct(s)}%`; el.selectionOverlay.style.width = `${pct(e) - pct(s)}%`;
    el.selectionTitle.textContent = title; el.selectionTime.textContent = `${fmt(s)} → ${fmt(e)} · ${(e - s).toFixed(2)} sec`;
    el.loop.disabled = false; el.clearSelection.disabled = false; el.extract.disabled = !state.audioBuffer;
    el.sectionTrack.querySelectorAll('.section-block').forEach((n, i) => n.classList.toggle('is-selected', state.sections[i] && Math.abs(state.sections[i].s - s) < .03 && Math.abs(state.sections[i].e - e) < .03));
  }

  function clearSelection() {
    state.selection = null; el.selectionOverlay.hidden = true; el.selectionTitle.textContent = 'No range selected'; el.selectionTime.textContent = 'Drag the waveform or click a section.';
    el.loop.disabled = true; el.clearSelection.disabled = true; el.extract.disabled = true; state.loop = false; el.loop.textContent = 'Loop';
    el.sectionTrack.querySelectorAll('.section-block').forEach(n => n.classList.remove('is-selected'));
  }

  function showBoundary(index) {
    const b = state.boundaries[index]; if (!b) return;
    el.boundaryTime.textContent = fmt(b.t); el.boundaryConfidence.textContent = b.confidence.toFixed(2); el.evidenceChange.textContent = b.score.toFixed(2); el.inspector.hidden = false;
  }

  function updatePlayhead() {
    const t = el.audio.currentTime || 0; el.current.textContent = fmt(t); el.seek.value = String(t);
    if (state.duration) { el.playhead.hidden = false; el.playhead.style.left = `${pct(t)}%`; }
    if (state.loop && state.selection && t >= state.selection.e - .015) { el.audio.currentTime = state.selection.s; if (el.audio.paused) el.audio.play().catch(() => {}); }
  }

  function setLoadedAudio(buffer, name, url, sourcePath) {
    if (state.objectUrl && state.objectUrl.startsWith('blob:')) URL.revokeObjectURL(state.objectUrl);
    state.audioBuffer = buffer; state.name = name; state.objectUrl = url; state.sourcePath = sourcePath || ''; state.duration = buffer.duration;
    el.audio.src = url; el.trackName.textContent = name; el.trackMeta.textContent = sourcePath ? `Repository source · ${sourcePath}` : 'Local audio file';
    el.seek.max = String(buffer.duration); el.seek.value = '0'; el.seek.disabled = false; el.play.disabled = false; el.duration.textContent = fmt(buffer.duration); clearSelection();
  }

  async function processBytes(bytes, name, audioUrl, sourcePath = '') {
    setProgress(.08, 'Decoding audio'); stepState('decode', 'active');
    const buffer = await decodeArrayBuffer(bytes); stepState('decode', 'done'); setLoadedAudio(buffer, name, audioUrl, sourcePath);
    setProgress(.35, 'Building waveform'); stepState('waveform', 'active');
    const mono = monoFromBuffer(buffer); state.envelope = buildEnvelope(mono); stepState('waveform', 'done'); drawWaveform(); renderRuler();
    setProgress(.62, 'Finding prototype change points'); stepState('change', 'active');
    await new Promise(r => setTimeout(r, 0)); state.boundaries = analyzeChangePoints(mono, buffer.sampleRate); state.sections = buildSections(state.boundaries); stepState('change', 'done');
    renderSections(); renderBoundaries(); renderCompare(); setProgress(1, 'UI prototype ready');
    el.progressPercent.textContent = `${state.boundaries.length} boundaries`;
    document.documentElement.dataset.structureCutterReady = 'true';
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

  function runSelfTest() {
    const sr = 8000, seconds = 24, frames = sr * seconds, x = new Float32Array(frames);
    for (let i = 0; i < frames; i++) { const t = i / sr, amp = t < 7 ? .12 : t < 14 ? .48 : t < 19 ? .2 : .62; x[i] = amp * Math.sin(2 * Math.PI * (t < 14 ? 180 : 260) * t); }
    const buffer = { sampleRate: sr, numberOfChannels: 1, length: frames, duration: seconds, getChannelData: () => x };
    state.duration = buffer.duration; state.audioBuffer = buffer; state.name = 'selftest.wav'; state.envelope = buildEnvelope(x); state.boundaries = analyzeChangePoints(x, sr); state.sections = buildSections(state.boundaries); renderSections(); renderBoundaries(); renderCompare(); renderRuler(); drawWaveform(); setSelection(2, 6, 'Self-test selection');
    const ok = state.sections.length >= 2 && state.boundaries.length >= 1 && !el.selectionOverlay.hidden && el.sectionTrack.querySelectorAll('.section-block').length === state.sections.length;
    document.documentElement.dataset.structureCutterSelftest = ok ? 'PASS' : 'FAIL'; el.engineNotice.textContent = `structure cutter self-test: ${ok ? 'PASS' : 'FAIL'}`;
  }

  el.sampleSelect.addEventListener('change', () => { el.loadSample.disabled = !el.sampleSelect.value; const s = REPO_SAMPLES[el.sampleSelect.value]; if (s) { el.trackName.textContent = s.title; el.trackMeta.textContent = `Repository source · ${s.path}`; } });
  el.loadSample.addEventListener('click', () => loadRepositorySample(el.sampleSelect.value));
  el.openFile.addEventListener('click', () => el.fileInput.click()); el.fileInput.addEventListener('change', () => { const f = el.fileInput.files?.[0]; if (f) loadLocal(f); });
  el.play.addEventListener('click', async () => { if (!el.audio.src) return; if (el.audio.paused) await el.audio.play(); else el.audio.pause(); });
  el.audio.addEventListener('play', () => el.play.textContent = '❚❚'); el.audio.addEventListener('pause', () => el.play.textContent = '▶'); el.audio.addEventListener('timeupdate', updatePlayhead);
  el.seek.addEventListener('input', () => { el.audio.currentTime = Number(el.seek.value) || 0; updatePlayhead(); }); el.volume.addEventListener('input', () => el.audio.volume = clamp(Number(el.volume.value) / 100, 0, 1));
  el.sectionTrack.addEventListener('click', e => { const b = e.target.closest('[data-section]'); if (!b) return; const s = state.sections[Number(b.dataset.section)]; if (s) setSelection(s.s, s.e, s.label); });
  el.boundaryLayer.addEventListener('click', e => { const b = e.target.closest('[data-boundary]'); if (b) showBoundary(Number(b.dataset.boundary)); }); el.closeInspector.addEventListener('click', () => el.inspector.hidden = true);
  el.modeTabs.addEventListener('click', e => { const b = e.target.closest('[data-mode]'); if (!b) return; state.mode = b.dataset.mode; el.modeTabs.querySelectorAll('.mode-tab').forEach(n => n.classList.toggle('is-active', n === b)); el.engineNotice.textContent = b.dataset.pending === 'true' ? `${b.textContent.trim()} engine is not connected yet; the timeline remains on real prototype change points.` : (state.mode === 'change-point' ? 'Showing the live prototype energy/ZCR change-point track.' : 'Prototype consensus currently equals the live change-point track until additional engines are connected.'); });
  el.toggleCompare.addEventListener('click', () => { el.comparePanel.hidden = !el.comparePanel.hidden; el.toggleCompare.textContent = el.comparePanel.hidden ? 'Compare engines' : 'Hide comparison'; });
  el.mixTrack.addEventListener('pointerdown', e => { if (!state.duration) return; state.dragStart = timeFromPointer(e); state.dragMoved = false; el.mixTrack.setPointerCapture?.(e.pointerId); });
  el.mixTrack.addEventListener('pointermove', e => { if (state.dragStart == null) return; const t = timeFromPointer(e); if (Math.abs(t - state.dragStart) > .06) state.dragMoved = true; setSelection(state.dragStart, t, 'Manual selection'); });
  el.mixTrack.addEventListener('pointerup', e => { if (state.dragStart == null) return; const t = timeFromPointer(e); if (!state.dragMoved) { el.audio.currentTime = t; updatePlayhead(); } else setSelection(state.dragStart, t, 'Manual selection'); state.dragStart = null; state.dragMoved = false; el.mixTrack.releasePointerCapture?.(e.pointerId); });
  el.mixTrack.addEventListener('pointercancel', () => { state.dragStart = null; state.dragMoved = false; });
  el.loop.addEventListener('click', () => { if (!state.selection) return; state.loop = !state.loop; el.loop.textContent = state.loop ? 'Loop on' : 'Loop'; if (state.loop) { el.audio.currentTime = state.selection.s; el.audio.play().catch(() => {}); } });
  el.clearSelection.addEventListener('click', clearSelection); el.extract.addEventListener('click', extractSelection);
  window.addEventListener('resize', drawWaveform);

  const gpu = !!navigator.gpu; el.gpuBadge.textContent = gpu ? 'WebGPU available' : 'WebGPU unavailable'; el.gpuBadge.classList.add(gpu ? 'good' : 'warn');
  el.audio.volume = Number(el.volume.value) / 100;
  drawWaveform();
  window.__structureCutterLab = { state, REPO_SAMPLES, analyzeChangePoints, buildSections, setSelection, runSelfTest };
  if (new URLSearchParams(location.search).get('selftest') === '1') setTimeout(runSelfTest, 0);
})();
