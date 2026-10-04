import fs from 'node:fs';
import vm from 'node:vm';

const htmlPath=process.argv[2];
if(!htmlPath)throw new Error('usage: node annotation-explorer-regression.mjs <index.html>');
const html=fs.readFileSync(htmlPath,'utf8');

for(const required of [
  'Annotation Explorer','Tree → Time','TIME → TREE','PLAYHEAD → TREE','RAW CONTINUOUS TIME',
  'selectionStartSec','selectionEndSec','setSelection','computeTreeMatches','intersectTwo',
  '同一Tree内はOR、Tree間はAND','区間番号への変換は行いません','pointermove','選択時間 WAV'
]) if(!html.includes(required)) throw new Error('missing contract: '+required);

if(html.includes('startIndex')) throw new Error('segment index selection leaked into Annotation Explorer');
if(html.includes('selectionRange()')) throw new Error('Segment Window range model leaked into Annotation Explorer');

const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
if(scripts.length!==1)throw new Error('expected one inline script, got '+scripts.length);
new Function(scripts[0]);
console.log('syntax: PASS');

function extractFunction(source,name){
  const start=source.indexOf('function '+name+'(');if(start<0)throw new Error('function not found: '+name);
  const brace=source.indexOf('{',start);let depth=0;
  for(let i=brace;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'){depth--;if(depth===0)return source.slice(start,i+1)}}
  throw new Error('unterminated function: '+name);
}
const src=scripts[0],ctx={Math};
vm.createContext(ctx);
vm.runInContext(extractFunction(src,'normalizeRanges')+';'+extractFunction(src,'intersectTwo')+';this.normalizeRanges=normalizeRanges;this.intersectTwo=intersectTwo;',ctx);
const a=[{s:1.23,e:4.56},{s:8.1,e:9.2}],b=[{s:2.34,e:5.67},{s:8.6,e:10.0}];
const x=ctx.intersectTwo(a,b);
if(x.length!==2||Math.abs(x[0].s-2.34)>1e-9||Math.abs(x[0].e-4.56)>1e-9||Math.abs(x[1].s-8.6)>1e-9||Math.abs(x[1].e-9.2)>1e-9)throw new Error('continuous time intersection failed');
console.log('continuous-time intersection: PASS');

for(const pattern of [
  /el\.tree\.addEventListener\('click',[\s\S]*?setSelection\(Number\(b\.dataset\.selectS\),Number\(b\.dataset\.selectE\),'tree-occurrence'\)/,
  /el\.laneGrid\.addEventListener\('click',[\s\S]*?setSelection\(Number\(b\.dataset\.selectS\),Number\(b\.dataset\.selectE\),'timeline-annotation'\)/,
  /el\.waveWrap\.addEventListener\('pointermove',[\s\S]*?setSelection\(state\.dragAnchor,t,'wave-drag'\)/,
  /bindTimeInput\(el\.startRange,el\.startNumber,'start'\)/,
  /bindTimeInput\(el\.endRange,el\.endNumber,'end'\)/
]) if(!pattern.test(src))throw new Error('interaction wiring missing: '+String(pattern));
console.log('interaction wiring: PASS');

console.log('Annotation Explorer regression: PASS');
