import itertools
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import torch
from ultralytics.utils import nms

from sajana.src.yolov8_validation import CompleteSegmentationValidator, complete_nms


class CompleteValidationTests(unittest.TestCase):
    def prediction(self):
        p=torch.zeros((3,5,1))
        p[:,0,0]=100;p[:,1,0]=100;p[:,2:4,0]=10;p[:,4,0]=0.9
        return p

    def test_busy_machine_clock_cannot_skip_later_images(self):
        clock=itertools.count(0,100)
        with patch('ultralytics.utils.nms.time.time',side_effect=lambda:next(clock)):
            baseline=nms.non_max_suppression(self.prediction(),conf_thres=0.1,nc=1)
        self.assertEqual([len(x) for x in baseline],[1,0,0])
        clock=itertools.count(0,100)
        with patch('ultralytics.utils.nms.time.time',side_effect=lambda:next(clock)):
            fixed=complete_nms(self.prediction(),conf_thres=0.1,nc=1)
        self.assertEqual([len(x) for x in fixed],[1,1,1])

    def test_normal_predictions_and_thresholds_are_preserved(self):
        expected=nms.non_max_suppression(self.prediction(),conf_thres=0.1,iou_thres=0.7,nc=1)
        actual=complete_nms(self.prediction(),conf_thres=0.1,iou_thres=0.7,nc=1)
        for a,b in zip(expected,actual):self.assertTrue(torch.equal(a,b))
        self.assertTrue(all(len(x)==0 for x in complete_nms(self.prediction(),conf_thres=0.99,nc=1)))

    def test_validator_preserves_all_mask_outputs_in_a_batch(self):
        validator=object.__new__(CompleteSegmentationValidator)
        validator.args=SimpleNamespace(conf=0.1,iou=0.7,single_cls=False,agnostic_nms=False,max_det=300)
        validator.nc=1;validator.end2end=False
        validator.process=lambda proto,coeff,boxes,shape:torch.zeros((len(boxes),*shape))
        pred=torch.cat([self.prediction(),torch.zeros((3,32,1))],dim=1)
        outputs=validator.postprocess((pred,torch.zeros((3,32,8,8))))
        self.assertEqual(validator.complete_nms_images,3)
        self.assertEqual([r['masks'].shape for r in outputs],[(1,32,32)]*3)
        self.assertTrue(all(set(r)=={'bboxes','conf','cls','masks'} for r in outputs))


if __name__=='__main__':unittest.main()
