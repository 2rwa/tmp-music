#!/usr/bin/env python3
"""Find repeated vocal/arrangement cycles using MFCC template similarity."""
import argparse,csv,json
from pathlib import Path
import librosa,numpy as np
from scipy.signal import find_peaks

def main():
 p=argparse.ArgumentParser()
 p.add_argument('audio',type=Path); p.add_argument('--out',type=Path,required=True)
 p.add_argument('--template-start',type=float,default=12.0)
 p.add_argument('--template-end',type=float,default=34.0)
 p.add_argument('--min-gap',type=float,default=20.0)
 p.add_argument('--sr',type=int,default=16000)
 a=p.parse_args(); out=a.out; out.mkdir(parents=True,exist_ok=True)
 y,sr=librosa.load(a.audio,sr=a.sr,mono=True)
 onset=librosa.onset.onset_strength(y=y,sr=sr,hop_length=512)
 tempo_arr,beats=librosa.beat.beat_track(onset_envelope=onset,sr=sr,hop_length=512)
 tempo=float(np.asarray(tempo_arr).reshape(-1)[0])
 hop=int(sr*.25)
 M=librosa.feature.mfcc(y=y,sr=sr,n_mfcc=20,n_fft=2048,hop_length=hop)
 Z=(M-M.mean(axis=1,keepdims=True))/(M.std(axis=1,keepdims=True)+1e-9)
 Z=Z/(np.linalg.norm(Z,axis=0,keepdims=True)+1e-9)
 step=hop/sr; i0=round(a.template_start/step); i1=round(a.template_end/step); T=Z[:,i0:i1]
 scores=[]
 for st in range(Z.shape[1]-T.shape[1]):
  scores.append(float(np.mean(np.sum(T*Z[:,st:st+T.shape[1]],axis=0))))
 scores=np.asarray(scores)
 peaks,_=find_peaks(scores,distance=max(1,round(a.min_gap/step)),prominence=.02)
 starts=[{'start_s':float(i*step),'similarity':float(scores[i])} for i in peaks]
 starts=sorted(starts,key=lambda x:x['start_s'])
 gaps=[starts[i+1]['start_s']-starts[i]['start_s'] for i in range(len(starts)-1)]
 result={'duration_s':len(y)/sr,'tempo_bpm_half_time_candidate':tempo,'double_time_candidate_bpm':tempo*2,
 'template_start_s':a.template_start,'template_end_s':a.template_end,'candidate_cycle_starts':starts,
 'cycle_gap_median_s':float(np.median(gaps)) if gaps else None,'cycle_gap_mean_s':float(np.mean(gaps)) if gaps else None}
 (out/'repetition.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with (out/'template-similarity.csv').open('w',newline='') as f:
  w=csv.writer(f); w.writerow(['time_s','similarity'])
  for i,s in enumerate(scores): w.writerow([i*step,s])
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
