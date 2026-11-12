import csv
from pathlib import Path
import re

csv_path = Path("evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv")
with open(csv_path, encoding="utf-8") as f:
    csv_map = {r["Scenario_ID"]: r for r in csv.DictReader(f)}

d1_path = Path("evals/capri_comprehensive/reports/CAPRI_COMPREHENSIVE_EVALUATION.md")
d1_text = d1_path.read_text(encoding="utf-8")

# In D1, each group has:
# - **Успішні сценарії:**
#   - `MEM-06` ...
# - **Провалені сценарії та причини відмов:**
#   - `MEM-01` ...
# - **Заблоковані сценарії:**

pass_pattern = re.compile(r"Успішні сценарії.*?\n((?:\s*-\s*`?[A-Z]+-[0-9]{2}`?.*?\n)+)", re.DOTALL)
fail_pattern = re.compile(r"Провалені сценарії.*?\n((?:\s*-\s*`?[A-Z]+-[0-9]{2}`?.*?\n)+)", re.DOTALL)
blocked_pattern = re.compile(r"Заблоковані сценарії.*?\n((?:\s*-\s*`?[A-Z]+-[0-9]{2}`?.*?\n)+)", re.DOTALL)

sid_extract = re.compile(r"`?([A-Z]+-[0-9]{2})`?")

# Let's extract all scenario mentions under each subsection
sections = re.split(r"### 4\.[0-9]+ Група", d1_text)

mismatches = []
checked_sids = set()

for idx, sec in enumerate(sections[1:], 1):
    header = sec.split("\n")[0]
    print(f"\nAnalyzing section: Group {idx} ({header})")
    
    # Find passed mentions
    p_match = pass_pattern.search(sec)
    passed_sids = []
    if p_match:
        passed_sids = sid_extract.findall(p_match.group(1))

    # Find failed mentions
    f_match = fail_pattern.search(sec)
    failed_sids = []
    if f_match:
        failed_sids = sid_extract.findall(f_match.group(1))

    # Find blocked mentions
    b_match = blocked_pattern.search(sec)
    blocked_sids = []
    if b_match:
        blocked_sids = sid_extract.findall(b_match.group(1))

    print(f"  Passed in text ({len(passed_sids)}): {passed_sids}")
    print(f"  Failed in text ({len(failed_sids)}): {failed_sids}")
    print(f"  Blocked in text ({len(blocked_sids)}): {blocked_sids}")

    for sid in passed_sids:
        checked_sids.add(sid)
        c_status = csv_map[sid]["Execution_Status"]
        if c_status != "EXECUTED_PASS":
            mismatches.append((sid, "PASS in text", c_status))

    for sid in failed_sids:
        checked_sids.add(sid)
        c_status = csv_map[sid]["Execution_Status"]
        if c_status != "EXECUTED_FAIL":
            mismatches.append((sid, "FAIL in text", c_status))

    for sid in blocked_sids:
        checked_sids.add(sid)
        c_status = csv_map[sid]["Execution_Status"]
        if not c_status.startswith("BLOCKED"):
            mismatches.append((sid, "BLOCKED in text", c_status))

print(f"\nTotal unique scenarios checked in detailed sections: {len(checked_sids)}")
print(f"Mismatches: {len(mismatches)}")
for m in mismatches:
    print(f" - {m[0]}: {m[1]} vs CSV={m[2]}")
