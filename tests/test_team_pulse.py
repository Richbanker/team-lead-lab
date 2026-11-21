from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import Mock

from scripts.team_pulse import ROW_LIMIT, GitHub, markdown_text, render_report, task_status


def issue(number, *labels, assignees=(), **fields):
    return {
        "number": number,
        "title": f"Задача {number}",
        "labels": [{"name": label} for label in labels],
        "assignees": [{"login": login} for login in assignees],
        "updated_at": "2026-11-19T10:00:00Z",
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

    def test_inactive_tasks_include_exact_cutoff_and_show_oldest_first(self):
        repo_url = "https://github.com/Richbanker/team-lead-lab"
        github = Mock(web=repo_url)
        github.issues.side_effect = [
            [],
            [
                issue(1, updated_at="2026-11-17T10:00:01Z"),
                issue(2, updated_at="2026-11-17T10:00:00Z", assignees=("Richbanker",)),
                issue(3, updated_at="2026-11-17T09:59:59Z"),
            ],
            [],
        ]
        github.pages.return_value = []
        midday = datetime(2026, 11, 19, 13, tzinfo=timezone(timedelta(hours=3)))
        report = render_report(github, midday, "Обеденная сводка")
        self.assertIn(
            "### Без движения 48 часов (2)\n\n"
            f"- [#3]({repo_url}/issues/3) Задача 3\n"
            f"- [#2]({repo_url}/issues/2) Задача 2 · Richbanker\n\n"
            "### Открытые PR",
            report,
        )

    def test_inactive_section_limits_rows_but_shows_total(self):
        repo_url = "https://github.com/Richbanker/team-lead-lab"
        github = Mock(web=repo_url)
        total = ROW_LIMIT + 1
        tasks = [issue(number, updated_at="2026-11-17T09:00:00Z") for number in range(1, total + 1)]
        github.issues.side_effect = [[], tasks, []]
        github.pages.return_value = []
        now = datetime(2026, 11, 19, 10, tzinfo=timezone.utc)
        report = render_report(github, now, "Обеденная сводка")
        heading = f"### Без движения 48 часов ({total})\n\n"
        self.assertIn(heading, report)
        inactive_section = report.partition(heading)[2].partition("\n\n### ")[0]
        self.assertEqual(inactive_section.count(f"]({repo_url}/issues/"), ROW_LIMIT)
        self.assertIn(f"[Открыть полный список]({repo_url}/issues)", inactive_section)


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
