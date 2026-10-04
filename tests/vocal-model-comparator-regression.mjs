import fs from 'node:fs';
import vm from 'node:vm';
const [htmlPath,appPath,cssPath]=process.argv.slice(2);
if(!htmlPath||!appPath||!cssPath)throw new Error('usage: node vocal-model-comparator-regression.mjs <html> <app> <css>');
const html=fs.readFileSync(htmlPath,'utf8'),src=fs.readFileSync(appPath,'utf8'),css=fs.readFileSync(cssPath,'utf8');
for(const required of ['Vocal Model Comparator','比較モデル','比較結果','modelGrid','compareBtn','results'])if(!html.includes(required))throw new Error('HTML contract missing: '+required);
for(const required of ['web-audio-separation@0.3.1/+esm','runComparison','runOneModel','cloneUrls','wavBlobFromRange','clearResults','executionProviders:[\'webgpu\',\'wasm\']','runBrowserSelfTest'])if(!src.includes(required))throw new Error('JS contract missing: '+required);
for(const required of ['.model-grid','.results','.result-card','.primary'])if(!css.includes(required))throw new Error('CSS contract missing: '+required);
new Function(src);
function extractFunction(source,name){const start=source.indexOf('function '+name+'(');if(start<0)throw new Error('function not found: '+name);const brace=source.indexOf('{',start);let depth=0;for(let i=brace;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'){depth--;if(depth===0)return source.slice(start,i+1)}}throw new Error('unterminated function: '+name);}
const ctx={Math,Blob,ArrayBuffer,DataView};vm.createContext(ctx);vm.runInContext(extractFunction(src,'normalizeSelection')+';'+extractFunction(src,'wavBlobFromRange')+';this.normalizeSelection=normalizeSelection;this.wavBlobFromRange=wavBlobFromRange;',ctx);
const r=ctx.normalizeSelection(8,2,10);if(r.start!==2||r.end!==8)throw new Error('selection ordering wrong');
const rate=10,data=new Float32Array(20);data.fill(.1,0,10);data.fill(.8,10);const fake={sampleRate:rate,duration:2,numberOfChannels:2,getChannelData:()=>data};const blob=ctx.wavBlobFromRange(fake,1.2,1.6),ab=await blob.arrayBuffer(),first=new DataView(ab).getInt16(44,true)/32767;if(Math.abs(first-.8)>.02)throw new Error('comparator mid-file crop started from source head');
if(!/for\(let i=0;i<models\.length;i\+\+\)/.test(src))throw new Error('models are not processed sequentially');
if(!/mod\.createSeparator\(model,config\(\)\)/.test(src))throw new Error('fresh separator per model missing');
if(!/if\(changed&&state\.results\.length\)clearResults\('selection changed'\)/.test(src))throw new Error('selection-change invalidation missing');
console.log('mid-file crop: PASS');
console.log('sequential fresh-model lifecycle: PASS');
console.log('Vocal Model Comparator regression: PASS');
