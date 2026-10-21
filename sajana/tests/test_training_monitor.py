import tempfile
import unittest
import hashlib
import json
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sajana.src.check_yolov8_training import ROOT, completed_rows, epoch_timing, inspect, save_report, watch_training


class TrainingMonitorTests(unittest.TestCase):
    def test_partial_epoch_write_does_not_inflate_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'results.csv'
            path.write_text('epoch,time,train/seg_loss\n1,100,2.5\n2,20')
            self.assertEqual(completed_rows(path), [{'epoch': 1.0, 'time': 100.0, 'train/seg_loss': 2.5}])

    def test_eta_uses_recent_differences_not_cumulative_times(self):
        times = [10, 30, 60, 100, 150, 210]
        rows = [{'epoch': i+1, 'time': t} for i, t in enumerate(times)]
        result = epoch_timing(rows, 10)
        self.assertEqual(result['recent_seconds_per_epoch_median'], 40)
        self.assertEqual(result['remaining_seconds_to_epoch_budget'], 160)
        self.assertEqual(result['remaining_seconds_observed_range'], [80, 240])
        self.assertFalse(result['early_stopping_finish_time_predictable'])

    def test_invalid_or_finished_timings_never_create_negative_eta(self):
        self.assertIsNone(epoch_timing([], 100))
        self.assertIsNone(epoch_timing([{'epoch': 1, 'time': float('nan')}], 100))
        self.assertIsNone(epoch_timing([{'epoch': 1, 'time': 30}, {'epoch': 2, 'time': 20}], 100))
        self.assertEqual(epoch_timing([{'epoch': 2, 'time': 100}], 2)['remaining_seconds_to_epoch_budget'], 0)

    def test_resume_eta_uses_new_elapsed_timer_only(self):
        rows=[{'epoch':1,'time':300},{'epoch':22,'time':8000},
              {'epoch':23,'time':200},{'epoch':24,'time':450}]
        result=epoch_timing(rows,100,resumed_after=22)
        self.assertEqual(result['recent_seconds_per_epoch_median'],225)
        self.assertEqual(result['remaining_seconds_to_epoch_budget'],17100)
        self.assertIsNone(epoch_timing(rows[:2],100,resumed_after=22))

    def test_missing_checkpoints_or_stale_heartbeat_cannot_claim_healthy_training(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'fit/weights').mkdir(parents=True)
            now = datetime.now(ZoneInfo('Asia/Colombo'))
            state = {'run_directory': str(root), 'updated_at': (now-timedelta(hours=1)).isoformat(),
                     'phase': 'training', 'planned_epochs': 100, 'full_run_started': True,
                     'last_training_loss': 3.0, 'target_classes': {'0': 'litter'}}
            (root/'status.json').write_text(json.dumps(state))
            (root/'data.yaml').write_text('train: images/train\nval: images/val\n')
            digest = hashlib.sha256((ROOT/'src/train_yolov8.py').read_bytes()).hexdigest()
            (root/'run_manifest.json').write_text(json.dumps({'test_split_loaded': False, 'trainer_source_sha256': digest}))
            keys = ['train/seg_loss', 'train/cls_loss', 'val/seg_loss', 'metrics/mAP50(M)',
                    'metrics/mAP50-95(M)', 'metrics/precision(M)', 'metrics/recall(M)']
            (root/'fit/results.csv').write_text('epoch,time,'+','.join(keys)+'\n1,100,'+','.join(['0.4']*len(keys))+'\n')
            report, _ = inspect(root/'status.json', now)
            self.assertFalse(report['training_functioning_at_check'])
            self.assertTrue(any('heartbeat' in issue for issue in report['issues']))
            self.assertTrue(any('checkpoint' in issue for issue in report['issues']))
            state['updated_at'] = now.isoformat(); (root/'status.json').write_text(json.dumps(state))
            for name in ('best', 'last'): (root/'fit/weights'/f'{name}.pt').write_bytes(b'fixture')
            report, _ = inspect(root/'status.json', now)
            self.assertTrue(report['training_functioning_at_check'])
            self.assertFalse(report['app_model_ready'])
            self.assertIn('estimated_full_budget_finish', report)
            # A fresh heartbeat must not hide a trainer lost during a reboot.
            state['pid'] = 12345
            (root/'status.json').write_text(json.dumps(state))
            with patch('sajana.src.check_yolov8_training.os.kill', side_effect=ProcessLookupError):
                report, _ = inspect(root/'status.json', now)
            self.assertFalse(report['training_functioning_at_check'])
            self.assertFalse(report['training_process_alive'])
            self.assertNotIn('estimated_full_budget_finish', report)
            state.pop('pid'); (root/'status.json').write_text(json.dumps(state))
            (root/'console.log').write_text('WARNING NMS time limit 2.400s exceeded\n')
            report, _ = inspect(root/'status.json', now)
            self.assertFalse(report['training_functioning_at_check'])
            self.assertEqual(report['validation_timeout_warning_count'],1)
            self.assertTrue(any('timeout' in issue for issue in report['issues']))
            (root/'console.log').unlink()
            # A numerical failure must still produce a valid, explicitly failed JSON report.
            (root/'fit/results.csv').write_text('epoch,time,'+','.join(keys)+'\n1,100,'+','.join(['nan']*len(keys))+'\n')
            report, _ = inspect(root/'status.json', now)
            self.assertFalse(report['training_functioning_at_check'])
            save_report(report, root/'report')
            saved = json.loads((root/'report/health_report.json').read_text())
            self.assertIsNone(saved['validation_trend']['metrics/recall(M)']['latest'])

    def test_watch_refreshes_after_pause_then_stops_on_completion(self):
        common = {'checked_at': 'fixture', 'completed_epochs': 57, 'timing': None, 'app_model_ready': False}
        reports = [dict(common, phase='training', training_functioning_at_check=False, issues=['stale heartbeat']),
                   dict(common, phase='training', training_functioning_at_check=True, issues=[]),
                   dict(common, phase='completed', training_functioning_at_check=True, issues=[])]
        args = SimpleNamespace(status=Path('fixture.json'), output=Path('fixture'),
                               watch=True, plot=False, interval=60)
        with patch('sajana.src.check_yolov8_training.inspect', side_effect=[(r, []) for r in reports]), \
             patch('sajana.src.check_yolov8_training.save_report') as save, \
             patch('sajana.src.check_yolov8_training.time.sleep') as sleep, redirect_stdout(io.StringIO()):
            watch_training(args)
        self.assertEqual([call.args[0] for call in save.call_args_list], reports)
        self.assertEqual(sleep.call_count, 2)


if __name__ == '__main__':
    unittest.main()
