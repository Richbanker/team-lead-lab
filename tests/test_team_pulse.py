from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import TestCase
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfoNotFoundError

from scripts.team_pulse import GitHub, main, markdown_text, render_report, task_status


def issue(number, *labels, assignees=(), **fields):
    return {
        "number": number,
        "title": f"Задача {number}",
        "labels": [{"name": label} for label in labels],
        "assignees": [{"login": login} for login in assignees],
        **fields,
    }


class ReportTests(TestCase):
    def test_blockers_take_precedence_when_labels_overlap(self):
        task = issue(1, "status:in-review", "status:blocked", assignees=("Richbanker",))
        self.assertEqual(task_status(task), "Блокеры")
        self.assertEqual(task_status(issue(2, assignees=("Richbanker",))), "Назначены")
        self.assertEqual(task_status(issue(3)), "Без исполнителя")
        self.assertEqual(task_status(issue(4, "status:ready")), "Готовы к запуску")

    def test_only_recent_completed_tasks_count_as_accepted(self):
        github = Mock(web="https://github.com/Richbanker/team-lead-lab")
        github.issues.side_effect = [
            [issue(1)],
            [issue(2, "status:in-review")],
            [
                issue(3, closed_at="2026-11-18T10:00:00Z", state_reason="completed"),
                issue(4, closed_at="2026-11-18T09:59:59Z", state_reason="completed"),
                issue(5, closed_at="2026-11-19T09:00:00Z", state_reason="not_planned"),
            ],
        ]
        github.pages.return_value = [{"number": 6, "title": "Проверка", "draft": True}]
        midday = datetime(2026, 11, 19, 13, tzinfo=timezone(timedelta(hours=3)))
        report = render_report(github, midday, "Обеденная сводка")
        self.assertIn("принято за 24 часа **1**", report)
        self.assertIn("### На ревью (1)", report)
        self.assertIn("/issues/3", report)
        self.assertIn("/pull/6) Проверка (черновик)", report)
        self.assertNotIn("/issues/4", report)
        self.assertNotIn("/issues/5", report)

    def test_title_formatting_neutralizes_markup_and_mentions(self):
        self.assertEqual(markdown_text("@someone\n**wow** <img>"), r"&#64;someone \*\*wow\*\* &lt;img&gt;")


class GitHubTests(TestCase):
    def setUp(self):
        self.github = GitHub("Richbanker/team-lead-lab", "test-token")
        self.github.request = Mock()

    def test_accepts_repository_id_pagination(self):
        next_page = "https://api.github.com/repositories/1/issues?page=2"
        self.github.request.side_effect = [([issue(1)], f'<{next_page}>; rel="next"'), ([issue(2)], "")]
        self.assertEqual([item["number"] for item in self.github.issues()], [1, 2])
        self.github.request.assert_called_with(next_page)

    def test_report_retry_updates_existing_bot_comment_only(self):
        marker = "<!-- team-pulse:2026-11-19:morning -->"
        day_start = "2026-11-18T21:00:00Z"
        self.github.pages = Mock(return_value=[
            {"id": 1, "user": {"login": "visitor"}, "body": f"{marker}\nVisitor text"},
            {"id": 2, "user": {"login": "github-actions[bot]"}, "body": f"{marker}\nOld report"},
        ])
        self.github.request.return_value = ({"html_url": "https://github.com/example#issuecomment-2"}, "")
        body = f"{marker}\nNew report"
        report_url = self.github.publish(1, marker, body, day_start)
        self.assertTrue(report_url.endswith("#issuecomment-2"))
        self.github.pages.assert_called_once_with("issues/1/comments", since=day_start)
        self.github.request.assert_called_once_with(f"{self.github.api}/issues/comments/2", "PATCH", {"body": body})


class ReportCommandTests(TestCase):
    def run_main(self, github, args, *, timezone_available=True):
        moscow = timezone(timedelta(hours=3))
        now = datetime(2026, 11, 20, 9, tzinfo=moscow)
        env = {"GITHUB_REPOSITORY": "Richbanker/team-lead-lab", "GITHUB_TOKEN": "test-token"}
        output = StringIO()
        with (
            patch.dict("os.environ", env, clear=True),
            patch("scripts.team_pulse.GitHub", return_value=github),
            patch("scripts.team_pulse.ZoneInfo", return_value=moscow) as zone,
            patch("scripts.team_pulse.datetime") as clock,
            redirect_stdout(output),
        ):
            if not timezone_available:
                zone.side_effect = ZoneInfoNotFoundError("Europe/Moscow")
            clock.now.side_effect = lambda tz: now.astimezone(tz)
            main(args)
            clock.now.assert_called_once_with(moscow)
        return output.getvalue()

    def test_preview_prints_markdown_without_reporting_issue_or_publication(self):
        github = Mock(web="https://github.com/Richbanker/team-lead-lab")
        github.issues.side_effect = [[], [issue(5, "team:task", "status:ready")], []]
        github.pages.return_value = []

        output = self.run_main(github, ["--preview"], timezone_available=False)

        self.assertTrue(output.startswith("<!-- team-pulse:2026-11-20:manual -->\n"))
        self.assertIn("## Сводка по запросу · 20.11.2026 09:00 МСК", output)
        self.assertIn("### Готовы к запуску (1)", output)
        self.assertIn("/issues/5", output)
        self.assertNotIn("team:overview", [call.kwargs["labels"] for call in github.issues.call_args_list])
        github.publish.assert_not_called()

    def test_default_publishes_the_same_markdown_as_preview(self):
        github = Mock(owner="richbanker", web="https://github.com/Richbanker/team-lead-lab")
        github.issues.side_effect = [[], [], []]
        github.pages.return_value = []
        preview = self.run_main(github, ["--preview"])
        github.issues.side_effect = [[issue(1, "team:overview", user={"login": "Richbanker"})], [], [], []]
        github.publish.return_value = "https://github.com/Richbanker/team-lead-lab/issues/1#issuecomment-1"

        output = self.run_main(github, [])

        github.publish.assert_called_once_with(
            1, "<!-- team-pulse:2026-11-20:manual -->", preview, "2026-11-19T21:00:00Z",
        )
        self.assertEqual(output, github.publish.return_value + "\n")
