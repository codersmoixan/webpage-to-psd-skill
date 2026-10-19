"""Validate native Photoshop output against its job; seal evidence only after observed UI/visual QA."""
import argparse,hashlib,json
from pathlib import Path
from psd_tools import PSDImage
from psd_tools.constants import Tag,Resource

def require(ok,message):
 if not ok:raise ValueError(message)
def validate(job_dir,psd_path):
 root=Path(job_dir);file=Path(psd_path);data=json.loads((root/'photoshop-rebuild-data.json').read_text(encoding='utf-8-sig'));manifest=json.loads((root/'web_layers.json').read_text(encoding='utf-8-sig'));raw=json.loads((root/'photoshop-native-results.json').read_text(encoding='utf-8-sig'));doc=PSDImage.open(file)
 require(not raw.get('errors'),'Photoshop runtime errors: '+str(raw.get('errors')))
 require(raw.get('status')=='pending-independent-validation','Native Photoshop run did not complete')
 require(doc.size==(data['width'],data['height']),'Final canvas dimensions differ')
 res=doc.image_resources.get_data(Resource.RESOLUTION_INFO);require(res.horizontal==res.vertical==72*65536,'Final PSD must be 72 PPI')
 layers=list(doc.descendants());ids=[l.tagged_blocks.get_data(Tag.LAYER_ID) for l in layers];require(all(isinstance(i,int) and i>0 for i in ids) and len(ids)==len(set(ids)),'Missing or duplicate native layer IDs');byid=dict(zip(ids,layers))
 specs=[dict(bounds=[0,0,data['width'],data['height']],radii=[0]*4,fill=[255,255,255,1],stroke=None,strokeWidth=0,opacity=1)]+[sp for item in data['items'] for sp in item['specs']]
 tests=raw.get('shapeTests',[]);shapes=[l for l in layers if l.kind=='shape'];require(len(specs)==len(tests)==len(shapes),'Expected/actual shape count differs')
 for t,sp in zip(tests,specs):
  l=byid.get(t['layerId']);require(l is not None and l.kind=='shape' and l.has_vector_mask() and l.has_origination(),'Missing native shape path/origination')
  o=l.origination[0];x,y,w,h=sp['bounds'];require(max(abs(a-b) for a,b in zip(o.bbox,[x,y,x+w,y+h]))<.05,'Native shape bounds differ: '+l.name)
  rd=getattr(o,'radii',None);rr=[rd[k].value for k in [b'topLeft',b'topRight',b'bottomRight',b'bottomLeft']] if rd else [0]*4
  require(max(abs(a-b) for a,b in zip(rr,sp['radii']))<.05,'Native corner radii differ: '+l.name)
  fill=(l.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING) or l.tagged_blocks.get_data(Tag.VECTOR_STROKE_CONTENT_DATA))[b'Clr ']
  require(max(abs(fill[k].value-v) for k,v in zip([b'Rd  ',b'Grn ',b'Bl  '],sp['fill'][:3]))<.05,'Native fill color differs')
  enabled=bool(sp['stroke'] and sp['strokeWidth']);require(l.has_stroke() and l.stroke.enabled==enabled,'Stroke enabled state differs')
  if enabled:
   require(abs(l.stroke.line_width-sp['strokeWidth'])<.05,'Stroke width differs')
   sc=l.stroke.content[b'Clr '];require(max(abs(sc[k].value-v) for k,v in zip([b'Rd  ',b'Grn ',b'Bl  '],sp['stroke'][:3]))<.05,'Stroke color differs')
  alpha=sp['fill'][3] if sp['fill'][3]>0 else (sp['stroke'] or [0,0,0,1])[3];require(abs(l.opacity-255*sp['opacity']*alpha)<=1.1,'Native shape opacity differs')
  require(all(t.get(k) is True for k in ['moveCommitted','positionVerified','undoVerified','reopenedMoveCommitted','reopenedUndoVerified']),'Real Photoshop edit test incomplete')
 expected=[a['text'] for a in manifest['atoms'] if a['kind']=='text'];actual=[l.text.rstrip('\r\x00') for l in layers if l.kind=='type'];require(expected==actual,'Native text content/order differs')
 require(all(l.is_group() for l in doc),'Ungrouped root layers')
 expected_groups=['页面背景'];keys=set()
 for item in data['items']:
  if item['moduleId'] not in keys:keys.add(item['moduleId']);expected_groups.append(item['module'])
 require([l.name for l in doc]==expected_groups,'Module group names/order differ')
 result={'nativeShapeLayers':len(shapes),'expectedShapeLayers':len(specs),'nativeTextLayers':len(actual),'moduleGroups':expected_groups,'canvas':list(doc.size),'finalPsdSha256':hashlib.sha256(file.read_bytes()).hexdigest(),'structuralValidation':'passed','photoshopEditTest':'pending-visual-and-ui-validation'}
 (root/'native_structure_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 return result,raw

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--job-dir',required=True,type=Path);p.add_argument('--psd',required=True,type=Path);p.add_argument('--ui-evidence',type=Path);p.add_argument('--confirm-ui-properties',action='store_true');p.add_argument('--confirm-visual',action='store_true');args=p.parse_args()
 result,raw=validate(args.job_dir,args.psd)
 if args.ui_evidence or args.confirm_ui_properties or args.confirm_visual:
  require(args.ui_evidence and args.ui_evidence.is_file() and args.ui_evidence.stat().st_size>0,'Actual Photoshop UI evidence required')
  require(args.confirm_ui_properties and args.confirm_visual,'Observed UI properties and full visual QA must both be confirmed')
  raw['status']='passed';raw['visualLayoutVerified']=True;raw['finalPsdSha256']=result['finalPsdSha256'];raw['uiEvidence']=[str(args.ui_evidence.resolve())]
  for family in raw['familyTests']:family['cornersVerified']=True
  path=args.job_dir/'photoshop_edit_validation.json';path.write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf8')
  from check_photoshop_edit_gate import check
  result.update(check(args.psd,path))
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
