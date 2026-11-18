"""Build hashed, non-runnable draft fixtures from a synthetic case catalog."""

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath

DECISIONS = {"ACT", "NO_TOOL", "ASK", "DEFER", "SILENT", "INCONCLUSIVE"}
RISKS = {"read_only", "synthetic_mutation", "permission_sensitive"}
SPLITS = {"dev", "validation", "locked_test", "longitudinal_holdout"}
FAMILY_ID = re.compile(r"(?:C|M)\d{2}\Z")


def _relative_path(value, name):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{name} must be a relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{name} must be a normalized relative POSIX path")
    return path


def _reject_symlink_parents(root, relative_path):
    current = root
    for part in relative_path.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError("output path contains a symlink parent")
        if current.exists() and not current.is_dir():
            raise ValueError("output parent is not a directory")


def _validate_cases(cases):
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be an object")
        family = case.get("family_id")
        if not isinstance(family, str) or not FAMILY_ID.fullmatch(family):
            raise ValueError("family_id must match Cnn or Mnn")
        if family in seen:
            raise ValueError(f"duplicate family_id: {family}")
        seen.add(family)
        expected_track = "control" if family.startswith("C") else "memory"
        if case.get("track") != expected_track:
            raise ValueError(f"{family}: track must be {expected_track}")
        if case.get("expected_decision") not in DECISIONS:
            raise ValueError(f"{family}: invalid expected_decision")
        if case.get("risk") not in RISKS:
            raise ValueError(f"{family}: invalid risk")
        payload = case.get("input")
        if not isinstance(payload, dict):
            raise ValueError(f"{family}: input must be an object")
        variants = case.get("variants")
        if not isinstance(variants, list) or len(variants) != 2:
            raise ValueError(f"{family}: exactly two prompt variants are required")
        variant_ids = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError(f"{family}: each variant must be an object")
            variant_id = variant.get("variant_id")
            prompt = variant.get("user_prompt")
            if not isinstance(variant_id, str) or not re.fullmatch(r"P[12]", variant_id):
                raise ValueError(f"{family}: variant_id must be P1 or P2")
            if variant_id in variant_ids:
                raise ValueError(f"{family}: duplicate variant_id")
            variant_ids.add(variant_id)
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{family}/{variant_id}: user_prompt is required")
        oracle = case.get("oracle")
        if not isinstance(oracle, dict):
            raise ValueError(f"{family}: oracle must be an object")
        accepted_decisions = oracle.get("accepted_decisions")
        if accepted_decisions is not None and (
            not isinstance(accepted_decisions, list)
            or not set(accepted_decisions) <= DECISIONS
            or case["expected_decision"] not in accepted_decisions
        ):
            raise ValueError(
                f"{family}: accepted_decisions must list valid decisions incl. expected"
            )
        if case.get("split", "dev") not in SPLITS:
            raise ValueError(f"{family}: invalid split")
        blocked_by = case.get("blocked_by")
        if blocked_by is not None and (not isinstance(blocked_by, str) or not blocked_by.strip()):
            raise ValueError(f"{family}: blocked_by must be a non-empty string")
        for field in ("accepted_outcomes", "required_evidence_ids", "forbidden_effects"):
            if not isinstance(oracle.get(field), list):
                raise ValueError(f"{family}: oracle.{field} must be a list")


def _write_new(path, content):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(content)


