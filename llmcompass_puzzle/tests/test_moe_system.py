"""Conservation and admission tests; synthetic timing coefficients are not calibration."""
import copy
import unittest

from ratio_dse.common import ROOT, read_json
from ratio_dse.area_model import import_profiles
from llmcompass_puzzle.characterize import scale_profile
from llmcompass_puzzle.moe_system import (E, Q, evaluate, make_design, matrix_stage,
                                         packed, resident_bytes, routing)
from llmcompass_puzzle.system_contract import quantization_work


class MoESystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = read_json(ROOT/'llmcompass_puzzle/configs/moe_system_study.json')
        a = read_json(ROOT/'llmcompass_puzzle/configs/characterize.json')
        hardware, _ = import_profiles(read_json(ROOT/a['dp_evidence']))
        cls.p = scale_profile(hardware['profiles'][0], a['process'], a['common_clock_hz'])
        cls.s, cls.power = cls.cfg['settings'], cls.cfg['power']
        cls.d = make_design(cls.p, 128, 1, cls.cfg['hbm_bundles'][1], cls.cfg['l2_bundles'][1], cls.s)
        cls.model = read_json(ROOT/'paper/data/inputs/models/DeepSeek-V4-Flash/inference/config.json')

    def test_routing_conserves_work_without_averaging_hot_experts(self):
        maxima = []
        for policy in ('balanced', 'hot'):
            ranks = routing(self.model, 2048, 8, policy)
            assignments = [sum(m*n for m,n in rank.items()) for rank in ranks]
            self.assertEqual(sum(assignments), 2048*self.model['n_activated_experts'])
            maxima.append(max(assignments))
        self.assertGreater(maxima[1], maxima[0])

    def test_residency_uses_all_experts_and_nv_metadata(self):
        w = resident_bytes(self.model, 'w4a8', 8, 0)
        self.assertEqual(w, resident_bytes(self.model, 'routed_mxfp4', 8, 0))
        self.assertGreater(resident_bytes(self.model, 'routed_nvfp4', 8, 0), w)
        changed = self.model | {'n_activated_experts': 1}
        self.assertEqual(w, resident_bytes(changed, 'w4a8', 8, 0))
        result, trace = evaluate(self.model, 256, 'w4a8', True,
                                 self.d | {'hbm_capacity_bytes': 1}, self.p, self.s, self.power, None)
        self.assertEqual(result['status'], 'capacity_infeasible')
        self.assertEqual(trace, [])

    def test_local_unpack_not_hbm_materialization_and_spill_rereads(self):
        settings = self.s | {'tiles': [[32, 128]]}
        args = ('expert', {64: 2}, 256, 512)
        q = matrix_stage(*args, Q, E, self.d, self.p, 0, settings, self.power, None)
        e = matrix_stage(*args, E, E, self.d, self.p, 0, settings, self.power, None)
        self.assertEqual(q['hbm_bytes'], 2*packed(256, 512, E))
        self.assertEqual(q['hbm_bytes'], e['hbm_bytes'])
        self.assertEqual(q['useful_macs'], e['useful_macs'])
        self.assertGreater(q['vector_service_s'], 0)
        self.assertEqual(e['vector_service_s'], 0)
        spill = matrix_stage(*args, Q, E, self.d, self.p, self.d['l2_bytes']+1,
                             settings, self.power, None)
        self.assertEqual(spill['hbm_bytes']-q['hbm_bytes'], 2*packed(64,512,Q)*2+2*2*64*256)
        self.assertIsNone(matrix_stage(*args, Q, E, self.d | {'sram_bytes': 1}, self.p,
                                      0, settings, self.power, None))

    def test_quant_formats_and_fusion_keep_conversion_work(self):
        q = quantization_work(1,32,Q,self.s['quant_recipe'])
        e = quantization_work(1,32,E,self.s['quant_recipe'])
        nv = quantization_work(1,32,'nvfp4',self.s['quant_recipe'])
        self.assertEqual(q['source_read_bytes']+q['output_payload_bytes']+q['output_scale_bytes'],97)
        self.assertEqual(e['source_read_bytes']+e['output_payload_bytes']+e['output_scale_bytes'],81)
        self.assertEqual((nv['blocks'],nv['output_scale_bytes']), (2,6))
        standalone, st = evaluate(self.model,256,'routed_mxfp4',False,self.d,self.p,self.s,self.power,None)
        fused, ft = evaluate(self.model,256,'routed_mxfp4',True,self.d,self.p,self.s,self.power,None)
        self.assertLess(fused['seconds'],standalone['seconds'])
        self.assertEqual([r['vector_service_s'] for r in st], [r['vector_service_s'] for r in ft])
        self.assertEqual(len([r for r in ft if r['name'].startswith('input_quant')]), 2)

    def test_cap_is_per_stage_and_insufficient_power_rejects(self):
        result, rows = evaluate(self.model,2048,'w4a8',True,self.d,self.p,self.s,self.power,250)
        self.assertEqual(result['status'],'analytical_subgraph')
        self.assertTrue(all(r['power_envelope_w_proxy'] <= 250 for r in rows))
        self.assertTrue(all(r['energy_j_proxy'] <= r['power_envelope_w_proxy']*r['seconds']+1e-9 for r in rows))
        failed, _ = evaluate(self.model,2048,'w4a8',True,self.d,self.p,self.s,self.power,1)
        self.assertEqual(failed['status'],'power_or_mapping_infeasible')


if __name__ == '__main__':
    unittest.main()
