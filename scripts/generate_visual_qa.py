"""Keep full-resolution artifacts local and export bounded visual QA inputs."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def crop_box(rect, size, limit=(1000, 600), padding=24):
    x, y, width, height = rect
    left = max(0, math.floor(x - padding))
    top = max(0, math.floor(y - padding))
    right = min(size[0], math.ceil(x + width + padding))
    bottom = min(size[1], math.ceil(y + height + padding))
    left = min(left, max(0, size[0] - 1))
    top = min(top, max(0, size[1] - 1))
    return (left, top, max(left + 1, min(right, left + limit[0])),
            max(top + 1, min(bottom, top + limit[1])))


def generate_visual_qa(root, preview_path, validation=None, composite_path=None):
    manifest = json.loads((root / 'web_layers.json').read_text(encoding='utf-8-sig'))
    scale = manifest.get('renderScale', 1)
    expected_size = (manifest['width'] * scale, manifest['height'] * scale)
    qa_dir = root / 'visual_qa'
    qa_dir.mkdir(exist_ok=True)
    with Image.open(preview_path) as image:
        assert image.size == expected_size, 'Preview size differs from manifest'
        overview = image.copy()
        overview.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        overview.convert('RGB').save(qa_dir / 'overview.png')
        overview_size = overview.size

    source = composite_path or preview_path
    text = [a for a in manifest['atoms'] if a['kind'] == 'text' and a.get('pixelBox')]
    candidates = []
    chosen = set()

    def select(category, options, key, reverse=False):
        for atom in sorted(options, key=key, reverse=reverse):
            if atom['id'] not in chosen:
                candidates.append((category, atom))
                chosen.add(atom['id'])
                break

    def font_size(atom):
        return float(atom['css']['fontSize'].removesuffix('px'))

    cjk = [a for a in text if any('\u3400' <= ch <= '\u9fff' for ch in a['text'])]
    select('small_cjk', [a for a in cjk if len(a['text'].strip()) >= 6], font_size)
    select('heading', [a for a in text if any(ch.isalpha() for ch in a['text'])],
           font_size, reverse=True)
    select('latin', [a for a in text if len(a['text'].strip()) >= 4
                    and all(ord(ch) < 128 for ch in a['text'])], font_size)
    icons = [a for a in manifest['atoms'] if a['kind'] == 'icon' and a.get('pixelBox')]
    select('icon', icons, lambda a: a['pixelBox'][2] * a['pixelBox'][3], reverse=True)
    if len(candidates) < 3:
        select('body_text', text, font_size)
    if len(candidates) < 3:
        images = [a for a in manifest['atoms'] if a['kind'] == 'image' and a.get('pixelBox')]
        select('image', images, lambda a: a['pixelBox'][2] * a['pixelBox'][3], reverse=True)

    # Use local difference pixels to select one additional region for human review.
    difference_path = root / 'web_difference.png'
    difference_rect = None
    if difference_path.exists():
        with Image.open(difference_path) as difference:
            assert difference.size == (manifest['width'], manifest['height'])
            scores = np.asarray(difference.convert('RGB')).max(axis=2)
        tile_width = max(1, 1000 // scale)
        tile_height = max(1, 600 // scale)
        best = (-1, 0, 0, 0, 0)
        for y in range(0, scores.shape[0], tile_height):
            for x in range(0, scores.shape[1], tile_width):
                tile = scores[y:y + tile_height, x:x + tile_width]
                score = float(tile.mean())
                if score > best[0]:
                    best = (score, x, y, tile.shape[1], tile.shape[0])
        if best[0] > 0:
            difference_rect = [v * scale for v in best[1:]]

    crops = []
    with Image.open(source) as image:
        assert image.size == expected_size, 'QA source size differs from manifest'
        for category, atom in candidates:
            box = crop_box(atom['pixelBox'], image.size)
            path = qa_dir / f'{category}.png'
            image.crop(box).convert('RGB').save(path)
            crops.append({'category': category, 'path': str(path), 'box': list(box),
                          'atomId': atom['id'], 'text': (atom.get('text') or '')[:100],
                          'nativePixels': True,
                          'partialLine': atom['pixelBox'][2] + 48 > 1000})
        if difference_rect is not None and len(crops) < 5:
            box = crop_box(difference_rect, image.size, padding=0)
            path = qa_dir / 'high_difference.png'
            image.crop(box).convert('RGB').save(path)
            crops.append({'category': 'high_difference', 'path': str(path),
                          'box': list(box), 'nativePixels': True})

    warnings = []
    if not cjk:
        warnings.append('No CJK text available for sampling.')
    elif not any(c['category'] == 'small_cjk' for c in crops):
        warnings.append('No sufficiently long CJK line; inspect a shorter line when needed.')
    if len(crops) < 3:
        warnings.append('Fewer than three representative crops available; inspect relevant content manually.')
    report = validation or {}
    summary = {
        'canvas': list(expected_size), 'renderScale': scale,
        'resolutionPPI': report.get('resolutionPPI'),
        'layers': report.get('layers'), 'nativeTextLayers': report.get('nativeTextLayers'),
        'originalImageLayers': report.get('originalImageLayers'),
        'imageRasterFallbacks': [{'id': a['id'], 'reason': a.get('fallbackReason')}
                                for a in report.get('imageRasterFallbacks', [])],
        'referenceMeanAbsoluteError': report.get('meanAbsoluteError'),
        'roundtripMeanAbsoluteError': report.get('roundtripMeanAbsoluteError'),
        'overview': str(qa_dir / 'overview.png'), 'overviewSize': list(overview_size),
        'crops': [{'category': c['category'], 'path': c['path']} for c in crops],
        'warnings': warnings,
        'visualReviewRequired': True,
    }
    (qa_dir / 'manifest.json').write_text(json.dumps(
        {'source': str(source), 'summary': summary, 'crops': crops}, ensure_ascii=False, indent=2), encoding='utf8')
    (qa_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-dir', type=Path, required=True)
    parser.add_argument('--preview', type=Path)
    args = parser.parse_args()
    root = args.job_dir.resolve()
    validation_path = root / 'PSD_validation.json'
    validation = json.loads(validation_path.read_text(encoding='utf-8-sig')) if validation_path.exists() else {}
    preview = args.preview or Path(validation['preview'])
    composite = root / 'PSD_reopened_composite.png'
    summary = generate_visual_qa(root, preview, validation,
                                 composite if composite.exists() else None)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
