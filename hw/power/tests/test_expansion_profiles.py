"""Power stimuli must reach the last physical group and use native workload K."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'hw/power/scripts' / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


runner = module('expansion_runner', 'run_power.py')
prepare = module('expansion_prepare', 'prepare_expansion_plan.py')


class ExpansionPowerTest(unittest.TestCase):
    def test_last_physical_group_survives_vector_encoding(self):
        for top, groups in [('dp_top_t8h16q64e64', 8), ('dp_top_t8h16q32e192', 12),
                            ('dp_top_t8h16q32e256', 16), ('dp_top_t8h16q96e192', 12),
                            ('dp_top_t8h16q128e256', 16)]:
            with self.subTest(top=top), tempfile.TemporaryDirectory() as temporary:
                work = Path(temporary)
                request = dict(a_datatype=3, b_datatype=3, c_datatype=0,
                               a_scale_datatype=1, b_scale_datatype=1, last=False,
                               a=hex(1 << ((groups-1)*64))[2:], b='0', c='0',
                               a_scale='0', b_scale='0', a_e1='0', b_e1='0', a_e2='0', b_e2='0')
                point = dict(top=top, cmodel_frontend=top[7:])
                expected = dict(cmodel_results={point['cmodel_frontend']: '00000000'}, last=False)
                with patch.object(runner, 'check_data', return_value=([request], [expected])), \
                     patch.object(runner, 'evaluate', side_effect=lambda rows, **kwargs:
                                  [dict(d='00000000', d_datatype=0, last=False) for row in rows]):
                    runner.prepare_vectors(point, work, runner.physical_groups(top))
                row = (work / 'vectors.txt').read_text().splitlines()[-1].split()
                self.assertEqual(int(row[4], 16), 1 << ((groups-1)*64))
                self.assertEqual(len(row[4]), groups*16)

    def test_unknown_top_does_not_silently_use_four_groups(self):
        with self.assertRaisesRegex(ValueError, 'Unknown physical'):
            runner.physical_groups('dp_top_future')

    def test_wrong_native_k_rejected_before_model_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / 'manifest.json').write_text(json.dumps(dict(datatype=7, logical_k=128)))
            with self.assertRaisesRegex(ValueError, 'native K'):
                prepare.derive(path, path / 'out', 't8h16q32e192', path / 'archive', {})

    def test_other_frequency_cannot_be_labelled_one_ghz(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / 'inputs').mkdir()
            resolved = dict(gate=dict(top='dp_top_t8h16q32e192'),
                            technology=dict(pvt=dict(corner='TT', voltage_v=0.7, temperature_c=85)),
                            constraints=dict(period_ns=2, clock_gating=True))
            (path / 'inputs/resolved.json').write_text(json.dumps(resolved))
            with self.assertRaisesRegex(ValueError, 'declared N12 TT 1GHz'):
                prepare.make_plan('t8h16q32e192', path / 'archive', [], path, 'test')


if __name__ == '__main__':
    unittest.main()
