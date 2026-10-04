(() => {
'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const el = {
  drop: $('#drop-zone'), choose: $('#choose-file'), file: $('#file-input'), synthetic: $('#synthetic-test'), cancel: $('#cancel-analysis'),
  status: $('#status'), progress: $('#progress'), fileChip: $('#file-chip'), audio: $('#audio'), workspace: $('#workspace'),
  waveform: $('#waveform'), waveWrap: $('#wave-wrap'), play: $('#play-toggle'), playSelection: $('#play-selection'), playContext: $('#play-context'),
  loop: $('#loop-toggle'), seek: $('#seek'), current: $('#current-time'), duration: $('#duration-time'), volume: $('#volume'), volumeValue: $('#volume-value'),
  rangeStart: $('#range-start'), rangeEnd: $('#range-end'), rangeCount: $('#range-count'), rangeTime: $('#range-time'), rangeDuration: $('#range-duration'),
  start: $('#start-slider'), startValue: $('#start-value'), startMaxLabel: $('#start-max-label'), span: $('#span-slider'), spanValue: $('#span-value'), presets: $('#span-presets'),
  prevOne: $('#prev-one'), nextOne: $('#next-one'), prevWindow: $('#prev-window'), nextWindow: $('#next-window'), fromCurrent: $('#from-current'),
  strip: $('#segment-strip'), total: $('#segment-total'), download: $('#download-selection'), provenance: $('#provenance')
};

const state = {
  data: null,
  segments: [],
  sourceAudio: null,
  sourceMono: null,
  objectUrl: null,
  abortToken: 0,
  analyzing: false,
  startIndex: 0,
  span: 1,
  loopEnabled: false,
  playbackMode: 'track',
  playbackRange: null,
  raf: 0,
  currentSegment: -1,
  drawCount: 0
};

const clamp = (v,a,b) => Math.max(a, Math.min(b, v));
const sleep = (ms=0) => new Promise(r => setTimeout(r, ms));
function percentile(arr,p){const v=arr.filter(Number.isFinite);if(!v.length)return NaN;const s=[...v].sort((a,b)=>a-b);const i=(s.length-1)*p,lo=Math.floor(i),hi=Math.ceil(i);return s[lo]+(s[hi]-s[lo])*(i-lo)}
const median = (a) => percentile(a,.5);
function timeCode(sec){sec=Math.max(0,Number(sec)||0);const m=Math.floor(sec/60),s=sec-m*60;return `${String(m).padStart(2,'0')}:${s.toFixed(2).padStart(5,'0')}`}
function fmt(v,d=2){return Number.isFinite(Number(v)) ? Number(v).toFixed(d) : '—'}
function setStatus(s){el.status.textContent=s}
function setProgress(p){el.progress.style.width=`${clamp(p,0,1)*100}%`}
function setAnalyzing(on){state.analyzing=on;el.cancel.disabled=!on;el.file.disabled=on;el.choose.disabled=on;el.synthetic.disabled=on}

function fft(re,im,inverse=false){
  const n=re.length;
  for(let i=1,j=0;i<n;i++){let bit=n>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit;if(i<j){[re[i],re[j]]=[re[j],re[i]];[im[i],im[j]]=[im[j],im[i]]}}
  for(let len=2;len<=n;len<<=1){const ang=2*Math.PI/len*(inverse?1:-1),wr0=Math.cos(ang),wi0=Math.sin(ang);for(let i=0;i<n;i+=len){let wr=1,wi=0;for(let j=0;j<len/2;j++){const ur=re[i+j],ui=im[i+j],k=i+j+len/2,vr=re[k]*wr-im[k]*wi,vi=re[k]*wi+im[k]*wr;re[i+j]=ur+vr;im[i+j]=ui+vi;re[k]=ur-vr;im[k]=ui-vi;const nwr=wr*wr0-wi*wi0;wi=wr*wi0+wi*wr0;wr=nwr}}}
  if(inverse)for(let i=0;i<n;i++){re[i]/=n;im[i]/=n}
}
function regression(xs,ys){const n=Math.min(xs.length,ys.length);if(n<2)return{slope:0,intercept:ys[0]||0,r2:0};let sx=0,sy=0,sxx=0,sxy=0;for(let i=0;i<n;i++){sx+=xs[i];sy+=ys[i];sxx+=xs[i]*xs[i];sxy+=xs[i]*ys[i]}const den=n*sxx-sx*sx,slope=Math.abs(den)<1e-12?0:(n*sxy-sx*sy)/den,intercept=(sy-slope*sx)/n,mean=sy/n;let tot=0,res=0;for(let i=0;i<n;i++){const pred=intercept+slope*xs[i];tot+=(ys[i]-mean)**2;res+=(ys[i]-pred)**2}return{slope,intercept,r2:tot>1e-12?clamp(1-res/tot,0,1):0}}
function resampleLinear(input,srcRate,dstRate){if(srcRate<=dstRate+1)return{samples:input,rate:srcRate};const ratio=srcRate/dstRate,out=new Float32Array(Math.floor(input.length/ratio));for(let i=0;i<out.length;i++){const p=i*ratio,i0=Math.floor(p),i1=Math.min(input.length-1,i0+1),a=p-i0;out[i]=input[i0]*(1-a)+input[i1]*a}return{samples:out,rate:dstRate}}
function downmix(buffer){const n=buffer.length,ch=buffer.numberOfChannels,mono=new Float32Array(n);for(let c=0;c<ch;c++){const src=buffer.getChannelData(c);for(let i=0;i<n;i++)mono[i]+=src[i]/ch}return mono}
function downmixChannels(channels){const n=Math.min(...channels.map(ch=>ch.length)),mono=new Float32Array(n);for(const src of channels)for(let i=0;i<n;i++)mono[i]+=src[i]/channels.length;return mono}
function frameMetrics(samples,sr,start,fftSize,window,work){
  const {re,im,pow,acR,acI,cepR,cepI,cmnd}=work;let sumSq=0,mean=0;
  for(let i=0;i<fftSize;i++)mean+=samples[start+i]||0;mean/=fftSize;
  for(let i=0;i<fftSize;i++){const x=(samples[start+i]||0)-mean;sumSq+=x*x;re[i]=x*window[i];im[i]=0}
  const rms=Math.sqrt(sumSq/fftSize),rmsDb=20*Math.log10(rms+1e-12);fft(re,im,false);for(let i=0;i<fftSize;i++)pow[i]=re[i]*re[i]+im[i]*im[i];
  for(let i=0;i<fftSize;i++){acR[i]=pow[i];acI[i]=0}fft(acR,acI,true);const ac0=Math.max(1e-12,acR[0]),minLag=Math.max(2,Math.floor(sr/1200)),maxLag=Math.min(Math.floor(sr/55),Math.floor(fftSize/2)-2);let chosen=-1,best=Infinity,cum=0;cmnd[0]=1;
  for(let lag=1;lag<=maxLag;lag++){const d=Math.max(0,2*(ac0-acR[lag]));cum+=d;cmnd[lag]=d*lag/Math.max(cum,1e-12)}
  for(let lag=minLag+1;lag<maxLag-1;lag++){if(cmnd[lag]<.18&&cmnd[lag]<=cmnd[lag-1]&&cmnd[lag]<=cmnd[lag+1]){chosen=lag;break}if(cmnd[lag]<best){best=cmnd[lag];chosen=lag}}
  let refined=chosen;if(chosen>minLag&&chosen<maxLag){const a=cmnd[chosen-1],b=cmnd[chosen],c=cmnd[chosen+1],den=a-2*b+c;if(Math.abs(den)>1e-9)refined=chosen+.5*(a-c)/den}
  let confidence=chosen>0?clamp(1-cmnd[chosen],0,1):0;if(rmsDb<-55)confidence*=clamp((rmsDb+70)/15,0,1);const f0=confidence>.15&&refined>0?sr/refined:NaN,lagIdx=clamp(Math.round(refined||1),1,maxLag),corr=clamp(acR[lagIdx]/ac0,.0001,.9999),hnr=10*Math.log10(corr/(1-corr));
  const half=fftSize>>1,xs=[],ys=[],minBin=Math.max(1,Math.ceil(200*fftSize/sr)),maxHz=Math.min(5000,sr*.45),maxBin=Math.min(half-1,Math.floor(maxHz*fftSize/sr));for(let k=minBin;k<=maxBin;k++){xs.push(Math.log2((k*sr/fftSize)/1000));ys.push(10*Math.log10(pow[k]+1e-18))}const tilt=regression(xs,ys).slope;
  for(let i=0;i<fftSize;i++){cepR[i]=0;cepI[i]=0}cepR[0]=Math.log(pow[0]+1e-18);for(let k=1;k<half;k++){const lp=Math.log(pow[k]+1e-18);cepR[k]=lp;cepR[fftSize-k]=lp}cepR[half]=Math.log(pow[half]+1e-18);fft(cepR,cepI,true);
  return{rmsDb,f0,confidence,hnr,tilt};
}
function classify(q){if(!q||q.rmsDb<-55)return'quiet';if((q.rmsDb>-38&&q.confidence<.45&&q.hnr<4)||(q.tilt>-3&&q.confidence<.4&&q.rmsDb>-48))return'transient';if(Number.isFinite(q.f0)&&q.confidence>=.6&&q.hnr>=5)return'periodic';return'mixed'}
function smoothKinds(frames){const raw=frames.map(classify),order=['quiet','periodic','transient','mixed'];if(raw.length<5)return raw;return raw.map((k,i)=>{const c=Object.fromEntries(order.map(x=>[x,0]));for(let j=Math.max(0,i-2);j<=Math.min(raw.length-1,i+2);j++)c[raw[j]]++;return order.reduce((best,x)=>c[x]>c[best]?x:best,k)})}
function buildSegments(data){const {frames}=data;if(!frames.length)return data.duration_s>0?[{id:1,s:0,e:data.duration_s,kind:'mixed',frames:0}]:[];const kinds=smoothKinds(frames),out=[];let start=0;for(let i=1;i<=frames.length;i++){if(i<frames.length&&kinds[i]===kinds[start])continue;const end=i-1,s=Math.max(0,frames[start].t-data.frame_hop_ms/2000),e=Math.min(data.duration_s,frames[end].t+data.frame_hop_ms/2000);out.push({id:out.length+1,s,e,kind:kinds[start],frames:end-start+1});start=i}return out}
async function analyzePcm(samples,sr,meta,token){
  const targetRate=Math.min(24000,sr);setStatus(`resampling ${fmt(sr,0)} Hz → ${fmt(targetRate,0)} Hz`);await sleep();const rr=resampleLinear(samples,sr,targetRate);samples=rr.samples;sr=rr.rate;
  const fftSize=1024,hop=Math.max(1,Math.round(sr*.020)),duration=samples.length/sr,frameCount=Math.max(0,Math.floor((samples.length-fftSize)/hop)+1),window=new Float64Array(fftSize);for(let i=0;i<fftSize;i++)window[i]=.5-.5*Math.cos(2*Math.PI*i/(fftSize-1));
  const work={re:new Float64Array(fftSize),im:new Float64Array(fftSize),pow:new Float64Array(fftSize),acR:new Float64Array(fftSize),acI:new Float64Array(fftSize),cepR:new Float64Array(fftSize),cepI:new Float64Array(fftSize),cmnd:new Float64Array(fftSize)},frames=[];
  for(let fi=0;fi<frameCount;fi++){if(token!==state.abortToken)throw new Error('cancelled');const start=fi*hop,m=frameMetrics(samples,sr,start,fftSize,window,work);frames.push({t:(start+fftSize/2)/sr,...m});if((fi&31)===0){setProgress(frameCount?fi/frameCount:.0);setStatus(`区間解析 ${fi.toLocaleString()} / ${frameCount.toLocaleString()}`);await sleep()}}
  setProgress(1);return{name:meta.name||'audio',mime:meta.mime||'',duration_s:duration,source_sample_rate_hz:meta.sourceRate||sr,analysis_sample_rate_hz:sr,frame_hop_ms:hop/sr*1000,fft_size:fftSize,frames};
}

function selectionRange(){
  if(!state.segments.length)return null;
  const span=clamp(state.span,1,state.segments.length),maxStart=Math.max(0,state.segments.length-span),startIndex=clamp(state.startIndex,0,maxStart),endIndex=Math.min(state.segments.length-1,startIndex+span-1),first=state.segments[startIndex],last=state.segments[endIndex];
  return{startIndex,endIndex,count:endIndex-startIndex+1,s:first.s,e:last.e,duration:last.e-first.s};
}
function setStart(index,scroll=true){
  if(!state.segments.length)return;
  const maxStart=Math.max(0,state.segments.length-state.span);state.startIndex=clamp(Math.round(Number(index)||0),0,maxStart);updateSelection(scroll);
}
function setSpan(value){
  if(!state.segments.length)return;
  state.span=clamp(Math.round(Number(value)||1),1,state.segments.length);state.startIndex=clamp(state.startIndex,0,Math.max(0,state.segments.length-state.span));updateSelection(true);
}
function moveStart(delta){setStart(state.startIndex+delta,true)}
function currentSegmentIndex(t=el.audio.currentTime||0){if(!state.segments.length)return-1;let best=0;for(let i=0;i<state.segments.length;i++){const s=state.segments[i];if(t>=s.s&&t<=s.e)return i;if(s.s<=t)best=i;else break}return best}
function contextRange(){const r=selectionRange();if(!r)return null;const si=Math.max(0,r.startIndex-2),ei=Math.min(state.segments.length-1,r.endIndex+2);return{s:state.segments[si].s,e:state.segments[ei].e,startIndex:si,endIndex:ei,count:ei-si+1}}

function updateSelection(scrollStrip=false){
  const r=selectionRange();if(!r)return;
  el.start.max=String(Math.max(1,state.segments.length-state.span+1));el.start.value=String(r.startIndex+1);el.startValue.textContent=String(r.startIndex+1);el.startMaxLabel.textContent=`#${Math.max(1,state.segments.length-state.span+1)}`;
  el.span.max=String(state.segments.length);el.span.value=String(state.span);el.spanValue.textContent=String(state.span);
  el.rangeStart.textContent=`#${r.startIndex+1}`;el.rangeEnd.textContent=`#${r.endIndex+1}`;el.rangeCount.textContent=`${r.count}区間`;el.rangeTime.textContent=`${timeCode(r.s)}–${timeCode(r.e)}`;el.rangeDuration.textContent=`${r.duration.toFixed(2)}秒`;
  $$('#span-presets button').forEach(b=>{const v=b.dataset.span==='all'?state.segments.length:Number(b.dataset.span);b.classList.toggle('is-active',v===state.span);b.disabled=state.analyzing||v>state.segments.length});
  Array.from(el.strip.children).forEach((node,i)=>node.classList.toggle('is-selected',i>=r.startIndex&&i<=r.endIndex));
  if(scrollStrip){const node=el.strip.children[r.startIndex];node?.scrollIntoView?.({block:'nearest',inline:'center',behavior:'smooth'})}
  document.documentElement.dataset.selectionRange=`${r.startIndex}:${r.endIndex}`;document.documentElement.dataset.selectionCount=String(r.count);document.documentElement.dataset.selectionSeconds=r.duration.toFixed(4);
  drawWaveform();
}
function updateCurrentSegment(){
  const idx=currentSegmentIndex();if(idx===state.currentSegment)return;state.currentSegment=idx;Array.from(el.strip.children).forEach((node,i)=>node.classList.toggle('is-current',i===idx));document.documentElement.dataset.currentSegment=String(idx);
}
function renderSegments(){
  el.strip.innerHTML='';for(const [i,s] of state.segments.entries()){const b=document.createElement('button');b.type='button';b.className=`segment-cell ${s.kind}`;b.dataset.index=String(i);b.title=`#${i+1} ${timeCode(s.s)}–${timeCode(s.e)} · ${s.kind}`;b.setAttribute('aria-label',`区間 ${i+1}`);el.strip.appendChild(b)}el.total.textContent=`${state.segments.length.toLocaleString()}区間`;
}
function enableUi(on){
  const nodes=[el.play,el.playSelection,el.playContext,el.loop,el.seek,el.volume,el.start,el.span,el.prevOne,el.nextOne,el.prevWindow,el.nextWindow,el.fromCurrent,el.download];for(const n of nodes)n.disabled=!on;$$('#span-presets button').forEach(b=>b.disabled=!on);el.workspace.classList.toggle('is-disabled',!on);
}

function getCanvasSize(){const rect=el.waveform.getBoundingClientRect(),dpr=Math.max(1,window.devicePixelRatio||1),w=Math.max(1,Math.round(rect.width*dpr)),h=Math.max(1,Math.round(rect.height*dpr));if(el.waveform.width!==w||el.waveform.height!==h){el.waveform.width=w;el.waveform.height=h}return{w,h,dpr}}
function drawWaveform(){
  const {w,h}=getCanvasSize(),ctx=el.waveform.getContext('2d');ctx.clearRect(0,0,w,h);ctx.fillStyle='#1d1c19';ctx.fillRect(0,0,w,h);if(!state.sourceMono||!state.data){ctx.fillStyle='#746e65';ctx.font=`${12*(window.devicePixelRatio||1)}px system-ui`;ctx.fillText('音声を読み込むと波形を表示します',18,32);return}
  const dur=Math.max(.001,state.data.duration_s),r=selectionRange(),x0=r?r.s/dur*w:0,x1=r?r.e/dur*w:0;
  if(r){ctx.fillStyle='rgba(181,91,54,.26)';ctx.fillRect(x0,0,Math.max(2,x1-x0),h)}
  ctx.strokeStyle='#8b877f';ctx.lineWidth=Math.max(1,window.devicePixelRatio||1);ctx.beginPath();const mid=h/2,n=state.sourceMono.length,cols=Math.max(1,Math.floor(w));for(let x=0;x<cols;x++){const a=Math.floor(x/cols*n),b=Math.max(a+1,Math.floor((x+1)/cols*n));let peak=0;for(let i=a;i<b;i++)peak=Math.max(peak,Math.abs(state.sourceMono[i]||0));const y=peak*(h*.43);ctx.moveTo(x,mid-y);ctx.lineTo(x,mid+y)}ctx.stroke();
  if(state.segments.length){ctx.strokeStyle='rgba(238,230,216,.12)';ctx.lineWidth=1;for(const s of state.segments){const x=s.s/dur*w;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke()}}
  if(r){ctx.strokeStyle='#e8a26f';ctx.lineWidth=Math.max(2,2*(window.devicePixelRatio||1));ctx.strokeRect(x0,1,Math.max(2,x1-x0),h-2)}
  const ph=clamp((el.audio.currentTime||0)/dur,0,1)*w;ctx.strokeStyle='#f3b15d';ctx.lineWidth=Math.max(1.5,1.5*(window.devicePixelRatio||1));ctx.beginPath();ctx.moveTo(ph,0);ctx.lineTo(ph,h);ctx.stroke();state.drawCount++;document.documentElement.dataset.waveDrawCount=String(state.drawCount);
}

function setPlaybackRange(range,mode){state.playbackRange=range;state.playbackMode=mode;document.documentElement.dataset.playbackMode=mode}
async function playRange(range,mode){if(!range)return;setPlaybackRange(range,mode);el.audio.currentTime=range.s;await el.audio.play()}
function syncPlayback(){
  if(!state.data)return;const t=clamp(el.audio.currentTime||0,0,state.data.duration_s);el.current.textContent=timeCode(t);el.seek.value=String(t);updateCurrentSegment();drawWaveform();
  const r=state.playbackRange;if(!el.audio.paused&&r&&t>=r.e-.005){if(state.loopEnabled&&state.playbackMode==='selection'){el.audio.currentTime=r.s}else{el.audio.pause();el.audio.currentTime=r.e;setPlaybackRange(null,'track')}}
}
function playbackTick(){state.raf=0;syncPlayback();if(!el.audio.paused&&!el.audio.ended)state.raf=requestAnimationFrame(playbackTick)}
function startPlaybackLoop(){if(state.raf)cancelAnimationFrame(state.raf);playbackTick()}
function stopPlaybackLoop(){if(state.raf)cancelAnimationFrame(state.raf);state.raf=0;syncPlayback()}
function toggleLoop(){state.loopEnabled=!state.loopEnabled;el.loop.classList.toggle('is-on',state.loopEnabled);el.loop.textContent=`↻ ループ ${state.loopEnabled?'ON':'OFF'}`;document.documentElement.dataset.loop=state.loopEnabled?'on':'off'}

function writeAscii(view,offset,text){for(let i=0;i<text.length;i++)view.setUint8(offset+i,text.charCodeAt(i))}
function buildWavBlob(range){
  const src=state.sourceAudio;if(!src||!range)throw new Error('音声データがありません');const channels=src.channels.filter(Boolean),channelCount=channels.length,sr=src.sampleRate;if(!channelCount||!sr)throw new Error('PCMデータがありません');const maxFrames=Math.min(...channels.map(ch=>ch.length)),start=clamp(Math.floor(range.s*sr),0,maxFrames),end=clamp(Math.ceil(range.e*sr),start,maxFrames),frames=end-start,blockAlign=channelCount*2,buffer=new ArrayBuffer(44+frames*blockAlign),view=new DataView(buffer);
  writeAscii(view,0,'RIFF');view.setUint32(4,36+frames*blockAlign,true);writeAscii(view,8,'WAVE');writeAscii(view,12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,channelCount,true);view.setUint32(24,sr,true);view.setUint32(28,sr*blockAlign,true);view.setUint16(32,blockAlign,true);view.setUint16(34,16,true);writeAscii(view,36,'data');view.setUint32(40,frames*blockAlign,true);let off=44;for(let i=start;i<end;i++)for(let c=0;c<channelCount;c++){const x=clamp(channels[c][i]||0,-1,1);view.setInt16(off,x<0?Math.round(x*32768):Math.round(x*32767),true);off+=2}return new Blob([buffer],{type:'audio/wav'});
}
function downloadSelection(){const r=selectionRange();if(!r)return;const blob=buildWavBlob(r),url=URL.createObjectURL(blob),a=document.createElement('a'),base=(state.sourceAudio.name||'segment-window').replace(/\.[^.]+$/,'');a.href=url;a.download=`${base}.segments-${r.startIndex+1}-${r.endIndex+1}.wav`;a.click();document.documentElement.dataset.lastDownload=a.download;setStatus(`WAV ready · #${r.startIndex+1}–#${r.endIndex+1} · ${r.duration.toFixed(2)} s`);setTimeout(()=>URL.revokeObjectURL(url),1000)}

function acceptAnalysis(data,sourceAudio,sourceMono,playUrl){
  state.data=data;state.sourceAudio=sourceAudio;state.sourceMono=sourceMono;state.segments=buildSegments(data);state.startIndex=0;state.span=Math.min(8,Math.max(1,state.segments.length));state.loopEnabled=false;state.playbackRange=null;state.playbackMode='track';state.currentSegment=-1;
  if(state.objectUrl)URL.revokeObjectURL(state.objectUrl);state.objectUrl=playUrl||null;if(playUrl){el.audio.src=playUrl;el.audio.hidden=false}else{el.audio.removeAttribute('src');el.audio.load()}
  el.duration.textContent=timeCode(data.duration_s);el.seek.max=String(data.duration_s);el.seek.value='0';el.current.textContent='00:00.00';el.fileChip.hidden=false;el.fileChip.textContent=`${data.name} · ${timeCode(data.duration_s)} · ${state.segments.length} segments`;renderSegments();enableUi(!!playUrl);el.start.disabled=false;el.span.disabled=false;el.download.disabled=!sourceAudio;el.fromCurrent.disabled=!playUrl;el.prevOne.disabled=el.nextOne.disabled=el.prevWindow.disabled=el.nextWindow.disabled=false;$$('#span-presets button').forEach(b=>b.disabled=false);updateSelection(false);updateCurrentSegment();drawWaveform();el.provenance.textContent=`browser-local · source ${Math.round(data.source_sample_rate_hz)} Hz · analysis ${Math.round(data.analysis_sample_rate_hz)} Hz · FFT ${data.fft_size} · hop ${data.frame_hop_ms.toFixed(1)} ms · Sonic Chronicle-compatible segmentation`;document.documentElement.dataset.analysis='ready';document.documentElement.dataset.segmentCount=String(state.segments.length);setStatus(`done · ${state.segments.length.toLocaleString()} 区間`);
}
async function analyzeFile(file){
  const token=++state.abortToken;setAnalyzing(true);setProgress(.01);setStatus(`decoding ${file.name}`);try{const bytes=await file.arrayBuffer(),ac=new(window.AudioContext||window.webkitAudioContext)();let buffer;try{buffer=await ac.decodeAudioData(bytes.slice(0))}finally{await ac.close().catch(()=>{})}const channels=Array.from({length:buffer.numberOfChannels},(_,c)=>new Float32Array(buffer.getChannelData(c))),mono=downmix(buffer),data=await analyzePcm(mono,buffer.sampleRate,{name:file.name,mime:file.type,sourceRate:buffer.sampleRate},token),url=URL.createObjectURL(file);acceptAnalysis(data,{name:file.name,sampleRate:buffer.sampleRate,channels},mono,url)}catch(err){if(String(err?.message||err)==='cancelled')setStatus('cancelled');else{console.error(err);setStatus(`error: ${err?.message||err}`)}}finally{if(token===state.abortToken)setAnalyzing(false)}}
function makeSynthetic(){const sr=24000,duration=6,n=Math.floor(sr*duration),samples=new Float32Array(n);let phase=0;for(let i=0;i<n;i++){const t=i/sr;let f=220,amp=.28,noise=0;if(t<1.15)f=220*(2**((16*Math.sin(2*Math.PI*5.2*t))/1200));else if(t<1.45){amp=0}else if(t<2.10){f=180;amp=.015;noise=.25}else if(t<2.35){amp=0}else if(t<3.35){f=330;amp=.27}else if(t<4.55){f=330*2**(((t-3.35)/1.20*420)/1200);amp=.30}else if(t<5.25){f=520;amp=.34}else{amp=0;f=220}phase+=2*Math.PI*f/sr;const pseudo=noise*(.52*Math.sin(i*1.731)+.31*Math.sin(i*2.947)+.17*Math.sin(i*5.113));samples[i]=amp*Math.sin(phase)+(amp*.07)*Math.sin(2*phase)+pseudo}return{samples,sr}}
async function runSynthetic(selftest=false){
  const token=++state.abortToken;setAnalyzing(true);setProgress(.01);setStatus(selftest?'selftest: synthetic':'synthetic demo');if(selftest)document.documentElement.dataset.selftest='running';try{const s=makeSynthetic(),data=await analyzePcm(s.samples,s.sr,{name:'segment-window-demo.wav',mime:'audio/synthetic',sourceRate:s.sr},token),src={name:'segment-window-demo.wav',sampleRate:s.sr,channels:[s.samples]},full={s:0,e:s.samples.length/s.sr},url=URL.createObjectURL(buildWavFromSource(src,full));acceptAnalysis(data,src,s.samples,url);if(selftest)runUiSelftest()}catch(err){console.error(err);setStatus(`error: ${err?.message||err}`);if(selftest)document.documentElement.dataset.selftest='fail'}finally{if(token===state.abortToken)setAnalyzing(false)}}
function buildWavFromSource(src,range){const old=state.sourceAudio;state.sourceAudio=src;try{return buildWavBlob(range)}finally{state.sourceAudio=old}}
function runUiSelftest(){
  const before=state.drawCount,n=state.segments.length;let ok=n>=3;if(ok){setSpan(Math.min(2,n));setStart(Math.min(1,Math.max(0,n-state.span)),false);moveStart(1);const r=selectionRange();ok=!!r&&r.count===state.span&&Number(el.start.value)===r.startIndex+1&&Number(el.span.value)===state.span&&state.drawCount>before&&document.documentElement.dataset.selectionRange===`${r.startIndex}:${r.endIndex}`}
  document.documentElement.dataset.selftest=ok?'pass':'fail';setStatus(`selftest ${ok?'PASS':'FAIL'} · ${n} segments · ${document.documentElement.dataset.selectionRange||'—'}`);
}

el.choose.addEventListener('click',()=>el.file.click());
el.file.addEventListener('change',()=>{const f=el.file.files?.[0];if(f)analyzeFile(f)});
el.drop.addEventListener('dragover',e=>{e.preventDefault();el.drop.classList.add('drag')});el.drop.addEventListener('dragleave',()=>el.drop.classList.remove('drag'));el.drop.addEventListener('drop',e=>{e.preventDefault();el.drop.classList.remove('drag');const f=e.dataTransfer?.files?.[0];if(f)analyzeFile(f)});el.drop.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.file.click()}});
el.synthetic.addEventListener('click',()=>runSynthetic(false));el.cancel.addEventListener('click',()=>{state.abortToken++;setAnalyzing(false);setStatus('cancelled')});
el.start.addEventListener('input',()=>setStart(Number(el.start.value)-1,true));el.span.addEventListener('input',()=>setSpan(Number(el.span.value)));el.presets.addEventListener('click',e=>{const b=e.target.closest('button[data-span]');if(!b)return;setSpan(b.dataset.span==='all'?state.segments.length:Number(b.dataset.span))});
el.prevOne.addEventListener('click',()=>moveStart(-1));el.nextOne.addEventListener('click',()=>moveStart(1));el.prevWindow.addEventListener('click',()=>moveStart(-state.span));el.nextWindow.addEventListener('click',()=>moveStart(state.span));el.fromCurrent.addEventListener('click',()=>setStart(currentSegmentIndex(),true));
el.strip.addEventListener('click',e=>{const b=e.target.closest('.segment-cell');if(!b)return;setStart(Number(b.dataset.index),true)});
el.waveWrap.addEventListener('click',e=>{if(!state.data||!el.audio.src)return;const r=el.waveWrap.getBoundingClientRect(),x=clamp(e.clientX-r.left,0,r.width);el.audio.currentTime=x/r.width*state.data.duration_s;setPlaybackRange(null,'track');syncPlayback()});
el.play.addEventListener('click',async()=>{if(el.audio.paused){setPlaybackRange(null,'track');await el.audio.play()}else el.audio.pause()});el.playSelection.addEventListener('click',()=>playRange(selectionRange(),'selection'));el.playContext.addEventListener('click',()=>playRange(contextRange(),'context'));el.loop.addEventListener('click',toggleLoop);el.download.addEventListener('click',downloadSelection);
el.seek.addEventListener('input',()=>{el.audio.currentTime=Number(el.seek.value)||0;setPlaybackRange(null,'track');syncPlayback()});el.volume.addEventListener('input',()=>{const p=clamp(Math.round(Number(el.volume.value)||0),0,100);el.audio.volume=p/100;el.volumeValue.textContent=`${p}%`});
el.audio.addEventListener('play',()=>{el.play.textContent='❚❚ 一時停止';startPlaybackLoop()});el.audio.addEventListener('pause',()=>{el.play.textContent='▶ 再生';stopPlaybackLoop()});el.audio.addEventListener('ended',()=>{el.play.textContent='▶ 再生';setPlaybackRange(null,'track');stopPlaybackLoop()});el.audio.addEventListener('timeupdate',syncPlayback);
window.addEventListener('resize',drawWaveform);if(window.ResizeObserver)new ResizeObserver(drawWaveform).observe(el.waveWrap);
window.addEventListener('keydown',e=>{if(!state.data||/INPUT|BUTTON|SELECT|TEXTAREA/.test(document.activeElement?.tagName||''))return;if(e.key==='ArrowLeft'){e.preventDefault();moveStart(e.shiftKey?-state.span:-1)}else if(e.key==='ArrowRight'){e.preventDefault();moveStart(e.shiftKey?state.span:1)}else if(e.key===' '){e.preventDefault();el.playSelection.click()}else if(e.key.toLowerCase()==='l'){toggleLoop()}});

enableUi(false);drawWaveform();
if(new URLSearchParams(location.search).get('selftest')==='1')setTimeout(()=>runSynthetic(true),0);
})();
