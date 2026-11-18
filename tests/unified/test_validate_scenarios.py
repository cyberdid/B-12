import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "evals/unified/validate_scenarios.py"


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "inputs").mkdir()
        (self.root / "oracles").mkdir()
        (self.root / "inputs/a.json").write_text("{}")
        (self.root / "oracles/a.json").write_text('{"expected":true}')
        self.scenario = {
            "scenario_id": "s1",
            "family_id": "f1",
            "track": "memory",
            "split": "dev",
            "input_fixture": "inputs/a.json",
            "oracle_fixture": "oracles/a.json",
            "expected_decision": "NO_TOOL",
            "risk": "read_only",
            "status": "DRAFT",
        }

    def validate(self, scenarios, version=1):
        if not PATH.exists():
            self.fail("scenario validator is missing")
        spec = importlib.util.spec_from_file_location("scenario_validator", PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.validate(
            {"schema_version": version, "set_id": "demo", "scenarios": scenarios}, self.root
        )

    def frozen_scenario(self):
        scenario = dict(self.scenario, status="FROZEN")
        scenario["input_fixture_sha256"] = hashlib.sha256(
            (self.root / scenario["input_fixture"]).read_bytes()
        ).hexdigest()
        scenario["oracle_fixture_sha256"] = hashlib.sha256(
            (self.root / scenario["oracle_fixture"]).read_bytes()
        ).hexdigest()
        return scenario

    def test_valid_set(self):
        self.assertEqual(self.validate([self.scenario]), [])

    def test_family_cannot_cross_splits(self):
        second = dict(self.scenario, scenario_id="s2", split="locked_test")
        self.assertTrue(any("split" in x for x in self.validate([self.scenario, second])))

    def test_duplicate_scenario_id(self):
        self.assertTrue(
            any("duplicate" in x for x in self.validate([self.scenario, self.scenario]))
        )

    def test_oracle_must_not_be_input(self):
        self.scenario["oracle_fixture"] = self.scenario["input_fixture"]
        self.assertTrue(any("oracle" in x for x in self.validate([self.scenario])))

    def test_symlink_escape_rejected(self):
        (self.root / "inputs/escape").symlink_to(Path("/etc/passwd"))
        self.scenario["input_fixture"] = "inputs/escape"
        self.assertTrue(any("outside" in x for x in self.validate([self.scenario])))

    def test_nonexistent_fixture_rejected(self):
        self.scenario["input_fixture"] = "inputs/missing"
        self.assertTrue(any("missing" in x for x in self.validate([self.scenario])))

    def test_copied_oracle_content_rejected(self):
        (self.root / "oracles/a.json").write_bytes((self.root / "inputs/a.json").read_bytes())
        self.assertTrue(any("oracle" in x for x in self.validate([self.scenario])))

    def test_hardlinked_oracle_rejected(self):
        (self.root / "oracles/a.json").unlink()
        (self.root / "oracles/a.json").hardlink_to(self.root / "inputs/a.json")
        self.assertTrue(any("oracle" in x for x in self.validate([self.scenario])))

    def test_v2_validates_frozen_fixture_hashes(self):
        scenario = self.frozen_scenario()
        self.assertEqual(self.validate([scenario], version=2), [])
        (self.root / "inputs/a.json").write_text('{"changed":true}')
        self.assertTrue(any("hash mismatch" in x for x in self.validate([scenario], version=2)))

    def test_v2_rejects_symlink_even_when_target_is_inside_root(self):
        (self.root / "inputs/alias").symlink_to("a.json")
        scenario = self.frozen_scenario()
        scenario["input_fixture"] = "inputs/alias"
        self.assertTrue(any("unsafe" in x for x in self.validate([scenario], version=2)))

    def test_v2_requires_fixture_hashes(self):
        scenario = dict(self.scenario, status="FROZEN")
        problems = self.validate([scenario], version=2)
        self.assertTrue(any("input_fixture_sha256" in x for x in problems))
        self.assertTrue(any("oracle_fixture_sha256" in x for x in problems))

    def test_v2_hashes_optional_setup_fixture(self):
        (self.root / "setups").mkdir()
        (self.root / "setups/a.json").write_text('{"harness_setup":{}}')
        scenario = self.frozen_scenario()
        scenario["setup_fixture"] = "setups/a.json"
        scenario["setup_fixture_sha256"] = hashlib.sha256(
            (self.root / "setups/a.json").read_bytes()
        ).hexdigest()
        self.assertEqual(self.validate([scenario], version=2), [])
        (self.root / "setups/a.json").write_text('{"harness_setup":{"x":1}}')
        problems = self.validate([scenario], version=2)
        self.assertTrue(any("setup_fixture hash mismatch" in x for x in problems))

    def test_v2_setup_fixture_requires_its_hash_and_differs_from_input(self):
        scenario = self.frozen_scenario()
        scenario["setup_fixture"] = "inputs/a.json"
        problems = self.validate([scenario], version=2)
        self.assertTrue(any("must appear together" in x for x in problems))
        scenario["setup_fixture_sha256"] = scenario["input_fixture_sha256"]
        problems = self.validate([scenario], version=2)
        self.assertTrue(any("setup fixture is also used as input" in x for x in problems))
