"""Fail delivery unless actual Photoshop shape edit evidence covers the exact PSD.
Run with a Python environment containing psd-tools. Evidence must come from Photoshop,
never this validator or a structural roundtrip. See the linked compatibility reference.
"""
import argparse,hashlib,json
from pathlib import Path

def check(psd_path,report_path):
 from psd_tools import PSDImage
 def need(value,message):
  if not value:raise ValueError(message)
 psd_path=Path(psd_path);report_path=Path(report_path)
 need(report_path.is_file(),'Photoshop edit evidence missing; native-shape delivery blocked')
 report=json.loads(report_path.read_text(encoding='utf-8-sig'))
 need(report.get('status')=='passed','Photoshop edit test is failed or not run')
 need(report.get('application')=='Adobe Photoshop' and report.get('version') and report.get('exporterIdentity'),'Application/version/exporter evidence missing')
 need(report.get('finalPsdSha256')==hashlib.sha256(psd_path.read_bytes()).hexdigest(),'Evidence does not match final PSD bytes')
 need(not report.get('errors'),'Photoshop errors were reported')
 for flag in ['openWithoutRepair','groupMoveUndo','saveCloseReopen','visualLayoutVerified']:
  need(report.get(flag) is True,'Missing observed Photoshop operation: '+flag)
 for key in ['executionLog','uiEvidence']:
  items=report.get(key,[]);items=[items] if isinstance(items,str) else items
  need(items,'Missing '+key)
  for item in items:
   file=Path(item);file=file if file.is_absolute() else report_path.parent/file
   need(file.is_file() and file.stat().st_size>0,'Missing/nonempty evidence file: '+str(file))
 psd=PSDImage.open(psd_path);shapes=[l for l in psd.descendants() if l.kind=='shape']
 need(shapes,'No native shapes found; wrong delivery gate or document')
 from psd_tools.constants import Tag
 ids=[];all_ids=[]
 for layer in psd.descendants():
  identifier=layer.tagged_blocks.get_data(Tag.LAYER_ID)
  need(isinstance(identifier,int) and identifier>0,'Missing positive unique layer ID: '+layer.name)
  all_ids.append(identifier)
  if layer.kind=='shape':ids.append(identifier)
 need(len(all_ids)==len(set(all_ids)),'Duplicate document layer IDs')
 tests=report.get('shapeTests',[])
 need(len(tests)==len(ids) and set(t.get('layerId') for t in tests)==set(ids),'Move tests do not cover every final native shape')
 for t in tests:
  for flag in ['moveCommitted','positionVerified','undoVerified','reopenedMoveCommitted','reopenedUndoVerified']:
   need(t.get(flag) is True,'Missing Photoshop shape test: '+str(t.get('layerId'))+' '+flag)
 families=report.get('emittedShapeFamilies',[]);family_tests=report.get('familyTests',[])
 need(families and set(families)==set(t.get('family') for t in family_tests),'Shape family edit coverage incomplete')
 for t in family_tests:
  for flag in ['scaleCommitUndo','rotateCommitUndo','fillStrokeVerified','cornersVerified']:
   need(t.get(flag) is True,'Missing family test: '+str(t.get('family'))+' '+flag)
 return {'photoshopEditTest':'passed','nativeShapeLayers':len(ids),'photoshopVersion':report['version'],'finalPsdSha256':report['finalPsdSha256']}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--psd',required=True,type=Path);p.add_argument('--evidence',required=True,type=Path);args=p.parse_args()
 try:print(json.dumps(check(args.psd,args.evidence),ensure_ascii=False))
 except (ValueError,OSError,KeyError,TypeError) as e:p.exit(2,'DELIVERY BLOCKED: '+str(e)+'\n')
if __name__=='__main__':main()
