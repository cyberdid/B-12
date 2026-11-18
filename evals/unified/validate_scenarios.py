"""Validate a synthetic scenario set before it reaches an evaluation harness."""

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).with_name("scenarios.schema.json")
SCHEMA_V2 = Path(__file__).with_name("scenarios-v2.schema.json")


def validate(document, root):
    schema_version = document.get("schema_version")
    schema_path = {1: SCHEMA, 2: SCHEMA_V2}.get(schema_version)
    if schema_path is None:
        return ["schema_version"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    problems = [
        f"schema: {error.message}" for error in Draft202012Validator(schema).iter_errors(document)
    ]
    if problems:
        return sorted(problems)
    root = Path(root).resolve()
    ids, families = set(), {}
    inputs, oracles, setups = {}, {}, {}
    for scenario in document["scenarios"]:
        sid = scenario["scenario_id"]
        if sid in ids:
            problems.append(f"{sid}: duplicate scenario_id")
        ids.add(sid)
        family, split = scenario["family_id"], scenario["split"]
        if family in families and families[family] != split:
            problems.append(f"{family}: family crosses split boundaries")
        families[family] = split
        if ("setup_fixture" in scenario) != ("setup_fixture_sha256" in scenario):
            problems.append(f"{sid}: setup_fixture and its sha256 must appear together")
        checks = [
            ("input_fixture", "input_fixture_sha256", inputs),
            ("oracle_fixture", "oracle_fixture_sha256", oracles),
        ]
        if "setup_fixture" in scenario and "setup_fixture_sha256" in scenario:
            checks.append(("setup_fixture", "setup_fixture_sha256", setups))
        for key, hashes_key, fixtures in checks:
            try:
                digest, identity = _hash_fixture(root, scenario[key])
            except FileNotFoundError:
                problems.append(f"{sid}: {key} missing or not a regular file")
                continue
            except (OSError, ValueError):
                problems.append(f"{sid}: {key} outside or unsafe fixture path")
                continue
            fixtures.setdefault(identity, set()).add(digest)
            if schema_version == 2 and digest != scenario[hashes_key]:
                problems.append(f"{sid}: {key} hash mismatch")
    if inputs.keys() & oracles.keys():
        problems.append("oracle fixture is also used as input")
    if inputs.keys() & setups.keys():
        problems.append("setup fixture is also used as input")
    input_hashes = {digest for digests in inputs.values() for digest in digests}
    oracle_hashes = {digest for digests in oracles.values() for digest in digests}
    if input_hashes & oracle_hashes:
        problems.append("oracle fixture has identical content to an input")
    setup_hashes = {digest for digests in setups.values() for digest in digests}
    if input_hashes & setup_hashes:
        problems.append("setup fixture has identical content to an input")
    return sorted(problems)


def _hash_fixture(root, relative_path):
    relative = PurePosixPath(relative_path)
    if (
        not relative_path
        or "\\" in relative_path
        or relative.as_posix() != relative_path
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("fixture path must be a normalized relative POSIX path")

    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if not directory_flag or not nofollow_flag or os.open not in os.supports_dir_fd:
        raise ValueError("platform lacks safe relative file opening support")
    current_fd = os.open(root, os.O_RDONLY | directory_flag)
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | directory_flag | nofollow_flag,
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(relative.parts[-1], os.O_RDONLY | nofollow_flag, dir_fd=current_fd)
        try:
            file_stat = os.fstat(file_fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise ValueError("fixture is not a regular file")
            with os.fdopen(file_fd, "rb", closefd=False) as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            return digest, (file_stat.st_dev, file_stat.st_ino)
        finally:
            os.close(file_fd)
    finally:
        os.close(current_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_set", type=Path)
    parser.add_argument("fixture_root", type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.scenario_set.read_text(encoding="utf-8"))
        problems = validate(document, args.fixture_root)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot validate: {exc}\n")
    if problems:
        parser.exit(1, "\n".join(problems) + "\n")
    print("Scenario set valid; semantic checks are limited to documented scope.")


if __name__ == "__main__":
    main()
