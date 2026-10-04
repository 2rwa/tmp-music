import fs from 'node:fs';
import vm from 'node:vm';

const appPath = process.argv[2] || 'docs/m6-status/sonic-chronicle/app.js';
const htmlPath = process.argv[3] || 'docs/m6-status/sonic-chronicle/index.html';
const cssPath = process.argv[4] || 'docs/m6-status/sonic-chronicle/style.css';

class ClassList {
  constructor(){this.s=new Set()}
  add(...xs){xs.forEach(x=>this.s.add(x))}
  remove(...xs){xs.forEach(x=>this.s.delete(x))}
  toggle(x,on){if(on===undefined) on=!this.s.has(x);on?this.s.add(x):this.s.delete(x);return on}
  contains(x){return this.s.has(x)}
}
class ElementStub {
  constructor(id=''){
    this.id=id;this.style={};this.dataset={};this.disabled=false;this.hidden=false;this.checked=true;this.value='';this.files=[];
    this.textContent='';this._innerHTML='';this.listeners=new Map();this.classList=new ClassList();this.children=[];this.parentElement=this;
    this.currentTime=0;this.duration=6;this.paused=true;this.ended=false;this.playbackRate=1;this.tagName='DIV';
  }
  set innerHTML(v){this._innerHTML=String(v);this._entryNodes=new Map();for(const m of this._innerHTML.matchAll(/data-entry-id="([^"]+)"/g)){const n=new ElementStub('entry');n.dataset.entryId=m[1];this._entryNodes.set(m[1],n)}this._metricCards=[];for(const m of this._innerHTML.matchAll(/class="metric-card" data-filter="([^"]+)"/g)){const n=new ElementStub('metric');n.dataset.filter=m[1];this._metricCards.push(n)}this._eventLists=[...this._innerHTML.matchAll(/class="event-list"/g)].map(()=>new ElementStub('events'))}
  get innerHTML(){return this._innerHTML}
  addEventListener(name,fn){const xs=this.listeners.get(name)||[];xs.push(fn);this.listeners.set(name,xs)}
  dispatch(name,event={}){for(const fn of this.listeners.get(name)||[]) fn({type:name,preventDefault(){},...event})}
  click(){this.dispatch('click',{target:this})}
  play(){this.paused=false;this.dispatch('play',{target:this});return Promise.resolve()}
  pause(){this.paused=true;this.dispatch('pause',{target:this})}
  appendChild(n){this.children.push(n);n.parentElement=this;return n}
  remove(){}
  querySelectorAll(sel){if(sel==='.entry.is-current') return [...(this._entryNodes?.values()||[])].filter(n=>n.classList.contains('is-current'));if(sel==='.metric-card') return this._metricCards||[];if(sel==='.event-list') return this._eventLists||[];if(sel==='.mini-segment,.mini-event') return this.children.filter(n=>n.className?.includes('mini-'));return[]}
  querySelector(sel){const m=sel.match(/\[data-entry-id="([^"]+)"\]/);if(m)return this._entryNodes?.get(m[1])||null;return null}
  closest(){return null}
  scrollIntoView(opts){this.lastScrollIntoView=opts}
  getBoundingClientRect(){return{left:0,top:0,width:100,height:600,right:100,bottom:600}}
}

const ids=['loader-panel','drop-zone','choose-file','file-input','audio','status','progress','cancel-analysis','export-json','synthetic-test','file-chip','play-toggle','back-5','forward-5','current-time','duration-time','seek','speed','follow-toggle','return-now','loop-current','mode-note','chronicle-scroll','chronicle','entry-count','minimap','minimap-playhead','comparison','comparison-body','clear-comparison','provenance'];
const elements=new Map(ids.map(id=>['#'+id,new ElementStub(id)]));
const density=['read','detail','raw'].map(x=>{const e=new ElementStub('density-'+x);e.dataset.density=x;return e});
const filters=['pitch','periodicity','spectrum','modulation','events'].map(x=>{const e=new ElementStub('filter-'+x);e.dataset.filter=x;e.checked=true;return e});
const body=new ElementStub('body');body.dataset={};
const documentElement=new ElementStub('html');documentElement.dataset={};
const document={
  body,documentElement,
  querySelector:(s)=>elements.get(s)||new ElementStub(s),
  querySelectorAll:(s)=>s==='.density'?density:s==='[data-filter]'?filters:[],
  createElement:(tag)=>{const e=new ElementStub(tag);e.tagName=tag.toUpperCase();return e}
};
const context={console,document,location:{search:'?selftest=1'},URLSearchParams,URL,Blob,Math,Number,Array,Float32Array,Float64Array,Map,Set,Promise,setTimeout,clearTimeout,Date,devicePixelRatio:1,requestAnimationFrame:(fn)=>setTimeout(()=>fn(Date.now()),0),cancelAnimationFrame:clearTimeout};
context.window=context;context.window.AudioContext=null;context.window.webkitAudioContext=null;context.addEventListener=()=>{};
vm.createContext(context);
vm.runInContext(fs.readFileSync(appPath,'utf8'),context,{filename:appPath});

const started=Date.now();
while(!documentElement.dataset.selftest||documentElement.dataset.selftest==='running'){
  if(Date.now()-started>20000) throw new Error(`timeout selftest=${documentElement.dataset.selftest||'unset'} status=${elements.get('#status').textContent}`);
  await new Promise(r=>setTimeout(r,25));
}
if(documentElement.dataset.selftest!=='pass') throw new Error(`synthetic selftest failed: ${elements.get('#status').textContent}`);
const entryCount=Number(documentElement.dataset.chronicleEntries);
if(entryCount<3) throw new Error(`too few chronicle entries: ${entryCount}`);
if(!elements.get('#chronicle').innerHTML.includes('前区間')) throw new Error('delta-from-previous text did not render');
if(!elements.get('#chronicle').innerHTML.includes('なぜそう判断した？')) throw new Error('Evidence UI did not render');
if(!elements.get('#chronicle').innerHTML.includes('音高・周期の確かさ')) throw new Error('readable metric labels missing');
console.log(`synthetic: PASS · ${entryCount} intervals`);

const api=context.window.__sonicTest;
const audio=elements.get('#audio');audio.hidden=false;audio.currentTime=3.5;audio.paused=false;api.syncPlayhead(3.5,true);
if(!documentElement.dataset.currentEntry) throw new Error('NOW entry was not tracked');
if(elements.get('#current-time').textContent==='00:00.00') throw new Error('transport clock did not update');
console.log(`playhead: ${elements.get('#current-time').textContent} · current=${documentElement.dataset.currentEntry}`);

api.setFollow('FOLLOW');elements.get('#chronicle-scroll').dispatch('wheel');
if(documentElement.dataset.followMode!=='BROWSE') throw new Error('manual scroll did not switch FOLLOW -> BROWSE');
if(audio.paused) throw new Error('manual browsing paused audio');
elements.get('#return-now').dispatch('click');
if(documentElement.dataset.followMode!=='FOLLOW') throw new Error('return-now did not restore FOLLOW');
console.log('follow/browse: PASS');

elements.get('#seek').value='4.2';elements.get('#seek').dispatch('input');
if(Math.abs(audio.currentTime-4.2)>.001) throw new Error(`seek did not update audio.currentTime: ${audio.currentTime}`);
if(Math.abs(api.state.playhead-4.2)>.001) throw new Error('seek did not redraw playhead state');
console.log('seek: PASS');

density.find(x=>x.dataset.density==='detail').dispatch('click');
if(documentElement.dataset.density!=='detail'||body.dataset.density!=='detail') throw new Error('density change did not update UI state');
const pitchFilter=filters.find(x=>x.dataset.filter==='pitch');pitchFilter.checked=false;pitchFilter.dispatch('change');
if((documentElement.dataset.filters||'').split(',').includes('pitch')) throw new Error('filter state did not update');
const pitchCards=elements.get('#chronicle')._metricCards.filter(x=>x.dataset.filter==='pitch');
if(!pitchCards.length||pitchCards.some(x=>x.dataset.filterHidden!=='1')) throw new Error('pitch cards did not hide');
console.log('density/filter: PASS');

if(documentElement.dataset.minimap!=='ready') throw new Error('minimap did not render');
if(elements.get('#minimap').children.length<entryCount) throw new Error('minimap missing interval segments');
console.log('minimap: PASS');

const html=fs.readFileSync(htmlPath,'utf8'),css=fs.readFileSync(cssPath,'utf8');
for(const required of ['Sonic Chronicle','解析クロニクル','現在位置へ戻る','何を読みたい？','20ms']) if(!html.includes(required)) throw new Error(`HTML missing ${required}`);
if(!/\.transport\{[^}]*position:sticky/s.test(css)) throw new Error('desktop sticky transport regression');
if(!/@media\(max-width:560px\)[\s\S]*?\.transport\{[^}]*position:fixed/s.test(css)) throw new Error('mobile fixed transport regression');
if(!/body\{[^}]*overflow-x:hidden/s.test(css)) throw new Error('page horizontal overflow guard missing');
if(/\.chronicle[^\{]*\{[^}]*min-width\s*:\s*(?:[5-9]\d\d|\d{4,})px/s.test(css)) throw new Error('chronicle forces wide min-width');
if(!/\.metric-grid\{[^}]*minmax\(0,1fr\)/s.test(css)) throw new Error('responsive metric grid missing');
if(!css.includes('color-scheme:light')) throw new Error('warm editorial light palette missing');
if(!css.includes('--bg:#f2eee5')||!css.includes('--accent:#a64b32')) throw new Error('paper/rust design tokens regressed');
if(!css.includes('Hiragino Mincho ProN')) throw new Error('editorial serif heading contract missing');
if(!css.includes('--transport:#24211c')) throw new Error('warm equipment transport palette missing');
for(const legacy of ['#090e18','#111827','#69c7d8','#8bd5e1']) if(css.includes(legacy)) throw new Error('legacy cool-blue palette returned: '+legacy);
console.log('warm editorial design: PASS');
console.log('responsive/static contracts: PASS');
