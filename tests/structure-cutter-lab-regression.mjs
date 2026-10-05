import fs from 'node:fs';
const root = process.argv[2];
if (!root) throw new Error('usage: node structure-cutter-lab-regression.mjs <directory>');
const html = fs.readFileSync(`${root}/index.html`, 'utf8');
const js = fs.readFileSync(`${root}/app.js`, 'utf8');
const css = fs.readFileSync(`${root}/style.css`, 'utf8');

for (const token of [
  'Structure Cutter Lab','STRUCTURE VIEW','Consensus','Section AI','Repetition','Change Point',
  'Stem Activity','Beat / Bars','Vocal Phrase','Compare engines','Extract MIX WAV','PLAYBACK SOURCES','MIX','VOCALS','DRUMS','BASS','OTHER','stop-playback',
  'stem-vocals','stem-drums','stem-bass','stem-other','evidence-section','evidence-repetition','evidence-vocal','evidence-beat','cut-alignment','Vocal phrase edge','Low energy','Cancel'
]) if (!html.includes(token)) throw new Error(`missing UI contract: ${token}`);

for (const token of [
  "import { Separator } from 'unblend'","DEMUCS_MODEL = 'htdemucs'","backend: 'webgpu'","precision: 'fp16'",
  'samples/whisper-ao/source/whisper-ao.mp3','samples/jugemu/source/jugemu.mp3',
  'samples/chichinu-fiija/source/chichinu-fiija.mp3','runWholeTrackDemucs','prepareWholeTrackForDemucs',
  'computeSectionAISpectrograms','postprocessFunctionalStructure','runSectionAIInference','runSectionAIAnalysis','dataset.sectionAiReady','currentPlaybackTime','selectedPlaybackNames','playbackSelectionKey','setPlaybackSource','startPlayback','pausePlayback','seekPlayback','stemMergeWavBlob','mergedStemSample','MAX_STEM_PLAYBACK = 3','state.playback','playback.stemNames','node.loop = true','dataset.playbackSource','dataset.playbackSourceCount','analyzeBeatGrid','alignCutRange','alignLowEnergyRange','analyzeRepetition','analyzeStemActivity','analyzeVocalPhrases','nearestPhraseBoundary','buildConsensusBoundaries','installStemResult','dataset.consensusSources'
]) if (!js.includes(token)) throw new Error(`missing behavior contract: ${token}`);


if (js.includes('auditionStem') || js.includes('state.audition') || js.includes('el.audio.play') || js.includes('data-stem-audition')) {
  throw new Error('legacy dual-player stem audition path must be removed');
}
if (!js.includes("if (state.loop && state.playback.playing) startPlayback(s)")) {
  throw new Error('selection changes must restart the active loop source');
}
if (!js.includes("const restartWithoutLoop = state.loop && state.playback.playing")) {
  throw new Error('clearing a selection must clear the loop source');
}
if (!js.includes("Maximum 3 stems. Deselect one before adding another.")) {
  throw new Error('1–3 stem selection limit must be visible');
}
if (!js.includes("stemMergeWavBlob(names, state.selection.s, state.selection.e)")) {
  throw new Error('WAV export must follow selected playback stems');
}

for (const token of [
  '.timeline-card','.boundary-marker','.selection-overlay','.compare-panel',
  '.stem-vocal','.stem-drums','.stem-bass','.stem-other','.stem-track','.micro-button'
]) if (!css.includes(token)) throw new Error(`missing visual contract: ${token}`);

new Function(
  js
    .replace("import { Separator } from 'unblend';", '')
    .replace("import { analyzeRepetition } from './repetition-core.js';", '')
    .replace("import { analyzeBeatGrid, alignCutRange, nearestGridTime } from './beat-core.js';", '')
    .replace("import { analyzeVocalPhrases, nearestPhraseBoundary } from './vocal-core.js';", '')
    .replace("import { alignLowEnergyRange } from './cut-core.js';", '')
    .replace("import { computeSectionAISpectrograms } from './section-ai-features.js';", '')
    .replace("import { postprocessFunctionalStructure } from './section-ai-postprocess.js';", '')
    .replace("import { runSectionAIInference } from './section-ai-runtime.js';", '')
);
console.log('Structure Cutter Lab regression: PASS');
