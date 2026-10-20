import json,tempfile,unittest
from pathlib import Path
from sajana.src.data.audit_component2_datasets import catalog
class ComponentCatalogTests(unittest.TestCase):
    def test_missing_reports_never_certify_datasets_or_local_ground_truth(self):
        with tempfile.TemporaryDirectory() as t:
            r=catalog(Path(t));self.assertFalse(r['all_component_datasets_preprocessed']);self.assertFalse(r['litter_baseline_data_ready']);self.assertFalse(r['full_concurrent_model_data_ready'])
    def test_certificate_without_photos_and_labels_does_not_certify_current_data(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'data/processed/litter_taco_mju_aux/readiness.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'built':True,'training_ready':True,'splits':{'train':{'images':1}}}))
            r=catalog(root);self.assertFalse(r['litter_baseline_data_ready'])
    def test_pair_coverage_and_full_certificate_are_required_together(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ds=root/'data/processed/litter_taco_mju_aux';(ds/'images/train').mkdir(parents=True);(ds/'labels/train').mkdir(parents=True)
            (ds/'images/train/a.jpg').write_bytes(b'audited fixture');(ds/'labels/train/a.txt').write_text('source audited fixture')
            p=ds/'readiness.json';p.write_text(json.dumps({'built':True,'training_ready':True,'splits':{'train':{'images':1}}}))
            self.assertTrue(catalog(root)['litter_baseline_data_ready'])
            p.write_text(json.dumps({'passed':True,'labels_only':True,'training_ready':True,'splits':{'train':{'images':1}}}))
            self.assertFalse(catalog(root)['litter_baseline_data_ready'])
            self.assertFalse(catalog(root)['full_concurrent_model_data_ready'])
    def test_wildscenes_author_pair_counts_use_semantic_dataset_path(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ds=root/'data/processed/wildscenes_terrain_semantic'
            for kind in ('images','masks'):
                p=ds/kind/'train/a.png';p.parent.mkdir(parents=True);p.write_bytes(b'previously source-verified fixture')
            report=root/'results/wildscenes_preprocessing/local_readiness.json';report.parent.mkdir(parents=True)
            report.write_text(json.dumps({'passed':True,'training_ready':True,'splits':{'train':{'expected_pairs':1,'verified_pairs':1}}}))
            source=next(e for e in catalog(root)['datasets'] if e['key']=='wildscenes')
            self.assertTrue(source['available_data_ready']);self.assertTrue(source['source_release_complete'])
if __name__=='__main__':unittest.main()
