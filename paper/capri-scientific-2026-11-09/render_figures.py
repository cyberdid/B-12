"""Regenerate four figures from bundled aggregates, without private data or GitHub."""
from pathlib import Path
import json
OUT=Path(__file__).resolve().parent
FIG=OUT/'figures'
FIG.mkdir(exist_ok=True)
summary={'by_ctx':json.loads((OUT/'artifacts/historical-aggregates.json').read_text())}
# Technical diagrams are independent vector PDFs; all coordinates and data are reproducible.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
plt.rcParams.update({'font.size':10,'pdf.fonttype':42})
def diagram(name,nodes,edges,caption):
 fig,ax=plt.subplots(figsize=(8,3.8));ax.set(xlim=(0,10),ylim=(0,6));ax.axis('off')
 for key,(x,y,label) in nodes.items():
  ax.add_patch(FancyBboxPatch((x-.95,y-.38),1.9,.76,boxstyle='round,pad=.08',fc='#edf3f8',ec='#25465f'))
  ax.text(x,y,__import__('textwrap').fill(label,21),ha='center',va='center',fontsize=9)
 for a,b in edges:
  x,y,_=nodes[a];u,v,_=nodes[b]
  dx,dy=u-x,v-y
  if abs(dx)>abs(dy):
   sign=1 if dx>0 else -1; start=(x+sign*1.04,y);end=(u-sign*1.04,v)
  else:
   sign=1 if dy>0 else -1; start=(x,y+sign*.46);end=(u,v-sign*.46)
  ax.annotate('',xy=end,xytext=start,arrowprops={'arrowstyle':'->','color':'#4b6070','lw':1})
 ax.text(5,.1,caption,ha='center',fontsize=8)
 fig.savefig(FIG/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
diagram('architecture',{'ui':(1.3,5,'CLI / Web / Qt'),'agent':(4.7,5,'Agent / ContextBuilder'),'model':(8.3,5,'OllamaModel'),'control':(1.3,3,'ControlStore / grants'),'tools':(4.7,3,'ToolRegistry'),'stores':(8.3,3,'Memory / Sessions'),'auto':(1.3,1.2,'Goals / Scheduler'),'purge':(4.7,1.2,'PurgeCoordinator'),'know':(8.3,1.2,'Knowledge / Evidence')},[('ui','agent'),('agent','model'),('control','tools'),('agent','tools'),('agent','stores'),('auto','agent'),('purge','stores'),('know','purge')],'Logical dependencies in the inspected feature snapshot; not a performance diagram.')
diagram('lifecycle',{'req':(1.3,5,'Request / identity'),'admit':(4.7,5,'Evidence + admission'),'model':(8.3,5,'Generate / tool call'),'auth':(8.3,3,'Validate / approval'),'effect':(4.7,3,'Execute / result'),'end':(1.3,3,'Terminal / commit'),'resume':(4.7,1.2,'Resume / revalidate')},[('req','admit'),('admit','model'),('model','auth'),('auth','effect'),('effect','admit'),('effect','end'),('auth','resume'),('resume','auth')],'Approval waits and unknown outcomes are distinct from successful completion.')
diagram('provenance',{'doc':(1.3,5,'Document revision'),'ev':(4.7,5,'Evidence ID'),'mem':(8.3,5,'Canonical memory'),'change':(1.3,3,'Reindex / remove'),'stale':(4.7,3,'Invalidate / stale'),'goal':(8.3,3,'Pause dependent goal'),'forget':(1.3,1.2,'Explicit forget'),'purge':(4.7,1.2,'Transitive purge'),'receipt':(8.3,1.2,'Store acknowledgments')},[('doc','ev'),('ev','mem'),('change','stale'),('stale','mem'),('stale','goal'),('forget','purge'),('purge','receipt')],'Staleness retains a historical record; forgetting deletes registered dependents.')
cats=summary['by_ctx']['4096']['by_category']
fig,ax=plt.subplots(figsize=(8,3.4))
names=list(cats); passed=[cats[k]['passed'] for k in names]; failed=[cats[k]['runs']-cats[k]['passed'] for k in names]
ax.barh(names,passed,label='Passed',color='#447799');ax.barh(names,failed,left=passed,label='Failed',color='#bb6655')
ax.set_xlabel('Recorded executions (not independent cases)');ax.legend();fig.tight_layout();fig.savefig(FIG/'evaluation.pdf');plt.close(fig)
