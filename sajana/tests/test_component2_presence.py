import unittest

from sajana.src.component2_presence import calibrate_presence, presence_counts


class PresenceTests(unittest.TestCase):
    def test_positive_only_photos_do_not_establish_false_positive_performance(self):
        rows=[dict(target_classes=[0], predicted_classes=[0], confidence=[.1])]
        result=calibrate_presence(rows,{0:'litter'},.4)['litter']
        self.assertEqual(result['threshold'],.4)
        self.assertEqual(result['recall_on_positive_images'],0)
        self.assertIsNone(result['false_positive_rate'])
        self.assertFalse(result['general_photo_accuracy_established'])

    def test_presence_counts_images_not_duplicate_boxes(self):
        rows=[dict(target_classes=[1,1,1],predicted_classes=[1,1],confidence=[.8,.7]),
              dict(target_classes=[],predicted_classes=[1],confidence=[.9])]
        result=presence_counts(rows,1,.5)
        self.assertEqual((result['tp'],result['fp']),(1,1))
        self.assertEqual(result['observed_precision'],.5)


if __name__=='__main__':unittest.main()
