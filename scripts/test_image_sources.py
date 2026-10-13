"""Regression checks for original-file image generation; no browser is needed."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from psd_tools import PSDImage

from build_psd import prepare, build
from image_sources import local_image_path, render_source_image, UnsupportedImagePaint


TEMPLATE = Path(__file__).resolve().parents[1] / 'assets' / 'text-template.psd'


class OriginalImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / 'project'
        self.project.mkdir()
        self.job = Path(self.temp.name) / 'job'
        self.job.mkdir()
        self.path = self.project / 'two colors.png'
        image = Image.new('RGBA', (200, 100), 'red')
        image.paste('blue', (100, 0, 200, 100))
        image.save(self.path)
        self.css = dict(backgroundColor='rgba(0, 0, 0, 0)', backgroundImage='none',
                        backgroundSize='cover', backgroundPosition='50% 50%',
                        backgroundRepeat='no-repeat', backgroundOrigin='padding-box',
                        backgroundClip='border-box', backgroundAttachment='scroll',
                        opacity='1', boxShadow='none', borderRadius='0px',
                        objectFit='contain', objectPosition='50% 50%', filter='none',
                        transform='none', mixBlendMode='normal', zIndex='auto')
        for side in ['Top', 'Right', 'Bottom', 'Left']:
            self.css.update({f'border{side}Width': '0px', f'border{side}Style': 'none',
                             f'border{side}Color': 'rgba(0, 0, 0, 0)', f'padding{side}': '0px'})
        self.element = dict(index=0, parent=-1, tag='img', cls='photo',
                            rect=dict(x=10, y=10, w=40, h=40), css=self.css,
                            src='http://127.0.0.1:12345/two%20colors.png?version=1',
                            alt='Original photo', text=[], pseudo=[], svg=None, placeholder=None)
        self.source = dict(url='http://127.0.0.1:12345/index.html',
                           projectDirectory=str(self.project))
        (self.job / 'local_source.json').write_text(json.dumps(self.source))
        (self.job / 'web_assets.json').write_text(json.dumps({'assets': []}))
        Image.new('RGB', (80, 80), 'white').save(self.job / 'web_reference.png')

    def tearDown(self):
        self.temp.cleanup()

    def write_capture_contract(self, scale, scale_source):
        state = dict(url=self.source['url'], width=80, height=80, viewportHeight=80,
                     scrollX=0, scrollY=0, clientWidth=80, scrollbarWidth=0, ratio=1,
                     fontStatus='loaded', pendingVisibleImages=[], elements=[self.element])
        (self.job / 'web_dom.json').write_text(json.dumps(state))
        (self.job / 'web_dom_after.json').write_text(json.dumps(state))
        dimensions = dict(widthSource='explicit', requestedViewportWidth=80,
                          measuredInnerWidth=80, measuredInnerHeight=80,
                          clientWidth=80, scrollbarWidth=0, devicePixelRatio=1,
                          screenshotWidth=80, screenshotHeight=80,
                          scaleSource=scale_source, requestedRenderScale=scale)
        (self.job / 'capture_dimensions.json').write_text(json.dumps(dimensions))

    def run_prepare(self, allow=False):
        self.write_capture_contract(4, 'explicit')
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.job, 4, allow, auto_scale=False)
        return json.loads((self.job / 'web_layers.json').read_text())

    def test_default_scale_and_wide_atlas(self):
        self.element.update(tag='div',src=None)
        self.element['rect']['w']=2560
        self.css['backgroundColor']='red'
        self.write_capture_contract(1, 'default-1')
        with contextlib.redirect_stdout(io.StringIO()): prepare(self.job)
        manifest=json.loads((self.job/'web_layers.json').read_text())
        self.assertEqual(manifest['renderScale'],1)
        atom=manifest['atoms'][0];page=manifest['pages'][atom['atlasPage']]
        self.assertGreaterEqual(page['width'],atom['atlasX']+atom['w'])

    def test_gradient_photo_color_and_negative_pseudo_order(self):
        self.element.update(tag='div',src=None)
        url='http://127.0.0.1:12345/two%20colors.png'
        self.css['backgroundColor']='white'
        self.css['backgroundImage']=f'linear-gradient(rgba(0,0,0,.5),rgba(0,0,0,.5)), url("{url}")'
        for key in ['backgroundSize','backgroundPosition','backgroundRepeat','backgroundOrigin','backgroundClip','backgroundAttachment']:
            self.css[key]=self.css[key]+', '+self.css[key]
        self.element['pseudo']=[dict(selector='::before',css={'width':'40px','height':'40px','background-color':'red','z-index':'-1'})]
        m=self.run_prepare()
        kinds=[a['kind'] for a in m['atoms']]
        self.assertEqual(kinds,['shape','background_image','shape','overlay'])
        self.assertTrue(m['atoms'][0]['basePaint'])
        self.assertEqual(m['atoms'][1]['imageSource'],'original-file')
        self.assertEqual(m['atoms'][3]['paintZ'],-1)

    def test_blank_text_cache_aborts_and_preserves_previous_output(self):
        m=self.run_prepare()
        atom=dict(m['atoms'][0],id=1,kind='text',text='Expected text',atlasPage=0,atlasX=0,atlasY=0,w=20,h=20,pixelBox=[1,1,2,2])
        atom.pop('imageSource');m['atoms']=[atom];m['pages']=[dict(width=80,height=80)]
        (self.job/'web_layers.json').write_text(json.dumps(m))
        Image.new('RGB',(80,80),'white').save(self.job/'atlas_0_white.png')
        Image.new('RGB',(80,80),'black').save(self.job/'atlas_0_black.png')
        target=self.job/'old.psd';target.write_bytes(b'previous valid export')
        with self.assertRaisesRegex(ValueError,'Missing rendered text cache'):
            build(self.job,TEMPLATE,'old.psd')
        self.assertEqual(target.read_bytes(),b'previous valid export')

    def test_image_only_psd_needs_no_screenshot_atlases(self):
        manifest = self.run_prepare()
        self.assertEqual(manifest['pages'], [])
        atom = manifest['atoms'][0]
        self.assertEqual(atom['imageSource'], 'original-file')
        self.assertEqual(Path(atom['sourcePath']).read_bytes(), self.path.read_bytes())
        self.assertNotIn('atlasPage', atom)
        with contextlib.redirect_stdout(io.StringIO()):
            build(self.job, TEMPLATE, 'direct.psd')
        psd = PSDImage.open(self.job / 'direct.psd')
        composite = psd.composite(force=True)
        self.assertEqual(composite.getpixel((60, 100))[:3], (255, 0, 0))
        self.assertEqual(composite.getpixel((180, 100))[:3], (0, 0, 255))
        self.assertEqual(composite.getpixel((60, 50))[:3], (255, 255, 255))
        report = json.loads((self.job / 'PSD_validation.json').read_text())
        self.assertEqual(report['resolutionPPI'], [72.0, 72.0])
        self.assertEqual(report['captureDimensions']['finalPSDWidth'], 320)
        self.assertEqual(report['originalImageLayers'], 1)
        self.assertEqual(report['imageRasterFallbacks'], [])
        self.assertEqual(len(list(self.job.glob('atlas_*.png'))), 0)

    def test_cover_position_radius_opacity_and_ancestor_clip(self):
        atom = self.run_prepare()['atoms'][0]
        atom['css']['objectFit'] = 'cover'
        atom['css']['objectPosition'] = 'right top'
        atom['css']['borderRadius'] = '10px'
        atom['opacity'] = 0.5
        atom['imageClips'] = [dict(rect=dict(x=10, y=10, w=20, h=40), clip=True)]
        paint = render_source_image(atom, 4)
        self.assertEqual(paint.getpixel((52, 80)), (0, 0, 255, 128))
        self.assertEqual(paint.getpixel((12, 12))[3], 0)
        self.assertEqual(paint.getpixel((120, 80))[3], 0)

    def test_css_background_reads_original_file(self):
        self.element.update(tag='div', src=None)
        self.css['backgroundImage'] = 'url("http://127.0.0.1:12345/two%20colors.png")'
        atom = self.run_prepare()['atoms'][0]
        self.assertEqual(atom['kind'], 'background_image')
        self.assertEqual(atom['imageSource'], 'original-file')
        self.assertEqual(render_source_image(atom, 4).getpixel((30, 80))[:3], (255, 0, 0))

    def test_translated_ancestor_uses_captured_geometry_once(self):
        atom = self.run_prepare()['atoms'][0]
        atom['imageClips'] = [dict(rect=dict(x=10,y=10,w=20,h=40),clip=True,
                                 transform='matrix(1,0,0,1,-100,50)')]
        paint = render_source_image(atom,4)
        self.assertEqual(paint.getpixel((30,80))[:3],(255,0,0))
        self.assertEqual(paint.getpixel((120,80))[3],0)

    def test_responsive_image_uses_browser_logical_intrinsic_size(self):
        self.element['naturalSize'] = {'w': 20, 'h': 10}
        self.css['objectFit'] = 'none'
        self.css['objectPosition'] = 'left top'
        atom = self.run_prepare()['atoms'][0]
        paint = render_source_image(atom, 4)
        self.assertEqual(paint.getpixel((20, 20))[:3], (255, 0, 0))
        self.assertEqual(paint.getpixel((70, 20))[:3], (0, 0, 255))
        self.assertEqual(paint.getpixel((100, 20))[3], 0)

    def test_missing_files_do_not_fall_back_to_screenshots(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_prepare(allow=True)

    def test_effect_fallback_is_explicit_and_recorded(self):
        self.css['filter'] = 'blur(3px)'
        with self.assertRaises(UnsupportedImagePaint):
            self.run_prepare()
        manifest = self.run_prepare(allow=True)
        self.assertEqual(manifest['atoms'][0]['imageSource'], 'atlas-effect-fallback')
        self.assertIn('filter', manifest['atoms'][0]['fallbackReason'])
        self.assertTrue(manifest['pages'])

    def test_url_decoding_and_root_confinement(self):
        self.assertEqual(local_image_path(self.element['src'], self.source), self.path.resolve())
        with self.assertRaises(ValueError):
            local_image_path('http://127.0.0.1:12345/%2e%2e/outside.png', self.source)


if __name__ == '__main__':
    unittest.main()
