"""Gate regression tests use synthetic evidence; never delivery evidence."""
import unittest,tempfile,json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from check_photoshop_edit_gate import check
class GateTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.psd=self.root/'candidate.psd';self.psd.write_bytes(b'fixture');self.evidence=self.root/'evidence.json'
 def tearDown(self):self.temp.cleanup()
 def test_missing_evidence_blocks(self):
  with self.assertRaisesRegex(ValueError,'evidence missing'):check(self.psd,self.evidence)
 def test_untested_blocks(self):
  self.evidence.write_text(json.dumps({'status':'not-run'}))
  with self.assertRaisesRegex(ValueError,'failed or not run'):check(self.psd,self.evidence)
 def test_different_final_file_blocks(self):
  self.evidence.write_text(json.dumps({'status':'passed','application':'Adobe Photoshop','version':'fixture','exporterIdentity':'fixture','finalPsdSha256':'wrong'}))
  with self.assertRaisesRegex(ValueError,'final PSD bytes'):check(self.psd,self.evidence)
 def test_reported_program_error_blocks(self):
  self.evidence.write_text(json.dumps({'status':'passed','application':'Adobe Photoshop','version':'fixture','exporterIdentity':'fixture','finalPsdSha256':hashlib.sha256(self.psd.read_bytes()).hexdigest(),'errors':['e348c8.1140']}))
  with self.assertRaisesRegex(ValueError,'errors were reported'):check(self.psd,self.evidence)
if __name__=='__main__':unittest.main()
