"""Complete offline validation for pinned Ultralytics 8.4.183.

The upstream NMS wall-clock budget can break out before later images in a
batch are processed on a busy Mac. Validation must finish all images regardless
of speed. Confidence, IoU and detection-count thresholds remain unchanged.
"""
from copy import copy

from ultralytics.models.yolo.segment.train import SegmentationTrainer
from ultralytics.models.yolo.segment.val import SegmentationValidator
from ultralytics.utils import nms


def complete_nms(predictions, *args, **kwargs):
    kwargs['max_time_img'] = float('inf')
    return nms.non_max_suppression(predictions, *args, **kwargs)


class CompleteSegmentationValidator(SegmentationValidator):
    def init_metrics(self, model):
        super().init_metrics(model)
        self.complete_nms_images = 0

    def postprocess(self, predictions):
        # Preserve the pinned validator's prototype/mask handling and output
        # contract while removing only the inference-style wall-clock cutoff.
        proto = predictions[0][1] if isinstance(predictions[0], tuple) else predictions[1]
        outputs = complete_nms(predictions[0], self.args.conf, self.args.iou,
                               nc=self.nc, multi_label=True,
                               agnostic=self.args.single_cls or self.args.agnostic_nms,
                               max_det=self.args.max_det, end2end=self.end2end,
                               rotated=False)
        shape = [4*x for x in proto.shape[2:]]
        self.complete_nms_images = getattr(self, 'complete_nms_images', 0) + len(outputs)
        return [{'bboxes':out[:, :4], 'conf':out[:, 4], 'cls':out[:, 5],
                 'masks':self.process(proto[i], out[:, 6:], out[:, :4], shape=shape)}
                for i,out in enumerate(outputs)]


class CompleteSegmentationTrainer(SegmentationTrainer):
    def get_validator(self):
        return CompleteSegmentationValidator(self.test_loader, save_dir=self.save_dir,
                                              args=copy(self.args), _callbacks=self.callbacks)
