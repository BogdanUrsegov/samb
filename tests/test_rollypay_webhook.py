import hashlib
import hmac
import unittest
from unittest.mock import patch

from bot.utils import payments


class RollyPayWebhookSignatureTests(unittest.TestCase):
    def test_accepts_valid_hmac_over_timestamp_and_raw_body(self):
        body = b'{"event_type":"payment.paid","payment_id":"pay_test"}'
        timestamp = "1791910000"
        secret = "test-signing-secret"
        signature = hmac.new(
            secret.encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()

        with patch.object(payments, "SIGNING_SECRET", secret):
            self.assertTrue(payments.verify_webhook_signature(body, timestamp, signature))

    def test_rejects_modified_body(self):
        body = b'{"event_type":"payment.paid","payment_id":"pay_test"}'
        timestamp = "1791910000"
        secret = "test-signing-secret"
        signature = hmac.new(
            secret.encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()

        with patch.object(payments, "SIGNING_SECRET", secret):
            self.assertFalse(
                payments.verify_webhook_signature(body + b" ", timestamp, signature)
            )

    def test_rejects_missing_secret_or_headers(self):
        with patch.object(payments, "SIGNING_SECRET", ""):
            self.assertFalse(payments.verify_webhook_signature(b"{}", "123", "sig"))
        with patch.object(payments, "SIGNING_SECRET", "secret"):
            self.assertFalse(payments.verify_webhook_signature(b"{}", "", "sig"))
            self.assertFalse(payments.verify_webhook_signature(b"{}", "123", ""))


if __name__ == "__main__":
    unittest.main()
