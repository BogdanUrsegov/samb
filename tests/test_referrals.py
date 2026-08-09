import unittest

from bot.utils.referrals import (
    referral_code_from_payload,
    referral_payload,
    normalize_referral_code,
)


class ReferralHelpersTest(unittest.TestCase):
    def test_valid_code_is_normalized(self):
        self.assertEqual(normalize_referral_code(" summer_2026 "), "summer_2026")
        self.assertEqual(normalize_referral_code("ref_summer_2026"), "summer_2026")

    def test_payload_round_trip(self):
        payload = referral_payload("summer_2026")
        self.assertEqual(payload, "ref_summer_2026")
        self.assertEqual(referral_code_from_payload(payload), "summer_2026")

    def test_non_referral_payload_is_ignored(self):
        self.assertIsNone(referral_code_from_payload("AbCd1234"))
        self.assertIsNone(referral_code_from_payload("start_123"))

    def test_invalid_codes_are_rejected(self):
        self.assertIsNone(normalize_referral_code(""))
        self.assertIsNone(normalize_referral_code("bad code"))
        self.assertIsNone(normalize_referral_code("bad-code"))
        self.assertIsNone(normalize_referral_code("русский"))
        self.assertIsNone(normalize_referral_code("a" * 61))

    def test_only_letters_digits_and_underscore_are_allowed(self):
        self.assertEqual(normalize_referral_code("abc_123XYZ"), "abc_123XYZ")
        self.assertIsNone(normalize_referral_code("abc-123"))
        self.assertIsNone(normalize_referral_code("abc.123"))
        self.assertIsNone(normalize_referral_code("abc/123"))


if __name__ == "__main__":
    unittest.main()
