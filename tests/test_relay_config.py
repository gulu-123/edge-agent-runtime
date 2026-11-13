import copy
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from relay_config import camera_command, load_config, receiver_command


class RelayConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.example = json.loads((ROOT / 'config/relay.example.json').read_text())

    def load(self, config):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(config))
            return load_config(path)

    def test_example_and_bounded_camera_command(self):
        config = self.load(self.example)
        argv = shlex.split(camera_command(config['camera'], 300))
        self.assertEqual(argv[:2], ['timeout', '310'])
        self.assertIn('video/x-raw,framerate=5/1', argv)
        self.assertIn('device=/dev/video1', argv)

    def test_ssh_target_rejects_options_and_shell_fragments(self):
        for target in ('-oProxyCommand=anything', 'root@host;command', 'root@host\ncommand'):
            config = copy.deepcopy(self.example)
            config['board']['target'] = target
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.load(config)

    def test_camera_rejects_shell_paths_and_unbounded_values(self):
        for field, value in (('device', '/dev/video1;command'), ('fps', 0),
                             ('output_width', 961), ('jpeg_quality', 100)):
            config = copy.deepcopy(self.example)
            config['camera'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load(config)

    def test_receiver_quotes_project_path_as_one_argument(self):
        project = '/home/demo/a project;literal'
        run, command = receiver_command(project, 'sample', 300)
        argv = shlex.split(command)
        self.assertEqual(argv[1], project + '/scripts/run-live.sh')
        self.assertEqual(argv[3], run)


if __name__ == '__main__':
    unittest.main()
