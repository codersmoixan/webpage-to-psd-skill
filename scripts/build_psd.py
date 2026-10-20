"""Rebuild the observed web layout as independent PSD paint and native type layers."""
from __future__ import annotations

import base64
import argparse
import copy
import html
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote_to_bytes

import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from psd_tools.constants import Tag, Resource
from psd_tools.psd.image_resources import ImageResource, ResoulutionInfo
from psd_tools.psd import engine_data as ed
from psd_tools.psd.descriptor import String, Integer
from psd_tools.psd.tagged_blocks import TaggedBlock
from generate_visual_qa import generate_visual_qa
from image_sources import (local_image_path, single_background_url,
                           render_source_image, UnsupportedImagePaint)
from capture_contract import (finalize_capture_dimensions,
                              validate_capture_dimensions,
                              verify_prepared_dimensions)

from export_support import choose_scale, select_font, atomic_save

DOCUMENT_PPI = 72


def require(condition, message):
    """Keep production validation active even when Python runs with -O."""
    if not condition:
        raise ValueError(message)


def px(value):
    return float(str(value).replace('px', '')) if value not in ('auto', 'none', '', None) else 0


def css_string(css):
    value=';'.join(f'{re.sub(r"[A-Z]", lambda m: "-"+m[0].lower(), k)}:{v}' for k, v in css.items())
    return html.escape(value,quote=True)


