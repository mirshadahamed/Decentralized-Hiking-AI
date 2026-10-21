"""Complete detection validation, preserving the pinned YOLO output contract."""
from copy import copy

from ultralytics.models.yolo.detect.train import DetectionTrainer
from ultralytics.models.yolo.detect.val import DetectionValidator

from .yolov8_validation import complete_nms


class CompleteDetectionValidator(DetectionValidator):
    def init_metrics(self, model):
        super().init_metrics(model)
        self.complete_nms_images = 0

    def postprocess(self, predictions):
        outputs = complete_nms(predictions, self.args.conf, self.args.iou,
                               nc=0 if self.args.task == 'detect' else self.nc,
                               multi_label=True,
                               agnostic=self.args.single_cls or self.args.agnostic_nms,
                               max_det=self.args.max_det, end2end=self.end2end,
                               rotated=self.args.task == 'obb')
        self.complete_nms_images = getattr(self, 'complete_nms_images', 0) + len(outputs)
        return [{'bboxes': out[:, :4], 'conf': out[:, 4], 'cls': out[:, 5], 'extra': out[:, 6:]}
                for out in outputs]


class CompleteDetectionTrainer(DetectionTrainer):
    def get_validator(self):
        return CompleteDetectionValidator(self.test_loader, save_dir=self.save_dir,
                                          args=copy(self.args), _callbacks=self.callbacks)
