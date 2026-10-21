import unittest

from sajana.src.assess_compact_models import check_test_identity
from sajana.src.finalize_compact_quality import choose_native, export_parity


class QualitySelectionTests(unittest.TestCase):
    def test_export_cannot_hide_one_collapsed_class_behind_another_class(self):
        original={'per_class':[dict(class_name=name,AP50_95=.5,recall_at_threshold=.8) for name in ('rock','log')]}
        changed={'per_class':[dict(class_name='rock',AP50_95=0,recall_at_threshold=0),
                              dict(class_name='log',AP50_95=1,recall_at_threshold=1)]}
        self.assertFalse(export_parity(original,changed)['passed'])

    def test_smaller_input_cannot_hide_large_recall_loss(self):
        large=dict(imgsz=640,AP50_95=.5,mean_recall_at_threshold=.8)
        small=dict(imgsz=416,AP50_95=.49,mean_recall_at_threshold=.5)
        self.assertEqual(choose_native([large,small]),large)

    def test_test_requires_the_exact_frozen_model_and_settings(self):
        selection={'validation_selection_complete':True,'test_used_to_select':False,
                   'models':{'litter':dict(checkpoint_sha256='frozen',imgsz=640,threshold=.4)}}
        check_test_identity(selection,'litter','frozen',640,.4)
        for digest,size,threshold in [('different',640,.4),('frozen',416,.4),('frozen',640,.2)]:
            with self.subTest(digest=digest,size=size,threshold=threshold),self.assertRaises(ValueError):
                check_test_identity(selection,'litter',digest,size,threshold)
        selection['test_used_to_select']=True
        with self.assertRaises(ValueError):check_test_identity(selection,'litter','frozen',640,.4)
