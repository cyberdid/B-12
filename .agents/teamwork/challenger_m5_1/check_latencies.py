import re
import csv
from pathlib import Path

csv_path = Path("evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv")
with open(csv_path, encoding="utf-8") as f:
    csv_map = {r["Scenario_ID"]: r for r in csv.DictReader(f)}

reports = [
    Path("evals/capri_comprehensive/reports/CAPRI_COMPREHENSIVE_EVALUATION.md"),
    Path("evals/capri_comprehensive/reports/CAPRI_MODEL_CONTINUITY.md"),
    Path("evals/capri_comprehensive/reports/CAPRI_SECURITY_EVALUATION.md"),
    Path("evals/capri_comprehensive/reports/CAPRI_LONG_TERM_PROTOCOL.md"),
]

# Match table rows with either | or │:
# │ CM-01 │ Persona Invariance Across Models │ FAIL │ 64078.5 мс │ ...
table_row_pattern = re.compile(r"[|│]\s*([A-Z]+-[0-9]{2})\s*[|│][^|│\n]*[|│][^|│\n]*[|│]\s*([0-9]+(?:\.[0-9]+)?)\s*мс")
# Match inline citations: `MEM-01` (6571.4 мс)
inline_pattern = re.compile(r"[`]?([A-Z]+-[0-9]{2})[`]?[^0-9\n]{1,30}([0-9]+(?:\.[0-9]+)?)\s*мс")

mismatches = []
total_found = 0

for rep in reports:
    print(f"\n--- Checking {rep.name} ---")
    text = rep.read_text(encoding="utf-8")
    
    # 1. Check table rows
    t_matches = table_row_pattern.findall(text)
    print(f"Found {len(t_matches)} table row latency citations.")
    for sid, lat_str in t_matches:
        total_found += 1
        lat = float(lat_str)
        if sid not in csv_map:
            print(f"WARNING: {sid} not in CSV!")
            continue
        csv_p50 = float(csv_map[sid]["P50_Latency_ms"])
        csv_p95 = float(csv_map[sid]["P95_Latency_ms"])
        diff_p50 = abs(lat - csv_p50)
        diff_p95 = abs(lat - csv_p95)
        if diff_p50 > 1.0 and (diff_p50 / (csv_p50 + 1e-6)) > 0.01:
            if diff_p95 > 1.0 and (diff_p95 / (csv_p95 + 1e-6)) > 0.01:
                mismatches.append((rep.name, sid, lat, csv_p50, csv_p95, "table"))
                print(f"MISMATCH in table: {rep.name} {sid} text={lat} ms vs CSV P50={csv_p50} ms, P95={csv_p95} ms")
            else:
                print(f"Matched P95 in table: {sid} text={lat} == P95={csv_p95}")
        else:
            print(f"Matched P50 in table: {sid} text={lat} == P50={csv_p50}")

    # 2. Check inline citations
    i_matches = inline_pattern.findall(text)
    print(f"Found {len(i_matches)} inline latency citations.")
    for sid, lat_str in i_matches:
        total_found += 1
        lat = float(lat_str)
        if sid not in csv_map:
            print(f"WARNING: {sid} not in CSV!")
            continue
        csv_p50 = float(csv_map[sid]["P50_Latency_ms"])
        csv_p95 = float(csv_map[sid]["P95_Latency_ms"])
        diff_p50 = abs(lat - csv_p50)
        diff_p95 = abs(lat - csv_p95)
        if diff_p50 > 1.0 and (diff_p50 / (csv_p50 + 1e-6)) > 0.01:
            if diff_p95 > 1.0 and (diff_p95 / (csv_p95 + 1e-6)) > 0.01:
                mismatches.append((rep.name, sid, lat, csv_p50, csv_p95, "inline"))
                print(f"MISMATCH in inline: {rep.name} {sid} text={lat} ms vs CSV P50={csv_p50} ms, P95={csv_p95} ms")
            else:
                print(f"Matched P95 inline: {sid} text={lat} == P95={csv_p95}")

print(f"\nTotal citations checked: {total_found}")
print(f"Total mismatches: {len(mismatches)}")
for m in mismatches:
    print(f" - In {m[0]} ({m[5]}): {m[1]} text={m[2]} ms vs CSV P50={m[3]} ms, P95={m[4]} ms")
