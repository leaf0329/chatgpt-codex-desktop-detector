import json
import tempfile
import unittest
from pathlib import Path
from detector import inspect


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / 'sessions').mkdir()
        (self.home / 'config.toml').write_text('model="target"', encoding='utf-8')
        self.file = self.home / 'sessions' / 'task.jsonl'

    def write(self, records):
        self.file.write_text(''.join(json.dumps(r)+'\n' for r in records), encoding='utf-8')

    def test_latest_model_and_no_prompt_leak(self):
        self.write([{'type':'turn_context','payload':{'model':'old'}},
                    {'type':'turn_context','payload':{'model':'target','effort':'medium'}},
                    {'type':'event_msg','payload':{'type':'user_message','message':'error secret'}},
                    {'type':'event_msg','payload':{'type':'error','message':'private-token'}}])
        result = inspect('task.jsonl', home=self.home)
        self.assertEqual(result['status'], 'match')
        self.assertEqual(result['historical_differences'], 1)
        self.assertEqual(result['event_count'], 1)
        self.assertNotIn('private-token', json.dumps(result))

    def test_missing_and_malformed_are_unknown(self):
        self.write([{'type':'turn_context','payload':{}}])
        self.assertEqual(inspect('task.jsonl', home=self.home)['status'], 'unknown')
        self.write([{'type':'turn_context','payload':{'model':'target'}}])
        with self.file.open('a') as f:
            f.write('{')
        self.assertEqual(inspect('task.jsonl', home=self.home)['status'], 'unknown')

    def test_mismatch_and_path_escape(self):
        self.write([{'type':'turn_context','payload':{'model':'other'}}])
        self.assertEqual(inspect('task.jsonl', home=self.home)['status'], 'different')
        with self.assertRaises(ValueError):
            inspect('../config.toml', home=self.home)


if __name__ == '__main__':
    unittest.main()
