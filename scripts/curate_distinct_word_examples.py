"""Verify and retain one successful example for 15 words absent from the in-app examples."""
import csv,hashlib,json,os,shutil
from pathlib import Path
from flask import Flask
from asl_lab.word_routes import word_routes
ROOT=Path.cwd()
def main():
 ranking=json.loads((ROOT/'reports/presentation-unseen-20261127-summary.json').read_text())['ranked_words']
 excluded={p.name for p in (ROOT/'static/word-examples').iterdir() if p.is_dir()}
 allrows=[]
 for name in ['presentation-unseen-20261127-results.json','showcase-fresh10-results.json','showcase-fresh40-results.json','showcase-retest19-results.json']:
  allrows.extend(json.loads((ROOT/'reports'/name).read_text())['rows'])
 scores=[]
 for word in json.loads((ROOT/'config/showcase50.json').read_text()):
  group=[r for r in allrows if r['word']==word];n=len(group);k=sum(r['correct'] for r in group)
  if word not in excluded and k:
   p=k/n;z=1.96
   lower=(p+z*z/(2*n)-z*((p*(1-p)/n+z*z/(4*n*n))**.5))/(1+z*z/n)
   scores.append((lower,n,word))
 scores.sort(key=lambda x:(-x[0],-x[1],x[2]));words=[x[2] for x in scores[:15]]
 assert len(words)==15 and not set(words)&excluded

 sources={s['sha256']:s for p in (ROOT/'datasets/raw').glob('showcase-*/sources.json') for s in json.loads(p.read_text()).get('sources',[])}
 sources.update({s['sha256']:s for s in json.loads((ROOT/'datasets/raw/presentation-unseen-20261127/sources.json').read_text())['sources']})
 reports=[ROOT/'reports/presentation-unseen-20261127-results.json']+[ROOT/'reports'/n for n in ['showcase-fresh10-results.json','showcase-fresh40-results.json','showcase-retest19-results.json']]
 old=json.loads((ROOT/'reports/showcase-word-ranking.json').read_text())['attempts']
 os.environ['ECHOGESTURE_WORD_MODEL']='showcase50';app=Flask(__name__);app.register_blueprint(word_routes(ROOT));client=app.test_client()
 selected=[];attempts=[]
 for word in words:
  candidates=[]
  for report in reports:
   for r in json.loads(report.read_text())['rows']:
    if r['word']==word and r['correct'] and r['sha256'] in sources:
     s=sources[r['sha256']];candidates.append(dict(path=s['path'],source=s['url'],evidence=report.name))
  for r in old:
   if r['label']==word and r['correct']:
    candidates.append(dict(path='datasets/raw/asl-citizen-selected/'+r['video'],source='ASL Citizen '+r['split']+' / '+r['video'],evidence='showcase-word-ranking.json (previously inspected cached evaluation)'))
  seen=set()
  example_hash=None
  for c in candidates:
   path=ROOT/c['path']
   if not path.exists() or str(path) in seen:continue
   seen.add(str(path))
   if hashlib.sha256(path.read_bytes()).hexdigest()==example_hash:continue
   with path.open('rb') as stream:response=client.post('/api/words/predict',data={'video':(stream,path.name)})
   result=response.get_json() or {};correct=response.status_code==200 and result.get('label')==word
   row=dict(word=word,**c,prediction=result.get('label'),status=result.get('status'),http=response.status_code,correct=correct,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
   attempts.append(row);print(word,row['prediction'],correct,flush=True)
   (ROOT/'reports/presentation-distinct15-verification.json').write_text(json.dumps(dict(words=words,attempts=attempts,selected=selected,complete=False),indent=2)+'\n')
   if correct:selected.append(row);break
  if not any(r['word']==word for r in selected):raise RuntimeError('No verified example for '+word)
 archive=ROOT/'datasets/raw/testproj-before-distinct15-20261127'
 assert not archive.exists();shutil.move(str(ROOT/'testproj'),str(archive))
 dest=ROOT/'testproj';dest.mkdir();rows=[]
 for row in selected:
  out=dest/row['word']/(row['word']+'.mp4');out.parent.mkdir();shutil.copy2(ROOT/row['path'],out)
  assert hashlib.sha256(out.read_bytes()).hexdigest()==row['sha256']
  assert row['sha256'] not in {hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'static/word-examples').rglob('*.mp4')}
  rows.append(dict(file=str(out.relative_to(dest)),**row))
 with (dest/'sources.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 (dest/'README.txt').write_text('Selected presentation examples — 27 November 2026\n\n15 upload-test words, all absent from the in-app examples dropdown. Each has one successful video. Every included video was rechecked through the unchanged showcase50 pipeline.\n\nWords: '+', '.join(words)+'\n\nUpload the word-named MP4 at http://127.0.0.1:8080/words. These are selected, previously inspected demonstrations, not an unseen test or a live accuracy guarantee. Chair/book/go use earlier evaluated ASL Citizen clips; provenance for every file is in sources.csv. All remain excluded from future training. Source rights remain with original owners.\n\nFull new-clip results remain in reports/presentation-unseen-20261127-summary.html. Previous testproj contents were preserved locally in datasets/raw/testproj-before-distinct15-20261127.\n')
 (ROOT/'reports/presentation-distinct15-verification.json').write_text(json.dumps(dict(words=words,attempts=attempts,selected=selected,complete=True),indent=2)+'\n')
 print('CURATED',len(selected),'words',flush=True)
if __name__=='__main__':main()
