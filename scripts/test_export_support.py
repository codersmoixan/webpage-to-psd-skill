import copy
import tempfile
import unittest
from pathlib import Path
from export_support import choose_scale, select_font, atomic_save, installed_fonts
from image_sources import is_translation
from check_capture_pair import compare


class ExportSupportTests(unittest.TestCase):
    def test_capture_rejects_unloaded_content_and_scrollbar_drift(self):
        base=dict(elements=[],width=2560,clientWidth=2560,fontStatus='loaded',pendingVisibleImages=[])
        self.assertTrue(compare(base,base)['stable'])
        for state in [dict(base,fontStatus='loading'),dict(base,pendingVisibleImages=[{'index':1}]),dict(base,clientWidth=2545)]:
            self.assertFalse(compare(base,state)['stable'])

    def test_default_scale_is_one(self):
        self.assertEqual(choose_scale(2560,6816),1)

    def test_long_page_preflight(self):
        self.assertEqual(choose_scale(1265,10115,4),2)
        self.assertEqual(choose_scale(100,100,4),4)
        with self.assertRaises(ValueError): choose_scale(1265,10115,4,False)
        with self.assertRaises(ValueError): choose_scale(100,30001)

    def test_translation_rejects_distortion_and_bad_matrices(self):
        self.assertTrue(is_translation('matrix(1, 0, 0, 1, -4229.81, 0)'))
        self.assertTrue(is_translation('matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,12,30,0,1)'))
        for value in ['matrix(1,0,0,1)', 'matrix(2,0,0,1,0,0)', 'matrix(0,-1,1,0,0,0)', 'matrix(1,0,0,1,nan,0)']:
            self.assertFalse(is_translation(value))

    def test_font_family_and_weight_selection(self):
        fonts=[{'aliases':['Microsoft YaHei','微软雅黑'],'postscript':'MicrosoftYaHei','styles':['Regular'],'path':'regular.ttf'},
               {'aliases':['Microsoft YaHei'],'postscript':'MicrosoftYaHei-Bold','styles':['Bold'],'path':'bold.ttf'}]
        result=select_font({'fontFamily':'"Missing", "Microsoft YaHei", Arial','fontWeight':'700'},'中文',fonts)
        self.assertEqual(result['postscript'],'MicrosoftYaHei-Bold')
        self.assertFalse(result['substituted'])
        result=select_font({'fontFamily':'Missing'},'中文',fonts)
        self.assertTrue(result['substituted'])
        self.assertFalse(select_font({},'中文',[])['installed'])

    def test_atomic_save_preserves_previous_file_on_failure(self):
        class Document:
            def save(self,path): Path(path).write_bytes(b'new')
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'final.psd'; output.write_bytes(b'old')
            def fail(path): raise ValueError('Invalid PSD')
            with self.assertRaises(ValueError): atomic_save(Document(),output,fail)
            self.assertEqual(output.read_bytes(),b'old')
            self.assertEqual(list(Path(folder).glob('*.tmp.psd')),[])
            atomic_save(Document(),output,lambda p: self.assertEqual(p.read_bytes(),b'new'))
            self.assertEqual(output.read_bytes(),b'new')

    def test_capture_detects_carousel_and_fixed_geometry_changes(self):
        state={'url':'test','width':1280,'height':10000,'elements':[{'index':1,'rect':{'x':100,'y':200,'w':20,'h':30},'css':{'transform':'none'},'src':'one.png'}]}
        self.assertTrue(compare(state,copy.deepcopy(state))['stable'])
        changed=copy.deepcopy(state); changed['elements'][0]['css']['transform']='matrix(1,0,0,1,100,0)'
        self.assertFalse(compare(state,changed)['stable'])
        changed=copy.deepcopy(state); changed['elements'][0]['rect']['y']+=1000
        self.assertFalse(compare(state,changed)['stable'])

    def test_native_type_and_unicode_layer_survive_atomic_save(self):
        from PIL import Image
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        from psd_tools.constants import Tag
        from psd_tools.psd.tagged_blocks import TaggedBlock
        from build_psd import native_text
        template=next(t for t in PSDImage.open(Path(__file__).resolve().parents[1]/'assets/text-template.psd').descendants() if t.kind=='type')
        atom={'id':0,'text':'中文测试','rect':{'x':1,'y':1},'css':{'fontFamily':'Microsoft YaHei','fontSize':'12px','fontWeight':'400','fontStyle':'normal','letterSpacing':'normal','color':'rgb(0, 0, 0)'}}
        document=PSDImage.new('RGBA',(100,50),(255,255,255,255))
        layer=PixelLayer.frompil(Image.new('RGBA',(80,25),'black'),document,name='Text')
        layer.name='中文文字图层'
        layer.tagged_blocks[Tag.TYPE_TOOL_OBJECT_SETTING]=TaggedBlock(key=Tag.TYPE_TOOL_OBJECT_SETTING,data=native_text(template,atom,2))
        with tempfile.TemporaryDirectory() as folder:
            def validate(path):
                reopened=PSDImage.open(path)
                self.assertEqual(reopened[0].name,'中文文字图层')
                self.assertEqual(reopened[0].text.rstrip('\r\x00'),'中文测试')
            atomic_save(document,Path(folder)/'test.psd',validate)


if __name__=='__main__': unittest.main()
