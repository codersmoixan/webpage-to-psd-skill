"""Explicit CSS shadow profiles supported by the Photoshop-native bridge.

Zero-offset hard outer shadows become native rectangles, zero-offset hard inset
shadows become native inside strokes, and qualified soft shadows use native
layer effects. Unknown, blurred/offset inset, and multiple shadows remain errors.
"""
import math
import re

SOFT_PROFILES = {
    (21, 57, 90, .04, 0, 2, 8, 0),
    (21, 57, 85, .047, 0, 6, 28, 0),
}

def parse_shadow(value, scale=1):
    if not value or value == 'none':
        return None
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('Invalid shadow scale')
    normalized = value.strip()
    inset = normalized.endswith(' inset')
    parsed_value = normalized[:-6].strip() if inset else normalized
    match = re.fullmatch(r'rgba?\(([^)]+)\)\s+(.+)', parsed_value)
    if not match:
        raise ValueError('Unsupported shadow family: ' + value)
    color = [float(v.strip()) for v in match[1].split(',')]
    if len(color) == 3:
        color.append(1)
    lengths = match[2].split()
    if len(color) != 4 or len(lengths) != 4 or any(not re.fullmatch(r'-?\d+(?:\.\d+)?px', v) for v in lengths):
        raise ValueError('Unsupported shadow family: ' + value)
    x, y, blur, spread = [float(v[:-2]) for v in lengths]
    if not all(math.isfinite(v) for v in color + [x,y,blur,spread]) or any(v < 0 or v > 255 for v in color[:3]) or not 0 <= color[3] <= 1:
        raise ValueError('Invalid shadow values: ' + value)
    if x == y == blur == 0 and spread > 0:
        return dict(kind='inset-stroke' if inset else 'outset-rectangle',
                    color=color, spread=spread*scale)
    if inset:
        raise ValueError('Unsupported inset shadow geometry: ' + value)
    key = tuple(color + [x,y,blur,spread])
    if key not in SOFT_PROFILES:
        raise ValueError('Unsupported shadow family; needs Photoshop fixture validation: ' + value)
    if scale != 1:
        raise ValueError('Scaled shadow requires separate Photoshop fixture validation')
    return dict(kind='drop-shadow', color=color, distance=math.hypot(x,y),
                angle=math.degrees(math.atan2(-y,x))+180 if x else (90 if y >= 0 else -90),
                blur=blur, spread=0)

def split_shadow(spec):
    """Return bottom-to-top native specs, preserving the solid surface itself."""
    shadow = parse_shadow(spec.get('shadow', 'none'))
    if shadow is None:
        return [spec]
    if shadow['kind'] == 'drop-shadow':
        spec['shadowEffect'] = shadow
        return [spec]
    if shadow['kind'] == 'inset-stroke':
        inner = dict(bounds=spec['bounds'][:], radii=spec['radii'][:],
                     fill=[0,0,0,0], stroke=shadow['color'],
                     strokeWidth=shadow['spread'], opacity=spec['opacity'],
                     shadow='none', purpose='内描边')
        spec['shadow'] = 'none'
        return [spec, inner]
    if spec['fill'][3] != 1:
        raise ValueError('Outset shadow requires an opaque casting fill')
    x,y,w,h = spec['bounds']; spread = shadow['spread']
    outer = dict(bounds=[x-spread,y-spread,w+2*spread,h+2*spread],
                 radii=[r+spread if r else 0 for r in spec['radii']],
                 fill=shadow['color'],stroke=None,strokeWidth=0,
                 opacity=spec['opacity'],shadow='none',purpose='外描边')
    spec['shadow'] = 'none'
    return [outer,spec]
