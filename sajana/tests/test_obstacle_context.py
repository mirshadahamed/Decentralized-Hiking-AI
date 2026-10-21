import unittest
import numpy as np

from sajana.src.data.prepare_obstacle_context import region_boxes


class ObstacleContextTests(unittest.TestCase):
    def test_components_keep_correct_classes_and_tiny_positive_geometry(self):
        mask=np.full((10,20),2,dtype=np.uint8)
        mask[2:6,4:10]=14;mask[8,19]=14;mask[0:2,0:2]=15
        boxes,counts=region_boxes(mask)
        self.assertEqual(counts,{'rock_region':2,'log_region':1})
        self.assertEqual(len(boxes),3)
        self.assertIn((0,7/20,4/10,6/20,4/10),boxes)
        self.assertIn((0,19.5/20,8.5/10,1/20,1/10),boxes)
        self.assertIn((1,1/20,1/10,2/20,2/10),boxes)

    def test_known_other_context_is_negative_only_for_rock_and_log(self):
        boxes,counts=region_boxes(np.full((4,4),7,dtype=np.uint8))
        self.assertEqual(boxes,[]);self.assertEqual(counts,{})

    def test_void_or_unknown_classes_cannot_become_yolo_background(self):
        for value in (0,19,255):
            with self.assertRaises(ValueError): region_boxes(np.full((4,4),value,dtype=np.uint8))


if __name__ == '__main__':unittest.main()
