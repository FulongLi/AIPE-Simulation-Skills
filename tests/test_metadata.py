import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_skills
import update_readme


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "skills.json").read_text())

    def test_metadata_matches_real_skills_and_access(self):
        self.assertEqual([], validate_skills.validate_catalogue(self.data))
        self.assertEqual(13, len(self.data["skills"]))
        ltspice = next(s for s in self.data["skills"] if s["id"] == "pe-ltspice-power-electronics")
        self.assertEqual("free_proprietary", ltspice["access"])
        self.assertFalse(ltspice["external_licence_required"])

    def test_reject_duplicate_and_missing_commercial_requirement(self):
        bad = copy.deepcopy(self.data)
        bad["skills"].append(bad["skills"][0])
        self.assertTrue(validate_skills.validate_catalogue(bad))
        self.data["skills"][0]["external_licence_required"] = False
        self.assertTrue(validate_skills.validate_catalogue(self.data))

    def test_deterministic_readme(self):
        self.assertEqual(update_readme.generate(), update_readme.generate())
        self.assertEqual(update_readme.generate(), (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
