"""Reserve unused WLASL YouTube sources for uncovered presentation words."""
import concurrent.futures, hashlib, json, os, subprocess, sys
from pathlib import Path
from scripts.acquire_wlasl import inspect_video
from scripts.acquire_word_training import dictionary_mirror_ids

ROOT=Path('datasets/raw/presentation-supplement-20261127')
def main():
 ROOT.mkdir(exist_ok=True); assert not (ROOT/'sources.json').exists()
 first=json.loads(Path('datasets/raw/presentation-unseen-20261127/sources.json').read_text())
 words=[w for w in first['words'] if not any(s['word']==w for s in first['sources'])]
 meta=json.loads(Path('datasets/raw/wlasl/WLASL_v0.3.json').read_text())
 known_urls=set();known_hashes=set();seen=[]
 def scan(x):
  if isinstance(x,dict):
   if isinstance(x.get('url'),str):seen.append(x)
   for k,v in x.items():
    if isinstance(v,str):
     if v.startswith('https://'):known_urls.add(v)
     if k in ('sha256','video_sha256') and len(v)==64:known_hashes.add(v)
    elif isinstance(v,(list,dict)):scan(v)
  elif isinstance(x,list):
   for v in x:scan(v)
 ids=set()
 for base in [Path('datasets/raw'),Path('datasets/preprocessed'),Path('reports'),Path('mytest'),Path('testproj')]:
  for p in base.rglob('*'):
   if ROOT in p.parents:continue
   if p.suffix in ('.mp4','.mov','.webm','.npy','.npz'):ids.add(p.stem)
   if p.suffix in ('.mp4','.mov','.webm'):known_hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
   if p.suffix=='.json' and p.name!='WLASL_v0.3.json' and p.stat().st_size<15000000:
    try:scan(json.loads(p.read_text()))
    except (ValueError,UnicodeError):pass
 ids.update(dictionary_mirror_ids(meta,seen))
 known_urls.update(i['url'] for e in meta for i in e['instances'] if str(i['video_id']) in ids)
 choices=[]
 for word in words:
  candidates=[dict(i,word=word) for e in meta if e['gloss']==word for i in e['instances'] if 'youtube.com/watch' in i['url'] and str(i['video_id']) not in ids and i['url'] not in known_urls]
  choices+=candidates[:3]
 env=dict(os.environ,PYTHONPATH='/private/tmp/echogesture-unseen-tools')
 import imageio_ffmpeg
 ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
 def fetch(item):
  row=dict(word=item['word'],url=item['url'],source_page='https://github.com/dxli94/WLASL',wlasl_ids=[item['video_id']],annotation=item,role='evaluation_only_never_train')
  try:
   raw=ROOT/(item['video_id']+'-raw.mp4')
   cmd=[sys.executable,'-m','yt_dlp','--no-playlist','--socket-timeout','8','--retries','0','--no-warnings','-f','best[ext=mp4][height<=720]/best[ext=mp4]','--max-filesize','30M','-o',str(raw),item['url']]
   p=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=45)
   if p.returncode:raise ValueError(p.stderr[-500:])
   sha=hashlib.sha256(raw.read_bytes()).hexdigest()
   if sha in known_hashes:raise ValueError('Known source bytes')
   out=ROOT/(item['word']+'-'+item['video_id']+'.mp4')
   cmd=[ffmpeg,'-v','error','-y','-i',str(raw),'-ss',str((item['frame_start']-1)/item['fps'])]
   if item['frame_end']!=-1:cmd+=['-t',str((item['frame_end']-item['frame_start']+1)/item['fps'])]
   cmd+=['-an','-c:v','libx264','-crf','18',str(out)]
   subprocess.run(cmd,check=True,capture_output=True,timeout=30)
   info=inspect_video(out)
   if info['duration_s']>10 or out.stat().st_size>8*1024*1024:raise ValueError('Outside upload limits')
   row.update(path=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),raw_sha256=sha,decode=info,status='reserved')
  except Exception as exc:row.update(status='unavailable',error=str(exc))
  print(item['word'],item['video_id'],row['status'],flush=True);return row
 with concurrent.futures.ThreadPoolExecutor(3) as pool:rows=list(pool.map(fetch,choices))
 accepted=[];hashes=set(known_hashes)
 for r in rows:
  if r['status']=='reserved':
   if r['sha256'] in hashes:r.update(status='duplicate_excluded')
   else:accepted.append(r);hashes.add(r['sha256'])
 manifest=dict(words=words,sources=accepted,selection_log=rows,model_sha256=first['model_sha256'],policy='Up to three unused official WLASL YouTube entries per uncovered word in metadata order, excluding known URLs, hashes, IDs and dictionary mirrors; official frame annotations applied before inference. Frozen before predictions. Signer and reencoded independence unverified.')
 (ROOT/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n');print('FROZEN',len(accepted),flush=True)
if __name__=='__main__':main()
