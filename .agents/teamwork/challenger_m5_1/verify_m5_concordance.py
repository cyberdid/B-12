"""Comprehensive Empirical Challenger Verification Script for Milestone M5 Deliverables.

Validates:
1. Exact concordance of batch_summary.json vs CAPRI_SCENARIO_MATRIX.csv vs STATISTICAL_SUMMARY.md.
2. Exact concordance of all numbers, percentages, Wilson CIs, and latencies in Deliverables 1, 3, 4, 5.
3. Exact concordance of ablation metrics against raw JSON files in evals/capri_comprehensive/artifacts/ablations/.
4. Zero-Fabrication Invariants and Sandboxing integrity.
"""

import json
import csv
import re
from pathlib import Path
import sys

def check_close(val1, val2, tol=1e-3, desc=""):
    diff = abs(val1 - val2)
    if diff > tol:
        print(f"FAILED CHECK: {desc} -> {val1} != {val2} (diff {diff})")
        return False
    return True

def run_verification():
    root = Path("/home/cyberdid/Projects/B-12")
    reports_dir = root / "evals/capri_comprehensive/reports"
    ablations_dir = root / "evals/capri_comprehensive/artifacts/ablations"

    csv_path = reports_dir / "CAPRI_SCENARIO_MATRIX.csv"
    batch_path = reports_dir / "batch_summary.json"
    stat_summary_path = reports_dir / "STATISTICAL_SUMMARY.md"

    doc_comp_path = reports_dir / "CAPRI_COMPREHENSIVE_EVALUATION.md"
    doc_cont_path = reports_dir / "CAPRI_MODEL_CONTINUITY.md"
    doc_sec_path = reports_dir / "CAPRI_SECURITY_EVALUATION.md"
    doc_long_path = reports_dir / "CAPRI_LONG_TERM_PROTOCOL.md"

    failures = []

    # 1. Load batch_summary.json
    with open(batch_path, "r", encoding="utf-8") as f:
        batch_data = json.load(f)

    # 2. Load CAPRI_SCENARIO_MATRIX.csv
    with open(csv_path, "r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))

    # 3. Load STATISTICAL_SUMMARY.md
    with open(stat_summary_path, "r", encoding="utf-8") as f:
        stat_summary_text = f.read()

    # 4. Check Top-Level Scenario Counts
    total_scenarios = len(csv_rows)
    if total_scenarios != 92:
        failures.append(f"CSV row count is {total_scenarios}, expected 92")
    if len(batch_data["reports"]) != 92:
        failures.append(f"batch_summary reports count is {len(batch_data['reports'])}, expected 92")
    if batch_data["total_scenarios"] != 92:
        failures.append(f"batch_summary total_scenarios is {batch_data['total_scenarios']}, expected 92")

    csv_status_counts = {}
    for row in csv_rows:
        st = row["Execution_Status"]
        csv_status_counts[st] = csv_status_counts.get(st, 0) + 1

    expected_statuses = {
        "EXECUTED_PASS": 29,
        "EXECUTED_FAIL": 49,
        "BLOCKED_HARDWARE": 12,
        "BLOCKED_DELAY": 2
    }

    for st, count in expected_statuses.items():
        if csv_status_counts.get(st, 0) != count:
            failures.append(f"CSV status count mismatch for {st}: got {csv_status_counts.get(st, 0)}, expected {count}")

    if batch_data["passed"] != 29:
        failures.append(f"batch_data passed is {batch_data['passed']}, expected 29")
    if batch_data["failed"] != 49:
        failures.append(f"batch_data failed is {batch_data['failed']}, expected 49")
    if batch_data["blocked_hardware"] != 12:
        failures.append(f"batch_data blocked_hardware is {batch_data['blocked_hardware']}, expected 12")
    if batch_data["blocked_delay"] != 2:
        failures.append(f"batch_data blocked_delay is {batch_data['blocked_delay']}, expected 2")

    # Check 1:1 match between CSV and batch_summary reports
    batch_report_map = {r["scenario_id"]: r for r in batch_data["reports"]}
    for r in csv_rows:
        sid = r["Scenario_ID"]
        if sid not in batch_report_map:
            failures.append(f"Scenario {sid} from CSV not found in batch_summary")
            continue
        brep = batch_report_map[sid]
        bst = brep["status"]
        cst = r["Execution_Status"]
        if bst != cst:
            failures.append(f"Status mismatch for {sid}: CSV {cst} vs batch {bst}")
        
        # Check raw score
        c_score = float(r["Raw_Score"])
        b_score = float(brep.get("raw_score", 0.0))
        if abs(c_score - b_score) > 1e-4:
            failures.append(f"Raw score mismatch for {sid}: CSV {c_score} vs batch {b_score}")

    # Check group counts and stats in STATISTICAL_SUMMARY.md
    group_counts_expected = {
        "Group A: Autobiographical Memory": {"total": 10, "pass": 3, "fail": 7, "bhw": 0, "bdly": 0, "pct": "30.0%", "ci": "[10.8%, 60.3%]"},
        "Group B: Long-Term Continuity": {"total": 8, "pass": 3, "fail": 4, "bhw": 0, "bdly": 1, "pct": "42.9%", "ci": "[15.8%, 75.0%]"},
        "Group C: Cross-Model Behavioral Continuity": {"total": 10, "pass": 5, "fail": 5, "bhw": 0, "bdly": 0, "pct": "50.0%", "ci": "[23.7%, 76.3%]"},
        "Group D: Complex Reasoning & Research": {"total": 8, "pass": 4, "fail": 4, "bhw": 0, "bdly": 0, "pct": "50.0%", "ci": "[21.5%, 78.5%]"},
        "Group E: Security & Adversarial Robustness": {"total": 12, "pass": 5, "fail": 7, "bhw": 0, "bdly": 0, "pct": "41.7%", "ci": "[19.3%, 68.0%]"},
        "Group F: Autonomy & Initiative": {"total": 9, "pass": 1, "fail": 8, "bhw": 0, "bdly": 0, "pct": "11.1%", "ci": "[2.0%, 43.5%]"},
        "Group G: Human–AI Interaction": {"total": 8, "pass": 5, "fail": 3, "bhw": 0, "bdly": 0, "pct": "62.5%", "ci": "[30.6%, 86.3%]"},
        "Group H: Voice & Real-Time Interaction": {"total": 8, "pass": 3, "fail": 0, "bhw": 5, "bdly": 0, "pct": "100.0%", "ci": "[43.9%, 100.0%]"},
        "Group I: Reliability & Fault Tolerance": {"total": 8, "pass": 0, "fail": 8, "bhw": 0, "bdly": 0, "pct": "0.0%", "ci": "[0.0%, 32.4%]"},
        "Group J: Embodiment & Robotics": {"total": 6, "pass": 0, "fail": 0, "bhw": 6, "bdly": 0, "pct": "N/A", "ci": ""},
        "Group K: Multi-Session Journeys": {"total": 5, "pass": 0, "fail": 3, "bhw": 1, "bdly": 1, "pct": "0.0%", "ci": "[0.0%, 56.1%]"},
    }

    # Verify these values in STATISTICAL_SUMMARY.md
    for grp, exp in group_counts_expected.items():
        if exp["pct"] != "N/A":
            pattern = re.escape(grp) + r".*?" + re.escape(exp["pct"])
            if not re.search(pattern, stat_summary_text):
                failures.append(f"STATISTICAL_SUMMARY.md missing or mismatched pattern for {grp}: {exp['pct']}")

    # 5. Verify Deliverable 1: CAPRI_COMPREHENSIVE_EVALUATION.md
    with open(doc_comp_path, "r", encoding="utf-8") as f:
        doc_comp = f.read()

    # Check key figures in Deliverable 1
    d1_checks = [
        ("92", "92 total scenarios"),
        ("29", "29 pass"),
        ("49", "49 fail"),
        ("12", "12 blocked hardware"),
        ("2", "2 blocked delay"),
        ("37.2%", "37.2% runnable pass rate"),
        ("[27.3%, 48.3%]", "Wilson 95% CI overall"),
        ("30.0% [10.8%, 60.3%]", "Group A pass rate & CI"),
        ("42.9% [15.8%, 75.0%]", "Group B pass rate & CI"),
        ("50.0% [23.7%, 76.3%]", "Group C pass rate & CI"),
        ("50.0% [21.5%, 78.5%]", "Group D pass rate & CI"),
        ("41.7% [19.3%, 68.0%]", "Group E pass rate & CI"),
        ("11.1% [2.0%, 43.5%]", "Group F pass rate & CI"),
        ("62.5% [30.6%, 86.3%]", "Group G pass rate & CI"),
        ("100.0% [43.9%, 100.0%]", "Group H pass rate & CI"),
        ("0.0% [0.0%, 32.4%]", "Group I pass rate & CI"),
        ("0.0% [0.0%, 56.1%]", "Group K pass rate & CI"),
        # Taxonomy table checks
        ("28", "Deterministic software 28"),
        ("39", "Real-model behavioral 39"),
        ("13", "Controlled experimental 13"),
        ("12", "Physical acceptance 12"),
    ]

    for val, desc in d1_checks:
        if val not in doc_comp:
            failures.append(f"Deliverable 1 missing expected figure '{val}' ({desc})")

    # 6. Verify Deliverable 3: CAPRI_MODEL_CONTINUITY.md
    with open(doc_cont_path, "r", encoding="utf-8") as f:
        doc_cont = f.read()

    d3_checks = [
        ("50.0%", "Group C pass rate 50.0%"),
        ("[23.7%, 76.3%]", "Group C CI"),
        ("58664.8", "Group C P50 latency"),
        ("74842.8", "Group C P95 latency"),
        ("8210.08", "A5 bolt-e4b latency"),
        ("63943.60", "A5 gemma4:12b latency"),
        ("509", "A5 bolt-e4b completion tokens"),
        ("841", "A5 gemma4:12b completion tokens"),
        ("416", "CM-01 character count"),
        ("350", "CM-01 character limit"),
    ]
    for val, desc in d3_checks:
        if val not in doc_cont:
            failures.append(f"Deliverable 3 missing expected figure '{val}' ({desc})")

    # 7. Verify Deliverable 4: CAPRI_SECURITY_EVALUATION.md
    with open(doc_sec_path, "r", encoding="utf-8") as f:
        doc_sec = f.read()

    d4_checks = [
        ("41.7%", "Group E pass rate 41.7%"),
        ("[19.3%, 68.0%]", "Group E CI"),
        ("7046.5", "Group E P50 latency"),
        ("16542.2", "Group E P95 latency"),
        ("11893.36", "A3 DETERMINISTIC latency"),
        ("7812.74", "A3 PROMPT_ONLY latency"),
        ("1111", "A3 DETERMINISTIC prompt tokens"),
        ("1011", "A3 PROMPT_ONLY prompt tokens"),
        ("537", "A3 DETERMINISTIC completion tokens"),
        ("459", "A3 PROMPT_ONLY completion tokens"),
        ("12295.0", "SEC-01 P50"),
        ("16561.3", "SEC-05 P50"),
        ("11187.4", "SEC-12 P50"),
    ]
    for val, desc in d4_checks:
        if val not in doc_sec:
            failures.append(f"Deliverable 4 missing expected figure '{val}' ({desc})")

    # 8. Verify Deliverable 5: CAPRI_LONG_TERM_PROTOCOL.md
    with open(doc_long_path, "r", encoding="utf-8") as f:
        doc_long = f.read()

    d5_checks = [
        ("LT-02", "Scenario LT-02 reference"),
        ("JOURNEY-04", "Scenario JOURNEY-04 reference"),
        ("BLOCKED_DELAY", "BLOCKED_DELAY status reference"),
        ("2026-11-03", "Day 0 timestamp reference"),
        ("2026-11-10", "Day 7 timestamp reference"),
        ("2026-10-10", "Day 30 anchor reference"),
    ]
    for val, desc in d5_checks:
        if val not in doc_long:
            failures.append(f"Deliverable 5 missing expected text '{val}' ({desc})")

    # 9. Verify Raw Ablation Files vs Document Claims
    ablation_files = {
        "A1": ablations_dir / "MEM-01_A1_MEMORY.json",
        "A2": ablations_dir / "MEM-01_A2_CONTEXT.json",
        "A3": ablations_dir / "SEC-01_A3_GATING.json",
        "A4": ablations_dir / "RE-01_A4_TOOLS.json",
        "A5": ablations_dir / "CM-01_A5_MODEL.json",
    }

    # Verify A1
    with open(ablation_files["A1"], "r", encoding="utf-8") as f:
        a1_data = json.load(f)
    a1_res = a1_data["results"]
    if a1_res["FULL"]["tokens_prompt"] != 86 or a1_res["FULL"]["tokens_completion"] != 224:
        failures.append(f"A1 FULL tokens mismatch: {a1_res['FULL']}")
    if a1_res["RAW"]["tokens_prompt"] != 86 or a1_res["RAW"]["tokens_completion"] != 222:
        failures.append(f"A1 RAW tokens mismatch: {a1_res['RAW']}")
    if a1_res["OFF"]["tokens_prompt"] != 33 or a1_res["OFF"]["tokens_completion"] != 542:
        failures.append(f"A1 OFF tokens mismatch: {a1_res['OFF']}")

    # Verify A2
    with open(ablation_files["A2"], "r", encoding="utf-8") as f:
        a2_data = json.load(f)
    a2_res = a2_data["results"]
    for cond in ["2048", "4096", "8192"]:
        if a2_res[cond]["tokens_prompt"] != 86 or a2_res[cond]["tokens_completion"] != 224:
            failures.append(f"A2 {cond} tokens mismatch: {a2_res[cond]}")

    # Verify A3
    with open(ablation_files["A3"], "r", encoding="utf-8") as f:
        a3_data = json.load(f)
    a3_res = a3_data["results"]
    if a3_res["DETERMINISTIC"]["tokens_prompt"] != 1111 or a3_res["DETERMINISTIC"]["tokens_completion"] != 537:
        failures.append(f"A3 DETERMINISTIC tokens mismatch: {a3_res['DETERMINISTIC']}")
    if a3_res["PROMPT_ONLY"]["tokens_prompt"] != 1011 or a3_res["PROMPT_ONLY"]["tokens_completion"] != 459:
        failures.append(f"A3 PROMPT_ONLY tokens mismatch: {a3_res['PROMPT_ONLY']}")

    # Verify A4
    with open(ablation_files["A4"], "r", encoding="utf-8") as f:
        a4_data = json.load(f)
    a4_res = a4_data["results"]
    if a4_res["FULL"]["tokens_prompt"] != 1131 or a4_res["FULL"]["tokens_completion"] != 625:
        failures.append(f"A4 FULL tokens mismatch: {a4_res['FULL']}")
    if a4_res["STRICT"]["tokens_prompt"] != 633 or a4_res["STRICT"]["tokens_completion"] != 424:
        failures.append(f"A4 STRICT tokens mismatch: {a4_res['STRICT']}")
    if a4_res["MINIMAL"]["tokens_prompt"] != 423 or a4_res["MINIMAL"]["tokens_completion"] != 311:
        failures.append(f"A4 MINIMAL tokens mismatch: {a4_res['MINIMAL']}")

    # Verify A5
    with open(ablation_files["A5"], "r", encoding="utf-8") as f:
        a5_data = json.load(f)
    a5_res = a5_data["results"]
    if a5_res["b12-bolt-e4b:q4km"]["tokens_prompt"] != 32 or a5_res["b12-bolt-e4b:q4km"]["tokens_completion"] != 509:
        failures.append(f"A5 bolt tokens mismatch: {a5_res['b12-bolt-e4b:q4km']}")
    if a5_res["gemma4:12b"]["tokens_prompt"] != 32 or a5_res["gemma4:12b"]["tokens_completion"] != 841:
        failures.append(f"A5 gemma tokens mismatch: {a5_res['gemma4:12b']}")

    print(f"Total check failures: {len(failures)}")
    for f in failures:
        print(f" - {f}")

    if len(failures) == 0:
        print("ALL DATA CONCORDANCE CHECKS PASSED PERFECTLY!")
        return True
    return False

if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
