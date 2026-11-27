"""Reserve new dictionary clips per frozen showcase word before inference."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from urllib.parse import urlsplit,unquote
from concurrent.futures import ThreadPoolExecutor
from scripts.acquire_wlasl import inspect_video
from scripts.acquire_word_training import dictionary_mirror_ids

ROOT=Path('datasets/raw/showcase-fresh10')
def curl(url):
 return subprocess.check_output(['curl','-fLsS','--max-time','25','--max-filesize','20000000','--proto','=https','--proto-redir','=https',url],timeout=30)
def main():
 global ROOT
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--words',nargs='+')
 parser.add_argument('--clips-per-word',type=int,default=3)
 parser.add_argument('--metadata-fallback',action='store_true')
 parser.add_argument('--start',type=int,default=0)
 parser.add_argument('--stop',type=int,default=10)
 parser.add_argument('--output',type=Path,default=ROOT)
 args=parser.parse_args();ROOT=args.output
 ROOT.mkdir(exist_ok=True)
 manifest=ROOT/'sources.json'
 if manifest.exists():raise RuntimeError('Frozen manifest already exists; do not replace after predictions')
 ranking=json.loads(Path('reports/showcase-word-ranking.json').read_text())
 words=args.words or [r['word'] for r in ranking['all_words'][args.start:args.stop]]
 metadata=json.loads(Path('datasets/raw/wlasl/WLASL_v0.3.json').read_text())
 local=[]
 for base in [Path('datasets/raw'),Path('mytest'),Path('testproj')]:
  if base.exists():local.extend(p for p in base.rglob('*') if p.suffix.lower() in ('.mp4','.mov','.webm','.m4v') and ROOT not in p.parents)
 ids={p.stem for p in local}
 ids.update(p.stem for p in Path('datasets/preprocessed').rglob('*.npz'))
 known_urls=set();known_hashes=set();seen_sources=[]
 def scan(value):
  if isinstance(value,dict):
   if isinstance(value.get('url'),str):seen_sources.append(value)
   for k,v in value.items():
    if isinstance(v,str):
     if v.startswith('https://'):known_urls.add(v)
     if k in ('sha256','video_sha256') and len(v)==64:known_hashes.add(v)
    elif isinstance(v,(dict,list)):scan(v)
  elif isinstance(value,list):
   for v in value:scan(v)
 for base in [Path('reports'),Path('datasets/raw'),Path('mytest'),Path('testproj')]:
  if not base.exists():continue
  for p in base.rglob('*.json'):
   if p.name=='WLASL_v0.3.json' or p.stat().st_size>15000000 or ROOT in p.parents:continue
   try:scan(json.loads(p.read_text()))
   except (ValueError,UnicodeError):pass
 for p in local:known_hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
 fitted=[i for e in metadata for i in e['instances'] if str(i['video_id']) in ids]
 known_urls.update(i['url'] for i in fitted)
 def key(url):
  u=urlsplit(url);parts=unquote(u.path).lower().split('/');provider=parts[3] if u.hostname=='media.signbsl.com' and len(parts)>4 else (u.hostname or '').split('.')[0]
  return provider,parts[-1]
 known_keys={key(u) for u in known_urls}
 def discover(word):
  page='https://www.signasl.org/sign/'+word
  try:html=curl(page).decode()
  except Exception as exc:return word,[],[dict(word=word,error=str(exc))]
  urls=list(dict.fromkeys(re.findall(r'<source\s+src="(https://[^\"]+\.(?:mp4|mov))"',html)))
  choices=[];log=[]
  for url in urls:
   name=unquote(urlsplit(url).path).split('/')[-1].lower()
   if not re.fullmatch(re.escape(word)+r'(?:[-_][a-z0-9-]+|\d*)?\.(?:mp4|mov)',name):continue
   mirrors=dictionary_mirror_ids(metadata,[dict(url=url)])
   if url in known_urls or key(url) in known_keys or mirrors & ids:
    log.append(dict(word=word,url=url,status='known_source_excluded'));continue
   choices.append(dict(word=word,url=url,source_page=page,wlasl_ids=sorted(mirrors),role='evaluation_only_never_train'))
  if args.metadata_fallback:
   for entry in metadata:
    if entry['gloss']!=word:continue
    for item in entry['instances']:
     url=item['url']
     if not url.startswith('https://') or not url.endswith('.mp4') or not any(host in url for host in ('signingsavvy.com/','handspeak.com/','aslsignbank.haskins.yale.edu/')):continue
     if 'handspeak.com/' in url and unquote(urlsplit(url).path).split('/')[-1]!=word+'.mp4':continue
     if str(item['video_id']) in ids or url in known_urls or key(url) in known_keys:continue
     if any(c['url']==url for c in choices):continue
     choices.append(dict(word=word,url=url,source_page='https://github.com/dxli94/WLASL',wlasl_ids=[str(item['video_id'])],wlasl_split=item['split'],role='evaluation_only_never_train'))
  return word,choices,log
 with ThreadPoolExecutor(3) as pool:discovered=list(pool.map(discover,words))
 rows=[];log=[];batch_hashes=set()
 for word,choices,logs in discovered:
  log.extend(logs);count=0
  for row in choices:
   try:
    data=curl(row['url']);sha=hashlib.sha256(data).hexdigest()
    if sha in known_hashes or sha in batch_hashes:raise ValueError('Previously present bytes or within-batch duplicate')
    out=ROOT/(word+'-'+sha[:12]+'.mp4');out.write_bytes(data)
    info=inspect_video(out)
    if len(data)>8*1024*1024:raise ValueError('Over upload size limit')
    if info['duration_s']>10:raise ValueError('Long clip; excluded before predictions')
    row.update(path=str(out),sha256=sha,decode=info,status='reserved');rows.append(row);batch_hashes.add(sha);count+=1
    print(word,'reserved',row['url'],flush=True)
    if count==args.clips_per_word:break
   except Exception as exc:log.append(dict(row,status='download_or_quality_excluded',error=str(exc)))
 manifest.write_text(json.dumps(dict(words=words,sources=rows,selection_log=log,model_sha256=ranking['model_sha256'],existing_video_files_hashed=len(local),policy='First requested number of downloadable exact-gloss dictionary clips per word after excluding existing URLs, provider/filename matches, local WLASL IDs and SHA256 content. Frozen before any prediction. No fitting. Same signer or reencoded duplicates cannot be conclusively excluded.'),indent=2)+'\n')
 print('FROZEN',len(rows),'clips for',len({r['word'] for r in rows}),'words',flush=True)
if __name__=='__main__':main()
