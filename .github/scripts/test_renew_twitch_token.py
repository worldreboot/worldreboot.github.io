import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import renew_twitch_token as renewal


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "code"
        self.path.write_text("Bearer oldtoken", encoding="utf-8")
        env = patch.dict(os.environ, {
            "TWITCH_CLIENT_ID": "testclient", "TWITCH_CLIENT_SECRET": "testsecret",
            "GITHUB_ACTIONS": "false",
        })
        env.start()
        self.addCleanup(env.stop)
        self.stdout = io.StringIO()
        output = contextlib.redirect_stdout(self.stdout)
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def metadata(self, expires_in=864000):
        return {"client_id": "testclient", "expires_in": expires_in}

    def test_healthy_token_does_not_request_replacement(self):
        with patch.object(renewal, "request_json", return_value=self.metadata()) as api:
            self.assertFalse(renewal.renew(self.path))
        api.assert_called_once()
        self.assertEqual(self.path.read_text(), "Bearer oldtoken")

    def test_expired_and_near_expiry_tokens_are_replaced_after_validation(self):
        for current in (None, self.metadata(604800)):
            with self.subTest(current=current), patch.object(renewal, "request_json", side_effect=[
                current, {"access_token": "newtoken", "token_type": "bearer"}, self.metadata(),
            ]) as api:
                self.assertTrue(renewal.renew(self.path))
                self.assertEqual(self.path.read_bytes(), b"Bearer newtoken")
                self.assertIn(b"grant_type=client_credentials", api.call_args_list[1].args[0].data)
        self.assertNotIn("newtoken", self.stdout.getvalue())
        self.assertNotIn("testsecret", self.stdout.getvalue())

    def test_force_renews_a_healthy_token(self):
        with patch.object(renewal, "request_json", side_effect=[
            self.metadata(), {"access_token": "newtoken", "token_type": "bearer"}, self.metadata(),
        ]):
            self.assertTrue(renewal.renew(self.path, force=True))

    def test_bad_response_or_failed_validation_preserves_existing_token(self):
        for response, validation in (({}, None), ({"access_token": "newtoken", "token_type": "bearer"}, None)):
            with self.subTest(response=response), patch.object(renewal, "request_json", side_effect=[
                None, response, validation,
            ]):
                with self.assertRaises(RuntimeError):
                    renewal.renew(self.path)
                self.assertEqual(self.path.read_text(), "Bearer oldtoken")

    def test_user_or_different_app_token_is_not_replaced(self):
        for extra in ({"user_id": "123"}, {"client_id": "otherapp"}):
            with self.subTest(extra=extra), patch.object(renewal, "request_json", return_value=self.metadata() | extra):
                with self.assertRaises(RuntimeError):
                    renewal.renew(self.path)
                self.assertEqual(self.path.read_text(), "Bearer oldtoken")

    def test_http_errors_only_treat_401_as_expiry(self):
        for status in (401, 429, 500):
            with self.subTest(status=status), patch.object(renewal.request, "urlopen", side_effect=HTTPError(
                "https://id.twitch.tv/oauth2/validate", status, "error", {}, None,
            )):
                if status == 401:
                    self.assertIsNone(renewal.validate("oldtoken"))
                else:
                    with self.assertRaises(RuntimeError):
                        renewal.validate("oldtoken")


if __name__ == "__main__":
    unittest.main()
