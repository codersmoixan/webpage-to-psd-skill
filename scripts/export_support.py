"""Font discovery, PSD size preflight and transactional saves."""
import os
import re
import struct
import tempfile
from functools import lru_cache
from pathlib import Path


def choose_scale(width, height, requested=1, automatic=True):
    allowed = min(4, 30000 // max(width, height))
    if allowed < 1:
        raise ValueError('Page exceeds standard PSD dimensions even at 1x; split the page or use PSB.')
    if requested > allowed and not automatic:
        raise ValueError(f'{requested}x exceeds standard PSD dimensions; maximum scale is {allowed}x.')
    return min(requested, allowed)


def font_records(path):
    """Read family/full/PostScript names from SFNT and TTC without a new dependency."""
    data = Path(path).read_bytes()
    offsets = [0]
    if data[:4] == b'ttcf':
        count = struct.unpack_from('>I', data, 8)[0]
        offsets = struct.unpack_from(f'>{count}I', data, 12)
    records = []
    for offset in offsets:
        count = struct.unpack_from('>H', data, offset + 4)[0]
        for i in range(count):
            pos = offset + 12 + i * 16
            tag, _, start, _ = struct.unpack_from('>4sIII', data, pos)
            if tag != b'name': continue
            _, entries, strings = struct.unpack_from('>HHH', data, start)
            names = {}
            for j in range(entries):
                platform, encoding, language, name_id, length, relative = struct.unpack_from('>6H', data, start + 6 + 12*j)
                if name_id not in (1, 2, 4, 6, 16): continue
                raw = data[start + strings + relative:start + strings + relative + length]
                try: value = raw.decode('utf-16-be' if platform in (0, 3) else 'mac_roman')
                except UnicodeError: continue
                names.setdefault(name_id, []).append(value)
            if names.get(6):
                records.append({'postscript': names[6][0], 'aliases': names.get(1, []) + names.get(4, []) + names.get(16, []),
                                'styles': names.get(2, []), 'path': str(path)})
    return records


@lru_cache(maxsize=1)
def installed_fonts():
    roots = [Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts',
             Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'Microsoft/Windows/Fonts',
             Path('/usr/share/fonts'), Path.home()/'.local/share/fonts',
             Path('/Library/Fonts'), Path('/System/Library/Fonts')]
    records = []
    for root in roots:
        if not root.is_dir(): continue
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() not in ('.ttf', '.otf', '.ttc'): continue
            try: records.extend(font_records(path))
            except (OSError, ValueError, struct.error): continue
    return records


def select_font(css, text, inventory=None):
    inventory = installed_fonts() if inventory is None else inventory
    normalize = lambda s: re.sub(r'[\s_-]', '', s).casefold()
    requested = [part.strip().strip('\"\'') for part in css.get('fontFamily', '').split(',')]
    cjk = any('\u3400' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff' or '\uac00' <= c <= '\ud7af' for c in text)
    fallbacks = ['Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', 'SimHei'] if cjk else ['Arial', 'Liberation Sans', 'DejaVu Sans']
    for family in requested + fallbacks:
        matches = [f for f in inventory if normalize(family) in {normalize(a) for a in f['aliases'] + [f['postscript']]}]
        if not matches: continue
        bold = int(css.get('fontWeight', '400')) >= 600
        italic = css.get('fontStyle', 'normal') != 'normal'
        def score(f):
            style = ' '.join(f['styles'] + [f['postscript']]).lower()
            return (('bold' in style) != bold) + (('italic' in style or 'oblique' in style) != italic)
        selected = min(matches, key=score)
        return {'requested': requested, 'postscript': selected['postscript'], 'path': selected['path'],
                'substituted': family not in requested, 'installed': True}
    return {'requested': requested, 'postscript': 'MicrosoftYaHei' if cjk else 'ArialMT',
            'path': None, 'substituted': True, 'installed': False}


def atomic_save(psd, output, validate):
    """Never replace a completed PSD until its sibling temporary file validates."""
    output = Path(output)
    fd, name = tempfile.mkstemp(prefix=output.stem+'.', suffix='.tmp.psd', dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        psd.save(temporary)
        validate(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
