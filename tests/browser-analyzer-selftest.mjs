import fs from 'node:fs';
import vm from 'node:vm';

const appPaths = process.argv.slice(2).length ? process.argv.slice(2) : ['docs/m6-status/timeline-browser/app-1.js','docs/m6-status/timeline-browser/app-2.js','docs/m6-status/timeline-browser/app-3.js','docs/m6-status/timeline-browser/app-4a.js','docs/m6-status/timeline-browser/app-4b.js','docs/m6-status/timeline-browser/app-5.js'];

class ElementStub {
  constructor(id = '') {
    this.id = id;
    this.style = {};
    this.dataset = {};
    this.disabled = false;
    this.hidden = false;
    this.checked = true;
    this.innerHTML = '';
    this.textContent = '';
    this.files = [];
    this.parentElement = this;
    this.currentTime = 0;
    this.paused = true;
    this.ended = false;
    this.listeners = new Map();
    this.tagName = id === 'details' ? 'DETAILS' : 'DIV';
    this.open = false;
    this.classList = { add() {}, remove() {} };
  }
  addEventListener(name, fn) {
    const xs = this.listeners.get(name) || [];
    xs.push(fn); this.listeners.set(name, xs);
  }
  dispatch(name, event = {}) { for (const fn of this.listeners.get(name) || []) fn({ type: name, ...event }); }
  setPointerCapture() {}
  click() {}
  querySelectorAll() { return []; }
  querySelector() { return null; }
  closest() { return null; }
  scrollIntoView() {}
  getBoundingClientRect() { return { width: 1200, height: 820, left: 0, top: 0 }; }
}

const ids = [
  'timeline', 'tooltip', 'file-input', 'choose-file', 'drop-zone', 'audio', 'status', 'progress',
  'cancel-analysis', 'export-json', 'synthetic-test', 'show-low', 'show-segments', 'show-movement',
  'show-register', 'reset-view', 'summary', 'provenance', 'playback-insights', 'playback-state',
  'playback-time', 'playback-overview', 'insight-f0', 'insight-voice', 'insight-spectrum',
  'insight-pitch', 'playhead-line', 'playhead-label', 'overview-panel', 'overview-timeline',
  'overview-playhead', 'overview-playhead-label', 'overview-readout', 'chronicle-panel', 'chronicle-log',
  'chronicle-count', 'follow-log', 'jump-current-log'
];
const elements = new Map(ids.map((id) => [`#${id}`, new ElementStub(id)]));
const canvasContext = {
  setTransform() {}, clearRect() {}, fillRect() {}, strokeRect() {}, fillText() {}, beginPath() {},
  moveTo() {}, lineTo() {}, stroke() {}, setLineDash() {}, fillStyle: '', strokeStyle: '', font: '',
  textAlign: '', lineWidth: 1, globalAlpha: 1,
};
elements.get('#timeline').getContext = () => canvasContext;
elements.get('#overview-timeline').getContext = () => canvasContext;

const documentElement = new ElementStub('html');
const document = {
  documentElement,
  querySelector: (selector) => elements.get(selector) ?? new ElementStub(selector),
  createElement: () => new ElementStub('created'),
};
const palette = {
  '--f0': '#72d6ff', '--f0low': '#526b82', '--cpps': '#ffd166', '--hnr': '#7ee787',
  '--tilt': '#ff9f68', '--rms': '#a5b4fc', '--vib': '#69dbd0', '--rate': '#f78fb3',
  '--reg': '#ff78c6', '--move': 'rgba(255,166,77,.13)', '--line': '#263653',
  '--muted': '#9faecc', '--text': '#edf3ff', '--playhead': '#ffe082',
  '--state-quiet':'#374151', '--state-periodic':'#45c7a1', '--state-transient':'#ff9f68', '--state-mixed':'#7185a5'
};

const context = {
  console,
  document,
  location: { search: '?selftest=1' },
  devicePixelRatio: 1,
  URLSearchParams,
  URL,
  Blob,
  Math,
  Number,
  Array,
  Float32Array,
  Float64Array,
  Map,
  Set,
  Promise,
  setTimeout,
  clearTimeout,
  requestAnimationFrame: (fn) => setTimeout(() => fn(Date.now()), 0),
  cancelAnimationFrame: (id) => clearTimeout(id),
  getComputedStyle: (el) => ({ getPropertyValue: (name) => palette[name] || '', height: el?.id === 'overview-timeline' ? '188px' : '820px' }),
  addEventListener: () => {},
};
context.window = context;
context.window.AudioContext = null;
context.window.webkitAudioContext = null;

