import unittest
from native_shadows import parse_shadow,split_shadow
from image_sources import rounded_mask,UnsupportedImagePaint

class NativeShadowTests(unittest.TestCase):
    def test_outset_remains_native_geometry(self):
        source=dict(bounds=[10,20,130,100],radii=[0,12,24,0],fill=[244,246,248,1],stroke=None,strokeWidth=0,opacity=.8,shadow='rgb(0, 78, 179) 0px 0px 0px 1px')
        outer,inner=split_shadow(source)
        self.assertEqual(outer['bounds'],[9,19,132,102])
        self.assertEqual(outer['radii'],[0,13,25,0])
        self.assertEqual(outer['fill'],[0,78,179,1])
        self.assertEqual(inner['bounds'],[10,20,130,100])
        self.assertEqual(inner['shadow'],'none')
    def test_soft_profile_preserves_source_parameters(self):
        s=parse_shadow('rgba(21, 57, 85, 0.047) 0px 6px 28px 0px')
        self.assertEqual((s['color'],s['distance'],s['blur'],s['angle']),([21,57,85,.047],6,28,90))
    def test_unknown_and_ambiguous_effects_stop(self):
        for s in ['rgba(0, 0, 0, .7) 0px 6px 28px 0px','inset rgb(0,0,0) 0px 0px 0px 1px','rgb(0,0,0) 0px 0px 0px 1px, rgb(0,0,0) 0px 2px 8px 0px']:
            with self.subTest(s=s),self.assertRaises(ValueError):parse_shadow(s)
        with self.assertRaisesRegex(ValueError,'Scaled shadow'):parse_shadow('rgba(21, 57, 85, 0.047) 0px 6px 28px 0px',2)
    def test_hard_inset_becomes_native_inside_stroke(self):
        source=dict(bounds=[20,30,180,120],radii=[0,12,24,36],fill=[244,246,248,1],stroke=None,strokeWidth=0,opacity=.75,shadow='rgb(0, 78, 179) 0px 0px 0px 2px inset')
        base,inner=split_shadow(source)
        self.assertEqual(base['fill'],[244,246,248,1])
        self.assertEqual(base['shadow'],'none')
        self.assertEqual(inner['bounds'],[20,30,180,120])
        self.assertEqual(inner['radii'],[0,12,24,36])
        self.assertEqual(inner['stroke'],[0,78,179,1])
        self.assertEqual(inner['strokeWidth'],2)
        self.assertEqual(inner['fill'][3],0)
        self.assertEqual(inner['opacity'],.75)
        self.assertEqual(inner['purpose'],'内描边')
    def test_blurred_or_offset_inset_stops(self):
        for s in ['rgb(0, 78, 179) 0px 1px 4px 2px inset','rgb(0, 78, 179) 1px 0px 0px 2px inset']:
            with self.subTest(s=s),self.assertRaisesRegex(ValueError,'inset shadow geometry'):
                parse_shadow(s)
    def test_transparent_casting_fill_stops(self):
        with self.assertRaisesRegex(ValueError,'opaque'):split_shadow(dict(bounds=[0,0,10,10],radii=[0]*4,fill=[0,0,0,.5],opacity=1,shadow='rgb(0,0,0) 0px 0px 0px 1px'))
    def test_independent_original_image_corners(self):
        mask=rounded_mask((100,60),[0,0,100,60],'0px 38px 0px 0px',1)
        self.assertEqual(mask.getpixel((0,0)),255)
        self.assertEqual(mask.getpixel((99,0)),0)
        self.assertEqual(mask.getpixel((99,59)),255)
        self.assertEqual(mask.getpixel((50,30)),255)
        with self.assertRaises(UnsupportedImagePaint):rounded_mask((100,60),[0,0,100,60],'10px / 5px',1)
if __name__=='__main__':unittest.main()
