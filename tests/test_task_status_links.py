from datetime import datetime, timezone
import re
from unittest import TestCase
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from scripts.team_pulse import ROW_LIMIT, render_report, section


REPO_URL = "https://github.com/Richbanker/team-lead-lab"


def task(number, *labels):
    return {
        "number": number,
        "title": f"Задача {number}",
        "labels": [{"name": label} for label in ("team:task", *labels)],
        "assignees": [],
        "updated_at": "2026-11-21T06:00:00Z",
    }


class TaskStatusLinksTests(TestCase):
    def test_overflow_links_apply_each_status_and_its_priority(self):
        statuses = [
            ("Блокеры", "status:blocked"),
            ("На ревью", "status:in-review"),
            ("В работе", "status:in-progress"),
            ("Готовы к запуску", "status:ready"),
        ]
        total = ROW_LIMIT + 1
        tasks = [task(1, *(label for _, label in statuses))]
        for index, (_, label) in enumerate(statuses):
            first = 2 + index * total
            count = ROW_LIMIT if index == 0 else total
            tasks.extend(task(number, label) for number in range(first, first + count))

        github = Mock(web=REPO_URL)
        github.issues.side_effect = [[], tasks, []]
        github.pages.return_value = []
        report = render_report(github, datetime(2026, 11, 21, 7, tzinfo=timezone.utc), "Сводка")

        excluded = []
        for title, label in statuses:
            with self.subTest(title=title):
                marker = f"### {title} ({total})\n\n"
                self.assertIn(marker, report)
                rows = report.split(marker, 1)[1].split("\n\n### ", 1)[0]
                self.assertEqual(len(re.findall(r"/issues/\d+\)", rows)), ROW_LIMIT)
                self.assertEqual("/issues/1)" in rows, label == "status:blocked")

                link = re.search(r"\[Открыть полный список\]\(([^)]+)\)", rows)
                self.assertIsNotNone(link)
                url = urlsplit(link.group(1))
                self.assertEqual((url.scheme, url.netloc, url.path),
                                 ("https", "github.com", "/Richbanker/team-lead-lab/issues"))
                qualifiers = ["is:issue", "is:open", 'label:"team:task"', *excluded, f'label:"{label}"']
                self.assertEqual(parse_qs(url.query), {"q": [" ".join(qualifiers)]})
            excluded.append(f'-label:"{label}"')

    def test_exact_limit_does_not_show_full_list_link(self):
        tasks = [task(number, "status:blocked") for number in range(1, ROW_LIMIT + 1)]
        output = section("Блокеры", tasks, REPO_URL)
        self.assertTrue(output.startswith(f"### Блокеры ({ROW_LIMIT})"))
        self.assertEqual(len(re.findall(r"/issues/\d+\)", output)), ROW_LIMIT)
        self.assertNotIn("Открыть полный список", output)
