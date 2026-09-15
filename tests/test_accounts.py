import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from weatherlab.accounts import AccountLink, private_get, sign, NoRedirect


class AccountTests(unittest.TestCase):
    def test_rfc8032_vector(self):
        seed = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
        expected = ('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f'
                    'b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
        self.assertEqual(base64.b64decode(sign(base64.b64encode(seed).decode(), '')).hex(), expected)

    def test_disallowed_endpoint_never_signs(self):
        with patch('weatherlab.accounts.sign') as signer:
            with self.assertRaises(ValueError):
                private_get({}, '/v1/orders')
            signer.assert_not_called()

    def test_redirect_never_forwards_auth(self):
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.org')

    def test_link_cache_and_disconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = AccountLink(tmp)
            responses = [{'balances': [{'currency': 'USD', 'buyingPower': 12, 'currentBalance': 13}]},
                         {'positions': {'some-contract': {}}, 'eof': False, 'nextCursor': 'next'}]
            with patch.object(link, 'credentials', return_value={'key_id': 'private-id', 'secret': 'private-value'}), \
                 patch('weatherlab.accounts.private_get', side_effect=responses) as get:
                result = link.refresh()
                self.assertEqual(result['status'], 'connected')
                self.assertEqual(result['positions_count'], 1)
                self.assertFalse(result['positions_complete'])
                for _ in range(10): link.state()
                self.assertEqual(get.call_count, 2)
            self.assertEqual(json.loads(link.config.read_text()), {'linked': True})
            self.assertNotIn('private-', json.dumps(result))
            self.assertEqual(AccountLink(tmp).state()['status'], 'unverified')
            marker = Path(tmp)/'saved.dpapi'
            marker.write_bytes(b'unchanged')
            link.disconnect()
            self.assertEqual(marker.read_bytes(), b'unchanged')
            self.assertFalse(link.config.exists())

    def test_errors_hide_provider_body_and_old_balance(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = AccountLink(tmp)
            link.snapshot['current_balance'] = 42
            with patch.object(link, 'credentials', side_effect=RuntimeError('secret-private-value')):
                result = link.refresh()
            self.assertEqual(result['status'], 'error')
            self.assertNotIn('secret-private-value', json.dumps(result))
            self.assertNotIn('current_balance', result)

    def test_invalid_balance_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = AccountLink(tmp)
            with patch.object(link, 'credentials', return_value={}), \
                 patch('weatherlab.accounts.private_get', return_value={'balances': [
                     {'currency': 'USD', 'buyingPower': float('nan')}]}):
                self.assertEqual(link.refresh()['status'], 'error')
            self.assertFalse(link.config.exists())
