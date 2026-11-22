from datetime import datetime, timezone
import re
from unittest import TestCase
from unittest.mock import Mock

from scripts.team_pulse import ROW_LIMIT, render_report


REPO_URL = "https://github.com/Richbanker/team-lead-lab"


def issue(number, **fields):
    return {
        "number": number,
        "title": f"Задача {number}",
        "labels": [],
        "assignees": [],
        "updated_at": "2026-11-21T20:00:00Z",
        **fields,
    }


def overdue_section(report, count):
    return report.split(f"### Просрочено ({count})\n\n", 1)[1].split("\n\n### ", 1)[0]


class OverdueTasksTests(TestCase):
    def test_overdue_section_uses_moscow_date_and_valid_open_task_deadlines(self):
        github = Mock(web=REPO_URL)
        github.issues.side_effect = [
            [issue(10, body="### Срок\n\n2026-11-19")],
            [
                issue(1, body="### Срок\n\n2026-11-21"),
                issue(2, body="### Срок\n\n2026-11-22"),
                issue(3, body="### Срок\r\n\r\n2026-11-20\r\n"),
                issue(4, body="### Срок\n\n_No response_"),
                issue(5, body="### Срок\n\n2026-02-30"),
                issue(6),
                issue(7, body="### Срок\n\n20261120"),
                issue(8, body="### Срок\n\n"),
                issue(9, body=None),
            ],
            [issue(11, body="### Срок\n\n2026-11-18", state_reason="not_planned")],
        ]
        github.pages.return_value = []
        now = datetime(2026, 11, 21, 21, 30, tzinfo=timezone.utc)
        report = render_report(github, now, "Сводка")

        self.assertIn("### Просрочено (2)", report)
        self.assertEqual(re.findall(r"/issues/(\d+)\)", overdue_section(report, 2)), ["3", "1"])
        github.issues.assert_any_call(state="open", labels="team:task", sort="created", direction="asc")

    def test_overdue_section_keeps_the_total_above_the_row_limit(self):
        total = ROW_LIMIT + 2
        github = Mock(web=REPO_URL)
        tasks = [issue(number, body=f"### Срок\n\n2026-11-{number:02d}") for number in range(total, 0, -1)]
        github.issues.side_effect = [[], tasks, []]
        github.pages.return_value = []
        report = render_report(github, datetime(2026, 11, 21, 12, tzinfo=timezone.utc), "Сводка")

        self.assertIn(f"### Просрочено ({total})", report)
        rows = overdue_section(report, total)
        self.assertEqual(re.findall(r"/issues/(\d+)\)", rows), [str(number) for number in range(1, ROW_LIMIT + 1)])
        self.assertIn(f"[Открыть полный список]({REPO_URL}/issues)", rows)
