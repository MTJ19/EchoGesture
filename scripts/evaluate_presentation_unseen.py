"""Run frozen fresh probes through the unchanged showcase50 upload pipeline once."""
import argparse,hashlib,json,os
from pathlib import Path
from flask import Flask
from asl_lab.word_routes import word_routes

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--manifest',type=Path,default=Path('datasets/raw/showcase-fresh10/sources.json'))
 parser.add_argument('--output',type=Path,default=Path('reports/showcase-fresh10-results.json'))
 args=parser.parse_args()
 root=Path.cwd();manifest=args.manifest
 frozen=json.loads(manifest.read_text());model=Path('models/word81-grammar-candidate.joblib')
 assert hashlib.sha256(model.read_bytes()).hexdigest()==frozen['model_sha256']
 output=args.output
 if output.exists():raise RuntimeError('Evaluation report already exists; preserve first results')
 os.environ['ECHOGESTURE_WORD_MODEL']='showcase50'
 app=Flask(__name__);app.register_blueprint(word_routes(root));client=app.test_client()
 rows=[]
 for source in frozen['sources']:
  path=Path(source['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
  with path.open('rb') as stream:response=client.post('/api/words/predict',data={'video':(stream,path.name)})
  result=response.get_json() or {}
  row=dict(word=source['word'],url=source['url'],source_page=source['source_page'],sha256=source['sha256'],http=response.status_code,prediction=result.get('label'),correct=response.status_code==200 and result.get('label')==source['word'],result=result)
  rows.append(row)
  report=dict(variant='showcase50',limitations=['Exact source and content checks cannot prove signer independence or exclude reencoded duplicates.','Small first-look dictionary batch; results are not a general live-accuracy estimate.','Active showcase50 vocabulary restriction; all attempts, including detector failures, retained.'],model=str(model),model_sha256=frozen['model_sha256'],frozen_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),selection_policy=frozen['policy'],attempted=len(rows),planned=len(frozen['sources']),correct=sum(r['correct'] for r in rows),rows=rows,complete=len(rows)==len(frozen['sources']))
  output.write_text(json.dumps(report,indent=2)+'\n')
  print(row['word'],row['prediction'],row['correct'],response.status_code,flush=True)
 print('TOTAL',sum(r['correct'] for r in rows),'/',len(rows),flush=True)
if __name__=='__main__':main()
