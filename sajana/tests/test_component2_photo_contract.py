import unittest

from sajana.src.component2_photo_contract import photo_assessment, quality_checks


class PhotoContractTests(unittest.TestCase):
    def test_empty_detections_never_claim_a_clear_trail(self):
        result = photo_assessment([])
        self.assertEqual(result['garbage_observation'], 'not_detected')
        self.assertEqual(result['trail_condition'], 'not_assessed')
        self.assertFalse(result['model_quality_accepted'])

    def test_object_presence_does_not_establish_blockage_or_a_detour(self):
        result = photo_assessment([dict(task='obstacle', label='rock_region', confidence=.9,
                                        box_xyxy_normalized=[.1, .2, .3, .4])])
        self.assertEqual(result['rock_log_observation'], 'detected')
        self.assertEqual(result['trail_condition'], 'not_assessed')
        self.assertEqual(result['route_advisory'], 'requires_map_and_reviewed_obstruction')

    def test_label_ids_from_different_tasks_cannot_be_confused(self):
        with self.assertRaises(ValueError):
            photo_assessment([dict(task='litter', label='rock_region', confidence=.9,
                                   box_xyxy_normalized=[.1, .2, .3, .4])])

    def test_invalid_prediction_data_is_rejected(self):
        for score, box in [(float('nan'), [.1, .2, .3, .4]), (.9, [.3, .2, .1, .4]),
                           (.9, [-.1, .2, .3, .4]), (1.1, [.1, .2, .3, .4])]:
            with self.subTest(score=score, box=box), self.assertRaises(ValueError):
                photo_assessment([dict(task='litter', label='litter', confidence=score,
                                       box_xyxy_normalized=box)])

    def test_good_average_scores_cannot_hide_an_unsupported_class(self):
        models={'litter':{'per_class':[
            dict(class_name='litter', precision_at_threshold=.99, recall_at_threshold=.99, labelled_images=30)]},
            'obstacle':{'per_class':[
            dict(class_name='log_region', precision_at_threshold=.99, recall_at_threshold=.99, labelled_images=30),
            dict(class_name='rock_region', precision_at_threshold=.99, recall_at_threshold=.1, labelled_images=3)]}}
        result=quality_checks(models,dict(per_class_precision=.8,per_class_recall=.7,
                                          minimum_validation_images_per_class=20))
        self.assertFalse(result['public_validation_quality_passed'])
        self.assertEqual(len(result['failures']),2)
        self.assertFalse(result['full_component_ready'])

    def test_absent_models_cannot_pass_quality_checks(self):
        result=quality_checks({},dict(per_class_precision=.8,per_class_recall=.7,
                                      minimum_validation_images_per_class=20))
        self.assertFalse(result['public_validation_quality_passed'])


if __name__ == '__main__':
    unittest.main()
