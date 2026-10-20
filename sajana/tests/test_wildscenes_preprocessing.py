"""WildScenes checks: source class IDs, author splits, and verified acquisition."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from sajana.src.data.download_wildscenes import split_records, safe_relative, download_object, verified_object
from sajana.src.data.preprocess_wildscenes import preprocess, verify, preview


class WildScenesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.raw=self.root/'raw';self.dataset=self.root/'dataset'
        metadata=self.raw/'official_metadata'
        source=metadata/'wildscenes/mmseg_wildscenes/dataset/wildscenes.py';source.parent.mkdir(parents=True)
        source.write_text("class AuthorDataset:\n    METAINFO = {'classes': ('unlabelled','dirt','water'), 'palette': [(0,0,0),(255,0,0),(0,0,255)]}\n")
        for index,split in enumerate(('train','val','test'),1):
            sample=f'{index}-{index}'
            image=f'WildScenes2d/K-01/image/{sample}.png';label=image.replace('/image/','/indexLabel/')
            path=metadata/'data/splits/opt2d'/(split+'.csv');path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['id','im_path','label_path']);writer.writerow([sample,image,label])
            for relative in (image,label):(self.raw/'source'/relative).parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(12,8),(index*50,20,10)).save(self.raw/'source'/image)
            # Palette luminance differs from class IDs; P -> L conversion would be wrong.
            mask=Image.new('P',(12,8),1);mask.putpalette([0,0,0,255,0,0,0,0,255]+[0]*759)
            mask.putpixel((4,3),2);mask.save(self.raw/'source'/label)

    def test_preserves_palette_indices_and_author_split_identity(self):
        result=preprocess(self.raw,self.dataset)
        self.assertTrue(result['preprocessed']);self.assertFalse(result['training_ready'])
        mask=Image.open(self.dataset/'masks/train/K-01__1-1.png')
        self.assertEqual(mask.mode,'L');self.assertEqual(mask.getpixel((0,0)),1);self.assertEqual(mask.getpixel((4,3)),2)
        self.assertTrue(verify(self.raw,self.dataset)['training_ready'])
        self.assertTrue(preview(self.dataset,self.root/'overlays.jpg').is_file())

    def test_missing_source_cannot_certify_training_or_write_manifests(self):
        (self.raw/'source/WildScenes2d/K-01/indexLabel/1-1.png').unlink()
        result=preprocess(self.raw,self.dataset)
        self.assertFalse(result['training_ready']);self.assertFalse(result['preprocessed'])
        self.assertFalse((self.dataset/'manifests/train.csv').exists())
        self.assertFalse(verify(self.raw,self.dataset)['training_ready'])

    def test_unknown_ids_and_wrong_geometry_do_not_become_valid_masks(self):
        Image.new('L',(12,8),4).save(self.raw/'source/WildScenes2d/K-01/indexLabel/1-1.png')
        Image.new('L',(10,8),1).save(self.raw/'source/WildScenes2d/K-01/indexLabel/2-2.png')
        result=preprocess(self.raw,self.dataset)
        self.assertFalse(result['preprocessed']);self.assertEqual(len(result['issues']),2)
        self.assertFalse(verify(self.raw,self.dataset)['training_ready'])

    def test_mask_tampering_and_cross_split_duplicates_fail_verification(self):
        preprocess(self.raw,self.dataset)
        Image.new('L',(12,8),0).save(self.dataset/'masks/train/K-01__1-1.png')
        self.assertFalse(verify(self.raw,self.dataset)['passed'])
        (self.raw/'source/WildScenes2d/K-01/image/2-2.png').write_bytes((self.raw/'source/WildScenes2d/K-01/image/1-1.png').read_bytes())
        preprocess(self.raw,self.dataset)
        self.assertFalse(verify(self.raw,self.dataset)['training_ready'])

    def test_rejects_unsafe_paths_and_duplicate_author_ids(self):
        for name in ('../outside.png','/outside.png','WildScenes2d\\outside.png','WildScenes2d/a:b.png'):
            with self.assertRaises(ValueError):safe_relative(name)
        csv_path=self.raw/'official_metadata/data/splits/opt2d/val.csv'
        csv_path.write_text((self.raw/'official_metadata/data/splits/opt2d/train.csv').read_text())
        with self.assertRaisesRegex(ValueError,'Duplicate'):split_records(self.raw/'official_metadata')

    def test_manifest_omission_and_source_byte_changes_are_detected(self):
        preprocess(self.raw,self.dataset)
        path=self.dataset/'manifests/val.csv';path.write_text(path.read_text().splitlines()[0]+'\n')
        self.assertFalse(verify(self.raw,self.dataset)['passed'])
        preprocess(self.raw,self.dataset)
        (self.raw/'source/WildScenes2d/K-01/indexLabel/1-1.png').write_bytes(b'corrupt')
        self.assertFalse(verify(self.raw,self.dataset)['passed'])

    def test_object_resume_validates_byte_range_and_md5(self):
        content=b'abcdef';relative='WildScenes2d/K-01/image/1-1.png'
        row={'path':relative,'key':'collection/'+relative,'bytes':len(content),'etag':hashlib.md5(content).hexdigest()}
        target=self.root/'downloaded'/relative;target.parent.mkdir(parents=True);target.with_name(target.name+'.part').write_bytes(b'abc')
        response=Mock(status_code=206,headers={'Content-Range':'bytes 3-5/6'})
        response.iter_content.return_value=[b'def'];response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        info={'endPointUrl':'https://public.example','bucket':'dataset','accessKey':'public-key','secretAccessKey':'public-secret'}
        with patch('sajana.src.data.download_wildscenes.requests.get',return_value=response) as get:
            self.assertEqual(download_object(info,row,self.root/'downloaded'),'downloaded')
        self.assertEqual(get.call_args.kwargs['headers']['Range'],'bytes=3-')
        self.assertEqual(target.read_bytes(),content);self.assertTrue(verified_object(target,row))
        with patch('sajana.src.data.download_wildscenes.requests.get') as get:
            self.assertEqual(download_object(info,row,self.root/'downloaded'),'reused')
        get.assert_not_called()

    def test_checksum_failure_never_promotes_partial_file(self):
        relative='WildScenes2d/K-01/image/1-1.png';row={'path':relative,'key':relative,'bytes':3,'etag':hashlib.md5(b'abc').hexdigest()}
        response=Mock(status_code=200,headers={});response.iter_content.side_effect=lambda _:iter([b'bad'])
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        info={'endPointUrl':'https://public.example','bucket':'dataset','accessKey':'public-key','secretAccessKey':'public-secret'}
        with patch('sajana.src.data.download_wildscenes.requests.get',return_value=response),patch('sajana.src.data.download_wildscenes.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):download_object(info,row,self.root/'downloaded')
        self.assertFalse((self.root/'downloaded'/relative).exists())

if __name__=='__main__':unittest.main()