def prepare(root, render_scale=1, allow_image_raster_fallback=False, auto_scale=True):
    required = ('web_dom.json', 'web_dom_after.json', 'web_reference.png',
                'web_assets.json', 'capture_dimensions.json')
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f'Required capture artifact(s) missing: {", ".join(missing)}')
    from check_capture_pair import compare
    before = json.loads((root/'web_dom.json').read_text(encoding='utf-8-sig'))
    after = json.loads((root/'web_dom_after.json').read_text(encoding='utf-8-sig'))
    state = compare(before, after)
    (root/'capture_validation.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf8')
    if not state['stable']:
        raise ValueError('Page changed across screenshot acquisition; recapture a stable state before preparing layers.')
    data = before
    resources = json.loads((root / 'web_assets.json').read_text(encoding='utf-8-sig'))
    with Image.open(root / 'web_reference.png') as reference_image:
        width, height = reference_image.size
    dimensions = validate_capture_dimensions(
        root, before, after, (width, height), render_scale, not auto_scale)
    requested_scale = render_scale
    render_scale = choose_scale(width, height, render_scale, auto_scale)
    dimensions = finalize_capture_dimensions(dimensions, (width, height), render_scale)
    (root/'capture_dimensions.json').write_text(
        json.dumps(dimensions, ensure_ascii=False, indent=2), encoding='utf8')
    assets_dir = root / 'web_psd_assets'
    assets_dir.mkdir(exist_ok=True)
    urls = {}
    image_paths = {}
    original_paths = {}
    local_source = json.loads((root/'local_source.json').read_text(encoding='utf-8-sig')) if (root/'local_source.json').exists() else None
    for resource in resources['assets']:
        source = Path(resource['path'])
        target = assets_dir / source.name
        if source.exists():
            target.write_bytes(source.read_bytes())
        elif not target.exists():
            raise FileNotFoundError(f'Bundled asset is unavailable: {source}')
        if resource['kind'] == 'image':
            mime = resource['contentType'] or 'image/png'
            urls[resource['url']] = f'data:{mime};base64,' + base64.b64encode(target.read_bytes()).decode()
            image_paths[resource['url']] = str(target)
            original_paths[resource['url']] = str(source)

    def source_path(url):
        if url.startswith('data:image/'):
            header, payload = url.split(',',1)
            content = base64.b64decode(payload) if header.endswith(';base64') else unquote_to_bytes(payload)
            target = assets_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.image')
            target.write_bytes(content)
            image_paths[url] = str(target)
            original_paths[url] = 'embedded-data-uri'
        local = local_image_path(url, local_source)
        if local:
            target = assets_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + local.suffix)
            target.write_bytes(local.read_bytes())
            image_paths[url] = str(target)
            original_paths[url] = str(local)
        if url not in image_paths:
            raise FileNotFoundError(f'Original image must be bundled before preparation: {url}')
        return image_paths[url]
    elements = {e['index']: e for e in data['elements']}
    atoms = []
    def inline_urls(value):
        for url, data_url in urls.items():
            value = value.replace(url, data_url)
        return value

    def ancestry(e):
        while e:
            yield e
            e = elements.get(e['parent'])

    def add(e, kind, rect, fragment, text=None, suffix=''):
        opacity = math.prod(float(a['css']['opacity']) for a in ancestry(e))
        if opacity == 0:
            return
        rect = dict(rect)
        x, y = math.floor(rect['x']), math.floor(rect['y'])
        pad = 60 if kind == 'shape' and e['css']['boxShadow'] != 'none' else 24 if kind == 'image' and e['css']['filter'] != 'none' else 3
        atom = dict(element=e['index'],kind=kind,rect=rect,x=x-pad,y=y-pad,
                    w=math.ceil(rect['w']+rect['x']-x)+pad*2,
                    h=math.ceil(rect['h']+rect['y']-y)+pad*2,
                    fragment=fragment,offsetX=rect['x']-x+pad,offsetY=rect['y']-y+pad,
                    opacity=opacity,css=e['css'],text=text,
                    name=(text or e.get('alt') or e['cls'] or e['tag'])[:65]+suffix)
        atoms.append(atom)
        return atom

    def direct_image(atom, e, url):
        if atom is None:
            return
        atom.update(sourceURL=url,sourcePath=source_path(url),originalPath=original_paths[url])
        if e.get('naturalSize'):
            atom['naturalSize'] = e['naturalSize']
        atom['imageClips'] = [dict(rect=a['rect'],borderRadius=a['css'].get('borderRadius','0px'),
                                  transform=a['css'].get('transform','none'),
                                  filter=a['css'].get('filter','none'),
                                  clip=any(v in ('hidden','clip','scroll','auto') for v in a['css'].get('overflow','visible').split()))
                              for a in ancestry(elements.get(e['parent']))]
        try:
            render_source_image(atom,1)
            atom['imageSource'] = 'original-file'
        except UnsupportedImagePaint as error:
            image_fallback(atom, str(error))

    def image_fallback(atom, reason):
        if not allow_image_raster_fallback:
            raise UnsupportedImagePaint(f'{reason}. Add a direct renderer, or explicitly enable --allow-image-raster-fallback and disclose the exception.')
        atom.update(imageSource='atlas-effect-fallback',fallbackReason=reason)

    def drawable(css):
        return css['backgroundColor'] not in ('rgba(0, 0, 0, 0)', 'transparent') or css['backgroundImage'] != 'none' or css['boxShadow'] != 'none' or any(px(css[f'border{s}Width']) and css[f'border{s}Style'] not in ('none', 'hidden') and css[f'border{s}Color'] != 'rgba(0, 0, 0, 0)' for s in ['Top','Right','Bottom','Left'])

    paint_keys = ['backgroundColor','backgroundImage','backgroundSize','backgroundPosition','borderRadius','boxShadow']
    for side in ['Top','Right','Bottom','Left']:
        paint_keys += [f'border{side}Width',f'border{side}Style',f'border{side}Color']

    # Collect each visible element's paint separately from its text and children.
    for e in elements.values():
        c, r = e['css'], e['rect']
        background_url = single_background_url(c['backgroundImage'])
        combined = re.fullmatch(r'(linear-gradient\(.+\)),\s*(url\(.+\))', c['backgroundImage'])
        if combined and combined[1].count('gradient(') == 1:
            base_color = c['backgroundColor']
            if base_color not in ('transparent','rgba(0, 0, 0, 0)'):
                base_style = dict(backgroundColor=base_color,borderRadius=c['borderRadius'],width=f"{r['w']}px",height=f"{r['h']}px")
                base = add(e,'shape',r,f'<div style="{css_string(base_style)}"></div>',suffix=' / 背景底色')
                if base: base['basePaint'] = True
            image_css = dict(c, backgroundImage=combined[2])
            for key in ['backgroundSize','backgroundPosition','backgroundRepeat','backgroundOrigin','backgroundClip','backgroundAttachment']:
                image_css[key] = image_css[key].split(',')[-1].strip()
            image_e = dict(e, css=image_css)
            url = single_background_url(combined[2])
            background = add(image_e,'background_image',r,'',suffix=' / 原始背景图片')
            if background:
                background['preShape'] = True
            direct_image(background,image_e,url)
            c = dict(c, backgroundImage=combined[1], backgroundColor='transparent')
            e = dict(e, css=c)
        if drawable(dict(c,backgroundImage='none') if background_url else c):
            style = {k:inline_urls(c[k]) for k in paint_keys}
            if background_url:
                style['backgroundImage'] = 'none'
            style.update(width=f"{r['w']}px",height=f"{r['h']}px",boxSizing='border-box')
            shape = add(e,'shape',r,f'<div style="{css_string(style)}"></div>',suffix=' / 背景边框')
            if not background_url and 'url(' in c['backgroundImage'] and shape:
                image_fallback(shape,'Multiple/combined CSS image backgrounds require a direct effect renderer')
        if background_url:
            style={k:inline_urls(c.get(k,'none')) for k in ['backgroundImage','backgroundSize','backgroundPosition','backgroundRepeat','borderRadius']}
            style.update(width=f"{r['w']}px",height=f"{r['h']}px")
            background=add(e,'background_image',r,f'<div style="{css_string(style)}"></div>',suffix=' / 背景图片')
            direct_image(background,e,background_url)
        if e['src'] and e['tag'] == 'img':
            style = {k:c[k] for k in ['objectFit','objectPosition','filter','borderRadius']}
            style.update(width=f"{r['w']}px",height=f"{r['h']}px",display='block')
            image=add(e,'image',r,f'<img src="{urls.get(e["src"], e["src"])}" style="{css_string(style)}">',suffix=' / 图片')
            direct_image(image,e,e['src'])
        if e['svg']:
            style={k:c[k] for k in ['color','fill','stroke','strokeWidth']}
            style.update(width=f"{r['w']}px",height=f"{r['h']}px",display='block')
            fragment=e['svg'].replace('<svg ',f'<svg style="{css_string(style)}" ',1)
            add(e,'icon',r,fragment,suffix=' / 图标')
        for t in e['text']:
            lines=[]
            for ch in t['chars']:
                if lines and abs(lines[-1][0]['y']-ch['y'])<.5:
                    lines[-1].append(ch)
                else:
                    lines.append([ch])
            for chars in lines:
                text=''.join(ch['char'] for ch in chars).rstrip()
                if not text.strip():
                    continue
                text = text.upper() if c['textTransform'] == 'uppercase' else text
                rr={'x':chars[0]['x'],'y':min(ch['y'] for ch in chars),
                    'w':max(ch['x']+ch['w'] for ch in chars)-chars[0]['x']+4,
                    'h':max(ch['h'] for ch in chars)+4}
                style={k:c[k] for k in ['color','fontFamily','fontSize','fontWeight','fontStyle','letterSpacing']}
                # An inline line box uses the browser's own font metrics and kerning.
                style.update(whiteSpace='pre',lineHeight=f"{chars[0]['h']}px",display='block',
                             textShadow=c.get('textShadow','none'))
                add(e,'text',rr,f'<span style="{css_string(style)}">{html.escape(text)}</span>',text=text)
        if e['placeholder']:
            rr={'x':r['x'],'y':r['y']+px(c['paddingTop'])+1,'w':r['w'],'h':18}
            style={k:c[k] for k in ['fontFamily','fontSize','fontWeight']}
            style.update(color='rgb(117,117,117)',lineHeight='15px',whiteSpace='pre')
            add(e,'text',rr,f'<span style="{css_string(style)}">{html.escape(e["placeholder"])}</span>',text=e['placeholder'])
        for p in e.get('pseudo', []):
            pc=p['css']
            pr=dict(r)
            pw, ph = px(pc.get('width')), px(pc.get('height'))
            if pw: pr['w'] = pw
            if ph: pr['h'] = ph
            if pc.get('left') not in ('auto', None): pr['x'] = r['x'] + px(pc['left'])
            elif pc.get('right') not in ('auto', None): pr['x'] = r['x'] + r['w'] - pr['w'] - px(pc['right'])
            if pc.get('top') not in ('auto', None): pr['y'] = r['y'] + px(pc['top'])
            elif pc.get('bottom') not in ('auto', None): pr['y'] = r['y'] + r['h'] - pr['h'] - px(pc['bottom'])
            style={k:v for k,v in pc.items() if k in ['background-color','background-image','border-radius']}
            style.update(width=f"{pr['w']}px",height=f"{pr['h']}px")
            overlay=add(e,'overlay',pr,f'<div style="{css_string(style)}"></div>',suffix=' / 遮罩')
            if overlay:
                overlay['isBefore'] = p.get('selector') == '::before'
                overlay['paintZ'] = int(pc.get('z-index')) if pc.get('z-index') not in (None,'auto') else (-1 if overlay['isBefore'] else 0)
            if 'url(' in pc.get('background-image','') and overlay:
                image_fallback(overlay,'Pseudo-element image backgrounds require a direct effect renderer')

    # Match paint order, including pseudo-element overlays below positive-z captions.
    by_element=defaultdict(list)
    for atom in atoms:
        by_element[atom['element']].append(atom)
    children=defaultdict(list)
    for e in elements.values():
        children[e['parent']].append(e)
    ordered=[]
    def visit(e):
        own=by_element[e['index']]
        ordered.extend(a for a in own if a.get('basePaint'))
        ordered.extend(a for a in own if a.get('preShape'))
        ordered.extend(a for a in own if a['kind']=='shape' and not a.get('basePaint'))
        ordered.extend(a for a in own if a['kind']=='background_image' and not a.get('preShape'))
        ordered.extend(a for a in own if a['kind'] in ('text','image','icon'))
        descendants=children[e['index']]
        for child in descendants:
            if child['css']['zIndex']!='auto' and int(child['css']['zIndex'])<0:
                visit(child)
        ordered.extend(a for a in own if a['kind']=='overlay' and a.get('paintZ',0)<0)
        for child in descendants:
            if child['css']['zIndex']=='auto' or int(child['css']['zIndex'])==0:
                visit(child)
        ordered.extend(a for a in own if a['kind']=='overlay' and a.get('paintZ',0)==0)
        positive = [(int(c['css']['zIndex']),0,c) for c in descendants if c['css']['zIndex']!='auto' and int(c['css']['zIndex'])>0]
        positive += [(a['paintZ'],1,a) for a in own if a['kind']=='overlay' and a.get('paintZ',0)>0]
        for _,kind,item in sorted(positive,key=lambda entry:(entry[0],entry[1])):
            if kind: ordered.append(item)
            else: visit(item)
    roots=[e for e in elements.values() if e['parent'] not in elements]
    # Header and floating controls are topmost; retain natural document section order.
    for e in sorted(roots,key=lambda e: int(e['css']['zIndex']) if e['css']['zIndex']!='auto' else 0):
        visit(e)
    if len(ordered)!=len(atoms):
        raise RuntimeError(f'Unassigned atoms: {len(atoms)-len(ordered)}')

    # Pack isolated paint objects into atlases for alpha-preserving browser rendering.
    pages=[]
    page=[]; x=y=row_h=0
    atlas_width=max(1400,max((a['w'] for a in ordered if a.get('imageSource')!='original-file'),default=1400))
    for n,a in enumerate(ordered):
        a['id']=n
        if a.get('imageSource')=='original-file':
            continue
        if x+a['w']>atlas_width:
            x=0;y+=row_h+8;row_h=0
        if y+max(row_h,a['h'])>1800 and page:
            pages.append((page,y+row_h+8));page=[];x=y=row_h=0
        a.update(atlasPage=len(pages),atlasX=x,atlasY=y)
        page.append(a);x+=a['w']+8;row_h=max(row_h,a['h'])
    if page:
        pages.append((page,y+row_h+8))
    for num,(items,page_height) in enumerate(pages):
        for bg in ['white','black']:
            parts=[f'<!doctype html><meta charset="utf-8"><style>*{{box-sizing:border-box}}html,body{{margin:0;background:{bg};width:{atlas_width*render_scale}px;height:{page_height*render_scale}px;overflow:hidden}}.scene{{position:absolute;transform:scale({render_scale});transform-origin:0 0;width:{atlas_width}px;height:{page_height}px}}.atom{{position:absolute}}</style><div class="scene">']
            for a in items:
                parts.append(f'<div class="atom" style="left:{a["atlasX"]+a["offsetX"]}px;top:{a["atlasY"]+a["offsetY"]}px;opacity:{a["opacity"]}">{a["fragment"]}</div>')
            parts.append('</div>')
            (root/f'atlas_{num}_{bg}.html').write_text(''.join(parts), encoding='utf8')
    manifest={'width':width,'height':height,'renderScale':render_scale,'requestedRenderScale':requested_scale,'scaleReduced':render_scale != requested_scale,'captureWidthSource':dimensions['widthSource'],'atoms':ordered,'pages':[{'width':atlas_width*render_scale,'height':h*render_scale} for _,h in pages]}
    (root/'web_layers.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2), encoding='utf8')
    print(json.dumps({'atoms':len(ordered),'text':sum(a['kind']=='text' for a in ordered),
                      'originalImageLayers':sum(a.get('imageSource')=='original-file' for a in ordered),
                      'imageFallbacks':[{'id':a['id'],'reason':a['fallbackReason']} for a in ordered if a.get('fallbackReason')],
                      'pages':manifest['pages']},ensure_ascii=False))


def native_text(template, atom, render_scale=1):
    setting=copy.deepcopy(template._data)
    text=atom['text']
    setting.text_data[b'Txt ']=String(text+'\x00')
    setting.text_data[b'TextIndex']=Integer(atom['id'])
    engine=setting.text_data[b'EngineData'].value
    engine_dict=engine['EngineDict']
    engine_dict['Editor']['Text']=ed.String(text+'\r')
    length=len((text+'\r').encode('utf-16-be'))//2
    para=engine_dict['ParagraphRun']
    para['RunArray']=ed.List([copy.deepcopy(para['RunArray'][0])])
    para['RunLengthArray']=ed.List([ed.Integer(length)])
    props=para['RunArray'][0]['ParagraphSheet']['Properties']
    props['Justification']=ed.Integer(0)
    props['AutoHyphenate']=ed.Bool(False)
    style=engine_dict['StyleRun']
    style['RunArray']=ed.List([copy.deepcopy(style['RunArray'][0])])
    style['RunLengthArray']=ed.List([ed.Integer(length)])
    ss=style['RunArray'][0]['StyleSheet']['StyleSheetData']
    font_size=px(atom['css']['fontSize'])
    values=[float(n) for n in re.findall(r'[\d.]+',atom['css']['color'])]
    rgb=values[:3];alpha=values[3] if len(values)>3 else 1
    ss['FontSize']=ed.Float(font_size * render_scale * 72 / DOCUMENT_PPI)
    ss['Font']=ed.Integer(0)
    font_info = select_font(atom['css'], text)
    atom['fontSelection'] = font_info
    # A real bold/italic face plus Photoshop faux styling changes glyph bounds
    # on first edit, even when the imported raster cache initially looks right.
    ss['FauxBold']=ed.Bool(int(atom['css']['fontWeight'])>=600 and not font_info['faceBold'])
    ss['FauxItalic']=ed.Bool(atom['css']['fontStyle']=='italic' and not font_info['faceItalic'])
    ss['AutoLeading']=ed.Bool(True)
    ss['Tracking']=ed.Integer(round(px(atom['css']['letterSpacing'])/font_size*1000)) if atom['css']['letterSpacing']!='normal' else ed.Integer(0)
    ss['FillColor']['Values']=ed.List([ed.Float(alpha)]+[ed.Float(v/255) for v in rgb])
    ss['FillFirst']=ed.Bool(True)
    ss['BaselineDirection']=ed.Integer(0)
    cjk=any(ord(ch)>255 for ch in text)
    font_name = font_info['postscript']
    for key in ['ResourceDict','DocumentResources']:
        engine[key]['FontSet'][0]['Name']=ed.String(font_name)
        engine[key]['FontSet'][0]['Script']=ed.Integer(2 if cjk else 0)
        engine[key]['StyleSheetSet'][0]['StyleSheetData']['Font']=ed.Integer(0)
    x,y=atom['rect']['x'],atom['rect']['y']
    engine_dict['AntiAlias']=ed.Integer(3)
    setting.transform=(1.,0.,0.,1.,x*render_scale,(y+font_size*.9)*render_scale)
    setting.left=setting.top=setting.right=setting.bottom=0
    return setting


def recover_alpha(white, black, box):
    """Recover large layers in strips to bound temporary float-array memory."""
    x,y,w,h=box
    result=Image.new('RGBA',(w,h))
    for row in range(0,h,256):
        bottom=min(h,row+256)
        a=np.asarray(white.crop((x,y+row,x+w,y+bottom)),dtype=np.float32)
        b=np.asarray(black.crop((x,y+row,x+w,y+bottom)),dtype=np.float32)
        alpha=np.clip(255-np.median(a-b,axis=2),0,255)
        rgb=np.divide(b*255,alpha[...,None],out=np.zeros_like(b),where=alpha[...,None]>0)
        rgba=np.concatenate([np.clip(rgb,0,255),alpha[...,None]],axis=2).round().astype(np.uint8)
        result.paste(Image.fromarray(rgba,'RGBA'),(0,row))
    return result


def build(root, template_path, output_name):
    manifest=json.loads((root/'web_layers.json').read_text(encoding='utf-8-sig'))
    capture_dimensions=verify_prepared_dimensions(root, manifest)
    scale=manifest.get('renderScale',1)
    size=(manifest['width']*scale,manifest['height']*scale)
    if max(size)>30000:
        raise ValueError('PSD dimensions exceed 30000 pixels; lower --render-scale or split the document.')
    psd=PSDImage.new('RGBA',size,color=(255,255,255,255))
    # PSD resolution values use 16.16 fixed-point pixels per inch.
    psd.image_resources[Resource.RESOLUTION_INFO] = ImageResource(
        key=Resource.RESOLUTION_INFO,
        data=ResoulutionInfo(horizontal=DOCUMENT_PPI << 16, horizontal_unit=1,
                            width_unit=1, vertical=DOCUMENT_PPI << 16,
                            vertical_unit=1, height_unit=1),
    )
    base_layer=PixelLayer.frompil(Image.new('RGBA',psd.size,'white'),psd,name='Page background')
    base_layer.name='页面底色'
    template=next(t for t in PSDImage.open(template_path).descendants() if t.kind=='type')
    atlas_page=None
    preview=Image.new('RGBA',psd.size,'white')
    export_dir=root/'web_psd_layers'
    export_dir.mkdir(exist_ok=True)
    count=0
    for atom in manifest['atoms']:
        atom.pop('pixelBox', None)
    for atom in manifest['atoms']:
        if atom.get('imageSource')=='original-file':
            im=render_source_image(atom,scale)
        else:
            if atom['kind'] in ('image','background_image') and atom.get('imageSource')!='atlas-effect-fallback':
                raise ValueError('Old image manifest: rerun prepare to use original files')
            if atlas_page!=atom['atlasPage']:
                atlas_page=atom['atlasPage']
                white=Image.open(root/f'atlas_{atlas_page}_white.png').convert('RGB')
                black=Image.open(root/f'atlas_{atlas_page}_black.png').convert('RGB')
                expected_atlas=(manifest['pages'][atlas_page]['width'],manifest['pages'][atlas_page]['height'])
                require(white.size == black.size == expected_atlas,
                        'Atlas dimensions differ from requested render scale')
            x,y=atom['atlasX']*scale,atom['atlasY']*scale;w,h=atom['w']*scale,atom['h']*scale
            im=recover_alpha(white,black,(x,y,w,h))
        box=im.getbbox()
        if not box:
            if atom['kind']=='text' and atom.get('text','').strip():
                raise ValueError(f"Missing rendered text cache for atom {atom['id']}: {atom['text']!r}. Recapture both atlas backgrounds at the full manifest viewport dimensions.")
            continue
        im=im.crop(box)
        left,top=atom['x']*scale+box[0],atom['y']*scale+box[1]
        name=f'{atom["id"]:03d} {atom["name"]}'
        layer=PixelLayer.frompil(im,psd,name=f'Layer {atom["id"]}',left=left,top=top)
        layer.name=name
        if atom['kind']=='text':
            layer.tagged_blocks[Tag.TYPE_TOOL_OBJECT_SETTING]=TaggedBlock(key=Tag.TYPE_TOOL_OBJECT_SETTING,data=native_text(template,atom,scale))
        im.save(export_dir/f'{atom["id"]:03d}.png')
        atom['pixelBox']=[left,top,im.width,im.height]
        preview.alpha_composite(im,(left,top))
        count+=1
    output=root/output_name
    # Set the actual rebuilt composite instead of using the original web screenshot.
    psd._record.image_data.set_data([ch.tobytes() for ch in preview.split()],psd._record.header)
    psd._updated=False
    def validate_saved(path):
        candidate = PSDImage.open(path)
        require(candidate.size == size, f'Reopened PSD canvas {candidate.size} differs from expected {size}')
        resolution = candidate.image_resources.get_data(Resource.RESOLUTION_INFO)
        require(resolution.horizontal == resolution.vertical == DOCUMENT_PPI << 16,
                f'Reopened PSD resolution is not {DOCUMENT_PPI} PPI')
        types = [t for t in candidate.descendants() if t.kind == 'type']
        expected = [a for a in manifest['atoms'] if a['kind'] == 'text']
        require(len(types) == len(expected),
                f'Reopened PSD has {len(types)} type layers; expected {len(expected)}')
        for t,a in zip(types, expected):
            require(t.text.rstrip('\r\x00') == a['text'],
                    f'Type layer {a["id"]} text changed during PSD round trip')
            x,y,w,h = a['pixelBox']
            require(tuple(t.bbox) == (x,y,x+w,y+h),
                    f'Type layer {a["id"]} bounds changed during PSD round trip')
    atomic_save(psd, output, validate_saved)
    preview_path=root/(output.stem+'_preview.png')
    preview.convert('RGB').save(preview_path)
    reopened=PSDImage.open(output)
    resolution = reopened.image_resources.get_data(Resource.RESOLUTION_INFO)
    require(resolution.horizontal == resolution.vertical == DOCUMENT_PPI << 16,
            f'Final PSD resolution is not {DOCUMENT_PPI} PPI')
    types=[t for t in reopened.descendants() if t.kind=='type']
    expected=[a for a in manifest['atoms'] if a['kind']=='text']
    require(len(types) == len(expected),
            f'Final PSD has {len(types)} type layers; expected {len(expected)}')
    for t,a in zip(types,expected):
        require(t.text.rstrip('\r\x00') == a['text'],
                f'Final type layer {a["id"]} text differs from the captured text')
        expected_box=(a['pixelBox'][0],a['pixelBox'][1],
                      a['pixelBox'][0]+a['pixelBox'][2],a['pixelBox'][1]+a['pixelBox'][3])
        require(tuple(t.bbox) == expected_box,
                f'Final type layer {a["id"]} bounds differ from the prepared layer')
    (root/'web_layers.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2), encoding='utf8')
    reference=np.asarray(Image.open(root/'web_reference.png').convert('RGB'),dtype=np.int16)
    actual=np.asarray(preview.convert('RGB').resize((manifest['width'],manifest['height']),Image.Resampling.LANCZOS),dtype=np.int16)
    diff=np.abs(reference-actual)
    report={'canvas':list(psd.size),'layers':count+1,'nativeTextLayers':len(types),'meanAbsoluteError':float(diff.mean()),'pixelsWithin10':float(np.mean(diff.max(axis=2)<=10))}
    report['resolutionPPI'] = [resolution.horizontal / 65536, resolution.vertical / 65536]
    report['renderScale'] = scale
    report['requestedRenderScale'] = manifest.get('requestedRenderScale', scale)
    report['scaleReduced'] = manifest.get('scaleReduced', False)
    report['captureDimensions'] = capture_dimensions
    report['fontSelections'] = [dict(id=a['id'], **a['fontSelection']) for a in manifest['atoms'] if a.get('fontSelection')]
    report['roundtripMethod'] = 'Independent psd-tools composite of reopened PSD in strips'
    image_provenance=[{'id':a['id'],'kind':a['kind'],'mode':a.get('imageSource'),
                      'url':a.get('sourceURL'),'originalPath':a.get('originalPath'),
                      'sourcePath':a.get('sourcePath'),'sourcePixels':a.get('sourcePixels'),
                      'fallbackReason':a.get('fallbackReason')}
                     for a in manifest['atoms'] if a.get('imageSource')]
    (root/'image_provenance.json').write_text(json.dumps(image_provenance,ensure_ascii=False,indent=2), encoding='utf8')
    report['originalImageLayers']=sum(a['mode']=='original-file' for a in image_provenance)
    report['imageRasterFallbacks']=[a for a in image_provenance if a['mode']=='atlas-effect-fallback']
    report['referenceComparisonScale'] = 'Downsample output to original CSS capture dimensions'
    # Check the entire layer stack in bounded horizontal strips.
    reopened_composite=Image.new('RGB',size)
    for row in range(0,size[1],512):
        bottom=min(size[1],row+512)
        strip=reopened.composite(viewport=(0,row,size[0],bottom),force=True).convert('RGB')
        reopened_composite.paste(strip,(0,row))
    reopened_small=reopened_composite.resize((manifest['width'],manifest['height']),Image.Resampling.LANCZOS)
    roundtrip=np.abs(np.asarray(reopened_small,dtype=np.int16)-actual)
    report['roundtripMeanAbsoluteError']=float(roundtrip.mean())
    report['output']=str(output)
    report['preview']=str(preview_path)
    report['visualQA'] = str(root/'visual_qa'/'summary.json')
    (root/'PSD_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf8')
    Image.fromarray(np.clip(diff*4,0,255).astype(np.uint8)).save(root/'web_difference.png')
    reopened_composite.save(root/'PSD_reopened_composite.png')
    generate_visual_qa(root, preview_path, report, root/'PSD_reopened_composite.png')
    print(json.dumps(report,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','build'))
    parser.add_argument('--job-dir',type=Path,required=True)
    parser.add_argument('--template',type=Path,default=Path(__file__).resolve().parents[1]/'assets'/'text-template.psd')
    parser.add_argument('--output-name',default='webpage_layered.psd')
    parser.add_argument('--render-scale',type=int,default=1,choices=(1,2,3,4))
    parser.add_argument('--strict-render-scale', action='store_true', help='Reject oversized output instead of reducing render scale before atlas rendering')
    parser.add_argument('--allow-image-raster-fallback',action='store_true',
                        help='Explicitly allow and record unsupported image-effect atlas fallbacks')
    args=parser.parse_args()
    root=args.job_dir.resolve()
    if args.mode=='prepare': prepare(root,args.render_scale,args.allow_image_raster_fallback,not args.strict_render_scale)
    else: build(root,args.template.resolve(),args.output_name)


if __name__=='__main__':
    main()
