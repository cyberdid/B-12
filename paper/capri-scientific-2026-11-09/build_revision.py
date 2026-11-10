"""Rebuild the manuscript additions, figures and provenance audit. No inference."""
from pathlib import Path
import subprocess,json,hashlib,csv,re,platform,sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
ART=OUT/'artifacts'; FIG=OUT/'figures'
def sh(*args): return subprocess.check_output(args,cwd=ROOT,text=True).strip()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,data): (ART/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
original=ROOT/'paper/capri-preprint/article-en.tex'
baseline=Path('/home/cyberdid/Projects/B-12/Статті/Capri-preprint-EN.pdf')
inventory=[]
for prefix in ['src/b12','tests','docs/superpowers/specs','docs/superpowers/plans','docs/audits','wiki/topics','wiki/project','evals','benchmarks']:
 for p in sorted((ROOT/prefix).rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.md','.json','.jsonl','.toml'):
   inventory.append({'path':str(p.relative_to(ROOT)),'sha256':digest(p),'bytes':p.stat().st_size})
dump('source-inventory.json',inventory)
prs=json.loads(sh('gh','pr','list','--state','all','--json','number,title,state,headRefName,baseRefName,headRefOid,url'))
dump('git-pr-snapshot.json',{'head':sh('git','rev-parse','HEAD'),'branch':sh('git','branch','--show-current'),'status':sh('git','status','--short'),'main_remote':sh('gh','api','repos/cyberdid/B-12/branches/main','--jq','.commit.sha'),'prs':prs,'source_inventory_sha256':digest(ART/'source-inventory.json'),'original_tex_sha256':digest(original),'original_root_pdf_sha256':digest(baseline)})
dump('environment.json',{'date':'2026-11-09','host':platform.node(),'platform':platform.platform(),'python':sys.version,'processor':platform.processor(),'model':'scripted test fixtures; no LLM inference','quantization':'not applicable','runtime':'pytest subprocess in existing project environment','configuration':'pytest defaults; temporary state; JUnit and text logs','cache':'not controlled; not a latency benchmark','power_mode':'not measured','limitations':'selected contract tests, not model benchmark, acoustic or UI acceptance'})
historical=Path('/home/cyberdid/Projects/B-12/.worktrees/runtime/artifacts/task14-eval-2026-10-27-merged')
summary=json.loads((historical/'summary.json').read_text())
metrics={k:{x:v for x,v in val.items() if x!='failed'} for k,val in summary['by_ctx'].items()}
dump('historical-aggregates.json',metrics)
dump('historical-source-hashes.json',{str(p):digest(p) for p in [historical/'summary.json',historical/'metadata-ctx4096.json',historical/'metadata-ctx8192.json',historical/'results.jsonl']})
failures=summary['by_ctx']['4096']['failed']
from collections import Counter
counts=Counter(row['case'] for row in failures)
dump('failed-case-counts.json',dict(counts))
claims=[
('C01','Shared stores are separate from the model','src/b12/runtime.py','def open_runtime','Implemented and tested by the project','Architecture'),
('C02','Immutable admitted request','src/b12/context.py','class AdmittedRequest','Implemented and tested by the project','Context'),
('C03','Exact local profile assets','src/b12/model_profile.py','class ModelProfile','Implemented and tested by the project','Context'),
('C04','Per-call deployment validation','src/b12/model.py','_check_deployment','Implemented and tested by the project','Context'),
('C05','Turn lifecycle and model lock','src/b12/agent.py','async def _drive','Implemented and tested by the project','Control'),
('C06','Working notes live in turn state','src/b12/agent.py','state.get("notes")','Implemented and tested by the project','Context'),
('C07','Long persist character budget test fails','tests/integration/test_agent_loop.py','test_long_persist_turn_keeps','Implemented but not experimentally validated','New checks'),
('C08','Evidence-tagged sessions','src/b12/sessions.py','class SessionStore','Implemented and tested by the project','Memory'),
('C09','Document version invalidation','src/b12/retrieval.py','def index_document','Implemented and tested by the project','Memory'),
('C10','Memory can become stale','src/b12/memory.py','def mark_stale_for_documents','Implemented and tested by the project','Memory'),
('C11','Coordinated deletion with receipts','src/b12/purge.py','class PurgeCoordinator','Implemented and tested by the project','Memory'),
('C12','Goal checkpoints track evidence','src/b12/goals.py','def checkpoint','Implemented and tested by the project','Autonomy'),
('C13','Scheduler uses non-full-execution grants','src/b12/autonomy.py','full_execution=False','Implemented and tested by the project','Autonomy'),
('C14','Attention gates proposals','src/b12/attention.py','def decide','Implemented and tested by the project','Autonomy'),
('C15','Evidence-backed reflection','src/b12/reflection.py','class Reflector','Implemented but not experimentally validated','Autonomy'),
('C16','Unknown outcomes distinct from failure','src/b12/tools/outcomes.py','class HandlerOutcome','Implemented and tested by the project','Control'),
('C17','Voice interruption code exists','src/b12/audio/duplex.py','class DuplexSession','Implemented but not experimentally validated','Voice'),
('C18','Desktop is a client','src/b12/desktop/client.py','class DesktopApiClient','Implemented but not experimentally validated','Desktop'),
('C19','Persona is prompt context','src/b12/persona.py','CAPRI_PERSONA_PROMPT','Implemented but not experimentally validated','Portability'),
('C20','Live model switching not implemented','src/b12/runtime.py','model = model or','Proposed architecture','Portability'),
('C21','Cross-model behavioral continuity unmeasured','wiki/topics/models.md','# Моделі','Future work','Portability'),
('C22','Historical 496/541','wiki/topics/evals.md','496/541','Implemented and tested by the project','Results'),
('C23','Physical robot acceptance absent','wiki/project/requirements-audit.md','R16','Future work','Validity'),
('C24','Voice hardware acceptance incomplete','wiki/topics/voice.md','# Голос','Implemented but not experimentally validated','Voice')]
with (OUT/'evidence-matrix.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Claim','Source','Evidence','Verification status','Paper section'])
 for ident,claim,path,needle,status,section in claims:
  p=ROOT/path; lines=p.read_text().splitlines() if p.exists() else []
  matches=[i+1 for i,t in enumerate(lines) if needle in t]
  line=matches[0] if matches else 1
  w.writerow([f'{ident}: {claim}',f'{path}:{line}',f'code inspection; SHA256 {digest(p) if p.exists() else "MISSING"}; selected tests in artifacts/focused-tests.xml; scope must be read with text',status,section])
(OUT/'evidence-matrix.md').write_text('# Evidence classification\n\nNo claim is marked independently verified. The new checks were run by the manuscript preparation agent using project-authored tests. The CSV gives exact source locations and hashes. A failure is a negative result, not validation. Implemented and tested means a scoped project check; it is never a whole-system guarantee.\n\n'+(OUT/'evidence-matrix.csv').read_text())
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
# Verified arXiv records, titles and authors as read from their primary abstract pages.
refs=[
('react','Shunyu Yao and Jeffrey Zhao and Dian Yu and Nan Du and Izhak Shafran and Karthik Narasimhan and Yuan Cao','ReAct: Synergizing Reasoning and Acting in Language Models','2022','2210.03629'),
('rag','Patrick Lewis and Ethan Perez and Aleksandra Piktus and Fabio Petroni and Vladimir Karpukhin and Naman Goyal and Heinrich Kuttler and Mike Lewis and Wen-tau Yih and Tim Rocktaschel and Sebastian Riedel and Douwe Kiela','Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks','2020','2005.11401'),
('lost','Nelson F. Liu and Kevin Lin and John Hewitt and Ashwin Paranjape and Michele Bevilacqua and Fabio Petroni and Percy Liang','Lost in the Middle: How Language Models Use Long Contexts','2023','2307.03172'),
('generative','Joon Sung Park and Joseph C. OBrien and Carrie J. Cai and Meredith Ringel Morris and Percy Liang and Michael S. Bernstein','Generative Agents: Interactive Simulacra of Human Behavior','2023','2304.03442'),
('memgpt','Charles Packer and Sarah Wooders and Kevin Lin and Vivian Fang and Shishir G. Patil and Ion Stoica and Joseph E. Gonzalez','MemGPT: Towards LLMs as Operating Systems','2023','2310.08560'),
('reflexion','Noah Shinn and Federico Cassano and Edward Berman and Ashwin Gopinath and Karthik Narasimhan and Shunyu Yao','Reflexion: Language Agents with Verbal Reinforcement Learning','2023','2303.11366'),
('voyager','Guanzhi Wang and Yuqi Xie and Yunfan Jiang and Ajay Mandlekar and Chaowei Xiao and Yuke Zhu and Linxi Fan and Anima Anandkumar','Voyager: An Open-Ended Embodied Agent with Large Language Models','2023','2305.16291'),
('character','Yunfan Shao and Linyang Li and Junqi Dai and Xipeng Qiu','Character-LLM: A Trainable Agent for Role-Playing','2023','2310.10158'),
('agentbench','Xiao Liu and others','AgentBench: Evaluating LLMs as Agents','2023','2308.03688'),
('injec','Qiusi Zhan and Zhixiang Liang and Zifan Ying and Daniel Kang','InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents','2024','2403.02691'),
('helm','Percy Liang and others','Holistic Evaluation of Language Models','2022','2211.09110'),
('awq','Ji Lin and Jiaming Tang and Haotian Tang and Shang Yang and Wei-Ming Chen and Wei-Chen Wang and Guangxuan Xiao and Xingyu Dang and Chuang Gan and Song Han','AWQ: Activation-aware Weight Quantization for LLM Compression and Acceleration','2023','2306.00978'),
('swe','John Yang and Carlos E. Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik Narasimhan and Ofir Press','SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering','2024','2405.15793')]
bib=''
for key,authors,title,year,aid in refs:
 bib+=f'@misc{{{key}, author={{{authors}}}, title={{{{{title}}}}}, year={{{year}}}, eprint={{{aid}}}, archivePrefix={{arXiv}}, doi={{10.48550/arXiv.{aid}}}, url={{https://arxiv.org/abs/{aid}}}}}\n'
bib+='@misc{b12,author={Oleksandr Pylypenko},title={{B-12 repository and documentation}},year={2026},url={https://github.com/cyberdid/B-12}}\n'
for key,aid,title in [('archive','23602155','Beyond Search Scores'),('wow','23911809','Two Language-Model Companions in a Private World of Warcraft Server'),('minecraft','23910891','Auditing AI Autonomy in Minecraft')]:
 bib+=f'@misc{{{key},author={{Oleksandr Pylypenko}},title={{{title}}},year={{2026}},doi={{10.5281/zenodo.{aid}}}}}\n'
(OUT/'references.bib').write_text(bib.replace('Joseph C. OBrien', "Joseph C. O'Brien"))
dump('bibliography-verification.json',[{'key':k,'title':t,'authors':a,'year':y,'arxiv':i,'url':'https://arxiv.org/abs/'+i,'checked_at':'2026-11-09','read_scope':'primary abstract and bibliographic page; not a full replication; arXiv original-submission year used'} for k,a,t,y,i in refs])
text=original.read_text()
text=text.replace('Working preprint draft, 8 November 2026','Scientific revision, 9 November 2026')
text=text.replace(r'\usepackage{booktabs}',r'\usepackage{booktabs,tabularx,longtable,graphicx,float,amsmath}'+'\n'+r'\newcolumntype{Y}{>{\raggedright\arraybackslash}X}')
text=re.sub(r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}',r'\\bibliographystyle{plain}\n\\bibliography{references}',text,flags=re.S)
# Label the existing results table and cite it.
text=text.replace(r'\caption{Historical evaluation at context 4096, commit \texttt{60a4c0b}.}',r'\caption{Historical evaluation at context 4096, commit \texttt{60a4c0b}.}\label{tab:historical}')
text=text.replace('The aggregate was 91.7',r'Table~\ref{tab:historical} reports the historical counts. The aggregate was 91.7',1)
extra=r'''
\section{Research Questions, Contribution and Evidence Scope}\label{sec:rq}
\textbf{RQ1 (model independence):} which state and authority can be separated from the generation model? \textbf{RQ2 (context integrity):} what does admission establish under a limited context and a model-specific template? \textbf{RQ3 (traceable memory):} how do source revisions, staleness and deletion affect stored and retrieved information? \textbf{RQ4 (controlled autonomy):} how are proposed actions separated from execution and unsolicited delivery? \textbf{RQ5 (practical limits):} what do measured local runs and new contract checks demonstrate, and where is evidence absent?

The contribution is a case study of integration and its failure boundaries. External memory, agent loops, reflection and local inference all have substantial prior art. We do not claim invention of those mechanisms, a new learning algorithm or state-of-the-art task performance. The potentially useful engineering contribution is their composition with explicit admission snapshots, deletion revisions, operation outcomes and a shared control path, accompanied by negative evidence and a version-aware audit.

The inspected feature snapshot has HEAD \texttt{1de4eee74776} and local modifications. The remote main was \texttt{2b30b5996ce2}; runtime PR \#1 at \texttt{023c9a1689ab} and desktop PR \#2 at \texttt{1de4eee74776} were open at inspection. The historical model experiment instead pins \texttt{60a4c0b49b2f}. A commit alone does not identify dirty files: the supplementary source inventory hashes production and test files, and the Git/PR snapshot records branch and status. Current code descriptions must be interpreted against this supplement, not as statements about merged main.

\begin{table}[ht]\small
\begin{tabularx}{\linewidth}{p{.19\linewidth}YY}\toprule
Evidence class & Meaning in this paper & Consequence\\\midrule
Independently verified & External reproduction by an independent party & No current subsystem receives this label.\\
Project-tested & Implementation plus scoped project tests or historical artifacts & Supports only the exercised contracts/configuration.\\
Implemented, unvalidated & Code exists; relevant experimental acceptance absent & No performance or behavioral-success claim.\\
Proposed architecture & Intended design, such as atomic live switching & Must not appear as an implemented capability.\\
Future work & Planned comparison or physical acceptance & No present empirical result.\\\bottomrule
\end{tabularx}
\caption{Evidence taxonomy used in the supplementary claim matrix.}\label{tab:status}
\end{table}
Table~\ref{tab:status} distinguishes evidence strength, not feature desirability. The matrix maps claims to source paths, locations and hashes. Tests written by the project and run by the manuscript-preparation agent are project verification, not independent scientific replication.

\begin{figure}[ht]\centering\includegraphics[width=\linewidth]{figures/architecture.pdf}
\caption{Logical architecture of the inspected feature snapshot. UI, control, stores and model are separate responsibilities; arrows represent dependencies rather than isolated security processes.}\label{fig:architecture}\end{figure}
Figure~\ref{fig:architecture} exposes an important qualification to local-first design: placing stores locally does not imply operating-system isolation among components running as the same user.
'''
text=text.replace(r'\section{System architecture}',extra+'\n'+r'\section{System architecture}',1)
# Replace the old related-work section.
start=text.index(r'\section{Related work}');end=text.index(r'\section{Methods and evidence}',start)
related=r'''
\section{Related Work and Positioning}\label{sec:related}
\subsection{Actions, interfaces and autonomous goals}
ReAct combines reasoning and environmental actions \cite{react}. B-12 follows the familiar interaction pattern of model, tool and result; its question is how runtime contracts constrain that pattern, not whether the pattern itself is novel. SWE-agent studies agent-computer interface design for software engineering \cite{swe}. Its relevance here is that descriptions, argument constraints and returned wrappers can alter agent behavior even when the underlying model is unchanged. B-12's wrong-path and wrapper-copying cases are observations consistent with an interface problem; they do not replicate SWE-agent's controlled experiments or establish the same effect size.

Voyager combines a curriculum, executable skill library and iterative environment feedback for Minecraft \cite{voyager}. B-12 instead schedules owner-defined goals with bounded budgets and trusted checks; it does not demonstrate open-ended skill acquisition or transfer between worlds. Reflexion uses verbal feedback and episodic memory to improve subsequent trials without weight updates \cite{reflexion}. B-12's evidence-backed reflection is a narrower record-producing mechanism. Its existence does not show that later task performance improves causally.

\subsection{Memory, retrieval and long contexts}
Generative Agents uses observation, memory retrieval, reflection and planning to support simulated social behavior \cite{generative}. It is directly relevant to companion architecture, but its evaluation of believable behavior is different from B-12's deterministic file, memory and tool checks. MemGPT treats context as a managed hierarchy and evaluates extended document and multi-session interactions \cite{memgpt}. B-12 likewise distinguishes persistent storage from the prompt window, but emphasizes explicit deployment-bound counting and stale-evidence exclusion rather than claiming virtual unlimited effective recall.

RAG combines parametric generation with non-parametric retrieval \cite{rag}. B-12's retrieval bridge and knowledge index use established retrieval ideas; no result here demonstrates better retrieval quality. The owner's separate multilingual archive study has different data and judging conditions \cite{archive}. Long-context position sensitivity \cite{lost} concerns whether a model uses available content; runtime truncation concerns whether content reaches the model at all. Exact admission addresses the latter boundary. It cannot solve position sensitivity or prove understanding of admitted evidence.

\subsection{Persona, local deployment and evaluation}
Character-LLM investigates trained character simulation using constructed experiences and interview-style evaluation \cite{character}. Capri currently uses prompt conditioning and owner style data rather than a character-specific trained model. Computational identity is treated here as stored identity-related records, configuration and behavior under test. It is not evidence of subjective experience. No character benchmark or human preference study was conducted.

AWQ studies activation-aware low-bit quantization and the associated TinyChat system for on-device deployment \cite{awq}. It establishes relevant compression and edge-inference research, but the Bolt Q4\_K\_M configuration in this report is not an AWQ experiment. File size, runtime residency, KV cache and other resident models must be measured separately. Consumer-laptop results do not establish a Jetson deployment.

AgentBench evaluates agents in multiple interactive environments \cite{agentbench}; HELM advocates broad scenarios and multiple metrics \cite{helm}. These works motivate category-level reporting and the separation of accuracy, latency and security outcomes. The B-12 corpus is project-authored and narrower. The owner's Minecraft audit explicitly distinguishes autonomous from operator-assisted achievements \cite{minecraft}, a useful reporting principle but not an independent validation of B-12. InjecAgent studies indirect prompt injection in tool-integrated agents \cite{injec}. B-12's five outbound-fetch failures and broad host permissions preclude presenting its control layer as a general solution to that threat.

The bibliography records verified primary-page titles, authors, submission years and arXiv-issued DOIs. The comparison is based on abstracts and bibliographic descriptions, not a systematic literature review or reproduction of each work's results. Table~\ref{tab:related} therefore compares design emphasis, not benchmark rankings.

\begin{table}[ht]\small
\begin{tabularx}{\linewidth}{p{.18\linewidth}YY}\toprule
Approach & Reported emphasis & B-12 distinction / untested claim\\\midrule
ReAct / SWE-agent & Action-feedback loops and interfaces & Adds runtime control contracts; no superiority comparison.\\
Generative Agents & Memory, reflection, social behavior & Uses source lifecycle; no believability study.\\
MemGPT / RAG & Context tiers and external retrieval & Binds admission to deployment profile; no retrieval-quality advantage.\\
Reflexion / Voyager & Feedback learning and skill acquisition & Bounded owner goals; no open-ended learning result.\\
Character-LLM & Trained role simulation & Prompt persona only; no character-fidelity score.\\
AWQ / TinyChat & Quantized edge inference & Q4\_K\_M laptop run; no quantizer or Jetson comparison.\\
AgentBench / HELM & Broader evaluation coverage & Project corpus and explicit missing dimensions.\\
InjecAgent & Injection attack measurement & Selected control checks; unresolved broad-access risks.\\\bottomrule
\end{tabularx}
\caption{Positioning against established approaches; the rows do not imply metric comparability.}\label{tab:related}\end{table}

'''
text=text[:start]+related+text[end:]
# Additional precise architecture.
arch=r'''
\section{Autonomy, Evidence State and Audio Boundaries}\label{sec:deep}
\subsection{Scheduler, goals and attention}
The inspected scheduler is in \texttt{autonomy.py}, not a separate scheduler module. It holds an exclusive scheduler lock, considers due goals and avoids an actor with registered active work. A background task intersects goal capabilities with owner capabilities and issues a task-scoped grant with full execution disabled. An approval wait pauses the goal. Budget consumption and checkpoint text are stored, and completion requires a trusted check plus live evidence. This is bounded automation under owner-defined criteria, not evidence of autonomous invention of useful long-term goals.

AttentionPolicy distinguishes whether execution may proceed from whether a proposal should be delivered. Owner stop blocks background execution; quiet settings, local quiet hours, cooldown and rate policies can defer nonurgent delivery. A silent agent may still execute authorized background work. Conversely, a visible notification does not establish useful task progress. This separation permits auditable initiative policies without interpreting animation or unsolicited text as cognition.

Reflection reads recent eligible observations, captures the current deletion revision and asks the model for one bounded hypothesis with evidence identifiers. Output is checked against the offered identifiers and current live evidence before storage. A late result after deletion must not resurrect the old observation. This is a consistency mechanism; factual correctness of the hypothesis and its usefulness to future turns need separate evaluation. The project has not demonstrated durable autonomous development over weeks.

\subsection{Canonical, episodic and semantic information}
Canonical SQLite memory stores records with actor scope and source metadata. Sessions preserve completed conversational turns under consent and evidence rules. These session records provide episodic information, but the paper does not infer a human-like episodic-memory mechanism. Semantic retrieval is an optional bridge to an external embedding process; a record's ranking score does not establish truth, freshness or ownership permission. The resolver and deletion lifecycle must remain authoritative after retrieval.

KnowledgeIndex associates a source with revisions and evidence locators. Reindexing changed bytes invalidates old evidence, while a same-content retry can preserve the original receipt. Memory citing invalidated document evidence becomes stale; dependent memory follows that invalidation, and dependent goals pause for review. Staleness and deletion are intentionally different: stale records can preserve a historical claim, whereas explicit forgetting removes registered dependents. New ingestion does not automatically make an old claim valid again.

Backups and restore add another temporal dimension. A snapshot may predate a deletion; replaying deletion state before serving restored data prevents a simple restore from intentionally resurrecting managed forgotten records. The snapshot and purge contract tests exercise controlled temporary stores. Their success does not certify every external backup, filesystem snapshot or provider process. Persistent working notes are also a separate category: notes are attached to active turn state and can survive tool-history trimming or an approval checkpoint, but they are not consented autobiographical memory or an arbitrary cross-session notebook.

\begin{figure}[ht]\centering\includegraphics[width=\linewidth]{figures/lifecycle.pdf}
\caption{Turn lifecycle, including admission, tool validation, approval and continuation. Effect uncertainty must be retained across interruption rather than automatically retried.}\label{fig:lifecycle}\end{figure}
The cycle in Figure~\ref{fig:lifecycle} shows why cancellation is not simply hiding a chat bubble. The request, model stream, tool processes and pending state can have different lifetimes. A completed cancellation acknowledgement or explicit status check is needed before a UI assumes the previous operation has ended.

\begin{figure}[ht]\centering\includegraphics[width=\linewidth]{figures/provenance.pdf}
\caption{Document-to-memory provenance, invalidation and explicit purge. Arrows show registered relationships; unlinked restatements and external copies remain outside this graph.}\label{fig:provenance}\end{figure}
Figure~\ref{fig:provenance} explains why provenance supports consistency rather than omniscient truth tracking: only relationships actually recorded by the system can be invalidated transitively.

\subsection{Voice pipeline and diagnostic evidence}
The conceptual audio path is microphone capture, acoustic echo cancellation, voice-activity detection and endpointing, ASR, agent generation, streamed TTS and speaker playback. Render-reference feedback connects playback to echo handling. The code contains faster-whisper recognition, Piper synthesis and Ukrainian/English paths; duplex components handle speech over playback and scoped interruption. Full-duplex here describes implementation intent and available software paths, not acceptance of the entire pipeline in a noisy room.

Barge-in involves detecting speech, stopping queued audio, cancelling the relevant voice turn and clearing obsolete synthesis work. A software stop timing measures only that path; it does not include acoustic propagation, device buffering or reliable detection of the true end of speech. Likewise, synthetic echo suppression, prerecorded ASR tests and small diagnostic speaker-verification trials cannot establish room-level robustness or population-level false-accept rates. No new acoustic or biometric experiment was performed for this revision. VoiceID is discussed only as B-12 code and diagnostics, without importing results or private data from other projects.

\subsection{Desktop deployment and presentation}
The desktop client shares sessions and approval recovery with the owner API. It can represent thinking, approval and cancellation graphically while the underlying runtime state remains authoritative. Activity hooks for Claude Code, Codex and Antigravity are opt-in integrations with bounded metadata; they do not approve external agents' actions. Configured launchers and local system panels have explicit user interaction paths and are not a grant source for arbitrary model output.

These features are in the inspected desktop branch, with recent additions lacking full host acceptance. Runtime changes in PR \#1 and desktop changes in PR \#2 remain distinct from remote main. A successful X11 overlay or offscreen render shows that widgets can be created, not that model conversation, launcher safety, Wayland interaction or long-term autonomous utility has been demonstrated.

'''
text=text.replace(r'\section{Implementation Details and Design Trade-offs}',arch+'\n'+r'\section{Implementation Details and Design Trade-offs}',1)
newchecks=r'''
\section{New Scoped Verification and Failure Taxonomy}\label{sec:newchecks}
This revision runs nine existing test modules without changing production code. Tests cover admission and evidence contracts, goal-checkpoint provenance, attention, document evidence, turn notes, model--tool rounds and coordinated/snapshot purge. They use temporary state and scripted providers, not Nemotron inference. The experiment is a regression check of selected contracts, not a new score on the 109-case model corpus.

The subprocess reported \textbf{118 passed and 1 failed in 18.41 seconds}. JUnit XML and full text output are included in the supplement. The failure is the existing long-persist fixed-character-budget assertion: total message content was 11,364 characters against a strict threshold below 10,000. This character-count assertion is not the tokenizer admission check and does not establish a real provider overflow. The root cause is not isolated here; increased system-prompt size is a plausible factor requiring controlled investigation, not a demonstrated cause. Production code was deliberately left unchanged.

\begin{table}[ht]\small
\begin{tabularx}{\linewidth}{p{.25\linewidth}YY}\toprule
Protocol & Material / scoring & Interpretation\\\midrule
Historical agent run & 109 cases; ordinary cases repeated five times; 541 executions & 496 checks passed; correlated repeats, project corpus.\\
Profile calibration & Five configurations, three repeats each & Exact agreement for 15 requests, narrow profile.\\
New CPU contracts & Nine modules, temporary stores and scripted model & 118 passed; one character-budget assertion failed.\\
Operational exercise & 8.007 active hours, four segments & Integrity/recovery observations; not continuous service.\\
Acoustic / persona study & Not run in this revision & Remains proposed; no new performance claim.\\\bottomrule
\end{tabularx}
\caption{Protocols use different units and cannot be pooled into one reliability score.}\label{tab:protocols}
\end{table}
Table~\ref{tab:protocols} keeps software contract checks distinct from model task success and human-facing acceptance. Exact test names, environment and version hashes are supplied in the machine-readable artifacts.

\begin{table}[ht]\small
\begin{tabularx}{\linewidth}{p{.22\linewidth}YY}\toprule
Failure class & Concrete evidence & Attribution limit\\\midrule
Reasoning / language & Incorrect Ukrainian fact; transliteration changes exact text & Output-check failures; no causal ablation.\\
Tool selection / policy & Outbound fetch selected in all five adversarial repeats & Model choice plus configured policy, not universal exploit.\\
Tool argument & Wrong path; serialized wrapper copied into output file & Model/interface boundary, not store corruption.\\
Context & Initial prompt truncation; new fixed-character test failure & Different versions and units; not equivalent incidents.\\
Memory use & Two correction-case failures in historical run & Stored availability does not prove correct retrieval/use.\\
Evaluation design & Changed command-tool and exact-text checks across corpus revisions & Aggregate differences confounded by scorer changes.\\
Runtime / operation & Injected provider outages; effect may become unknown & Typed failure/recovery, not automatically a model error.\\\bottomrule
\end{tabularx}
\caption{Non-exclusive failure taxonomy; counts cannot be summed by these explanatory labels.}\label{tab:failure}
\end{table}
Table~\ref{tab:failure} avoids forcing every failed check into one causal category. A reasoning error, an interface mismatch, a runtime failure and an evaluation defect require different remedies and different evidence.

\begin{figure}[ht]\centering\includegraphics[width=\linewidth]{figures/evaluation.pdf}
\caption{Historical executed checks by category at context 4096. Unequal category sizes and correlated repeats preclude reading bar lengths as comparative task difficulty.}\label{fig:eval}\end{figure}
Figure~\ref{fig:eval} is generated from the saved historical summary, not reconstructed from a new model run. The data and plotting script are included.

\section{Model Replacement, Portability and Identity}\label{sec:portability}
Preserving identity-related data means retaining eligible records, source identifiers, history, goals and persona configuration. Preserving behavioral identity means maintaining measurable patterns of language, preferences, memory use and decisions after a model change. The first is an architectural storage property; the second is an empirical claim. B-12 currently supports the former design separation but has not demonstrated the latter through a cross-model experiment.

The runtime and agent retain model-specific settings, a context builder and a model adapter. A safe switch must replace that bundle consistently. Request admission currently precedes acquiring the model lock, so replacing only the adapter can pair a request admitted under one template with another model. Pending approval checkpoints and reflection also outlive a single generation call. A future manager needs transition gating, candidate validation, atomic activation and a rollback policy. None of that is presented here as implemented live switching.

Tool portability depends on supported schema constructs, argument rendering, role conventions, reasoning delimiters and exact token accounting. Native context length is only a ceiling: schemas, retrieved evidence, history and output reserve share the configured window. A larger model may require offloading on an 8 GB GPU; package size is not measured resident memory. Gemma, Qwen and Nemotron are candidates for controlled comparison, not a ranking or a claim of readiness without profiles.

\begin{table}[ht]\small
\begin{tabularx}{\linewidth}{p{.23\linewidth}YY}\toprule
Property & Preserved by design / implemented path & What remains unestablished\\\midrule
Stored memory / goals & Separate stores and evidence scope & Correct interpretation by a new model.\\
Context budget & Profile-bound counting and rejection & Compatibility of an uncalibrated template.\\
Tools / grants & Runtime control and strict schemas & Argument accuracy across model families.\\
Persona configuration & Prompt and bounded style data & Stable behavior or character fidelity.\\
Live switching & Startup configuration only & Atomic manager, routing and rollback.\\
Hardware portability & Laptop measurements & Jetson, robot and combined voice residency.\\\bottomrule
\end{tabularx}
\caption{Data continuity and behavioral continuity are different claims.}\label{tab:portability}
\end{table}
Table~\ref{tab:portability} provides a concrete checklist for RQ1. A successful file-preservation check must not be substituted for a blinded persona-consistency study.
'''
text=text.replace(r'\section{Discussion}',newchecks+'\n'+r'\section{Discussion}',1)
# Explicit validity and reproducibility, replacing old generic limitations.
start=text.index(r'\section{Limitations and reproducibility}');end=text.index(r'\section{Conclusion}',start)
validity=r'''
\section{Threats to Validity}\label{sec:validity}
\textbf{Internal validity.} Changes to corpus prompts, scorers, tool descriptions and code between historical runs confound causal attribution. Neither the earlier score improvements nor the new regression isolate a single intervention. Scripted providers in contract tests deliberately control outputs and therefore cannot measure natural model tool selection or reasoning. Injected outages measure selected recovery paths rather than the frequency of real outages.

\textbf{Construct validity.} Pass/fail checks operationalize specific outcomes, not general intelligence, trust, autonomy or personality. A substring match can penalize a semantically correct answer or miss an incorrect rationale; a name-based command check can miss an equivalent unwanted effect. Stored data, retrieved data and correctly used data are different constructs. The new character-bound assertion uses a different unit from exact rendered-token admission.

\textbf{Statistical conclusion validity.} Five repeats of a case share a prompt, machine, model and scorer. Temperature zero does not guarantee independent or perfectly deterministic execution. One long conversation and one 8192-context repetition have limited evidential weight. We report observed fractions without binomial confidence intervals that would falsely imply independent random samples. The failure labels overlap; no percentage is presented as causal prevalence.

\textbf{External validity.} The core model evidence uses one laptop and one principal local model. Ukrainian/English tasks, the developer's habits and the constructed corpus do not represent all users or domains. No independent human language or persona evaluation, physical robot acceptance or actual Jetson deployment is available. Model-specific templates and tokenizer assets restrict portability. Current feature-branch behavior is not measured by the historical HEAD.

\textbf{Acoustic and security validity.} Synthetic echo, software cancellation and small speaker diagnostics do not establish full-duplex quality in real rooms or broad biometric accuracy. Logical consent and grants are not OS isolation from a process with wide filesystem and execution privileges. Local storage does not prevent data leaving through network tools or a future remote provider. Deletion guarantees are limited to registered stores and acknowledged cleanup; external copies and provider behavior remain outside the evidence.

\textbf{Researcher involvement and review.} The owner and project agents built the corpus, tests and implementation. This manuscript's audit and selected tests are not independent replication. Assertions labeled project-tested are conditional on source hashes, fixtures and scoring. Documentation was inventoried and selected sections read against code; an inventory does not mean every historical plan was experimentally validated. Full test coverage, formal verification and broad security certification are not claimed.

\section{Reproducibility Statement}\label{sec:repro}
The repository is \url{https://github.com/cyberdid/B-12}. The supplement records the original manuscript hashes, feature HEAD, branch, dirty status, remote main, open PR state, production/test source hashes, executed commands, machine environment and JUnit results. Historical metadata pins the model alias digest, template and tokenizer hashes, Ollama 0.33.3, context/output budgets, seed and temperature. Hardware for the historical experiment is the documented i9-14900HX / RTX 4060 Laptop 8 GB / 32 GB RAM machine; power mode and concurrent-load information are not uniformly controlled.

The source inventory identifies file existence and content hashes, not universal public availability. Current evaluation cases may be a newer revision than the historical case hashes. Reproducing the historical model score requires the old code and corpus together; running today's tests reproduces only the new scoped contract check. The supplement supplies commands and normalized aggregate data while leaving raw historical traces at their original local paths. Those traces must be reviewed before any public release because tool inputs and outputs can contain private material. No claim is made that attaching this manuscript alone makes all historical runs reproducible.

The four figures are generated by the accompanying Python script from explicit graph definitions and historical aggregate counts. Six tables are editable LaTeX. Bibliography metadata was checked against primary arXiv pages; the original-submission year is used without inventing conference publication details. Font and plotting dependencies are recorded as build requirements. Model weights, private user state, audio, tokens and the private character artwork are not distributed in this paper package.

\subsection{Answers to the research questions}
RQ1 is answered architecturally by separation of stores, control and generation; live switching and behavioral continuity remain untested. RQ2 has narrow historical calibration and current contract evidence, alongside a newly observed character-budget failure. RQ3 has project-tested revision, staleness and purge paths but no proof of human-like autobiographical recall. RQ4 has explicit execution and attention mechanisms, with no demonstrated long-duration autonomous usefulness. RQ5 is bounded by the reported machine, model, latencies, failures and segmented operational run. These answers establish inspectable engineering behavior under stated conditions rather than general companion reliability.

\subsection{Research gaps and publication boundary}
The next experiments are: cross-model profile calibration and controlled tool comparison; blinded persona consistency ratings; long-term provenance and memory-use evaluation; usefulness and interruption rates for initiative; real-room end-to-end voice acceptance; physical Reachy Mini and Jetson deployment; and continuous long-duration stability with RSS and deletion tracking. Each needs a declared configuration, corpus and raw results. They remain future work in this edition. Independent review and a redacted public historical artifact package would strengthen reproducibility before journal or conference submission.
'''
text=text[:start]+validity+text[end:]
# Correct the methods sentence to keep historical and new experiments distinct.
text=text.replace('We use three existing evidence sets, without running a new inference experiment.','We use three historical evidence sets and report a separate new CPU contract-test exercise in Section~\\ref{sec:newchecks}. No new model inference experiment was run.')
text=text.replace(r'\begin{abstract}',r'\begin{abstract}',1)
text=text.replace('We discuss context truncation, tool failures, privacy boundaries, reproducibility and requirements for safe model replacement.','New scoped CPU regression checks produced 118 passes and one fixed-character-budget failure. We discuss context truncation, tool failures, privacy boundaries, reproducibility and requirements for safe model replacement.')
(OUT/'manuscript.tex').write_text(text)
(OUT/'research-gaps.md').write_text('# Open research gaps\n\n1. Cross-model calibration and task comparisons.\n2. Blinded persona consistency and Ukrainian language evaluation.\n3. Long-term evidence-linked memory use, not merely record survival.\n4. Initiative utility, distraction and owner intervention.\n5. Real-room voice latency, echo, interruption and verification.\n6. Actual Reachy Mini and Jetson acceptance.\n7. Continuous stability and privacy-reviewed public raw artifacts.\n8. Root-cause investigation of the new fixed-character-budget regression.\n\nNone is reported as a completed new experiment.\n')
(OUT/'revision-report.md').write_text('# Scientific revision report\n\nOriginal: paper/capri-preprint/article-en.tex and root Capri-preprint-EN.pdf preserved byte-for-byte (hashes in artifacts/git-pr-snapshot.json).\n\nAdded explicit RQ1–RQ5, evidence taxonomy, open-PR and dirty-snapshot separation, primary-source bibliography, comparative positioning, autonomy/document/voice details, four reproducible vector figures, six tables, scoped CPU test results including failure, failure taxonomy, portability and identity distinctions, threats to validity, reproducibility statement and research gaps. No production code changes or new GPU benchmark.\n\nAudit scope: source locations in evidence-matrix.csv were inspected and project-authored tests were executed. Inventory covers requested documentation/source directories. Inventoried files are not all independently line-reviewed; the matrix and manuscript state the review boundary. No claim is classified independently verified.\n\nHistorical raw JSONL remains local. Normalized aggregates, source hashes, test output and metadata are included. Current corpus must not be substituted for historical hashes. The CPU test failure remains unfixed.\n')
(OUT/'README.md').write_text('# Scientific revision, 2026-11-09\n\nOpen manuscript.tex in Scribe. Build with tectonic manuscript.tex. Original English/Ukrainian manuscripts and root PDFs are preserved. references.bib contains verified primary-source metadata. build_revision.py regenerates the manuscript and figures from the original and local historical artifacts; it requires the original source tree and local metadata paths. Building the existing LaTeX/PDF does not require raw experiment traces.\n\nArtifacts include the source inventory, Git/PR snapshot, environment, historical aggregate data and hashes, scoped pytest JUnit/text outputs. See evidence-matrix.csv, revision-report.md and research-gaps.md. Python plotting requires matplotlib; compilation requires Tectonic and DejaVu Serif. No publication action is performed.\n')
print('Created manuscript, bibliography, figures, audit and reports.')
