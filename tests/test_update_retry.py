import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
import importlib.util
spec = importlib.util.spec_from_file_location('update_retry', Path(__file__).resolve().parents[1] / 'src/core/update_retry.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
retry_network = module.retry_network

class RetryTests(unittest.TestCase):
    def test_recovers_from_gateway_timeout(self):
        op=Mock(side_effect=[HTTPError('https://example.com',504,'Gateway timeout',{},None),'ok'])
        sleep=Mock(); progress=Mock()
        self.assertEqual(retry_network(op,progress,sleep),'ok')
        self.assertEqual(op.call_count,2)
        sleep.assert_called_once_with(2)
    def test_bounded_failure(self):
        op=Mock(side_effect=TimeoutError('timed out'))
        with self.assertRaises(RuntimeError): retry_network(op,Mock(),Mock())
        self.assertEqual(op.call_count,3)
    def test_does_not_retry_integrity_or_http_client_errors(self):
        for error in [ValueError('hash mismatch'),HTTPError('https://example.com',404,'not found',{},None)]:
            op=Mock(side_effect=error)
            with self.assertRaises(type(error)): retry_network(op,Mock(),Mock())
            self.assertEqual(op.call_count,1)
