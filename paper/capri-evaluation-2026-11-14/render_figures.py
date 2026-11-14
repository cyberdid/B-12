"""Render the manuscript's vector figures (TikZ/PGFPlots) from artifacts/data.json only."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIG = ROOT / "figures"
data = json.loads((ROOT / "artifacts/data.json").read_text(encoding="utf-8"))
FIG.mkdir(exist_ok=True)

# Figure: harness comparison (static diagram; no data).
(FIG / "harness.tex").write_text(r"""\begin{tikzpicture}[font=\small,
  box/.style={draw=inkmuted,rounded corners=2pt,align=center,minimum height=8mm,inner sep=3pt},
  arr/.style={-{Stealth[length=2mm]},draw=inkmuted}]
\node[box,text width=27mm] (s1) {Scenario\\(all memories)};
\node[box,right=6mm of s1,text width=30mm,fill=series2!12] (p1) {Harness-written\\system prompt};
\node[box,right=6mm of p1,text width=18mm] (m1) {Model};
\draw[arr] (s1) -- (p1); \draw[arr] (p1) -- (m1);
\node[anchor=west,font=\small\bfseries] at ([yshift=6mm]s1.north west) {(a) Raw-model harness};
\node[box,below=14mm of s1,text width=27mm] (s2) {Scenario\\(actors, consent)};
\node[box,right=6mm of s2,text width=30mm,fill=series1!12] (r2) {B-12 runtime\\grants, recall,\\persona, tools};
\node[box,right=6mm of r2,text width=18mm] (m2) {Model};
\node[box,right=6mm of m2,text width=20mm] (t2) {Tool results\\(sandbox)};
\draw[arr] (s2) -- (r2); \draw[arr] (r2) -- (m2); \draw[arr] (m2) -- (t2);
\draw[arr] (t2.south) |- ++(0,-5mm) -| (r2.south);
\node[anchor=west,font=\small\bfseries] at ([yshift=6mm]s2.north west) {(b) Runtime-faithful harness};
\end{tikzpicture}
""", encoding="utf-8")

# Figure: pass counts per run for each repeated configuration.
order = [("bolt", "Bolt + 12B"), ("bolt-evidence-after-user", "Bolt + 12B, Evidence moved"),
         ("gemma4-26b", "gemma4:26b (MoE)"), ("gemma4-31b", "gemma4:31b")]
points, means = [], []
for y, (key, _) in enumerate(reversed(order), 1):
    runs = data["repeats"][key]["per_run"]
    for i, v in enumerate(runs):
        points.append(f"({v},{y + (i - 1) * 0.12:.2f})")
    means.append(f"({data['repeats'][key]['mean']},{y})")
labels = ",".join("{" + name + "}" for _, name in reversed(order))
(FIG / "repeats.tex").write_text(rf"""\begin{{tikzpicture}}
\begin{{axis}}[width=.62\linewidth,height=52mm,xmin=38,xmax=56,ymin=.4,ymax=4.6,
  ytick={{1,2,3,4}},yticklabels={{{labels}}},xlabel={{Scenarios passed (of {data['runnable']} runnable)}},
  xmajorgrids,grid style={{gridline}},tick label style={{font=\small}},label style={{font=\small}},
  y tick label style={{align=right}},legend style={{font=\small,draw=none,at={{(0.5,1.03)}},anchor=south,/tikz/every odd column/.append style={{column sep=5mm}}}},legend columns=2]
\addplot[only marks,mark=*,mark size=2.2pt,color=series1] coordinates {{{' '.join(points)}}};
\addlegendentry{{single run}}
\addplot[only marks,mark=|,mark size=6pt,line width=1.4pt,color=series2] coordinates {{{' '.join(means)}}};
\addlegendentry{{mean of three runs}}
\end{{axis}}
\end{{tikzpicture}}
""", encoding="utf-8")

# Figure: prompt cache and TTFT by turn.
pc = data["prompt_cache"]
def series(values, start=1):
    return " ".join(f"({i},{v})" for i, v in enumerate(values[start:], start))
(FIG / "cache.tex").write_text(rf"""\begin{{tikzpicture}}
\begin{{axis}}[name=a,width=.44\linewidth,height=50mm,xlabel={{Turn in session}},ylabel={{TTFT (s)}},
  ymin=0,ymax=1.6,xtick={{1,...,6}},ymajorgrids,grid style={{gridline}},tick label style={{font=\small}},
  label style={{font=\small}},title={{(a) Time to first token}},title style={{font=\small}},
  legend style={{font=\scriptsize,draw=none,at={{(0.5,0.97)}},anchor=north}},legend columns=1]
