import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sajana.src import prepare_compact_component2 as compact


class CompactBudgetTests(unittest.TestCase):
    def test_budget_includes_validation_and_test(self):
        cfg = json.loads(compact.CONFIG.read_text())
        cfg['obstacle']['counts']['test'] += 1
        cfg['total_image_limit'] += 1
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps(cfg))
            with patch.object(compact, 'CONFIG', path), self.assertRaises(ValueError):
                compact.configuration()

    def test_sample_is_order_independent_and_keeps_rock_log_overlap(self):
        rows = [dict(source_id=str(i), sequence='forest', flat_file_name=f'{i}.png',
                     rock_components=str(int(i < 5)), log_components=str(int(i < 15))) for i in range(20)]
        quotas = {'rock': 3, 'log_only': 4, 'background': 2}
        selected = compact.select_obstacles(rows, quotas, 42)
        self.assertEqual(selected, compact.select_obstacles(list(reversed(rows)), quotas, 42))
        self.assertEqual(len({r['source_id'] for r in selected}), 9)
        self.assertEqual(sum(compact.obstacle_stratum(r) == 'rock' for r in selected), 3)
        self.assertTrue(all(int(r['log_components']) for r in selected if compact.obstacle_stratum(r) == 'rock'))
        self.assertEqual(sum(compact.obstacle_stratum(r) == 'background' for r in selected), 2)

    def test_missing_class_coverage_cannot_be_silently_replaced(self):
        row = dict(source_id='1', sequence='forest', flat_file_name='1.png',
                   rock_components='0', log_components='1')
        with self.assertRaises(ValueError):
            compact.select_obstacles([row], {'rock': 1}, 42)


if __name__ == '__main__':
    unittest.main()
