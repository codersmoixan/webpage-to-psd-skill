"""Regression tests use isolated job folders; they do not execute Photoshop or fabricate edit evidence."""
import unittest,tempfile,shutil,json,os
from pathlib import Path
from prepare_native_photoshop_job import generate
from validate_native_photoshop_output import validate
SOURCE=Path(os.environ.get('NATIVE_PHOTOSHOP_REFERENCE_JOB','__reference_job_not_provided__'))
@unittest.skipUnless(SOURCE.is_dir(),'Set NATIVE_PHOTOSHOP_REFERENCE_JOB to a real previously tested native Photoshop job')
class NativeHelpersTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.job=Path(self.tmp.name)
  for f in ['web_layers.json','web_dom.json','photoshop-native-results.json']:shutil.copyfile(SOURCE/f,self.job/f)
  self.stage=self.job/'staging.psd';self.stage.write_bytes(b'generator-input-only')
 def tearDown(self):self.tmp.cleanup()
 def test_proven_job_preparation_and_final_native_geometry(self):
  script=generate(self.job,self.stage,self.job/'different-page-name.psd')
  data=json.loads((self.job/'photoshop-rebuild-data.json').read_text(encoding='utf8'))
  self.assertEqual((data['width'],data['height']),(1920,4178));self.assertEqual(sum(len(i['specs']) for i in data['items']),40)
  text=script.read_text(encoding='utf-8-sig');self.assertNotIn('__ROOT_JSON__',text);self.assertNotIn('solution-detail-rebuilt-1920',text);self.assertIn('different-page-name.psd',text)
  result,raw=validate(self.job,SOURCE/'solution-detail-1920.psd');self.assertEqual(result['nativeShapeLayers'],41);self.assertEqual(result['nativeTextLayers'],113);self.assertEqual(result['photoshopEditTest'],'pending-visual-and-ui-validation')
 def test_canvas_dimensions_are_not_hardcoded(self):
  p=self.job/'web_layers.json';m=json.loads(p.read_text(encoding='utf8'));m['width']=1440;m['height']=2800;m['renderScale']=2;p.write_text(json.dumps(m),encoding='utf8')
  # This fixture has a 1x-only shadow; unsupported enlargement must block, never silently rescale it.
  with self.assertRaisesRegex(ValueError,'Scaled shadow'):generate(self.job,self.stage,self.job/'page.psd')
 def test_unsupported_shadow_blocks(self):
  p=self.job/'web_layers.json';m=json.loads(p.read_text(encoding='utf8'))
  for a in m['atoms']:
   if a['kind']=='shape' and 'box-shadow:rgba(21, 57, 90, 0.04)' in a['fragment']:a['fragment']=a['fragment'].replace('rgba(21, 57, 90, 0.04)','rgba(0, 0, 0, 0.7)')
  p.write_text(json.dumps(m),encoding='utf8')
  with self.assertRaisesRegex(ValueError,'shadow family'):generate(self.job,self.stage,self.job/'page.psd')
 def test_staging_must_not_replace_final(self):
  with self.assertRaisesRegex(ValueError,'must differ'):generate(self.job,self.stage,self.stage)
if __name__=='__main__':unittest.main()