\addplot[color=series2,mark=square*,mark size=1.6pt,thick] coordinates {{{series(pc['baseline']['ttft_by_turn'])}}};
\addlegendentry{{Evidence in system text}}
\addplot[color=series1,mark=*,mark size=1.6pt,thick] coordinates {{{series(pc['after']['ttft_by_turn'])}}};
\addlegendentry{{Evidence after user turn}}
\end{{axis}}
\begin{{axis}}[at={{(a.east)}},anchor=west,xshift=22mm,width=.44\linewidth,height=50mm,xlabel={{Turn in session}},
  ylabel={{Prompt tokens}},ymin=0,ymax=2700,xtick={{1,...,6}},ymajorgrids,grid style={{gridline}},
  tick label style={{font=\small}},label style={{font=\small}},title={{(b) Tokens reused from cache}},
  title style={{font=\small}},legend style={{font=\scriptsize,draw=none,at={{(0.5,0.03)}},anchor=south}},legend columns=2,
  scaled y ticks=false]
\addplot[color=series2,mark=square*,mark size=1.6pt,thick] coordinates {{{series(pc['baseline']['cached_by_turn'])}}};
\addlegendentry{{cached, before}}
\addplot[color=series1,mark=*,mark size=1.6pt,thick] coordinates {{{series(pc['after']['cached_by_turn'])}}};
\addlegendentry{{cached, after}}
\addplot[color=inkmuted,dashed] coordinates {{{series(pc['after']['prompt_by_turn'])}}};
\addlegendentry{{total, after}}
\end{{axis}}
\end{{tikzpicture}}
""", encoding="utf-8")

# Figure: brevity A/B.
ab = data["brevity_ab"]
c, t = ab["control"], ab["treatment"]
(FIG / "brevity.tex").write_text(rf"""\begin{{tikzpicture}}
\begin{{axis}}[name=a,ybar,bar width=9mm,width=.46\linewidth,height=48mm,ymin=0,ymax=400,
  symbolic x coords={{median,mean}},xtick=data,enlarge x limits=.55,ylabel={{Characters}},
  title={{(a) Length of conversational replies}},title style={{font=\small}},
  tick label style={{font=\small}},label style={{font=\small}},ymajorgrids,grid style={{gridline}},
  nodes near coords,every node near coord/.append style={{font=\scriptsize}},
  legend style={{font=\scriptsize,draw=none,at={{(0.03,0.97)}},anchor=north west}}]
\addplot[fill=series2!80,draw=none] coordinates {{(median,{c['casual_chars_median']}) (mean,{c['casual_chars_mean']})}};
\addlegendentry{{control}}
\addplot[fill=series1!80,draw=none] coordinates {{(median,{t['casual_chars_median']}) (mean,{t['casual_chars_mean']})}};
\addlegendentry{{brevity rule}}
\end{{axis}}
\begin{{axis}}[at={{(a.east)}},anchor=west,xshift=16mm,ybar,bar width=12mm,width=.40\linewidth,height=48mm,
  ymin=0,ymax={c['work_turns']},symbolic x coords={{control,brevity rule}},xtick=data,enlarge x limits=.6,
  ylabel={{Turns with $\geq$1 tool call}},title={{(b) Tool use on work turns (n={c['work_turns']})}},
  title style={{font=\small}},tick label style={{font=\small}},label style={{font=\small}},
  ymajorgrids,grid style={{gridline}},nodes near coords,every node near coord/.append style={{font=\scriptsize}}]
\addplot[fill=inkmuted!55,draw=none] coordinates {{(control,{c['work_turns_with_tool']}) (brevity rule,{t['work_turns_with_tool']})}};
\end{{axis}}
\end{{tikzpicture}}
""", encoding="utf-8")
print("figures:", sorted(p.name for p in FIG.glob("*.tex")))
