import copy
from pathlib import Path
import tempfile
import unittest

from ratio_dse.common import digest
from llmcompass_puzzle.quality import assess_quality, quality_key


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        artifact = Path(self.tmp.name) / "synthetic-unit-fixture.json"
        artifact.write_text('{"test_only": true}')
        self.key = quality_key("revision", "config", {"scope": "routed_experts", "activation": "MXFP4"})
        self.requirement = {"id": "ppl", "metric": "perplexity", "unit": "ppl", "dataset": "test-only",
                            "dataset_revision": "1", "protocol": "fixed-token-window", "scope": "full_model",
                            "direction": "lower", "degradation_mode": "relative", "max_degradation": 0.02}
        self.record = {k: v for k, v in self.requirement.items() if k in
                       ("metric", "unit", "dataset", "dataset_revision", "protocol", "scope")}
        self.record.update(quality_key=self.key, evidence_kind="synthetic_test_only", reference_value=10,
                           candidate_value=10.2, artifact=str(artifact), artifact_sha256=digest(artifact))

    def gate(self, records, requirements=None):
        return assess_quality(self.key, {"requirements": requirements or [self.requirement]}, records,
                              allow_test_records=True)

    def test_exact_threshold_and_recipe_binding(self):
        self.assertTrue(self.gate([self.record])["admitted"])
        wrong = self.record | {"quality_key": "different-recipe"}
        self.assertEqual(self.gate([wrong])["status"], "unknown")
        altered = self.record | {"candidate_value": 10.21}
        self.assertEqual(self.gate([altered])["status"], "failed")

    def test_missing_required_metric_not_passed_and_policy_separate(self):
        accuracy = self.requirement | {"id": "accuracy", "metric": "accuracy", "unit": "fraction"}
        self.assertEqual(self.gate([self.record], [self.requirement, accuracy])["status"], "unknown")
        self.assertFalse(assess_quality(self.key, {"requirements": []}, [self.record])["admitted"])
        strict = self.requirement | {"max_degradation": 0.01}
        self.assertFalse(self.gate([self.record | {"max_degradation": 1}], [strict])["admitted"])

    def test_unverified_artifact_or_prior_cannot_certify(self):
        for record in (self.record | {"artifact_sha256": "bad"}, self.record | {"evidence_kind": "literature_prior"}):
            self.assertEqual(self.gate([record])["status"], "unknown")
        self.assertFalse(assess_quality(self.key, {"requirements": [self.requirement]}, [self.record])["admitted"])
        with self.assertRaises(ValueError):
            self.gate([self.record, copy.deepcopy(self.record)])
