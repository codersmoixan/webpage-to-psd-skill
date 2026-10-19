import json
import tempfile
import unittest
from pathlib import Path

from generate_photoshop_batch_runner import load_manifest, rebuild_runner, type_edit_runner
from verify_delivery_bundle import safe_arcname, verify_visual_review


class BatchHelperTests(unittest.TestCase):
    def test_rebuild_runner_uses_manifest_paths_and_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / 'jobs.json'
            manifest.write_text(json.dumps({'waitSeconds': 9, 'jobs': [{
                'name': 'page-a', 'rebuildScript': 'a/rebuild.jsx',
                'result': 'a/result.json', 'resultStatus': 'ready'
            }]}), encoding='utf-8')
            path, data = load_manifest(manifest)
            source = rebuild_runner(path, data)
            self.assertIn('page-a', source)
            self.assertIn('a/rebuild.jsx', source)
            self.assertIn('ready', source)
            self.assertIn('waitMs=9000', source)

    def test_type_runner_requires_existing_psd_and_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'page.psd').write_bytes(b'fixture')
            manifest = root / 'jobs.json'
            manifest.write_text(json.dumps({'jobs': [{'name': 'page', 'psd': 'page.psd'}]}), encoding='utf-8')
            path, data = load_manifest(manifest)
            source = type_edit_runner(path, data)
            self.assertIn('SaveOptions.DONOTSAVECHANGES', source)
            self.assertIn("contents+' test'", source)
            self.assertIn("size*2", source)

    def test_visual_review_and_archive_paths_are_strict(self):
        with tempfile.TemporaryDirectory() as folder:
            review = Path(folder) / 'visual.json'
            review.write_text(json.dumps({'overview': True, 'layout': 'reviewed',
                'missingImagery': False, 'largeOffsets': False,
                'nativePixelCrops': ['heading']}), encoding='utf-8')
            verify_visual_review(review)
            self.assertEqual(safe_arcname('page/final.psd'), 'page/final.psd')
            with self.assertRaises(ValueError):
                safe_arcname('../outside.psd')

    def test_duplicate_names_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'jobs.json'
            manifest.write_text(json.dumps({'jobs': [{'name': 'same'}, {'name': 'same'}]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'unique'):
                load_manifest(manifest)


if __name__ == '__main__':
    unittest.main()
