from io import BytesIO
from unittest import TestCase
from unittest.mock import call, patch
from urllib.error import HTTPError

from scripts.team_pulse import GitHub


URL = "https://api.github.com/repos/Richbanker/team-lead-lab/issues"


@patch("scripts.team_pulse.sleep")
@patch("scripts.team_pulse.urlopen")
class GitHubRequestRetryTests(TestCase):
    def setUp(self):
        self.github = GitHub("Richbanker/team-lead-lab", "test-token")

    def http_error(self, status):
        error = HTTPError(URL, status, "Test response", {}, BytesIO())
        self.addCleanup(error.close)
        return error

    def test_get_can_succeed_on_third_attempt_and_preserves_pagination(self, open_url, wait):
        first = self.http_error(502)
        second = self.http_error(503)
        response = BytesIO(b'[{"number": 9}]')
        next_link = '<https://api.github.com/repositories/1/issues?page=2>; rel="next"'
        response.headers = {"Link": next_link}
        open_url.side_effect = [first, second, response]

        self.assertEqual(self.github.request(URL), ([{"number": 9}], next_link))
        self.assertEqual(open_url.call_count, 3)
        self.assertTrue(all(attempt.args[0].get_method() == "GET" for attempt in open_url.call_args_list))
        self.assertEqual(wait.call_args_list, [call(1), call(1)])
        self.assertTrue(first.fp.closed)
        self.assertTrue(second.fp.closed)

    def test_get_propagates_the_last_error_after_three_attempts(self, open_url, wait):
        errors = [self.http_error(504) for _ in range(3)]
        open_url.side_effect = errors

        with self.assertRaises(HTTPError) as raised:
            self.github.request(URL)

        self.assertIs(raised.exception, errors[-1])
        self.assertEqual(open_url.call_count, 3)
        self.assertEqual(wait.call_args_list, [call(1), call(1)])

    def test_access_errors_stop_without_a_retry(self, open_url, wait):
        for status in (401, 403):
            with self.subTest(status=status):
                open_url.reset_mock()
                error = self.http_error(status)
                open_url.side_effect = error
                with self.assertRaises(HTTPError) as raised:
                    self.github.request(URL)
                self.assertIs(raised.exception, error)
                open_url.assert_called_once()
                wait.assert_not_called()

    def test_post_and_patch_do_not_repeat_a_temporary_failure(self, open_url, wait):
        for method in ("POST", "PATCH"):
            with self.subTest(method=method):
                open_url.reset_mock()
                error = self.http_error(503)
                open_url.side_effect = error
                with self.assertRaises(HTTPError) as raised:
                    self.github.request(URL, method, {"body": "Сводка"})
                self.assertIs(raised.exception, error)
                open_url.assert_called_once()
                self.assertEqual(open_url.call_args.args[0].get_method(), method)
                wait.assert_not_called()
