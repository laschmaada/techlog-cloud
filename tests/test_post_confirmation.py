"""Tests for the Cognito PostConfirmation trigger (src/post_confirmation.py).

The trigger must add confirmed self-registered users to the Mechanic
group, must never grant Certifying, and must ignore other triggers.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class FakeCognito:
    def __init__(self):
        self.calls = []

    def admin_add_user_to_group(self, **kwargs):
        self.calls.append(kwargs)


class PostConfirmationTests(unittest.TestCase):
    def setUp(self):
        import post_confirmation
        self.mod = post_confirmation
        self.fake = FakeCognito()
        self.mod._client = self.fake

    def tearDown(self):
        self.mod._client = None

    def event(self, source):
        return {"triggerSource": source, "userPoolId": "pool-1",
                "userName": "naledi@highveldair.co.za"}

    def test_confirm_signup_adds_mechanic(self):
        evt = self.event("PostConfirmation_ConfirmSignUp")
        out = self.mod.handler(evt)
        self.assertIs(out, evt)
        self.assertEqual(len(self.fake.calls), 1)
        call = self.fake.calls[0]
        self.assertEqual(call["GroupName"], "Mechanic")
        self.assertEqual(call["Username"], "naledi@highveldair.co.za")
        self.assertEqual(call["UserPoolId"], "pool-1")

    def test_never_grants_certifying(self):
        self.mod.handler(self.event("PostConfirmation_ConfirmSignUp"))
        self.assertNotIn("Certifying", [c["GroupName"] for c in self.fake.calls])

    def test_other_triggers_ignored(self):
        self.mod.handler(self.event("PostConfirmation_ConfirmForgotPassword"))
        self.assertEqual(self.fake.calls, [])


if __name__ == "__main__":
    unittest.main()