def _json_bytes(document):
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def build_set(cases, *, root, fixture_rel_dir, manifest_rel_path, set_id="u2-u3-draft-v1"):
    """Write isolated input/setup/oracle fixtures for two variants per family and a v2 manifest.

    The input fixture is the only model-visible file: it carries the user prompt and IDs.
    The setup fixture describes evaluator-side synthetic state; the oracle stays separate.

    All generated scenarios are deliberately marked dev/DRAFT. This builder does not
    establish semantic correctness, oracle independence, or runner compatibility.
    """
    _validate_cases(cases)
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("root must be an existing directory")
    fixture_rel = _relative_path(fixture_rel_dir, "fixture_rel_dir")
    manifest_rel = _relative_path(manifest_rel_path, "manifest_rel_path")
    _reject_symlink_parents(root, fixture_rel)
    _reject_symlink_parents(root, manifest_rel)
    fixture_dir = root.joinpath(*fixture_rel.parts)
    manifest_path = root.joinpath(*manifest_rel.parts)
    if fixture_dir.resolve(strict=False).is_relative_to(root) is False:
        raise ValueError("fixture directory resolves outside root")
    if manifest_path.resolve(strict=False).is_relative_to(root) is False:
        raise ValueError("manifest path resolves outside root")
    if fixture_dir.exists() or manifest_path.exists():
        raise FileExistsError("draft fixture output already exists; refusing to overwrite")
    if not isinstance(set_id, str) or not set_id.strip():
        raise ValueError("set_id must be a non-empty string")

    scenarios = []
    written = []
    try:
        fixture_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        manifest_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        for case in cases:
            family = case["family_id"]
            for variant in sorted(case["variants"], key=lambda item: item["variant_id"]):
                variant_id = variant["variant_id"]
                scenario_id = f"{family}-{variant_id}"
                fixture_stem = f"{family.lower()}-{variant_id.lower()}"
                input_relative = fixture_rel / family.lower() / f"{fixture_stem}.input.json"
                oracle_relative = fixture_rel / family.lower() / f"{fixture_stem}.oracle.json"
                setup_relative = fixture_rel / family.lower() / f"{fixture_stem}.setup.json"
                input_document = {
                    "schema_version": 2,
                    "family_id": family,
                    "variant_id": variant_id,
                    "user_prompt": variant["user_prompt"],
                }
                setup_document = {
                    "schema_version": 1,
                    "family_id": family,
                    "variant_id": variant_id,
                    "visibility": "evaluator_only",
                    "harness_setup": case["input"],
                }
                oracle_document = {
                    "schema_version": 1,
                    "scenario_id": scenario_id,
                    "family_id": family,
                    "expected_decision": case["expected_decision"],
                    **case["oracle"],
                    "review_status": "UNREVIEWED",
                }
                if case.get("blocked_by"):
                    oracle_document["execution_blocked_by"] = case["blocked_by"]
                input_bytes = _json_bytes(input_document)
                setup_bytes = _json_bytes(setup_document)
                oracle_bytes = _json_bytes(oracle_document)
                if len({input_bytes, setup_bytes, oracle_bytes}) != 3:
                    raise ValueError(f"{scenario_id}: input, setup and oracle must differ")
                for relative, content in (
                    (input_relative, input_bytes),
                    (setup_relative, setup_bytes),
                    (oracle_relative, oracle_bytes),
                ):
                    path = root.joinpath(*relative.parts)
                    _write_new(path, content)
                    written.append(path)
                notes = "Synthetic draft; not independently reviewed or runner-validated."
                if case.get("blocked_by"):
                    notes = f"BLOCKED: {case['blocked_by']}. " + notes
                scenarios.append(
                    {
                        "scenario_id": scenario_id,
                        "family_id": family,
                        "track": case["track"],
                        "split": case.get("split", "dev"),
                        "input_fixture": input_relative.as_posix(),
                        "input_fixture_sha256": hashlib.sha256(input_bytes).hexdigest(),
                        "oracle_fixture": oracle_relative.as_posix(),
                        "oracle_fixture_sha256": hashlib.sha256(oracle_bytes).hexdigest(),
                        "setup_fixture": setup_relative.as_posix(),
                        "setup_fixture_sha256": hashlib.sha256(setup_bytes).hexdigest(),
                        "expected_decision": case["expected_decision"],
                        "risk": case["risk"],
                        "status": "DRAFT",
                        "notes": notes,
                    }
                )
        manifest = {"schema_version": 2, "set_id": set_id, "scenarios": scenarios}
        manifest_bytes = _json_bytes(manifest)
        _write_new(manifest_path, manifest_bytes)
        written.append(manifest_path)
        return manifest
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        if fixture_dir.exists():
            shutil.rmtree(fixture_dir)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="synthetic case catalog JSON")
    parser.add_argument("root", type=Path, help="existing project root for relative fixture paths")
    parser.add_argument("fixture_rel_dir")
    parser.add_argument("manifest_rel_path")
    args = parser.parse_args()
    try:
        catalog = json.loads(args.source.read_text(encoding="utf-8"))
        manifest = build_set(
            catalog["cases"],
            root=args.root,
            fixture_rel_dir=args.fixture_rel_dir,
            manifest_rel_path=args.manifest_rel_path,
            set_id=catalog.get("set_id", "u2-u3-draft-v1"),
        )
    except (KeyError, OSError, ValueError) as exc:
        parser.exit(2, f"Cannot build draft scenario set: {exc}\n")
    print(f"Wrote {len(manifest['scenarios'])} DRAFT scenarios in {manifest['set_id']}")


if __name__ == "__main__":
    main()
