#!/usr/bin/env python3
"""Run faster-whisper and compare output with the MP3 embedded English lyrics."""
import argparse,json,re,subprocess,tempfile
from pathlib import Path
from mutagen.id3 import ID3,USLT

def reftext(p):
 frames=[x for x in ID3(p).values() if isinstance(x,USLT)];
 for x in frames:
  if x.lang=='eng': return x.text.strip()
 return frames[0].text.strip() if frames else ''
def tokens(s): return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?",s.lower().replace('’',"'"))
def edit(ref,hyp):
 n,m=len(ref),len(hyp); d=[[0]*(m+1) for _ in range(n+1)]; op=[['']*(m+1) for _ in range(n+1)]
 for i in range(1,n+1): d[i][0]=i; op[i][0]='D'
 for j in range(1,m+1): d[0][j]=j; op[0][j]='I'
 for i in range(1,n+1):
  for j in range(1,m+1):
   if ref[i-1]==hyp[j-1]: d[i][j]=d[i-1][j-1]; op[i][j]='='
   else: d[i][j],op[i][j]=min((d[i-1][j-1]+1,'S'),(d[i-1][j]+1,'D'),(d[i][j-1]+1,'I'))
 i,j=n,m; c={'S':0,'D':0,'I':0,'=':0}; rows=[]
 while i or j:
  q=op[i][j]
  if q=='=' or q=='S': rows.append((q,ref[i-1],hyp[j-1])); i-=1;j-=1
  elif q=='D': rows.append((q,ref[i-1],''));i-=1
  elif q=='I': rows.append((q,'',hyp[j-1]));j-=1
  else: break
  c[q]+=1
 rows.reverse(); return {'substitutions':c['S'],'deletions':c['D'],'insertions':c['I'],'correct':c['='],'reference_units':n,'hypothesis_units':m,'error_rate':(c['S']+c['D']+c['I'])/n if n else None},rows
def clip(src,start,end,tmp):
 if start is None and end is None:return src
 out=tmp/'clip.wav'; cmd=['ffmpeg','-y','-v','error'];
 if start is not None:cmd+=['-ss',str(start)]
 cmd+=['-i',str(src)]
 if end is not None:cmd+=['-t',str(end-start)] if start is not None else ['-to',str(end)]
 cmd+=['-ac','1','-ar','16000','-c:a','pcm_s16le',str(out)];subprocess.run(cmd,check=True);return out
def transcribe(path,model,lang,device,ctype):
 from faster_whisper import WhisperModel
 w=WhisperModel(model,device=device,compute_type=ctype); segs,info=w.transcribe(str(path),language=lang,beam_size=5,vad_filter=True,word_timestamps=True); rows=[]; text=[]
 for s in segs:
  text.append(s.text.strip()); rows.append({'start':s.start,'end':s.end,'text':s.text,'avg_logprob':getattr(s,'avg_logprob',None),'no_speech_prob':getattr(s,'no_speech_prob',None)})
 return {'detected_language':info.language,'language_probability':info.language_probability,'text':' '.join(x for x in text if x),'segments':rows}
def main():
 p=argparse.ArgumentParser();p.add_argument('audio',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--model',default='small');p.add_argument('--modes',default='auto,en');p.add_argument('--device',default='cpu');p.add_argument('--compute-type',default='int8');p.add_argument('--start',type=float);p.add_argument('--end',type=float);a=p.parse_args();src=a.audio.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);ref=reftext(src);(out/'reference.txt').write_text(ref+'\n',encoding='utf-8');metrics={}
 with tempfile.TemporaryDirectory() as td:
  wav=clip(src,a.start,a.end,Path(td))
  for mode in [x.strip() for x in a.modes.split(',') if x.strip()]:
   r=transcribe(wav,a.model,None if mode=='auto' else mode,a.device,a.compute_type);(out/f'{mode}.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(out/f'{mode}.txt').write_text(r['text']+'\n',encoding='utf-8');wm,rows=edit(tokens(ref),tokens(r['text']));cm,_=edit(list(''.join(tokens(ref))),list(''.join(tokens(r['text']))));metrics[mode]={'word':wm,'character':cm}
   with (out/f'{mode}-alignment.tsv').open('w',encoding='utf-8') as f:f.write('op\tref\thyp\n');[f.write('\t'.join(x)+'\n') for x in rows]
 (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(metrics,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