vm.createContext(context);
for (const appPath of appPaths) vm.runInContext(fs.readFileSync(appPath, 'utf8'), context, { filename: appPath });

const started = Date.now();
while (!documentElement.dataset.selftest || documentElement.dataset.selftest === 'running') {
  if (Date.now() - started > 15000) {
    throw new Error(`timeout: selftest=${documentElement.dataset.selftest || 'unset'} status=${elements.get('#status').textContent}`);
  }
  await new Promise((resolve) => setTimeout(resolve, 20));
}

const status = elements.get('#status').textContent;
const summary = elements.get('#summary').innerHTML;
console.log(`browser analyzer selftest: ${documentElement.dataset.selftest}`);
console.log(status);
if (documentElement.dataset.selftest !== 'pass') process.exit(1);
if (!/median F0 22\d\.\d Hz/.test(status)) throw new Error(`unexpected F0 status: ${status}`);
if (!summary.includes('analysis frames') || !summary.includes('median HNR')) throw new Error('summary did not render expected fields');

const audio = elements.get('#audio');
audio.hidden = false;
audio.currentTime = 1.20;
audio.paused = false;
audio.dispatch('play');
await new Promise((resolve) => setTimeout(resolve, 40));
audio.paused = true;
audio.dispatch('pause');
await new Promise((resolve) => setTimeout(resolve, 20));

const playhead = Number(documentElement.dataset.playhead);
if (Math.abs(playhead - 1.20) > 0.02) throw new Error(`playhead did not follow playback: ${playhead}`);
if (elements.get('#playhead-line').hidden) throw new Error('playhead overlay stayed hidden during playback');
if (!elements.get('#playback-overview').textContent) throw new Error('playback overview did not render');
if (!elements.get('#insight-f0').innerHTML.includes('F0') || !elements.get('#insight-spectrum').innerHTML.includes('RMS')) {
  throw new Error('live parameter explanations did not render');
}
console.log(`playhead regression: ${playhead.toFixed(2)} s · live explanations rendered`);

const overview = elements.get('#overview-timeline');
if (documentElement.dataset.overviewTimeline !== 'ready' || overview.dataset.rendered !== 'ready') {
  throw new Error('overview timeline did not render');
}
const counts = JSON.parse(overview.dataset.stateCounts || '{}');
if (!counts.periodic || counts.periodic < 20) throw new Error(`overview classification missing periodic frames: ${overview.dataset.stateCounts}`);

audio.hidden = false;
audio.currentTime = 0;
audio.paused = true;
overview.dispatch('pointerdown', { clientX: 600 });
await new Promise((resolve) => setTimeout(resolve, 20));
const expectedSeek = 2.8 * ((600 - 58) / (1200 - 58 - 16));
if (Math.abs(audio.currentTime - expectedSeek) > 0.08) {
  throw new Error(`overview click seek failed: got ${audio.currentTime}, expected ${expectedSeek}`);
}
if (!elements.get('#overview-readout').textContent.includes('RMS')) throw new Error('overview readout did not update after seek');
console.log(`overview regression: rendered states ${overview.dataset.stateCounts} · click seek ${audio.currentTime.toFixed(2)} s`);

const logCount = Number(documentElement.dataset.chronicleEntries);
if (!Number.isFinite(logCount) || logCount < 1) throw new Error(`chronicle entries missing: ${documentElement.dataset.chronicleEntries}`);
const chronicleHtml = elements.get('#chronicle-log').innerHTML;
if (!chronicleHtml.includes('生フレーム') || !chronicleHtml.includes('周期音')) throw new Error('chronicle did not render readable state logs');
if (!documentElement.dataset.chronicleCurrent) throw new Error('chronicle current playback item was not tracked');
if (!elements.get('#chronicle-count').textContent.includes('logs')) throw new Error('chronicle count missing');
console.log(`chronicle regression: ${logCount} logs · current ${documentElement.dataset.chronicleCurrent}`);
