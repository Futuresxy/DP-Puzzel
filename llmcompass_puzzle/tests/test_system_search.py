import csv
import json
import os
from pathlib import Path
import tempfile
import unittest

from ratio_dse.common import ROOT, digest, read_json
from llmcompass_puzzle.system_search import run
from llmcompass_puzzle.summarize_system import summarize


class SearchTests(unittest.TestCase):
    def test_external_config_manifest_and_unknown_quality_exclusion(self):
        cfg = read_json(ROOT/'llmcompass_puzzle/configs/moe_system_study.json')
        for key in ('models','tokens','plans','fusion','physical_sms','vector_scales','caps_w','hbm_bundles','l2_bundles'):
            cfg[key] = cfg[key][:1]
        cfg['fusion']=[True,False]
        cfg['study_design']['fixed_system']={'physical_sms':cfg['physical_sms'][0],
            'vector_scale':cfg['vector_scales'][0],'hbm_id':cfg['hbm_bundles'][0]['id'],'l2_id':cfg['l2_bundles'][0]['id']}
        cfg['study_design']['primary_case']['tokens']=cfg['tokens'][0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input.json'
            path.write_text(json.dumps(cfg))
            output = Path(directory)/'output'
            result = run(Path(os.path.relpath(path)), output)
            self.assertEqual(result['designs'], 9)
            self.assertEqual(result['quality_recommendations'], 0)
            manifest = read_json(output/'manifest.json')
            self.assertEqual(manifest['inputs_sha256'][str(path)],digest(path))
            for name, sha in manifest['outputs_sha256'].items():
                self.assertEqual(digest(output/name),sha)
            with (output/'quality_constrained_selections.csv').open() as stream:
                self.assertEqual(list(csv.DictReader(stream)),[])
            with (output/'cost_only_selections.csv').open() as stream:
                directions = {r['direction'] for r in csv.DictReader(stream)}
            self.assertEqual(directions,{'hardware_to_migration','workload_to_hardware'})
            summary=summarize(output,Path(directory)/'summary')
            self.assertEqual(summary['primary_cells'],18)
            self.assertEqual(summary['quality_recommendations'],0)
            with self.assertRaises(ValueError):
                run(path,output)


if __name__ == '__main__':
    unittest.main()
