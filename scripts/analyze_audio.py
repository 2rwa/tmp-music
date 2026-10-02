#!/usr/bin/env python3
"""Measure metadata, spectrum, sections and pitch for one audio file."""
import argparse,csv,hashlib,json,subprocess
from pathlib import Path
import numpy as np, librosa, librosa.display
import matplotlib.pyplot as plt
from mutagen.id3 import ID3,USLT
from scipy.signal import find_peaks

def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def probe(p):
 r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size,bit_rate:format_tags','-of','json',str(p)],check=True,capture_output=True,text=True)
 return json.loads(r.stdout)
def lyrics(p):
 for f in ID3(p).values():
  if isinstance(f,USLT) and f.lang=='eng': return f.text
 return ''
def novelty_peaks(features,times,sr,hop):
 x=np.vstack(features); med=np.median(x,1,keepdims=True); mad=np.median(np.abs(x-med),1,keepdims=True)+1e-9; x=(x-med)/mad
 w=max(1,round(sr/hop)); k=np.ones(w)/w; x=np.vstack([np.convolve(r,k,'same') for r in x]); lag=max(1,round(1.5*sr/hop))
 n=np.zeros(x.shape[1]); d=x[:,lag:]-x[:,:-lag]; n[lag:]=np.sqrt(np.sum(d*d,0)); n=np.convolve(n,np.ones(max(1,w//2))/max(1,w//2),'same')
 pk,_=find_peaks(n,distance=max(1,round(8*sr/hop)),prominence=max(.1,np.percentile(n,75)*.15)); out=[{'time_s':float(times[i]),'novelty':float(n[i])} for i in pk]
 return sorted(out,key=lambda z:z['novelty'],reverse=True)[:8],n
def section(y,sr,a,b):
 z=y[int(a*sr):int(b*sr)]; S=np.abs(librosa.stft(z,n_fft=2048,hop_length=512)); P=S*S; f=librosa.fft_frequencies(sr=sr,n_fft=2048); total=P.sum()+1e-20
 ratio=lambda lo,hi: float(P[((f>=lo) if lo else True)&((f<hi) if hi else True)].sum()/total)
 onset=librosa.onset.onset_strength(y=z,sr=sr,hop_length=512); hits=librosa.onset.onset_detect(onset_envelope=onset,sr=sr,hop_length=512)
 return {'start_s':a,'end_s':b,'duration_s':b-a,'spectral_centroid_hz_mean':float(np.mean(librosa.feature.spectral_centroid(S=S,sr=sr))), 'spectral_flatness_mean':float(np.mean(librosa.feature.spectral_flatness(S=S))), 'onset_density_per_s':float(len(hits)/(b-a)), 'energy_lt_300_ratio':ratio(0,300),'energy_300_1000_ratio':ratio(300,1000),'energy_1000_4000_ratio':ratio(1000,4000),'energy_ge_4000_ratio':ratio(4000,None)}
def pitch(y,sr,end,out):
 hop=512; z=y[:int(end*sr)]; f0,_,pr=librosa.pyin(z,fmin=librosa.note_to_hz('C2'),fmax=librosa.note_to_hz('C7'),sr=sr,hop_length=hop); t=librosa.times_like(f0,sr=sr,hop_length=hop); m=np.full_like(f0,np.nan); c=np.full_like(f0,np.nan); ok=np.isfinite(f0); m[ok]=librosa.hz_to_midi(f0[ok]); c[ok]=100*(m[ok]-np.round(m[ok]))
 with (out/'pitch-f0.csv').open('w',newline='') as f:
  w=csv.writer(f); w.writerow(['time_s','f0_hz','cents_to_nearest_12tet','voiced_probability']);
  for i in range(len(f0)): w.writerow([t[i],'' if not ok[i] else f0[i],'' if not ok[i] else c[i],'' if pr is None else pr[i]])
 vc=np.abs(c[np.isfinite(c)]); return {'voiced_fraction':float(np.mean(ok)),'estimated_tuning_offset_cents':float(librosa.estimate_tuning(y=z,sr=sr)*100),'median_abs_distance_to_nearest_12tet_cents':float(np.median(vc)) if len(vc) else None}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('audio',type=Path); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--sr',type=int,default=16000); ap.add_argument('--skip-pitch',action='store_true'); ap.add_argument('--boundaries',help='reviewed boundaries, e.g. 21.7,77.5'); a=ap.parse_args(); p=a.audio.resolve(); o=a.out.resolve(); o.mkdir(parents=True,exist_ok=True)
 y,sr=librosa.load(p,sr=a.sr,mono=True); ints=librosa.effects.split(y,top_db=50); end=float(ints[-1,1]/sr) if len(ints) else 0.; ya=y[:int(end*sr)]; hop=512; S=np.abs(librosa.stft(ya,n_fft=2048,hop_length=hop)); P=S*S; fr=librosa.fft_frequencies(sr=sr,n_fft=2048); rms=librosa.feature.rms(S=S)[0]; cen=librosa.feature.spectral_centroid(S=S,sr=sr)[0]; flat=librosa.feature.spectral_flatness(S=S)[0]; zcr=librosa.feature.zero_crossing_rate(ya,frame_length=2048,hop_length=hop)[0]; onset=librosa.onset.onset_strength(y=ya,sr=sr,hop_length=hop); low=P[fr<300].sum(0)/(P.sum(0)+1e-20); n=min(map(len,[rms,cen,flat,zcr,onset,low])); times=librosa.times_like(rms[:n],sr=sr,hop_length=hop); cand,nov=novelty_peaks([rms[:n],cen[:n],flat[:n],zcr[:n],onset[:n],low[:n]],times,sr,hop)
 if a.boundaries: inner=sorted(float(x) for x in a.boundaries.split(',') if 0<float(x)<end); source='reviewed'
 else: inner=sorted(x['time_s'] for x in cand[:2]); source='automatic-top-novelty'
 bounds=[0.]+inner+[end]; secs=[section(y,sr,bounds[i],bounds[i+1]) for i in range(len(bounds)-1)]; ref=lyrics(p); meta={'sha256':sha(p),'size_bytes':p.stat().st_size,'decoded_duration_s':len(y)/sr,'active_end_s':end,'trailing_silence_s':len(y)/sr-end,'ffprobe':probe(p)}; dump(o/'metadata.json',meta); dump(o/'sections.json',{'candidate_boundaries':cand,'selected_boundaries_s':bounds,'selected_boundary_source':source,'sections':secs});
 if ref:(o/'embedded-lyrics-eng.txt').write_text(ref.rstrip()+'\n',encoding='utf-8')
 with (o/'spectral-features.csv').open('w',newline='') as f:
  w=csv.writer(f); w.writerow(['time_s','rms','centroid_hz','flatness','zcr','onset','lt300_ratio','novelty']); [w.writerow([times[i],rms[i],cen[i],flat[i],zcr[i],onset[i],low[i],nov[i]]) for i in range(n)]
 ps={'skipped':True} if a.skip_pitch else pitch(y,sr,end,o); dump(o/'pitch-summary.json',ps)
 fig,ax=plt.subplots(figsize=(14,4)); ax.plot(np.arange(len(y))/sr,y,linewidth=.35); ax.axvline(end,linestyle='--'); ax.set(xlabel='Time (s)',ylabel='Amplitude',title='Waveform'); fig.tight_layout(); fig.savefig(o/'waveform.png',dpi=160); plt.close(fig)
 fig,ax=plt.subplots(figsize=(14,6)); im=librosa.display.specshow(librosa.amplitude_to_db(S,ref=np.max),sr=sr,hop_length=hop,x_axis='time',y_axis='log',ax=ax); ax.set_title('Log-frequency spectrogram'); fig.colorbar(im,ax=ax); fig.tight_layout(); fig.savefig(o/'spectrogram.png',dpi=160); plt.close(fig)
 print(json.dumps({'sha256':meta['sha256'],'active_end_s':end,'candidate_boundaries':cand,'selected_boundaries_s':bounds,'pitch_summary':ps},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
