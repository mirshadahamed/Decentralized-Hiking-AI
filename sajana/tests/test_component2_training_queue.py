import csv
import fcntl
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sajana.src.component2_training_data import configuration, data_yaml, label_count, smoke_data
from sajana.src.run_component2_training_queue import lock_free, predecessor_gate
from sajana.src import run_component2_training_queue as queue
from sajana.src.train_yolov8 import sha256
from sajana.src.train_component2_yolov8 import update_plan
from sajana.src.finalize_component2_training import choose_litter


class ComponentTrainingQueueTests(unittest.TestCase):
    def test_context_milestone_cannot_claim_obstruction_readiness_or_overwrite_L1(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'configs/component2_training_plan.json';path.parent.mkdir()
            baseline={'experiment_id':'L1','completed_epochs':100}
            path.write_text(json.dumps({'first_experiments':[baseline,{'experiment_id':'L2'}],
                'next_context_experiment':{'experiment_id':'O1','blockage_training_ready':False}}))
            with patch('sajana.src.train_component2_yolov8.ROOT',root):
                update_plan('O1',{'phase':'completed','batches_seen':4,'completed_epochs':50,'device':'mps','versions':{}})
            plan=json.loads(path.read_text())
            self.assertEqual(plan['first_experiments'][0],baseline)
            self.assertTrue(plan['next_context_experiment']['training_started'])
            self.assertFalse(plan['next_context_experiment']['blockage_training_ready'])
            self.assertIn('/O1/',plan['next_context_experiment']['runtime_status'])

    def test_supervisor_waits_for_L1_and_never_launches_a_second_job_after_failure(self):
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                root=Path(folder);project=root/'runs/component2_training';results=root/'results/component2_training'
                results.mkdir(parents=True);project.mkdir(parents=True)
                (root/'runs/yolov8_litter').mkdir(parents=True)
                (root/'configs').mkdir()
                policy=root/'configs/component2_model_selection.json';policy.write_text('{}')
                cfg=configuration();status=root/cfg['predecessor_status'];status.parent.mkdir(parents=True)
                status.write_text(json.dumps({'experiment':'L1','phase':'training','pid':123}))
                (project/'prepared.json').write_text(json.dumps({'configuration_sha256':sha256(queue.CONFIG),
                    'source_sha256':{},'selection_policy_sha256':sha256(policy)}))
                for key in cfg['job_order']:
                    p=project/'smoke'/key/'status.json';p.parent.mkdir(parents=True)
                    p.write_text(json.dumps({'phase':'completed','batches_seen':4}))
                launched=[]

                def finish_predecessor(_):
                    status.write_text(json.dumps({'experiment':'L1','phase':'completed','completed_epochs':100}))

                def child(command, **kwargs):
                    self.assertEqual(json.loads(status.read_text())['phase'],'completed')
                    key=command[command.index('--job')+1];launched.append(key)
                    p=project/'jobs'/key/'status.json';p.parent.mkdir(parents=True)
                    p.write_text(json.dumps({'job':key,'phase':'failed' if failure else 'completed','completed_epochs':50}))
                    return Mock(poll=Mock(return_value=1 if failure else 0))

                with patch.object(queue,'ROOT',root),patch.object(queue,'PROJECT',project), \
                     patch.object(queue,'RESULTS',results),patch.object(queue,'configuration',return_value=cfg), \
                     patch.object(queue,'alive',return_value=True),patch.object(queue,'lock_free',return_value=True), \
                     patch.object(queue.time,'sleep',side_effect=finish_predecessor), \
                     patch.object(queue.subprocess,'Popen',side_effect=child), \
                     patch('sajana.src.train_component2_yolov8.source_hashes',return_value={}), \
                     patch('sajana.src.finalize_component2_training.finalize') as finalize:
                    if failure:
                        with self.assertRaises(RuntimeError):queue.run_queue(interval=10)
                        self.assertEqual(launched,['L2']);finalize.assert_not_called()
                    else:
                        queue.run_queue(interval=10)
                        self.assertEqual(launched,['L2','O1']);finalize.assert_called_once_with('mps')
                saved=json.loads((results/'queue_status.json').read_text())
                self.assertFalse(saved['full_component_ready'])
                self.assertEqual(saved['phase'],'stopped' if failure else 'public_jobs_completed_local_data_missing')

    def test_compact_selection_cannot_hide_a_large_accuracy_or_recall_drop(self):
        policy={'prefer_416_when_mask_map_drop_at_most':0.02,'prefer_416_when_mask_recall_drop_at_most':0.03}
        baseline={'imgsz':640,'mask_map':0.5,'mask_recall':0.6}
        smaller={'imgsz':416,'mask_map':0.49,'mask_recall':0.59}
        self.assertEqual(choose_litter([baseline,smaller],policy),smaller)
        smaller['mask_recall']=0.5
        self.assertEqual(choose_litter([baseline,smaller],policy),baseline)
        smaller.update(mask_recall=0.6,mask_map=0.45)
        self.assertEqual(choose_litter([baseline,smaller],policy),baseline)
        with self.assertRaises(ValueError):choose_litter([{'imgsz':416,'mask_map':float('nan'),'mask_recall':0.5}],policy)

    def test_active_or_interrupted_predecessor_never_releases_dependent_training(self):
        self.assertEqual(predecessor_gate({'experiment':'L1','phase':'training'},True,False),'waiting_for_L1')
        self.assertEqual(predecessor_gate({'experiment':'L1','phase':'training'},False,True),'predecessor_recovery_required')
        self.assertEqual(predecessor_gate({'experiment':'L1','phase':'failed'},False,True),'predecessor_recovery_required')
        self.assertEqual(predecessor_gate({'experiment':'L1','phase':'completed'},False,False),'waiting_for_release')
        self.assertEqual(predecessor_gate({'experiment':'L1','phase':'completed'},False,True),'ready')
        self.assertEqual(predecessor_gate({'experiment':'O1','phase':'completed'},False,True),'wrong_predecessor')

    def test_kernel_lock_rejects_competing_training(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.training.lock'
            with path.open('a+') as stream:
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                self.assertFalse(lock_free(path))
            self.assertTrue(lock_free(path))

    def test_task_yaml_excludes_test_and_keeps_detection_class_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            path=data_yaml(Path(folder)/'data.yaml',folder,{'0':'rock_region','1':'log_region'})
            text=path.read_text()
            self.assertNotIn('test:',text)
            self.assertNotIn('litter',text)
            self.assertIn('1: "log_region"',text)

    def test_invalid_or_cross_task_labels_cannot_pass_preflight(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'label.txt'
            for text in ['0 nan 0.5 0.2 0.2','0 0.5 0.5 0 0.2','2 0.5 0.5 0.2 0.2','0 0.5 0.5 0.2']:
                path.write_text(text)
                with self.assertRaises(ValueError):label_count(path,'detect',{'0':'rock_region','1':'log_region'})
            path.write_text('0 0.5 0.5 0.2 0.2\n')
            self.assertEqual(label_count(path,'detect',{'0':'rock_region'}),1)
            with self.assertRaises(ValueError):label_count(path,'segment',{'0':'litter'})
            path.write_text('')
            self.assertEqual(label_count(path,'detect',{'0':'rock_region'}),0)

    def test_config_rejects_architecture_switch_and_memory_policy_regression(self):
        original=configuration()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'queue.json'
            for change in ['model','cache']:
                cfg=json.loads(json.dumps(original))
                if change=='model':cfg['jobs']['L2']['model']='yolo11n-seg.pt'
                else:cfg['training']['cache']=True
                path.write_text(json.dumps(cfg))
                with self.assertRaises(ValueError):configuration(path)

    def test_cpu_smoke_covers_classes_and_background_without_held_out_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);dataset=root/'data'
            (dataset/'manifests').mkdir(parents=True)
            (dataset/'images/train').mkdir(parents=True);(dataset/'labels/train').mkdir(parents=True)
            rows=[]
            for i in range(12):
                name=f'{i}.jpg';rows.append({'flat_file_name':name})
                (dataset/'images/train'/name).write_bytes(b'fixture: no inference in this test')
                (dataset/'labels/train'/f'{i}.txt').write_text('' if i==2 else f'{i%2} 0.5 0.5 0.2 0.2\n')
            with (dataset/'manifests/train.csv').open('w') as stream:
                writer=csv.DictWriter(stream,fieldnames=['flat_file_name']);writer.writeheader();writer.writerows(rows)
            job={'dataset':'data','names':{'0':'rock_region','1':'log_region'}}
            with patch('sajana.src.component2_training_data.ROOT',root):
                yaml,count=smoke_data(job,root/'smoke')
            self.assertEqual(count,8)
            self.assertIn('val: "images/train"',yaml.read_text())
            self.assertFalse(list((root/'smoke').rglob('test')))
            labels=[p.read_text() for p in (root/'smoke/labels/train').iterdir()]
            self.assertIn('',labels)
            self.assertEqual({text.split()[0] for text in labels if text},{'0','1'})


if __name__=='__main__':unittest.main()
