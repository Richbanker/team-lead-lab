from unittest import TestCase
from unittest.mock import call, patch

from scripts.team_pulse import GitHub


class GitHubIssuesPaginationTests(TestCase):
    def test_issues_cross_page_boundaries_and_exclude_pull_requests(self):
        github = GitHub("Richbanker/team-lead-lab", "test-token")
        first_url = f"{github.api}/issues?per_page=100&state=open"
        second_url = f"{github.api}/issues?per_page=100&state=open&page=2"
        first_issues = [{"number": number} for number in range(1, 100)]
        second_issues = [{"number": 101}, {"number": 103}]

        with patch.object(github, "request", side_effect=[
            (
                [*first_issues[:1], {"number": 100, "pull_request": {}}, *first_issues[1:]],
                f'<{second_url}>; rel="next", <{second_url}>; rel="last"',
            ),
            (
                [second_issues[0], {"number": 102, "pull_request": {}}, second_issues[1]],
                f'<{first_url}>; rel="prev", <{first_url}>; rel="first"',
            ),
        ]) as request:
            self.assertEqual(github.issues(state="open"), [*first_issues, *second_issues])

        self.assertEqual(request.call_args_list, [call(first_url), call(second_url)])
