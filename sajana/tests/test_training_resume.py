"""Selection history must survive ordinary checkpoint recovery."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from sajana.src.resume_yolov8 import revalidate_checkpoint


class TrainingResumeTests(unittest.TestCase):
    def trainer(self):
        validator = Mock(return_value={'fitness': 0.6, 'metrics/mAP50(M)': 0.5})
        validator.complete_nms_images = 286
        return SimpleNamespace(validator=validator, metrics={}, fitness=None,
                               best_fitness=0.8, start_epoch=57,
                               stopper=SimpleNamespace(best_fitness=0.8, best_epoch=50, possible_stop=True),
                               save_model=Mock(return_value=True))

    def test_ordinary_resume_preserves_stronger_best_and_patience(self):
        trainer = self.trainer()
        revalidate_checkpoint(trainer, 286, reset_selection=False)
        self.assertEqual(trainer.fitness, 0.6)
        self.assertEqual(trainer.best_fitness, 0.8)
        self.assertEqual(vars(trainer.stopper), {'best_fitness': 0.8, 'best_epoch': 50, 'possible_stop': True})
        trainer.save_model.assert_not_called()

    def test_timeout_migration_establishes_complete_baseline(self):
        trainer = self.trainer()
        revalidate_checkpoint(trainer, 286, reset_selection=True)
        self.assertEqual(trainer.best_fitness, 0.6)
        self.assertEqual(vars(trainer.stopper), {'best_fitness': 0.6, 'best_epoch': 57, 'possible_stop': False})
        trainer.save_model.assert_called_once_with()

    def test_incomplete_validation_cannot_overwrite_selection(self):
        trainer = self.trainer()
        trainer.validator.complete_nms_images = 285
        with self.assertRaisesRegex(ValueError, 'Incomplete baseline validation'):
            revalidate_checkpoint(trainer, 286, reset_selection=True)
        self.assertEqual(trainer.best_fitness, 0.8)
        trainer.save_model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
