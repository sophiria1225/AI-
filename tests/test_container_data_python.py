import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from container_data_python import inspect_controls


class ContainerControlsTests(unittest.TestCase):
    def setUp(self):
        self.selection = {'manifest_digest': 'sha256:manifest', 'config_digest': 'sha256:config',
                          'image': 'docker.io/library/python@sha256:manifest'}
        self.info = {'Image': 'sha256:manifest', 'Mounts': [],
                     'Config': {'Image': self.selection['image'], 'User': '65534:65534',
                                'Labels': {'harness.export-purpose': 'bounded-python-comparator'}},
                     'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True, 'Binds': [],
                                    'Privileged': False, 'CapDrop': ['ALL'],
                                    'SecurityOpt': ['no-new-privileges=true'], 'Memory': 268435456,
                                    'NanoCpus': 1000000000, 'PidsLimit': 64, 'LogConfig': {'Type': 'none'}}}

    def test_supported_no_new_privileges_serializations(self):
        for item in ('no-new-privileges', 'no-new-privileges:true', 'no-new-privileges=true'):
            self.info['HostConfig']['SecurityOpt'] = [item]
            self.assertTrue(all(inspect_controls(self.info, self.selection).values()))

    def test_rejects_false_privilege_flag(self):
        self.info['HostConfig']['SecurityOpt'] = ['no-new-privileges=false']
        with self.assertRaisesRegex(ValueError, 'no_new_privileges'):
            inspect_controls(self.info, self.selection)

    def test_rejects_reference_mount_or_network_relaxation(self):
        mutations = [('Config', 'Image', 'python:latest'), ('HostConfig', 'NetworkMode', 'bridge'),
                     ('HostConfig', 'Binds', ['/tmp:/tmp']), ('HostConfig', 'Privileged', True),
                     ('HostConfig', 'Memory', 0), ('HostConfig', 'PidsLimit', 0)]
        for section, key, value in mutations:
            changed = copy.deepcopy(self.info)
            changed[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                inspect_controls(changed, self.selection)

    def test_only_pinned_image_ids(self):
        self.info['Image'] = 'sha256:config'
        self.assertTrue(all(inspect_controls(self.info, self.selection).values()))
        self.info['Image'] = 'sha256:another'
        with self.assertRaisesRegex(ValueError, 'pinned_image_id'):
            inspect_controls(self.info, self.selection)


if __name__ == '__main__':
    unittest.main()
