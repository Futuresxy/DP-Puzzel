"""Check the delivered power corpus without requiring its external source tree."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.cmodel import ROOT, DEFAULT_CONFIG, read_inputs, sha256
from adapters.logical import read_logical_inputs
from cases.import_qwen_power import DATASET, H_MODES, selections
from reference.exact import reference
from reference.logical import exact_logical, serialize_exact


class QwenPowerData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {}
        for _, modes, logical_k in selections():
            for mode in modes:
                directory = ROOT / 'test/data/power' / mode / f'K{logical_k}' / DATASET
                manifest = json.loads((directory / 'manifest.json').read_text())
                rows = (read_inputs(directory / 'inputs.txt')[1] if mode in H_MODES
                        else read_logical_inputs(directory)[1])
                expected = [json.loads(line) for line in (directory / 'expected.jsonl').read_text().splitlines()]
                cls.data[mode, logical_k] = directory, manifest, rows, expected

    def test_counts_hashes_and_control(self):
        self.assertEqual(len(self.data), 15)
        for directory, manifest, rows, expected in self.data.values():
            with self.subTest(directory=directory):
                self.assertEqual(len(rows), 1024)
                self.assertEqual(len(expected), 1024)
                self.assertEqual([row['id'] for row in rows], list(range(1024)))
                self.assertEqual([row['last'] for row in rows], [False] * 1023 + [True])
                self.assertFalse(manifest['ppa_eligible'])
                for name, digest in manifest['files_sha256'].items():
                    self.assertEqual(sha256(directory / name), digest)

    def test_shared_c_and_native_prefixes(self):
        shared_c = [int(row['c'], 16) for row in self.data['bf16', 16][2]]
        for (mode, logical_k), (_, manifest, rows, _) in self.data.items():
            with self.subTest(mode=mode, logical_k=logical_k):
                self.assertEqual([int(row['c'], 16) for row in rows], shared_c)
                if mode in H_MODES:
                    continue
                for (other_mode, other_k), (_, _, other_rows, _) in self.data.items():
                    if other_mode != mode or other_k <= logical_k:
                        continue
                    for field, width in manifest['packed_widths'].items():
                        self.assertEqual([int(row[field], 16) for row in rows],
                                         [int(row[field], 16) & ((1 << width) - 1) for row in other_rows])

    def test_exact_values_are_recomputed_from_packed_inputs(self):
        for (mode, logical_k), (_, _, rows, expected) in self.data.items():
            with self.subTest(mode=mode, logical_k=logical_k):
                for request, golden in zip(rows, expected):
                    exact = (reference(request, DEFAULT_CONFIG) if mode in H_MODES
                             else exact_logical(request, logical_k))
                    self.assertEqual(f"{exact['bits']:08x}", golden['exact_fp32_or_int32'])
                    self.assertEqual(serialize_exact(exact), golden['exact_value'])
                    self.assertEqual(golden['d'], golden['cmodel_results'][golden['cmodel_reference_frontend']])


if __name__ == '__main__':
    unittest.main()
