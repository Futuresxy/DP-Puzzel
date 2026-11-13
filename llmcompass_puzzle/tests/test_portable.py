import json
from pathlib import Path
import tempfile
import unittest

from llmcompass_puzzle.backend import verify_source_snapshot
from llmcompass_puzzle.export_handoff import sha, verify


class PortableTests(unittest.TestCase):
    def test_source_archive_retains_revision_and_hash_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'source.py';source.write_text('x = 1\n')
            lock={'commit':'fixed-revision','submodules':[], 'upstream_source_sha256':{'source.py':sha(source)}}
            snapshot={'schema_version':1,'commit':lock['commit'],'submodules':{},'files_sha256':lock['upstream_source_sha256']}
            (root/'.puzzle-source.json').write_text(json.dumps(snapshot))
            verify_source_snapshot(root,lock)
            source.write_text('x = 2\n')
            with self.assertRaisesRegex(ValueError,'modified portable source'):
                verify_source_snapshot(root,lock)
            source.write_text('x = 1\n')
            snapshot['commit']='another-revision'
            (root/'.puzzle-source.json').write_text(json.dumps(snapshot))
            with self.assertRaisesRegex(ValueError,'revision mismatch'):
                verify_source_snapshot(root,lock)

    def test_bundle_check_rejects_missing_modified_or_escaping_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'input.json';file.write_text('{}')
            manifest={'scope':'unit test','files_sha256':{'input.json':sha(file)}}
            (root/'handoff_manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(verify(root)['verified_files'],1)
            file.unlink()
            with self.assertRaisesRegex(ValueError,'missing or changed'):verify(root)
            manifest['files_sha256']={'../outside':'bad'}
            (root/'handoff_manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'workspace-relative'):verify(root)
