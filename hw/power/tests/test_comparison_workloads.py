"""Architecture comparisons must keep source activity and exact math unchanged."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'hw/power/scripts'))
import report_current_six as report


class ComparisonWorkloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mocked = patch.object(report, 'ROOT', self.root)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.points = []
        for name in ('old', 'new'):
            directory = self.root / name
            directory.mkdir()
            (directory / 'manifest.json').write_text('{}')
            (directory / 'inputs.jsonl').write_text('same original inputs')
            (directory / 'source_reference.jsonl').write_text('same source reference')
            rows = [dict(id=index, last=index == 1023, exact_fp32_or_int32='3f800000',
                         exact_value='1', cmodel_results={name: '3f800000'}) for index in range(1024)]
            (directory / 'expected.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            self.points.append(dict(dataset_directory=name))
        self.rehash()

    def rehash(self):
        for point in self.points:
            directory = self.root / point['dataset_directory']
            point['dataset_manifest_sha256'] = report.digest(directory / 'manifest.json')
            point['dataset_files_sha256'] = {
                name: report.digest(directory / name)
                for name in ('inputs.jsonl', 'source_reference.jsonl', 'expected.jsonl')}

    def test_changed_model_namespace_with_same_workload_allowed(self):
        report.compare_workloads(*self.points)

    def test_different_stimulus_rejected_even_with_updated_hash(self):
        (self.root / 'new/inputs.jsonl').write_text('different activity')
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'workload or exact'):
            report.compare_workloads(*self.points)

    def test_different_exact_math_rejected_even_with_updated_hash(self):
        path = self.root / 'new/expected.jsonl'
        path.write_text(path.read_text().replace('3f800000', '40000000', 1))
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'workload or exact'):
            report.compare_workloads(*self.points)

    def test_artifact_tamper_rejected(self):
        (self.root / 'new/expected.jsonl').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            report.compare_workloads(*self.points)


if __name__ == '__main__':
    unittest.main()
