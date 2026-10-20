import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from serve_research_model import poll_backend_error


class ServerFailureGuardTests(unittest.TestCase):
    def scan(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'server.log'
            path.write_text(content)
            return poll_backend_error(path)[0]

    def test_metal_out_of_memory_before_health_ready(self):
        self.assertIsNotNone(self.scan('error: Insufficient Memory (00000008:kIOGPUCommandBufferCallbackErrorOutOfMemory)\nserver ready\n'))

    def test_poisoned_backend(self):
        self.assertIsNotNone(self.scan('backend is in error state from a previous command buffer failure - recreate the backend to recover\n'))

    def test_nonfatal_fit_warning(self):
        self.assertIsNone(self.scan('common_fit_params: failed to fit params to free device memory: n_gpu_layers already set by user to 999, abort\n'))

    def test_split_log_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'server.log'
            path.write_text('error: kIOGPUCommandBufferCallbackError')
            failure, offset, carry = poll_backend_error(path)
            self.assertIsNone(failure)
            with path.open('a') as output:
                output.write('OutOfMemory\n')
            failure, _, _ = poll_backend_error(path, offset, carry)
            self.assertIsNotNone(failure)


if __name__ == '__main__':
    unittest.main()
