"""Check whether a structurally valid run manifest is ready for reproduction."""

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).with_name("manifest.schema.json")
SCHEMA_V2 = Path(__file__).with_name("manifest-v2.schema.json")
_REQUIRED = {
    "environment": ("host", "os", "python", "cpu", "gpu", "vram_bytes", "ram_bytes", "power_mode"),
    "model": (
        "name",
        "digest",
        "quantization",
        "runtime_version",
        "profile_sha256",
        "tokenizer_sha256",
        "chat_template_sha256",
    ),
    "configuration": ("context_tokens", "output_tokens", "repeats", "snapshot_sha256"),
}


def readiness_issues(manifest, artifact_root):
    schema_version = manifest.get("schema_version")
    schema_path = {1: SCHEMA, 2: SCHEMA_V2}.get(schema_version)
    if schema_path is None:
        return ["schema_version"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(manifest))
    if errors:
        return ["schema: " + error.message for error in errors]
    issues = []
    if manifest["status"] != "COMPLETED":
        issues.append("status")
    if schema_version == 1:
        if not manifest["scenario_set_sha256"]:
            issues.append("scenario_set_sha256")
        for section, fields in _REQUIRED.items():
            for field in fields:
                value = manifest[section][field]
                if value is None or value == "":
                    issues.append(f"{section}.{field}")
        if manifest["configuration"]["cache_state"] == "unknown":
            issues.append("configuration.cache_state")
    else:
        for field in ("os", "python", "cpu", "ram_bytes"):
            value = manifest["environment"][field]
            if value is None or value == "":
                issues.append(f"environment.{field}")
        if manifest["run_type"] == "software_suite":
            suite = manifest.get("suite") or {}
            for field in ("name", "command", "source_snapshot_sha256"):
                if not suite.get(field):
                    issues.append(f"suite.{field}")
            if not suite.get("test_roots"):
                issues.append("suite.test_roots")
            if not manifest["configuration"]["snapshot_sha256"]:
                issues.append("configuration.snapshot_sha256")
            elif (
                suite.get("source_snapshot_sha256") != manifest["configuration"]["snapshot_sha256"]
            ):
                issues.append("configuration.snapshot_sha256_mismatch")
            if manifest["configuration"]["cache_state"] != "not_applicable":
                issues.append("configuration.cache_state")
        else:
            if not manifest["scenario_set_sha256"]:
                issues.append("scenario_set_sha256")
            for section, fields in _REQUIRED.items():
                for field in fields:
                    value = manifest[section][field]
                    if value is None or value == "":
                        issues.append(f"{section}.{field}")
            if manifest["configuration"]["cache_state"] == "unknown":
                issues.append("configuration.cache_state")
    if not manifest["raw_results"]:
        issues.append("raw_results")
    root = Path(artifact_root).resolve()
    for artifact in manifest["raw_results"]:
        try:
            digest = _hash_safe_artifact(root, artifact["path"])
        except (OSError, ValueError):
            issues.append("raw_results.invalid_path")
            continue
        if digest != artifact["sha256"]:
            issues.append("raw_results.hash_mismatch")
    return issues


def _hash_safe_artifact(root, relative_path):
    """Hash a regular file beneath root without following any symlink component."""
    relative = PurePosixPath(relative_path)
    if (
        not relative_path
        or "\\" in relative_path
        or relative.as_posix() != relative_path
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("artifact path must be a normalized relative POSIX path")

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
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ValueError("artifact is not a regular file")
            with os.fdopen(file_fd, "rb", closefd=False) as source:
                return hashlib.file_digest(source, "sha256").hexdigest()
        finally:
            os.close(file_fd)
    finally:
        os.close(current_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        issues = readiness_issues(manifest, args.artifact_root)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"cannot validate manifest: {exc}\n")
    if issues:
        parser.exit(1, "\n".join(issues) + "\n")
    print("Metadata and referenced files are present; verify their accuracy separately.")


if __name__ == "__main__":
    main()
