"""Integration tests for capture artifacts, viewport defaults, and PSD sizing."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from build_psd import prepare
from capture_contract import CaptureContractError


class CaptureContractIntegrationTests(unittest.TestCase):
    def make_job(self, width, width_source, scale=1, scale_source='default-1',
                 screenshot_width=None, include_after=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        screenshot_width = width if screenshot_width is None else screenshot_width
        height = 40
        client_width = min(width, screenshot_width)
        scrollbar_width = width - client_width
        state = dict(url='http://127.0.0.1/test.html', width=width, height=height,
                     viewportHeight=height, scrollX=0, scrollY=0,
                     clientWidth=client_width, scrollbarWidth=scrollbar_width,
                     ratio=1, fontStatus='loaded', pendingVisibleImages=[], elements=[])
        (root/'web_dom.json').write_text(json.dumps(state))
        if include_after:
            (root/'web_dom_after.json').write_text(json.dumps(state))
        (root/'web_assets.json').write_text(json.dumps({'assets': []}))
        Image.new('RGB', (screenshot_width, height), 'white').save(root/'web_reference.png')
        dimensions = dict(widthSource=width_source, requestedViewportWidth=width,
                          measuredInnerWidth=width, measuredInnerHeight=height,
                          clientWidth=client_width, scrollbarWidth=scrollbar_width,
                          devicePixelRatio=1, screenshotWidth=screenshot_width,
                          screenshotHeight=height, scaleSource=scale_source,
                          requestedRenderScale=scale)
        (root/'capture_dimensions.json').write_text(json.dumps(dimensions))
        return root

    def prepare_quietly(self, root, scale=1, strict=False):
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(root, scale, auto_scale=not strict)
        return json.loads((root/'web_layers.json').read_text())

    def test_omitted_width_uses_2560_at_one_x(self):
        root = self.make_job(2560, 'default-2560')
        manifest = self.prepare_quietly(root)
        dimensions = json.loads((root/'capture_dimensions.json').read_text())
        self.assertEqual((manifest['width'], manifest['renderScale']), (2560, 1))
        self.assertEqual(dimensions['finalPSDWidth'], 2560)

    def test_explicit_width_uses_exact_value_at_default_scale(self):
        root = self.make_job(1440, 'explicit')
        manifest = self.prepare_quietly(root)
        dimensions = json.loads((root/'capture_dimensions.json').read_text())
        self.assertEqual((manifest['width'], manifest['renderScale']), (1440, 1))
        self.assertEqual(dimensions['finalPSDWidth'], 1440)

    def test_explicit_width_and_scale_are_both_preserved(self):
        root = self.make_job(1440, 'explicit', 2, 'explicit')
        manifest = self.prepare_quietly(root, 2, strict=True)
        dimensions = json.loads((root/'capture_dimensions.json').read_text())
        self.assertEqual((manifest['width'], manifest['renderScale']), (1440, 2))
        self.assertEqual(dimensions['finalPSDWidth'], 2880)

    def test_screenshot_width_loss_is_rejected(self):
        root = self.make_job(1440, 'explicit', screenshot_width=1425)
        with self.assertRaisesRegex(CaptureContractError, 'differs from requested viewport'):
            self.prepare_quietly(root)

    def test_second_dom_capture_is_required(self):
        root = self.make_job(1440, 'explicit', include_after=False)
        with self.assertRaisesRegex(FileNotFoundError, 'web_dom_after.json'):
            self.prepare_quietly(root)

    def test_explicit_scale_requires_strict_mode(self):
        root = self.make_job(1440, 'explicit', 2, 'explicit')
        with self.assertRaisesRegex(CaptureContractError, '--strict-render-scale'):
            self.prepare_quietly(root, 2, strict=False)


if __name__ == '__main__':
    unittest.main()
