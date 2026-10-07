import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("buck_control", ROOT / "pe-python-control-analysis/scripts/buck_control.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class OpenExampleTests(unittest.TestCase):
    def test_buck_gain_and_final_value(self):
        for vin in (24.0, 48.0, 60.0):
            for load in (5.0, 10.0, 20.0):
                report = model.analyse(vin=vin, resistance=load)
                values = report["results"]
                expected = 0.02 * vin / (1 + 0.02 * vin)
                self.assertAlmostEqual(vin, values["plant_dc_gain"]["value"])
                self.assertAlmostEqual(expected, values["closed_loop_dc_gain"]["value"])
                self.assertAlmostEqual(expected, values["final_unit_reference_response"]["value"], delta=1e-4)
                self.assertTrue(values["stable_linear_poles"])
                self.assertFalse(report["validation"]["measured"])
                json.dumps(report, allow_nan=False)

    def test_reject_nonphysical_inputs(self):
        for invalid in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                model.analyse(inductance=invalid)

    @unittest.skipUnless(shutil.which("ngspice"), "ngspice not installed; no solver execution claimed")
    def test_ngspice_buck_and_timestep_refinement(self):
        netlist = (ROOT / "pe-ngspice-switching-validation/assets/ideal-buck.cir").read_text()
        values = []
        with tempfile.TemporaryDirectory() as temporary:
            for step in ("100n", "50n"):
                directory = Path(temporary)
                model_path, log = directory / "buck.cir", directory / "buck.log"
                model_path.write_text(netlist.replace(".tran 100n 20m 0 100n", f".tran {step} 20m 0 {step}"))
                process = subprocess.run([shutil.which("ngspice"), "-b", "-o", str(log), str(model_path)], capture_output=True, text=True, cwd=temporary, timeout=60)
                output = log.read_text() if log.exists() else process.stdout + process.stderr
                self.assertEqual(0, process.returncode, output)
                match = re.search(r"vout_avg\s*=\s*([0-9.eE+-]+)", output)
                self.assertIsNotNone(match, output)
                average = float(match.group(1))
                self.assertGreater(average, 23)
                self.assertLess(average, 25)
                values.append(average)
        self.assertLess(abs(values[0] - values[1]), 0.05)


if __name__ == "__main__":
    unittest.main()
