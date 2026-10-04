import fs from 'node:fs';
const root = process.argv[2];
if (!root) throw new Error('usage: node structure-cutter-lab-regression.mjs <directory>');
const html = fs.readFileSync(`${root}/index.html`, 'utf8');
const js = fs.readFileSync(`${root}/app.js`, 'utf8');
const css = fs.readFileSync(`${root}/style.css`, 'utf8');

for (const token of [
  'Structure Cutter Lab','STRUCTURE VIEW','Consensus','Section AI','Repetition','Change Point',
  'Stem Activity','Beat / Bars','Vocal Phrase','Compare engines','Extract WAV',
  'stem-vocals','stem-drums','stem-bass','stem-other','evidence-repetition','Cancel'
]) if (!html.includes(token)) throw new Error(`missing UI contract: ${token}`);

for (const token of [
  "import { Separator } from 'unblend'","DEMUCS_MODEL = 'htdemucs'","backend: 'webgpu'","precision: 'fp16'",
  'samples/whisper-ao/source/whisper-ao.mp3','samples/jugemu/source/jugemu.mp3',
  'samples/chichinu-fiija/source/chichinu-fiija.mp3','runWholeTrackDemucs','prepareWholeTrackForDemucs',
  'analyzeRepetition','analyzeStemActivity','buildConsensusBoundaries','installStemResult','dataset.consensusSources'
]) if (!js.includes(token)) throw new Error(`missing behavior contract: ${token}`);

for (const token of [
  '.timeline-card','.boundary-marker','.selection-overlay','.compare-panel',
  '.stem-vocal','.stem-drums','.stem-bass','.stem-other','.stem-track','.micro-button'
]) if (!css.includes(token)) throw new Error(`missing visual contract: ${token}`);

new Function(
  js
    .replace("import { Separator } from 'unblend';", '')
    .replace("import { analyzeRepetition } from './repetition-core.js';", '')
);
console.log('Structure Cutter Lab regression: PASS');
