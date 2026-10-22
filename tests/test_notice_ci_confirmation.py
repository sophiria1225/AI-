import json
import unittest
from unittest.mock import patch

from probe_notice_calibration import confirmed_ci


class NoticeCIConfirmationTests(unittest.TestCase):
    def test_successful_run_with_pending_job_cannot_start_inference(self):
        jobs = {'jobs': [{'id': 3, 'name': 'accounting-and-syntax',
                          'status': 'in_progress', 'conclusion': None}]}
        with patch('probe_notice_calibration.check_ci', return_value=[{'id': 1}]), \
                patch('probe_notice_calibration.subprocess.check_output', return_value=json.dumps(jobs)):
            with self.assertRaisesRegex(ValueError, 'workflow and job'):
                confirmed_ci('head', [1, 2])

    def test_successful_job_id_is_bound_to_checked_run(self):
        jobs = {'jobs': [{'id': 3, 'name': 'accounting-and-syntax',
                          'status': 'completed', 'conclusion': 'success'}]}
        with patch('probe_notice_calibration.check_ci', return_value=[{'id': 1}]), \
                patch('probe_notice_calibration.subprocess.check_output', return_value=json.dumps(jobs)):
            self.assertEqual(confirmed_ci('head', [1, 2]), [{'id': 1, 'successful_job_id': 3}])
