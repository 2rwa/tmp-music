import fs from 'node:fs';
import vm from 'node:vm';
const [htmlPath,appPath,cssPath]=process.argv.slice(2);
if(!htmlPath||!appPath||!cssPath)throw new Error('usage: node vocal-separation-lab-regression.mjs <html> <app> <css>');
const html=fs.readFileSync(htmlPath,'utf8'),src=fs.readFileSync(appPath,'utf8'),css=fs.readFileSync(cssPath,'utf8');
for(const required of ['Vocal Separation Lab','P0 · 即時DSP比較','P2 · 分離する区間','P1 · MDX AI分離','webgpuBadge','selectionStart','selectionEnd','stemGrid'])if(!html.includes(required))throw new Error('HTML contract missing: '+required);
for(const required of ['web-audio-separation@0.3.1/+esm','UVR_MDXNET_KARA_2','executionProviders:[\'webgpu\',\'wasm\']','wavBlobFromRange','separator.separate(segmentUrl)','centerCancelSample','normalizeSelection'])if(!src.includes(required))throw new Error('JS contract missing: '+required);
for(const required of ['--accent:#e9a94b','.mode.active','.stem-grid'])if(!css.includes(required))throw new Error('CSS contract missing: '+required);
new Function(src);
function extractFunction(source,name){const start=source.indexOf('function '+name+'(');if(start<0)throw new Error('function not found: '+name);const brace=source.indexOf('{',start);let depth=0;for(let i=brace;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'){depth--;if(depth===0)return source.slice(start,i+1)}}throw new Error('unterminated function: '+name);}
const ctx={Math};vm.createContext(ctx);vm.runInContext(extractFunction(src,'centerCancelSample')+';'+extractFunction(src,'normalizeSelection')+';this.centerCancelSample=centerCancelSample;this.normalizeSelection=normalizeSelection;',ctx);
if(ctx.centerCancelSample(.4,.4)!==0)throw new Error('centered sample must cancel');
if(Math.abs(ctx.centerCancelSample(1,-1)-1)>1e-12)throw new Error('side sample math wrong');
const a=ctx.normalizeSelection(8,2,10);if(a.start!==2||a.end!==8)throw new Error('selection ordering wrong');
const b=ctx.normalizeSelection(-4,50,10);if(b.start!==0||b.end!==10)throw new Error('selection clamp wrong');
console.log('Vocal Separation Lab regression: PASS');
