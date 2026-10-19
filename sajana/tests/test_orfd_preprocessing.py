import csv,json,tempfile,unittest,zipfile,shutil,io
from pathlib import Path
from PIL import Image
from sajana.src.data.preprocess_orfd_rgb import preprocess,verify,binary_mask,refresh_component_status
from sajana.src.data.download_orfd_rgb import selected
from sajana.src.data.extract_orfd_partial import extract
class OrfdTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.raw=self.root/'raw';self.out=self.root/'out'
        for i,split in enumerate(('training','validation','testing')):
            p=self.raw/split/'image_data';g=self.raw/split/'gt_image';p.mkdir(parents=True);g.mkdir()
            Image.new('RGB',(12,8),((i+1)*50,20,10)).save(p/'100.png')
            im=Image.new('RGB',(12,8),(255,0,0));im.putpixel((3,4),(0,0,201));im.putpixel((4,4),(0,0,200));im.save(g/'100_fillcolor.png')
    def test_blue_threshold_and_class_ids(self):
        mask,palette=binary_mask(self.raw/'training/gt_image/100_fillcolor.png',(12,8))
        self.assertEqual(mask.getpixel((3,4)),1);self.assertEqual(mask.getpixel((4,4)),0);self.assertEqual(mask.histogram()[1],1)
    def test_complete_source_checked_and_tampering_fails(self):
        preprocess(self.raw,self.out);r=verify(self.raw,self.out);self.assertTrue(r['training_ready']);self.assertFalse(r['published_count_complete']);self.assertFalse(r['source_sequence_metadata_available'])
        Image.new('L',(12,8),0).save(self.out/'masks/train/100.png')
        self.assertFalse(verify(self.raw,self.out)['passed'])
    def test_missing_source_refuses_conversion(self):
        (self.raw/'training/gt_image/100_fillcolor.png').unlink()
        with self.assertRaises(ValueError):preprocess(self.raw,self.out)
        self.assertFalse((self.out/'manifests/train.csv').exists())
    def test_mismatched_gt_is_not_silently_resized(self):
        Image.new('RGB',(10,8),'blue').save(self.raw/'training/gt_image/100_fillcolor.png')
        self.assertFalse(preprocess(self.raw,self.out)['preprocessed']);self.assertFalse(verify(self.raw,self.out)['training_ready'])
    def test_duplicate_pixels_across_splits_fail(self):
        (self.raw/'validation/image_data/100.png').write_bytes((self.raw/'training/image_data/100.png').read_bytes())
        preprocess(self.raw,self.out);self.assertFalse(verify(self.raw,self.out)['passed'])
    def test_manifest_omission_and_unexpected_files_fail(self):
        preprocess(self.raw,self.out)
        p=self.out/'manifests/train.csv';p.write_text(p.read_text().splitlines()[0]+'\n')
        self.assertFalse(verify(self.raw,self.out)['passed'])
    def test_empty_dataset_never_ready(self):
        empty=self.root/'empty';empty.mkdir()
        self.assertFalse(verify(empty,self.out)['training_ready'])
    def test_partial_source_keeps_available_test_but_never_certifies_benchmark(self):
        shutil.rmtree(self.raw/'validation')
        with self.assertRaises(ValueError):preprocess(self.raw,self.out)
        preprocess(self.raw,self.out,allow_incomplete=True)
        report=verify(self.raw,self.out,allow_incomplete=True)
        self.assertTrue(report['training_pool_ready']);self.assertFalse(report['training_ready'])
        self.assertEqual(report['splits']['test']['verified_pairs'],1)
        self.assertFalse(verify(self.raw,self.out)['passed'])
    def test_train_only_pool_excludes_source_holdouts(self):
        preprocess(self.raw,self.out,train_only=True)
        report=verify(self.raw,self.out,train_only=True)
        self.assertTrue(report['training_pool_ready']);self.assertFalse(report['training_ready'])
        self.assertEqual(report['splits']['test']['images'],0)
    def test_partial_status_preserves_litter_evidence_and_reports_pool_readiness(self):
        preprocess(self.raw,self.out,train_only=True)
        report=verify(self.raw,self.out,train_only=True)
        folder=self.root/'results/taco_preprocessing';folder.mkdir(parents=True)
        status=folder/'supplied_preprocessing_status.json';status.write_text(json.dumps({'official':{'training_ready':True}}))
        register=folder/'supplied_dataset_register.csv'
        register.write_text('dataset,training_ready,training_pool_ready,path\nofficial,True,False,taco\n')
        refresh_component_status(report,self.root)
        saved=json.loads(status.read_text())
        self.assertTrue(saved['official']['training_ready']);self.assertFalse(saved['orfd']['training_ready'])
        with register.open(newline='') as f:rows=list(csv.DictReader(f))
        self.assertEqual(rows[-1]['training_pool_ready'],'True')
    def test_download_selection_excludes_other_modalities_and_unsafe_paths(self):
        self.assertTrue(selected(zipfile.ZipInfo('Final_Dataset/training/image_data/1.png')))
        self.assertTrue(selected(zipfile.ZipInfo('Final_Dataset/testing/gt_image/1_fillcolor.png')))
        for name in ('Final_Dataset/training/dense_depth/1.png', '../training/image_data/1.png',
                     'Final_Dataset/../../image_data/1.png', 'Final_Dataset/training/image_data/run.py'):
            self.assertFalse(selected(zipfile.ZipInfo(name)))
    def test_partial_extraction_requires_both_complete_crc_valid_members(self):
        cache=self.root/'cache';cache.mkdir();out=self.root/'recovered'
        buffer=io.BytesIO();Image.new('RGB',(12,8),'white').save(buffer,format='PNG')
        archive=cache/'orfd_rgb_ranges.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('Final_Dataset/training/image_data/1.png',buffer.getvalue())
            z.writestr('Final_Dataset/training/gt_image/1_fillcolor.png',buffer.getvalue())
            z.writestr('Final_Dataset/training/image_data/orphan.png',buffer.getvalue())
            z.writestr('padding.txt',b'x'*100000)
        state=cache/'drive_completed_ranges.json'
        state.write_text(json.dumps({'completed':[f'0-{archive.stat().st_size-1}']}))
        report=extract(cache,out)
        self.assertEqual(report['available_pairs'],1);self.assertTrue(report['crc_checks_passed'])
        self.assertFalse((out/'ORFD/training/image_data/orphan.png').exists())
        state.write_text(json.dumps({'completed':['0-20']}))
        with self.assertRaises(ValueError):extract(cache,self.root/'incomplete')
if __name__=='__main__':unittest.main()
