"""Check the digest workflow schedule against the script's report windows."""

from collections import Counter
from pathlib import Path
import sys

import yaml

from team_pulse import REPORT_SLOTS


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/team-pulse.yml"
TIMEZONE = "Europe/Moscow"


def check_schedule(path):
    # BaseLoader preserves GitHub Actions' "on" key as a string.
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    events = workflow.get("on") if isinstance(workflow, dict) else None
    if not isinstance(events, dict):
        raise ValueError("ожидается раздел on с событиями workflow.")

    scheduled = events.get("schedule")
    if not isinstance(scheduled, list) or not all(isinstance(slot, dict) for slot in scheduled):
        raise ValueError("on.schedule должен содержать список окон с cron и timezone.")

    actual = Counter(str(slot.get("cron")) for slot in scheduled)
    expected = Counter(cron for cron in REPORT_SLOTS if cron)
    if len(expected) != 3:
        raise ValueError(f"в REPORT_SLOTS должно быть ровно три плановых окна, найдено {len(expected)}.")
    if actual != expected:
        raise ValueError(
            f"on.schedule не совпадает с REPORT_SLOTS. "
            f"Ожидается {list(expected.elements())}, найдено {list(actual.elements())}."
        )

    for slot in scheduled:
        if slot.get("timezone") != TIMEZONE:
            raise ValueError(f"для cron {slot['cron']!r} ожидается timezone {TIMEZONE}, "
                             f"найдено {slot.get('timezone')!r}.")

    if "workflow_dispatch" not in events or "" not in REPORT_SLOTS:
        raise ValueError("ручной запуск требует workflow_dispatch и пустого ключа в REPORT_SLOTS.")


if __name__ == "__main__":
    try:
        check_schedule(WORKFLOW)
    except (OSError, ValueError, yaml.YAMLError) as error:
        sys.exit(f"Ошибка проверки расписания {WORKFLOW.name}: {error}")
    print("Проверены три плановых окна Europe/Moscow и ручной запуск.")
