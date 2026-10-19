"""Prepare a Photoshop-native rebuild job from a completed INTERNAL raster staging export.
Does not launch Photoshop or mark a file delivery-ready. See native-photoshop-workflow.md.
"""
import argparse,json,re,html,math
from pathlib import Path
from PIL import ImageColor
from native_shadows import split_shadow

def generate(job_dir,staging_psd,output_psd):
 p=Path(job_dir).resolve();staging_psd=Path(staging_psd).resolve();output_psd=Path(output_psd).resolve()
 if not staging_psd.is_file():raise FileNotFoundError(staging_psd)
 if staging_psd==output_psd:raise ValueError('Staging and final paths must differ')
 m=json.loads((p/'web_layers.json').read_text(encoding='utf8'));
 if m['width']<=0 or m['height']<=0 or max(m['width'],m['height'])*m.get('renderScale',1)>30000:raise ValueError('Invalid or oversized output canvas')
 d=json.loads((p/'web_dom.json').read_text(encoding='utf8'));es={e['index']:e for e in d['elements']}
 def chain(e):
  a=[]
  while e:a.append(e);e=es.get(e['parent'])
  return a
 def module(e):
  a=chain(e)
  for v in a:
   if v['tag'] in ('header','footer','aside') and not any(x['tag']=='section' for x in chain(v)[1:]):return v
  for v in a:
   if es.get(v['parent'],{}).get('tag')=='main':return v
  return a[-1]
 def col(s):
  if not s or s=='transparent':return [0,0,0,0]
  if s.startswith('rgb'):
   vals=[float(x) for x in re.findall(r'[\d.]+',s)];return vals if len(vals)==4 else vals+[1]
  c=ImageColor.getcolor(s,'RGBA');return list(c[:3])+[c[3]/255]
 def rr(s,w,h):
  if '/' in s:raise ValueError('Elliptical radii need a validated renderer')
  v=s.split();v=v*4 if len(v)==1 else v*2 if len(v)==2 else v+[v[1]] if len(v)==3 else v
  r=[float(x.strip('px%'))*(min(w,h)/100 if '%' in x else 1) for x in v];f=min([1]+[n/t for n,t in [(w,r[0]+r[1]),(w,r[2]+r[3]),(h,r[0]+r[3]),(h,r[1]+r[2])] if t]);return [x*f for x in r]
 mods={};items=[]
 for a in m['atoms']:
  e=es[a['element']];mo=module(e);mid=str(mo['index'])
  if mid not in mods:
   heads=[v for v in es.values() if v['tag'] in ('h1','h2','h3') and mo in chain(v)]
   mods[mid]=''.join(t['value'] for t in heads[0]['text']) if heads else {'header':'页头','footer':'页脚','aside':'快捷联系'}.get(mo['tag'],'面包屑导航' if 'crumb' in mo['cls'] else '页面内容')
  item={'marker':f"{a['id']:03d} ",'moduleId':mid,'module':mods[mid],'name':a.get('text') or e.get('alt') or {'image':'图片','background_image':'背景图片','icon':'图标','shape':'背景与边框','overlay':'渐变遮罩'}.get(a['kind'],'内容'),'specs':[]}
  if a['kind'] in ('shape','overlay'):
   st=re.search(r'style="([^"]*)"',html.unescape(a['fragment']));st=dict(x.split(':',1) for x in st[1].split(';') if ':' in x) if st else {};r=a['rect'];fill=col(st.get('background-color','transparent'));grad=st.get('background-image','none')
   if grad!='none' and (fill[3] or any(float(st.get('border-'+side+'-width','0px').replace('px','')) for side in ['top','right','bottom','left'])):raise ValueError('Split mixed solid fill and gradient before native preparation')
   if grad=='none':
    bw=[float(st.get('border-'+s+'-width','0px').replace('px','')) for s in ['top','right','bottom','left']];bc=[col(st.get('border-'+s+'-color','transparent')) for s in ['top','right','bottom','left']];uni=len(set(bw))==1 and len(set(map(tuple,bc)))==1
    bounds=[r['x'],r['y'],r['w'],r['h']]
    shadow=st.get('box-shadow','none')
    # Split only supported profiles; unknown shadows still fail explicitly.
    if a['css'].get('transform','none')!='none' or a['css'].get('clipPath','none')!='none':raise ValueError('Transformed/clipped surface needs a validated shape route')
    if fill[3] or (uni and bw[0] and bc[0][3]):item['specs'].append(dict(bounds=bounds,radii=rr(st.get('border-radius','0px'),r['w'],r['h']),fill=fill,stroke=bc[0] if uni else None,strokeWidth=bw[0] if uni else 0,opacity=a['opacity'],shadow=st.get('box-shadow','none')))
    if not uni:
     x,y,w,h=bounds
     for i,(width,c) in enumerate(zip(bw,bc)):
      if width and c[3]:item['specs'].append(dict(bounds=[[x,y,w,width],[x+w-width,y,width,h],[x,y+h-width,w,width],[x,y,width,h]][i],radii=[0]*4,fill=c,stroke=None,strokeWidth=0,opacity=a['opacity'],shadow='none'))

  item['specs']=[part for spec in item['specs'] for part in split_shadow(spec)]
  if a.get('pixelBox'):items.append(item)
 scale=m.get('renderScale',1)
 for item in items:
  for sp in item['specs']:
   sp['bounds']=[v*scale for v in sp['bounds']];sp['radii']=[v*scale for v in sp['radii']];sp['strokeWidth']*=scale
   if scale!=1 and sp.get('shadow','none')!='none':raise ValueError('Scaled shadow requires a separately validated effect renderer')
 (p/'photoshop-rebuild-data.json').write_text(json.dumps({'width':m['width']*m.get('renderScale',1),'height':m['height']*m.get('renderScale',1),'items':items},ensure_ascii=False),encoding='utf8')
 print('Native replacements:',sum(len(i['specs']) for i in items),'modules',len(mods))
 template=(Path(__file__).resolve().parents[1]/'assets/photoshop_native_rebuild.jsx.template').read_text(encoding='utf8')
 for key,value in [('__ROOT_JSON__',p.as_posix()),('__STAGING_JSON__',staging_psd.as_posix()),('__OUTPUT_JSON__',output_psd.as_posix())]:template=template.replace(key,json.dumps(value,ensure_ascii=False))
 (p/'rebuild-in-photoshop.jsx').write_text(template,encoding='utf-8-sig')
 (p/'native-job-config.json').write_text(json.dumps({'output':str(output_psd),'staging':str(staging_psd)},ensure_ascii=False),encoding='utf8')
 return p/'rebuild-in-photoshop.jsx'

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--job-dir',required=True,type=Path);parser.add_argument('--staging-psd',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
 print(generate(args.job_dir,args.staging_psd,args.output))
