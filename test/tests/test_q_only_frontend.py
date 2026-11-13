"""Q-only contract defaults, rejection boundary and token special semantics."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import ROOT, evaluate
from cases.common import make

RUN = ROOT / 'test/runs/cmodel/q_only_contract'


class QOnlyContract(unittest.TestCase):
    def test_new_profiles_default_to_current_arithmetic(self):
        for profile in ('q', 't8h16q64e64'):
            request = make('mxfp8_e5m2', 16 if profile == 'q' else 32)
            implicit = evaluate([request], config=dict(frontend=profile), run_dir=RUN)
            explicit = evaluate([request], config=dict(frontend=profile, architecture_v19=True), run_dir=RUN)
            self.assertEqual(implicit, explicit)

    def test_new_profiles_reject_legacy_arithmetic(self):
        RUN.mkdir(parents=True, exist_ok=True)
        for profile in ('q', 't8h16q64e64'):
            config = RUN / 'illegal_config.json'
            config.write_text(json.dumps(dict(frontend=profile, architecture_v19=False)))
            process = subprocess.run([str(ROOT / 'src/cmodel/build/dp_cmodel_cli'),
                                      '--config', str(config)], text=True, capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn('Q-only profiles require architecture_v19=true', process.stderr)

    def test_nan_scale_infinity_token_contract(self):
        request = make('mxfp8_e5m2', 32, a=[0] * 32 + [0x7c] * 32,
                       b=[0x3c] * 64, sa=[127, 255], sb=[127, 127])
        result = evaluate([request], config=dict(frontend='t8h16q64e64'), trace=True, run_dir=RUN)[0]
        for token in result['trace'][4]['data']['groups'][4:]:
            self.assertTrue(token['special']['nan'])
            self.assertTrue(token['special']['invalid'])
            self.assertFalse(token['special']['positive_inf'])
            self.assertFalse(token['special']['negative_inf'])


if __name__ == '__main__':
    unittest.main()
