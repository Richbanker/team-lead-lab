from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest import TestCase
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfoNotFoundError

from scripts.team_pulse import main


class ReportCommandTests(TestCase):
    def run_main(self, github, args, *, timezone_available=True, schedule=None):
        moscow = timezone(timedelta(hours=3))
        now = datetime(2026, 11, 20, 9, tzinfo=moscow)
        env = {"GITHUB_REPOSITORY": "Richbanker/team-lead-lab", "GITHUB_TOKEN": "test-token"}
        if schedule is not None:
            env["REPORT_SCHEDULE"] = schedule
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

    def test_unknown_schedule_fails_before_connecting_to_github(self):
        output = StringIO()
        errors = StringIO()
        with (
            patch.dict("os.environ", {"REPORT_SCHEDULE": "0 7 * * *"}, clear=True),
            patch("scripts.team_pulse.GitHub") as github,
            redirect_stdout(output),
            redirect_stderr(errors),
            self.assertRaises(SystemExit) as failure,
        ):
            main([])

        self.assertNotEqual(failure.exception.code, 0)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("REPORT_SCHEDULE '0 7 * * *'", errors.getvalue())
        self.assertIn(".github/workflows/team-pulse.yml", errors.getvalue())
        github.assert_not_called()

    def test_known_schedules_and_explicit_manual_window(self):
        windows = (
            ("0 9 * * *", "morning", "Утренняя сводка"),
            ("0 13 * * *", "noon", "Обеденная сводка"),
            ("0 18 * * *", "evening", "Вечерняя сводка"),
            ("", "manual", "Сводка по запросу"),
        )
        for schedule, slot, heading in windows:
            with self.subTest(schedule=schedule):
                github = Mock(web="https://github.com/Richbanker/team-lead-lab")
                github.issues.side_effect = [[], [], []]
                github.pages.return_value = []
                output = self.run_main(github, ["--preview"], schedule=schedule)
                self.assertTrue(output.startswith(f"<!-- team-pulse:2026-11-20:{slot} -->\n"))
                self.assertIn(f"## {heading}", output)
                github.publish.assert_not_called()

    def test_preview_prints_markdown_without_reporting_issue_or_publication(self):
        github = Mock(web="https://github.com/Richbanker/team-lead-lab")
        task = {
            "number": 5,
            "title": "Задача 5",
            "labels": [{"name": "team:task"}, {"name": "status:ready"}],
            "assignees": [],
            "updated_at": "2026-11-20T06:00:00Z",
        }
        github.issues.side_effect = [[], [task], []]
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
        overview = {"number": 1, "user": {"login": "Richbanker"}}
        github.issues.side_effect = [[overview], [], [], []]
        github.publish.return_value = "https://github.com/Richbanker/team-lead-lab/issues/1#issuecomment-1"

        output = self.run_main(github, [])

        github.publish.assert_called_once_with(
            1, "<!-- team-pulse:2026-11-20:manual -->", preview, "2026-11-19T21:00:00Z",
        )
        self.assertEqual(output, github.publish.return_value + "\n")
