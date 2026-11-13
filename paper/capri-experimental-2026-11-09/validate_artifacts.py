"""Validate recorded counts and manuscript cross-references; no model calls."""
from pathlib import Path
import json,re,hashlib,collections
OUT=Path(__file__).resolve().parent
src=Path('/home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task14-eval-2026-10-27-merged')
rows=[json.loads(l) for l in (src/'results.jsonl').read_text().splitlines() if l.strip()]
summary=json.loads((src/'summary.json').read_text())
checks={}
for ctx in (4096,8192):
 selected=[r for r in rows if r['num_ctx']==ctx]
 expected=summary['by_ctx'][str(ctx)]
 assert len(selected)==expected['runs']
 assert sum(r['passed'] for r in selected)==expected['passed']
 for category,stats in expected['by_category'].items():
  sub=[r for r in selected if r['category']==category]
  assert len(sub)==stats['runs'] and sum(r['passed'] for r in sub)==stats['passed']
 checks[str(ctx)]={'runs':len(selected),'passed':sum(r['passed'] for r in selected),'distinct_cases':len(set(r['case'] for r in selected))}
multi=[r for r in rows if r['num_ctx']==4096 and r['multi_step']]
assert len(multi)==150 and sum(r['passed'] for r in multi)==117
bad=[r for r in rows if r['num_ctx']==4096 and r['case']=='adv-exfiltrate-secret']
assert len(bad)==5 and sum(r['passed'] for r in bad)==0
with (OUT/'artifacts/normalized-outcomes.jsonl').open('w') as f:
 for row in rows:
  f.write(json.dumps({k:row[k] for k in ('case','category','repeat','num_ctx','multi_step','passed')})+'\n')
t=(OUT/'manuscript.tex').read_text()
labels=set(re.findall(r'\\label\{([^}]+)\}',t));refs=set(re.findall(r'\\ref\{([^}]+)\}',t))
bib=set(re.findall(r'@\w+\{([^,]+),',(OUT/'references.bib').read_text()))
cites={v for x in re.findall(r'\\cite\{([^}]+)\}',t) for v in x.split(',')}
assert not refs-labels and not cites-bib and not bib-cites,(refs-labels,cites-bib,bib-cites)
for f in re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',t): assert (OUT/f).exists(),f
snap=json.loads((OUT/'artifacts/git-pr-snapshot.json').read_text())
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert h(OUT.parent/'capri-preprint/article-en.tex')==snap['original_tex_sha256']
assert h(Path('/home/cyberdid/Projects/B-12/Статті/Capri-preprint-EN.pdf'))==snap['original_root_pdf_sha256']
root=OUT.parents[1]
inventory=json.loads((OUT/'artifacts/source-inventory.json').read_text())
for row in inventory:
 if row['path'].startswith(('src/','tests/','evals/')):
  assert h(root/row['path'])==row['sha256'],row['path']
checks.update({'figures':t.count(r'\begin{figure}'),'tables':t.count(r'\begin{table}'),'cited_references':len(cites),'originals_preserved':True,'production_test_eval_sources_unchanged':True,'raw_scoring':'recorded passed fields aggregated; no semantic rescoring'})
(OUT/'artifacts/validation.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
