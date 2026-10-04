import fs from 'node:fs';
import vm from 'node:vm';

const [htmlPath,appPath,cssPath]=process.argv.slice(2);
if(!htmlPath||!appPath||!cssPath)throw new Error('usage: node vocal-htdemucs-probe-regression.mjs <html> <app> <css>');
const html=fs.readFileSync(htmlPath,'utf8'),src=fs.readFileSync(appPath,'utf8'),css=fs.readFileSync(cssPath,'utf8');

for(const required of ['Vocal HTDemucs Probe','backendSelect','precisionSelect','selectionStart','selectionEnd','licenseText','stemGrid'])if(!html.includes(required))throw new Error('HTML contract missing: '+required);
for(const required of ["import { Separator } from 'unblend'","onnxruntime-web@1.26.0","separatorLoader","cropAudioBuffer","sliceRangeChannels","clearStemResults","separator?.unload","runBrowserSelfTest"])if(!src.includes(required))throw new Error('JS contract missing: '+required);
for(const required of ['.stem-grid','.stem-card','.status','.primary'])if(!css.includes(required))throw new Error('CSS contract missing: '+required);

function extractFunction(source,name){const start=source.indexOf('function '+name+'(');if(start<0)throw new Error('function not found: '+name);const brace=source.indexOf('{',start);let depth=0;for(let i=brace;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'){depth--;if(depth===0)return source.slice(start,i+1)}}throw new Error('unterminated function: '+name);}
const ctx={Math,Float32Array};vm.createContext(ctx);
vm.runInContext(
  extractFunction(src,'clamp')+';'+
  extractFunction(src,'normalizeSelection')+';'+
  extractFunction(src,'sliceRangeChannels')+
  ';this.normalizeSelection=normalizeSelection;this.sliceRangeChannels=sliceRangeChannels;',
  ctx
);
const r=ctx.normalizeSelection(8,2,10);if(r.start!==2||r.end!==8)throw new Error('selection ordering wrong');
const rate=10,data=new Float32Array(20);data.fill(.125,0,10);data.fill(.75,10);
const fake={sampleRate:rate,duration:2,numberOfChannels:2,getChannelData:()=>data};
const slice=ctx.sliceRangeChannels(fake,1.2,1.6);
if(slice.length!==4)throw new Error('range length wrong');
if(Math.abs(slice.channels[0][0]-.75)>.001)throw new Error('actual crop helper started at source head');
if(!/separatorLoader\(MODEL,/.test(src))throw new Error('real path does not use injectable separator loader');
if(!/renderStems\(result,r\)/.test(src))throw new Error('real result path missing');
console.log('actual range helper: PASS');
console.log('fresh separator lifecycle contract: PASS');
console.log('Vocal HTDemucs Probe regression: PASS');
