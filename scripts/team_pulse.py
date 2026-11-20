"""Preview or publish the repository's GitHub Issues digest."""

import argparse
from datetime import datetime, timedelta, timezone
import html
import json
import os
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


REPORT_SLOTS = {
    "0 9 * * *": ("morning", "Утренняя сводка"),
    "0 13 * * *": ("noon", "Обеденная сводка"),
    "0 18 * * *": ("evening", "Вечерняя сводка"),
    "": ("manual", "Сводка по запросу"),
}
ROW_LIMIT = 10


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("GITHUB_REPOSITORY must be in owner/repo form.")
        self.owner = repository.split("/")[0].lower()
        self.api = f"https://api.github.com/repos/{repository}"
        self.web = f"https://github.com/{repository}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "team-lead-lab",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def request(self, url, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, data=data, method=method, headers=self.headers)
        with urlopen(request, timeout=20) as response:
            return json.load(response), response.headers.get("Link", "")

    def pages(self, path, **params):
        url = f"{self.api}/{path}?{urlencode({'per_page': 100, **params})}"
        while url:
            items, links = self.request(url)
            yield from items
            next_page = re.search(r'<([^>]+)>; rel="next"', links)
            url = next_page.group(1) if next_page else None
            if url:
                parsed = urlsplit(url)
                if parsed.scheme != "https" or parsed.netloc != "api.github.com":
                    raise ValueError("Unexpected GitHub pagination URL.")

    def issues(self, **params):
        return [item for item in self.pages("issues", **params) if "pull_request" not in item]

    def publish(self, issue_number, marker, report, day_start):
        route = f"issues/{issue_number}/comments"
        for comment in self.pages(route, since=day_start):
            if comment["user"]["login"] == "github-actions[bot]" and comment["body"].startswith(marker + "\n"):
                if comment["body"] != report:
                    saved, _ = self.request(f"{self.api}/issues/comments/{comment['id']}", "PATCH", {"body": report})
                    return saved["html_url"]
                return comment["html_url"]
        saved, _ = self.request(f"{self.api}/{route}", "POST", {"body": report})
        return saved["html_url"]


def task_status(issue):
    labels = {label["name"] for label in issue["labels"]}
    for label, status in (
        ("status:blocked", "Блокеры"),
        ("status:in-review", "На ревью"),
        ("status:in-progress", "В работе"),
        ("status:ready", "Готовы к запуску"),
    ):
        if label in labels:
            return status
    return "Назначены" if issue["assignees"] else "Без исполнителя"


def markdown_text(value):
    value = " ".join(value.split())[:180]
    value = re.sub(r"([\\`*_{}\[\]()#+!|~])", r"\\\1", value)
    return html.escape(value, quote=False).replace("@", "&#64;")


def item_line(item, repo_url, kind):
    number = item["number"]
    title = markdown_text(item["title"])
    names = ", ".join(markdown_text(user["login"]) for user in item.get("assignees", []))
    if kind == "pull" and item["draft"]:
        title += " (черновик)"
    suffix = f" · {names}" if names else ""
    return f"- [#{number}]({repo_url}/{kind}/{number}) {title}{suffix}"


def section(title, items, repo_url, kind="issues"):
    rows = [f"### {title} ({len(items)})", ""]
    rows.extend(item_line(item, repo_url, kind) for item in items[:ROW_LIMIT])
    if not items:
        rows.append("—")
    if len(items) > ROW_LIMIT:
        index = "pulls" if kind == "pull" else "issues"
        rows.append(f"[Открыть полный список]({repo_url}/{index})")
    return "\n".join(rows)


def render_report(github, now, heading):
    cutoff = now - timedelta(hours=24)
    since = cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    goals = github.issues(state="open", labels="team:goal", sort="created", direction="asc")
    tasks = github.issues(state="open", labels="team:task", sort="created", direction="asc")
    closed = github.issues(state="closed", labels="team:task", since=since)
    completed = sorted(
        (issue for issue in closed if issue["state_reason"] == "completed" and issue["closed_at"] >= since),
        key=lambda issue: issue["closed_at"],
        reverse=True,
    )
    pulls = list(github.pages("pulls", state="open", sort="created", direction="asc"))

    groups = {status: [] for status in (
        "Блокеры", "На ревью", "В работе", "Готовы к запуску", "Назначены", "Без исполнителя",
    )}
    for task in tasks:
        groups[task_status(task)].append(task)

    sections = [
        f"## {heading} · {now:%d.%m.%Y %H:%M} МСК",
        f"Открыто задач **{len(tasks)}** · принято за 24 часа **{len(completed)}** · открыто PR **{len(pulls)}**",
        section("Открытые цели", goals, github.web),
        *(section(status, issues, github.web) for status, issues in groups.items()),
        section("Открытые PR", pulls, github.web, "pull"),
        section("Принято за 24 часа", completed, github.web),
    ]
    return "\n\n".join(sections) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Print the Markdown digest to stdout.")
    args = parser.parse_args(argv)

    github = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    try:
        report_timezone = ZoneInfo("Europe/Moscow")
    except ZoneInfoNotFoundError:
        report_timezone = timezone(timedelta(hours=3))
    now = datetime.now(report_timezone).replace(microsecond=0)
    slot, heading = REPORT_SLOTS[os.environ.get("REPORT_SCHEDULE", "")]
    marker = f"<!-- team-pulse:{now:%Y-%m-%d}:{slot} -->"
    issue_number = None
    if not args.preview:
        overview = [
            issue for issue in github.issues(state="open", labels="team:overview")
            if issue["user"]["login"].lower() == github.owner
        ]
        if len(overview) != 1:
            raise RuntimeError("Create exactly one open issue from the repository owner's account with label team:overview.")
        issue_number = overview[0]["number"]

    report = marker + "\n" + render_report(github, now, heading)
    if issue_number is None:
        print(report, end="")
        return

    day_start = now.replace(hour=0, minute=0, second=0).astimezone(timezone.utc)
    print(github.publish(issue_number, marker, report, day_start.strftime("%Y-%m-%dT%H:%M:%SZ")))


if __name__ == "__main__":
    main()
