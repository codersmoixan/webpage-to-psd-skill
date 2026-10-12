"""Compare a freshly rendered high-resolution text cache with an old 1x PSD."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from psd_tools import PSDImage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-dir', type=Path, required=True)
    parser.add_argument('--baseline-psd', type=Path, required=True)
    parser.add_argument('--text', required=True)
    parser.add_argument('--output-name', default='text_clarity_comparison.png')
    args = parser.parse_args()
    manifest = json.loads((args.job_dir / 'web_layers.json').read_text())
    scale = manifest['renderScale']
    atom = next(a for a in manifest['atoms'] if a['kind'] == 'text' and a['text'] == args.text)
    baseline = PSDImage.open(args.baseline_psd)
    layer = next(t for t in baseline.descendants() if t.kind == 'type' and t.text.rstrip('\r\x00') == args.text)
    old = layer.topil().convert('RGBA')
    new = Image.open(args.job_dir / 'web_psd_layers' / f'{atom["id"]:03d}.png').convert('RGBA')
    old = old.resize((old.width * scale, old.height * scale), Image.Resampling.NEAREST)
    width = max(old.width, new.width) + 32
    row_height = max(old.height, new.height) + 64
    comparison = Image.new('RGB', (width, row_height * 2), '#b8b8b8')
    draw = ImageDraw.Draw(comparison)
    draw.text((16, 12), f'Old 1x text cache enlarged {scale}x', fill='black')
    draw.text((16, row_height + 12), f'New text rerendered at {scale}x (native output pixels)', fill='black')
    comparison.paste(old, (16, 40), old)
    comparison.paste(new, (16, row_height + 40), new)
    output = args.job_dir / args.output_name
    comparison.save(output)
    # High-resolution antialiasing should add coverage beyond nearest-neighbor blocks.
    alpha = np.asarray(new.getchannel('A'))
    assert np.any((alpha > 0) & (alpha < 255)), 'Text cache has no antialiased edge pixels'
    assert new.width >= layer.width * (scale - 0.5), 'Text cache did not scale with the canvas'
    print(json.dumps({'text': args.text, 'scale': scale, 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
