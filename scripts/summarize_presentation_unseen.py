"""Produce an all-attempt ranking for the frozen presentation evaluation."""
import csv, hashlib, html, json, math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/presentation-unseen-20261127-results.json'
MANIFEST = ROOT / 'datasets/raw/presentation-unseen-20261127/sources.json'

def main():
    report = json.loads(REPORT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    assert report['complete'] and report['planned'] == len(manifest['sources'])
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == report['frozen_manifest_sha256']
    assert hashlib.sha256((ROOT / report['model']).read_bytes()).hexdigest() == report['model_sha256']
    sources = {s['sha256']: s for s in manifest['sources']}
    assert len(sources) == len(report['rows'])
    table = []
    for word in json.loads((ROOT / 'config/showcase50.json').read_text()):
        rows = [r for r in report['rows'] if r['word'] == word]
        n = len(rows); k = sum(r['correct'] for r in rows)
        p = k/n if n else 0; z = 1.96
        lower = (p + z*z/(2*n) - z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))) / (1+z*z/n) if n else 0
        table.append(dict(word=word, correct=k, attempted=n, accuracy=k/n if n else None,
                          wilson_lower_95=lower,
                          assessment='promising_3_of_3' if n>=3 and k==n else 'limited_perfect' if n and k==n else 'mixed' if k else 'failed' if n else 'no_new_clips',
                          misses=dict(Counter(r['prediction'] or r['result'].get('status','error') for r in rows if not r['correct']))))
    table.sort(key=lambda r:(-r['wilson_lower_95'],-r['attempted'],r['word']))
    limitations = ['Source/hash-screened new clips; unseen signer identities and re-encoded duplicates cannot be conclusively verified.',
                   'Clips are selected by availability before inference; exact dictionary filenames can still contain lexical variants.',
                   'Only three clips per word were targeted. Results are small-sample screening, not reliable live accuracy.',
                   'All predictions and detector failures count. Words without new clips are untested, not failed.',
                   'Ranking selects on this evaluation, so presentation examples are selected demonstrations, not a new independent test.',
                   'Model unchanged; these clips must remain excluded from future training.']
    summary = dict(variant=report['variant'], model_sha256=report['model_sha256'],
                   correct=sum(r['correct'] for r in report['rows']), total=len(report['rows']),
                   words_tested=sum(r['attempted']>0 for r in table), words_targeted=50,
                   ranked_words=table, limitations=limitations)
    supplemental_path = ROOT / 'datasets/raw/presentation-supplement-20261127/sources.json'
    if supplemental_path.exists():
        supplemental = json.loads(supplemental_path.read_text())
        summary['supplemental_acquisition'] = dict(attempted_sources=len(supplemental['selection_log']), usable_clips=len(supplemental['sources']), manifest=str(supplemental_path.relative_to(ROOT)))
    dest = ROOT / 'reports/presentation-unseen-20261127-summary'
    dest.with_suffix('.json').write_text(json.dumps(summary,indent=2)+'\n')
    with dest.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['word','correct','attempted','accuracy','wilson_lower_95','assessment','misses']);w.writeheader();w.writerows(table)
    attempts=[]
    with (ROOT/'reports/presentation-unseen-20261127-attempts.csv').open('w',newline='') as f:
        fields=['word','prediction','correct','status','source_url','path','sha256'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in report['rows']:
            s=sources[r['sha256']];row=dict(word=r['word'],prediction=r['prediction'],correct=r['correct'],status=r['result'].get('status'),source_url=r['url'],path=s['path'],sha256=r['sha256']);w.writerow(row);attempts.append(row)
    esc=html.escape
    content='<!doctype html><html><meta charset="utf-8"><title>EchoGesture presentation screening</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#213c31;background:#f4f1e9}table{border-collapse:collapse;width:100%;background:white}td,th{padding:9px;text-align:left;border-bottom:1px solid #ddd}a{color:#215a47}</style><h1>EchoGesture: new-clip presentation screening</h1>'
    content+=f'<p>27 November 2026 · showcase50 · {summary["correct"]}/{summary["total"]} correct · {summary["words_tested"]}/50 words covered.</p><p>Ranked by the 95% Wilson lower bound, so a single successful clip does not outrank stronger evidence. All failed attempts remain included.</p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in limitations)+'</ul><h2>All 50 words</h2><table><tr><th>Word</th><th>Correct / attempted</th><th>Assessment</th><th>Misses</th></tr>'
    for r in table:content+=f'<tr><td>{esc(r["word"])}</td><td>{r["correct"]}/{r["attempted"]}</td><td>{esc(r["assessment"])}</td><td>{esc(str(r["misses"]))}</td></tr>'
    content+='</table><h2>Every clip and prediction</h2><table><tr><th>Expected</th><th>Prediction</th><th>Correct</th><th>Clip</th><th>Source</th></tr>'
    for r in attempts:content+=f'<tr><td>{esc(r["word"])}</td><td>{esc(str(r["prediction"] or r["status"]))}</td><td>{r["correct"]}</td><td><a href="../{esc(r["path"],quote=True)}">Open local clip</a></td><td><a href="{esc(r["source_url"],quote=True)}">Original</a></td></tr>'
    dest.with_suffix('.html').write_text(content+'</table></html>')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
