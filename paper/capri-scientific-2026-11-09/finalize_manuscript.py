"""Editorial consolidation after build_revision.py; preserves the original edition."""
from pathlib import Path
import re
out=Path(__file__).resolve().parent
p=out/'manuscript.tex';s=p.read_text()
for first,last in [
(r'\section{Implementation Details and Design Trade-offs}',r'\section{Interpretation of the Evaluation}'),
(r'\section{Interpretation of the Evaluation}',r'\section{Future Experimental Programme}'),
(r'\section{Future Experimental Programme}',r'\section{New Scoped Verification and Failure Taxonomy}')]:
 if first in s:
  a=s.index(first);b=s.index(last,a);s=s[:a]+s[b:]
s=s.replace('The root cause is not isolated here;', 'A separate repeat reproduced this failure (1 failed in 1.59 seconds). The root cause is not isolated here;')
# Move the direct answers to the discussion.
start=s.index(r'\subsection{Answers to the research questions}')
end=s.index(r'\subsection{Research gaps and publication boundary}',start)
answers=s[start:end]
s=s[:start]+s[end:]
idx=s.index(r'\section{Threats to Validity}')
s=s[:idx]+answers+s[idx:]
future=r'''
\section{Future Work and Publication Boundary}
\textbf{Cross-model comparison.} Calibrate separate profiles for Gemma, Qwen and Nemotron, then run the same frozen tasks with declared context and output reserves. Report tool-call validity, task effects and memory-use correctness separately from token throughput. Candidate status is not compatibility evidence.

\textbf{Persona consistency.} Use blinded bilingual ratings over matched conversations, including disagreements, uncertainty and technical work. Retain the same identity-related records, but measure behavior rather than treating retained files as proof of character preservation. Model and prompt changes should be independent experimental factors.

\textbf{Long-term memory.} Test corrected and contradicted facts, changing document revisions, source disappearance and delayed deletion over weeks. Score both storage integrity and whether the model uses the right currently eligible evidence. The existing day-seven checkpoint is not a substitute for varied long-horizon interaction.

\textbf{Autonomous initiative.} Evaluate whether proposals are useful, correctly timed and grounded, with explicit records of owner intervention. Quiet-policy compliance and goal-budget accounting are necessary software checks; user-perceived usefulness is a separate endpoint. Do not count an operator-provided solution as an autonomous achievement.

\textbf{Voice acceptance.} Measure physical end-of-utterance to first meaningful audio, false interruption and recovery in noisy rooms with declared devices. Report cold and warm ASR/TTS residency and end-to-end latency distributions. Evaluate speaker verification on an appropriate consented dataset rather than generalizing from small diagnostic trials.

\textbf{Physical deployment.} Bring up Reachy Mini and NVIDIA Jetson using a single actuator writer and a separate motion control path. Laptop tests do not establish device compatibility, power requirements or actuation safety. Neither device is presented as an accepted B-12 deployment in this paper.

\textbf{Continuous stability.} Run uninterrupted experiments with store growth, descriptor counts, RSS, model outages and deletion checks. Evaluate later allocator maintenance on a long-lived worker and publish failure recovery events. This revision's segmented soak cannot answer those questions.

A privacy-reviewed public archive of historical raw results, a frozen source snapshot for the dirty feature tree, and independent scientific review are publication priorities. None of the experiments proposed above is counted as a completed result.
'''
a=s.index(r'\subsection{Research gaps and publication boundary}');b=s.index(r'\section{Conclusion}',a)
s=s[:a]+future+'\n'+s[b:]
s=s.replace('Six tables are editable LaTeX','Six tables are editable LaTeX')

s=s.replace("The owner's Minecraft audit explicitly", "The owner's game-companion study reports typed action boundaries in a separate environment "+r"\cite{wow}"+". The owner's Minecraft audit explicitly")
if (out/'scoring-method.tex').exists() and r'\subsection{Scoring and artifact reconstruction}' not in s:
 s=s.replace(r'\section{Results}',(out/'scoring-method.tex').read_text()+r'\section{Results}',1)
p.write_text(s)
p=out/'references.bib';bib=p.read_text().replace('Joseph C. OBrien',"Joseph C. O'Brien")
bib=bib.replace('title={Beyond Search Scores}', 'title={Beyond Search Scores: Retrieval Quality, Computational Cost, and LLM Judgment Sensitivity in a Multilingual Research Archive}')
bib=bib.replace('title={Two Language-Model Companions in a Private World of Warcraft Server}', 'title={Two Language-Model Companions in a Private World of Warcraft Server: Typed Actions, Shared Perception, and One Week of Human--Agent Co-Development}')
bib=bib.replace('title={Auditing AI Autonomy in Minecraft}', 'title={Auditing AI Autonomy in Minecraft: Skill Libraries, Human Intervention, and the Limits of Agentic Progress}')
p.write_text(bib)

# plain.bst ignores doi/url fields; retain visible resolvers in the compiled PDF.
import re
lines=[]
for line in p.read_text().splitlines():
 doi=re.search(r'doi=\{([^}]+)\}',line)
 url=re.search(r'url=\{([^}]+)\}',line)
 link='https://doi.org/'+doi[1] if doi else (url[1] if url else None)
 if link and 'note=' not in line:
  line=line[:-1]+', note={'+r'\url{'+link+'}}}'
 lines.append(line)
p.write_text('\n'.join(lines)+'\n')

p=out/'manuscript.tex'
s=p.read_text()
if r'\subsection{Cognitive runtime and admission contract}' not in s:
 s=s.replace(r'\subsection{Companion, voice and information access}',(out/'runtime-detail.tex').read_text()+r'\subsection{Companion, voice and information access}',1)
p.write_text(s)
