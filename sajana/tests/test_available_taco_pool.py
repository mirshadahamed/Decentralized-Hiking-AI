import json,tempfile,unittest
from pathlib import Path
from PIL import Image
from sajana.src.data.preprocess_taco import preprocess
from sajana.src.data.prepare_available_taco_pool import prepare
class AvailablePoolTests(unittest.TestCase):
    def test_whole_missing_duplicate_and_holdout_examples_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.json';dataset=root/'expected';benchmark=root/'benchmark';out=root/'available';derived=root/'derived.json'
            data={'categories':[{'id':0,'name':'litter'}],'images':[],'annotations':[]}
            for i in range(5):
                data['images'].append({'id':i,'file_name':f'unofficial/{i}.jpg','width':32,'height':32})
                data['annotations'].append({'id':i,'image_id':i,'category_id':0,'segmentation':[[2,2,20,2,20,20,2,20]]})
            source.write_text(json.dumps(data));original=source.read_bytes();preprocess(source,dataset,split_policy='train_only')
            for i,color in [(0,'red'),(1,'red'),(2,'blue'),(3,'green')]:Image.new('RGB',(32,32),color).save(dataset/'images/train'/f'unofficial__{i}.jpg')
            (benchmark/'images/val').mkdir(parents=True)
            (benchmark/'images/val/heldout.jpg').write_bytes((dataset/'images/train/unofficial__2.jpg').read_bytes())
            r=prepare(source,dataset,out,derived,benchmark)
            self.assertTrue(r['training_pool_ready']);self.assertFalse(r['training_ready']);self.assertFalse(r['canonical_source_complete'])
            self.assertEqual(r['exclusion_reason_counts'],{'missing_or_invalid_photo':1,'exact_pixels_in_official_holdout':1,'exact_duplicate_in_auxiliary_pool':1})
            self.assertEqual([im['id'] for im in json.loads(derived.read_text())['images']],[0,3]);self.assertEqual(source.read_bytes(),original)
if __name__=='__main__':unittest.main()
