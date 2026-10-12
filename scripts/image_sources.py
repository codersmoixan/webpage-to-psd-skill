"""Build image paint from original files, without browser screenshot crops."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageChops, ImageDraw, ImageOps


class UnsupportedImagePaint(ValueError):
    pass


def local_image_path(url, source):
    if not source:
        return None
    parsed, base = urlsplit(url), urlsplit(source['url'])
    if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
        return None
    root = Path(source['projectDirectory']).resolve()
    path = (root / unquote(parsed.path).lstrip('/')).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Image URL escapes the supplied project directory')
    if not path.is_file():
        raise FileNotFoundError(f'Referenced local image is missing: {path}')
    return path


def single_background_url(value):
    match = re.fullmatch(r'url\(\s*([\'"])(.*?)\1\s*\)', value.strip())
    if not match:
        match = re.fullmatch(r'url\(\s*([^\s()]+)\s*\)', value.strip())
        return match[1] if match else None
    return match[2]


def length(value, extent):
    if value.endswith('%'):
        return float(value[:-1]) * extent / 100
    if value.endswith('px'):
        return float(value[:-2])
    if value == '0':
        return 0.0
    raise UnsupportedImagePaint(f'Unsupported CSS length: {value}')


def position(value, space, scale):
    parts = value.split()
    if len(parts) == 1:
        parts = ['center', parts[0]] if parts[0] in ('top', 'bottom') else [parts[0], 'center']
    if len(parts) != 2:
        raise UnsupportedImagePaint(f'Unsupported image position: {value}')
    if parts[0] in ('top', 'bottom') or parts[1] in ('left', 'right'):
        parts.reverse()
    keywords = {'left': '0%', 'top': '0%', 'center': '50%', 'right': '100%', 'bottom': '100%'}
    result = []
    for part, remaining in zip(parts, space):
        part = keywords.get(part, part)
        result.append(length(part, remaining) if part.endswith('%') else length(part, 0) * scale)
    return result


def image_size(natural, box, fit):
    if fit == 'fill':
        return box
    if fit == 'none':
        return natural
    if fit not in ('cover', 'contain', 'scale-down'):
        raise UnsupportedImagePaint(f'Unsupported object-fit: {fit}')
    factor = (max if fit == 'cover' else min)(box[0] / natural[0], box[1] / natural[1])
    if fit == 'scale-down':
        factor = min(1, factor)
    return tuple(max(1, round(v * factor)) for v in natural)


def rounded_mask(size, rect, radius, scale):
    mask = Image.new('L', size)
    draw = ImageDraw.Draw(mask)
    x, y, w, h = rect
    values = radius.split()
    if '/' in radius or (len(values) > 1 and len(set(values)) != 1):
        raise UnsupportedImagePaint(f'Unsupported asymmetric border radius: {radius}')
    r = length(values[0] if values else '0px', min(w, h) / scale) * scale
    bounds = (round(x), round(y), round(x + w) - 1, round(y + h) - 1)
    draw.rounded_rectangle(bounds, radius=min(r, w / 2, h / 2), fill=255)
    return mask


def is_translation(value):
    if value == 'none': return True
    match = re.fullmatch(r'matrix(3d)?\(([^)]+)\)', value.strip())
    if not match: return False
    try: values = [float(v.strip()) for v in match[2].split(',')]
    except ValueError: return False
    if not all(__import__('math').isfinite(v) for v in values): return False
    if not match[1]:
        return len(values) == 6 and all(abs(a-b) < 1e-9 for a,b in zip(values[:4], [1,0,0,1]))
    identity = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
    return len(values) == 16 and all(abs(v-identity[i]) < 1e-9 for i,v in enumerate(values) if i not in (12,13,14))


def render_source_image(atom, scale):
    css = atom['css']
    for key, normal in [('filter', 'none'), ('mixBlendMode', 'normal'), ('transform', 'none')]:
        if css.get(key, normal) != normal:
            raise UnsupportedImagePaint(f'{key}={css[key]} requires an effect renderer')
    if css.get('clipPath','none') != 'none':
        raise UnsupportedImagePaint('clip-path requires an effect renderer')
    if any(not is_translation(c.get('transform', 'none')) for c in atom.get('imageClips', [])):
        raise UnsupportedImagePaint('Ancestor transform requires an effect renderer')
    if any(c.get('filter', 'none') != 'none' for c in atom.get('imageClips', [])):
        raise UnsupportedImagePaint('Ancestor filter requires an effect renderer')
    try:
        with Image.open(atom['sourcePath']) as source:
            image = ImageOps.exif_transpose(source).convert('RGBA')
    except (OSError, ValueError) as error:
        raise UnsupportedImagePaint(f'Original image format needs another decoder: {error}') from error
    natural = image.size
    rect = atom['rect']
    width, height = rect['w'], rect['h']
    inset = lambda side: float(css.get(f'border{side}Width', '0px').removesuffix('px'))
    padding = lambda side: float(css.get(f'padding{side}', '0px').removesuffix('px'))
    background = atom['kind'] == 'background_image'
    left = inset('Left') + (0 if background else padding('Left'))
    top = inset('Top') + (0 if background else padding('Top'))
    right = inset('Right') + (0 if background else padding('Right'))
    bottom = inset('Bottom') + (0 if background else padding('Bottom'))
    box = (max(1, round((width - left - right) * scale)),
           max(1, round((height - top - bottom) * scale)))
    logical = atom.get('naturalSize') or {'w': natural[0], 'h': natural[1]}
    intrinsic = (logical['w'] * scale, logical['h'] * scale) if not background else (natural[0] * scale, natural[1] * scale)
    if background:
        if css.get('backgroundOrigin', 'padding-box') != 'padding-box' or css.get('backgroundAttachment', 'scroll') != 'scroll':
            raise UnsupportedImagePaint('Non-default background origin/attachment requires an effect renderer')
        if css.get('backgroundClip', 'border-box') not in ('border-box', 'padding-box'):
            raise UnsupportedImagePaint('Unsupported background clipping mode')
        value = css.get('backgroundSize', 'auto')
        if value in ('cover', 'contain'):
            target = image_size(intrinsic, box, value)
        else:
            parts = value.split()
            if len(parts) == 1:
                parts.append('auto')
            if len(parts) != 2:
                raise UnsupportedImagePaint(f'Unsupported background-size: {value}')
            target = [None if part == 'auto' else length(part, box[i] / scale) * scale
                      for i, part in enumerate(parts)]
            if target == [None, None]:
                target = intrinsic
            elif target[0] is None:
                target[0] = target[1] * natural[0] / natural[1]
            elif target[1] is None:
                target[1] = target[0] * natural[1] / natural[0]
            target = tuple(max(1, round(v)) for v in target)
        placement = css.get('backgroundPosition', '0% 0%')
        repeat = css.get('backgroundRepeat', 'repeat')
        repeat_modes = {'no-repeat': (False, False), 'repeat': (True, True),
                        'repeat-x': (True, False), 'repeat-y': (False, True),
                        'repeat no-repeat': (True, False), 'no-repeat repeat': (False, True)}
        if repeat not in repeat_modes:
            raise UnsupportedImagePaint(f'Unsupported background-repeat: {repeat}')
        rx, ry = repeat_modes[repeat]
    else:
        target = image_size(intrinsic, box, css.get('objectFit', 'fill'))
        placement = css.get('objectPosition', '50% 50%')
        rx = ry = False
    resized = image.resize(target, Image.Resampling.LANCZOS)
    ox, oy = position(placement, (box[0] - target[0], box[1] - target[1]), scale)
    ox, oy = round(ox), round(oy)
    canvas = Image.new('RGBA', box)
    xs = range(ox % target[0] - target[0], box[0], target[0]) if rx else [ox]
    ys = range(oy % target[1] - target[1], box[1], target[1]) if ry else [oy]
    for y in ys:
        for x in xs:
            canvas.alpha_composite(resized, (x, y))
    output = Image.new('RGBA', (atom['w'] * scale, atom['h'] * scale))
    origin = ((rect['x'] - atom['x']) * scale, (rect['y'] - atom['y']) * scale)
    output.alpha_composite(canvas, (round(origin[0] + left * scale), round(origin[1] + top * scale)))
    masks = [(rect, css.get('borderRadius', '0px'))]
    masks += [(c['rect'], c.get('borderRadius', '0px')) for c in atom.get('imageClips', []) if c.get('clip')]
    alpha = output.getchannel('A')
    for r, radius in masks:
        relative = ((r['x'] - atom['x']) * scale, (r['y'] - atom['y']) * scale,
                    r['w'] * scale, r['h'] * scale)
        alpha = ImageChops.multiply(alpha, rounded_mask(output.size, relative, radius, scale))
    opacity = atom.get('opacity', 1)
    if opacity != 1:
        alpha = alpha.point(lambda v: round(v * opacity))
    output.putalpha(alpha)
    atom['sourcePixels'] = list(natural)
    return output
