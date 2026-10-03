(() => {
  'use strict';
  const TRACKS = [
    ['whisper-ao','Whisper AO'],
    ['jugemu','Jugemu'],
    ['chichinu-fiija','Chichinu Fiija']
  ];
  const $ = s => document.querySelector(s);
  const canvas = $('#timeline'), ctx = canvas.getContext('2d');
  const tooltip = $('#tooltip');
  const state = {track:'whisper-ao', data:null, cache:new Map(), view:[0,1], hover:null, drag:null};
  const css = getComputedStyle(document.documentElement);
  const C = n => css.getPropertyValue(n).trim();
  const colors = {f0:C('--f0'),f0low:C('--f0low'),cpps:C('--cpps'),hnrp:C('--hnrp'),hnra:C('--hnra'),reg:C('--reg'),move:C('--move'),line:C('--line'),muted:C('--muted'),text:C('--text')};
  const showLow = $('#show-low'), showMove = $('#show-movement'), showReg = $('#show-register');

  const tabs = $('#track-tabs');
  TRACKS.forEach(([id,label]) => {
    const b=document.createElement('button'); b.textContent=label; b.dataset.track=id;
    b.addEventListener('click',()=>loadTrack(id)); tabs.appendChild(b);
  });
  [showLow,showMove,showReg].forEach(el=>el.addEventListener('change',draw));
  $('#reset-view').addEventListener('click',resetView);

  function fmt(v,d=2){ return Number.isFinite(v) ? v.toFixed(d) : '—'; }
  function clamp(v,a,b){ return Math.max(a,Math.min(b,v)); }
  function percentile(a,p){ if(!a.length)return 0; const s=[...a].sort((x,y)=>x-y), i=(s.length-1)*p, lo=Math.floor(i), hi=Math.ceil(i); return s[lo]+(s[hi]-s[lo])*(i-lo); }
  function binSearch(points,t){ let lo=0,hi=points.length-1; while(lo<hi){const m=(lo+hi)>>1;if(points[m][0]<t)lo=m+1;else hi=m;} if(lo&&Math.abs(points[lo-1][0]-t)<Math.abs(points[lo][0]-t))lo--; return points[lo]; }

  async function loadTrack(id){
    state.track=id; [...tabs.children].forEach(b=>b.classList.toggle('active',b.dataset.track===id));
    let data=state.cache.get(id);
    if(!data){ const r=await fetch(`./data/${id}.json`,{cache:'no-store'}); if(!r.ok)throw new Error(`data load failed: ${r.status}`); data=await r.json(); state.cache.set(id,data); }
    state.data=data; state.view=[0,data.duration_s]; state.hover=null; state.drag=null; renderSummary(); draw(); renderProvenance();
  }
  function resetView(){ if(state.data){state.view=[0,state.data.duration_s];draw();} }
  function renderSummary(){ const d=state.data,s=d.summary; $('#summary').innerHTML=`
    <div class="stat"><b>${d.label}</b><small>track</small></div>
    <div class="stat"><b>${fmt(d.duration_s,1)} s</b><small>full pitch timeline</small></div>
    <div class="stat"><b>${s.stable_targets}</b><small>stable segments</small></div>
    <div class="stat"><b>${s.movement_candidates}</b><small>pitch-movement candidates</small></div>
    <div class="stat"><b>${s.register_candidates}</b><small>register candidates</small></div>`; }
  function renderProvenance(){ const d=state.data; $('#provenance').innerHTML=`source commit <code>${d.source_commit}</code> · M6 artifact <code>${d.artifacts.m6}</code> · pitch artifact <code>${d.artifacts.pitch}</code> · movement confidence floor <code>${d.summary.movement_confidence_floor}</code>`; }

  function layout(){
    const dpr=Math.max(1,window.devicePixelRatio||1), rect=canvas.getBoundingClientRect();
    const w=Math.max(320,Math.floor(rect.width)),h=Math.floor(parseFloat(getComputedStyle(canvas).height));
    if(canvas.width!==Math.floor(w*dpr)||canvas.height!==Math.floor(h*dpr)){canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr);}
    ctx.setTransform(dpr,0,0,dpr,0,0);
    const L=w<560?48:62,R=18,top=34,gap=30;
    const f0={x:L,y:top,w:w-L-R,h:260};
    const vq={x:L,y:f0.y+f0.h+gap,w:f0.w,h:145};
    const vib={x:L,y:f0.y+f0.h+gap+145+gap,w:f0.w,h:105};
    return {w,h,L,R,f0,vq,vib};
  }
  function mapX(t,p){const [a,b]=state.view;return p.x+(t-a)/(b-a)*p.w;}
  function timeAtX(x,p){const [a,b]=state.view;return a+(x-p.x)/p.w*(b-a);}
  function visibleRange(a,b){return b>=state.view[0]&&a<=state.view[1];}

  function panelBase(p,title,subtitle){
    ctx.fillStyle='#0a1322';ctx.fillRect(p.x,p.y,p.w,p.h);ctx.strokeStyle=colors.line;ctx.strokeRect(p.x+.5,p.y+.5,p.w-1,p.h-1);
    ctx.fillStyle=colors.text;ctx.font='600 12px system-ui';ctx.fillText(title,8,p.y+15);ctx.fillStyle=colors.muted;ctx.font='10px system-ui';ctx.fillText(subtitle,8,p.y+29);
  }
  function drawTimeGrid(p){
    const [a,b]=state.view,span=b-a; const target=8; const rough=span/target; const steps=[.5,1,2,5,10,20,30,60,120]; let step=steps.find(s=>s>=rough)||300;
    ctx.font='10px system-ui';ctx.textAlign='center';ctx.fillStyle=colors.muted;ctx.strokeStyle='rgba(70,93,126,.28)';ctx.lineWidth=1;
    const first=Math.ceil(a/step)*step; for(let t=first;t<=b+.001;t+=step){const x=mapX(t,p);ctx.beginPath();ctx.moveTo(x,p.y);ctx.lineTo(x,p.y+p.h);ctx.stroke();ctx.fillText(`${Math.round(t)}s`,x,p.y+p.h+15);}
    ctx.textAlign='start';
  }
  function overlayEvents(p){
    const d=state.data;
    if(showMove.checked){ctx.fillStyle=colors.move;for(const e of d.movement){if(!visibleRange(e.s,e.e))continue;const x1=mapX(e.s,p),x2=mapX(e.e,p);ctx.fillRect(x1,p.y,Math.max(1,x2-x1),p.h);}}
    if(showReg.checked){ctx.strokeStyle=colors.reg;ctx.lineWidth=1.4;for(const r of d.register){if(r.t<state.view[0]||r.t>state.view[1])continue;const x=mapX(r.t,p);ctx.beginPath();ctx.moveTo(x,p.y);ctx.lineTo(x,p.y+p.h);ctx.stroke();}}
  }
  function drawF0(p){
    panelBase(p,'F0','selected-F0 · log-frequency axis'); overlayEvents(p);
    const pts=state.data.f0.filter(q=>q[0]>=state.view[0]&&q[0]<=state.view[1]);
    const ref=pts.filter(q=>q[2]>=.5).map(q=>q[1]); const vals=ref.length?ref:pts.map(q=>q[1]);
    let lo=percentile(vals,.02),hi=percentile(vals,.98); if(!lo||!hi||lo===hi){lo=80;hi=1000;} lo*=.9;hi*=1.12;
    const ly=v=>p.y+p.h-(Math.log2(v)-Math.log2(lo))/(Math.log2(hi)-Math.log2(lo))*p.h;
    const ticks=[55,82.4,110,165,220,330,440,660,880,1320,1760].filter(v=>v>lo&&v<hi);
    ctx.font='10px system-ui';ctx.fillStyle=colors.muted;ctx.strokeStyle='rgba(70,93,126,.25)';ctx.textAlign='right';
    for(const v of ticks){const y=ly(v);ctx.beginPath();ctx.moveTo(p.x,y);ctx.lineTo(p.x+p.w,y);ctx.stroke();ctx.fillText(v>=1000?`${(v/1000).toFixed(1)}k`:`${Math.round(v)}`,p.x-6,y+3);}
    function series(low){ctx.strokeStyle=low?colors.f0low:colors.f0;ctx.lineWidth=low?1:1.35;ctx.globalAlpha=low?.58:.94;let started=false,lastT=-99;ctx.beginPath();for(const q of pts){const isLow=q[2]<.5;if(isLow!==low)continue;if(low&&!showLow.checked)continue;const x=mapX(q[0],p),y=ly(q[1]);if(!started||q[0]-lastT>.035){ctx.moveTo(x,y);started=true;}else ctx.lineTo(x,y);lastT=q[0];}ctx.stroke();ctx.globalAlpha=1;}
    series(true);series(false);ctx.textAlign='start';
  }
  function drawVQ(p){
    panelBase(p,'Voice quality','stable-segment representative values (dB)'); overlayEvents(p);
    const segs=state.data.segments.filter(s=>visibleRange(s.s,s.e)); const vals=[];segs.forEach(s=>vals.push(s.cpps,s.hnr_praat,s.hnr_auto)); let lo=Math.floor((Math.min(...vals,0)-2)/5)*5,hi=Math.ceil((Math.max(...vals,20)+2)/5)*5;if(hi-lo<20)hi=lo+20;
    const yy=v=>p.y+p.h-(v-lo)/(hi-lo)*p.h;ctx.font='10px system-ui';ctx.fillStyle=colors.muted;ctx.strokeStyle='rgba(70,93,126,.25)';ctx.textAlign='right';for(let v=Math.ceil(lo/5)*5;v<=hi;v+=5){const y=yy(v);ctx.beginPath();ctx.moveTo(p.x,y);ctx.lineTo(p.x+p.w,y);ctx.stroke();ctx.fillText(`${v}`,p.x-6,y+3);}ctx.textAlign='start';
    const specs=[['cpps',colors.cpps],['hnr_praat',colors.hnrp],['hnr_auto',colors.hnra]]; for(const [k,c] of specs){ctx.strokeStyle=c;ctx.fillStyle=c;ctx.lineWidth=2;for(const s of segs){const x1=mapX(s.s,p),x2=mapX(s.e,p),y=yy(s[k]);ctx.beginPath();ctx.moveTo(x1,y);ctx.lineTo(Math.max(x1+1,x2),y);ctx.stroke();ctx.beginPath();ctx.arc((x1+x2)/2,y,2.2,0,Math.PI*2);ctx.fill();}}
  }
  function drawVibrato(p){
    panelBase(p,'Vibrato extent','stable-segment detrended F0 p95 − p05 (cent)'); overlayEvents(p);
    const segs=state.data.segments.filter(s=>visibleRange(s.s,s.e)); const max=Math.max(50,Math.ceil(Math.max(...segs.map(s=>s.vib),50)/25)*25); const yy=v=>p.y+p.h-v/max*p.h;
    ctx.font='10px system-ui';ctx.fillStyle=colors.muted;ctx.strokeStyle='rgba(70,93,126,.25)';ctx.textAlign='right';for(let v=0;v<=max;v+=25){const y=yy(v);ctx.beginPath();ctx.moveTo(p.x,y);ctx.lineTo(p.x+p.w,y);ctx.stroke();ctx.fillText(`${v}`,p.x-6,y+3);}ctx.textAlign='start';
    ctx.fillStyle='rgba(124,196,255,.35)';ctx.strokeStyle=colors.f0;for(const s of segs){const x1=mapX(s.s,p),x2=mapX(s.e,p),y=yy(s.vib);ctx.fillRect(x1,y,Math.max(1,x2-x1),p.y+p.h-y);ctx.beginPath();ctx.moveTo(x1,y);ctx.lineTo(Math.max(x1+1,x2),y);ctx.stroke();}
  }
  function crosshair(L){if(state.hover==null)return; const p=L.f0,x=mapX(state.hover,p); if(x<p.x||x>p.x+p.w)return;ctx.strokeStyle='rgba(255,255,255,.55)';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,L.f0.y);ctx.lineTo(x,L.vib.y+L.vib.h);ctx.stroke();ctx.setLineDash([]);}
  function selection(L){if(!state.drag||state.drag.current==null)return;const a=state.drag.start,b=state.drag.current,x1=mapX(Math.min(a,b),L.f0),x2=mapX(Math.max(a,b),L.f0);ctx.fillStyle='rgba(124,196,255,.12)';ctx.fillRect(x1,L.f0.y,x2-x1,L.vib.y+L.vib.h-L.f0.y);}
  function draw(){if(!state.data)return;const L=layout();ctx.clearRect(0,0,L.w,L.h);drawF0(L.f0);drawVQ(L.vq);drawVibrato(L.vib);drawTimeGrid(L.vib);crosshair(L);selection(L);}

  function tooltipAt(t,clientX,clientY){
    const d=state.data, p=binSearch(d.f0,t), seg=d.segments.find(s=>t>=s.s&&t<=s.e), mov=d.movement.find(e=>t>=e.s&&t<=e.e), reg=d.register.reduce((best,r)=>Math.abs(r.t-t)<Math.abs((best?.t??1e9)-t)?r:best,null); const nearReg=reg&&Math.abs(reg.t-t)<=.45?reg:null;
    let h=`<b>${d.label}</b> · ${fmt(t,2)} s`;
    if(p&&Math.abs(p[0]-t)<.12) h+=`<br>F0: <b>${fmt(p[1],1)} Hz</b> <span class="muted">conf ${fmt(p[2],2)}</span>`;
    if(seg) h+=`<br><span class="muted">stable #${seg.i} ${fmt(seg.s,2)}–${fmt(seg.e,2)}s</span><br>CPPS ${fmt(seg.cpps)} dB · Praat HNR ${fmt(seg.hnr_praat)} dB · autocorr HNR ${fmt(seg.hnr_auto)} dB<br>vibrato ${fmt(seg.vib,1)} cent · tilt ${fmt(seg.tilt)} dB/oct`;
    if(mov) h+=`<br><span class="muted">movement:</span> ${mov.dir}, ${fmt(mov.change,0)} cent, conf ${fmt(mov.conf,2)}`;
    if(nearReg) h+=`<br><span class="muted">register candidate @ ${fmt(nearReg.t,2)}s:</span> ${nearReg.features.join(', ')}`;
    tooltip.innerHTML=h;tooltip.hidden=false; const shell=tooltip.parentElement.getBoundingClientRect(); let x=clientX-shell.left+14,y=clientY-shell.top+14; const tw=tooltip.offsetWidth,th=tooltip.offsetHeight; if(x+tw>shell.width-8)x-=tw+28;if(y+th>shell.height-8)y-=th+28;tooltip.style.left=`${Math.max(8,x)}px`;tooltip.style.top=`${Math.max(8,y)}px`;
  }
  function pointTime(ev){const L=layout(),r=canvas.getBoundingClientRect(),x=ev.clientX-r.left;if(x<L.f0.x||x>L.f0.x+L.f0.w)return null;return clamp(timeAtX(x,L.f0),state.view[0],state.view[1]);}
  canvas.addEventListener('pointermove',ev=>{const t=pointTime(ev);if(t==null)return;if(state.drag)state.drag.current=t;state.hover=t;tooltipAt(t,ev.clientX,ev.clientY);draw();});
  canvas.addEventListener('pointerleave',()=>{if(!state.drag){state.hover=null;tooltip.hidden=true;draw();}});
  canvas.addEventListener('pointerdown',ev=>{const t=pointTime(ev);if(t==null)return;state.drag={start:t,current:t};canvas.setPointerCapture(ev.pointerId);});
  canvas.addEventListener('pointerup',ev=>{if(!state.drag)return;const a=state.drag.start,b=state.drag.current;state.drag=null;if(Math.abs(a-b)>.35)state.view=[Math.min(a,b),Math.max(a,b)];draw();});
  canvas.addEventListener('dblclick',resetView);
  canvas.addEventListener('wheel',ev=>{if(!state.data)return;ev.preventDefault();const t=pointTime(ev);if(t==null)return;const [a,b]=state.view,span=b-a,factor=ev.deltaY>0?1.35:.74,newSpan=clamp(span*factor,2,state.data.duration_s),rel=(t-a)/span;let na=t-rel*newSpan,nb=na+newSpan;if(na<0){nb-=na;na=0;}if(nb>state.data.duration_s){na-=nb-state.data.duration_s;nb=state.data.duration_s;}state.view=[Math.max(0,na),Math.min(state.data.duration_s,nb)];draw();},{passive:false});
  window.addEventListener('resize',draw);
  loadTrack(state.track).catch(err=>{console.error(err);$('#summary').innerHTML=`<div class="stat"><b>Load error</b><small>${err.message}</small></div>`;});
})();
