import fs from 'node:fs';
import vm from 'node:vm';

const [htmlPath, appPath, cssPath] = process.argv.slice(2);
if(!htmlPath || !appPath || !cssPath) throw new Error('usage: node vocal-htdemucs-probe-regression.mjs <html> <app> <css>');

const html = fs.readFileSync(htmlPath, 'utf8'), src = fs.readFileSync(appPath, 'utf8'), css = fs.readFileSync(cssPath, 'utf8');

for(const required of ['Vocal HTDemucs Probe', 'backendSelect', 'precisionSelect', 'webgpuBadge', 'selectionStart', 'selectionEnd', 'stemGrid', 'processBtn']) {
  if(!html.includes(required)) throw new Error('HTML contract missing: ' + required);
}

for(const required of ['unblend', 'Separator.load', 'separator.separate', 'URL.revokeObjectURL', 'clearStemResults', 'wavBlobFromRange', 'normalizeSelection', 'runBrowserSelfTest']) {
  if(!src.includes(required)) throw new Error('JS contract missing: ' + required);
}

for(const required of ['.stem-grid', '.result-card']) {
  if(!css.includes(required)) throw new Error('CSS contract missing: ' + required);
}

function extractFunction(source,name){
  const start=source.indexOf('function '+name+'(');
  if(start<0)throw new Error('function not found: '+name);
  const brace=source.indexOf('{',start);
  let depth=0;
  for(let i=brace;i<source.length;i++){
    if(source[i]==='{')depth++;
    else if(source[i]==='}'){
      depth--;
      if(depth===0)return source.slice(start,i+1);
    }
  }
  throw new Error('unterminated function: '+name);
}

const ctx = { Math, Blob, ArrayBuffer, DataView };
vm.createContext(ctx);
vm.runInContext(extractFunction(src,'normalizeSelection') + ';' + extractFunction(src,'wavBlobFromRange') + ';this.normalizeSelection=normalizeSelection;this.wavBlobFromRange=wavBlobFromRange;', ctx);

const a = ctx.normalizeSelection(8, 2, 10);
if(a.start !== 2 || a.end !== 8) throw new Error('selection ordering wrong');
const b = ctx.normalizeSelection(-4, 50, 10);
if(b.start !== 0 || b.end !== 10) throw new Error('selection clamp wrong');

const rate = 10, data = new Float32Array(20);
data.fill(.1, 0, 10);
data.fill(.75, 10);
const fake = { sampleRate: rate, duration: 2, numberOfChannels: 2, getChannelData: () => data };
const crop = ctx.wavBlobFromRange(fake, 1.2, 1.6);
const ab = await crop.arrayBuffer();
const first = new DataView(ab).getInt16(44, true) / 32767;

if(Math.abs(first - .75) > .02) throw new Error('mid-file WAV crop started from source head');
console.log('mid-file WAV crop: PASS');

if(!/clearStemResults/.test(src) || !/URL\.revokeObjectURL/.test(src)) throw new Error('separation result lifecycle reset missing');
console.log('result lifecycle contract: PASS');

console.log('Vocal HTDemucs Probe regression: PASS');
