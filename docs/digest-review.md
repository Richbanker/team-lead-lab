# Проверка пути от Actions до журнала

Проверка проведена 26 ноября 2026 года по версии [main `71b265b`](https://github.com/Richbanker/team-lead-lab/commit/71b265bc4d0bbbc7cbd28c571ec1d1243dc71889). Использованы история Actions, логи задания **report** и опубликованные комментарии из [журнала #1](https://github.com/Richbanker/team-lead-lab/issues/1).

В каждом запуске ниже событие было `schedule`, а результат — **Success**. В шаге **Опубликовать сводку** проверены `REPORT_SCHEDULE` и напечатанный URL. По этому URL найден комментарий от `github-actions[bot]` с ожидаемым названием окна.

| Окно | Расписание | Запуск | Комментарий в журнале |
| --- | --- | --- | --- |
| Утро | `0 9 * * *` | [Запуск #18](https://github.com/Richbanker/team-lead-lab/actions/runs/45657246706) | [Утренняя сводка, 25.11 в 19:44 МСК](https://github.com/Richbanker/team-lead-lab/issues/1#issuecomment-7168472097) |
| Обед | `0 13 * * *` | [Запуск #19](https://github.com/Richbanker/team-lead-lab/actions/runs/45689239494) | [Обеденная сводка, 25.11 в 22:51 МСК](https://github.com/Richbanker/team-lead-lab/issues/1#issuecomment-7172852325) |
| Вечер | `0 18 * * *` | [Запуск #20](https://github.com/Richbanker/team-lead-lab/actions/runs/45721774339) | [Вечерняя сводка, 26.11 в 02:29 МСК](https://github.com/Richbanker/team-lead-lab/issues/1#issuecomment-7177638658) |

## Что может сбить с толку

**Публикация после полуночи.** Вечерний запуск ссылается на комментарий, помеченный датой 26 ноября. В логе указан вечерний cron, а дата комментария соответствует времени фактической публикации по Москве. Скрипт берёт дату для ключа журнала из текущего московского времени. При поиске отчёта сразу после полуночи проверяйте ссылку из запуска и заголовок комментария. По одной дате в журнале нельзя установить исходный календарный день расписания.

**Два запуска могут вести к одному комментарию.** Откройте шаг **Опубликовать сводку** в [запуске #13](https://github.com/Richbanker/team-lead-lab/actions/runs/45274895387) и [запуске #16](https://github.com/Richbanker/team-lead-lab/actions/runs/45482196431). В обоих логах обеденный cron и один [URL](https://github.com/Richbanker/team-lead-lab/issues/1#issuecomment-7115146901). Комментарий создан 24 ноября в 00:57:44 МСК и обновлён в 23:34:27 МСК. Это согласуется с обновлением сводки для того же окна и московской даты. При разборе раннего запуска ссылка показывает позднюю редакцию сводки. Время и факт ранней публикации можно сверить по раннему логу и `created_at`.

## Как повторить

1. В [истории workflow](https://github.com/Richbanker/team-lead-lab/actions/workflows/team-pulse.yml) выберите запуск с событием `schedule`.
2. В задании **report** откройте **Опубликовать сводку**. Сопоставьте значение `REPORT_SCHEDULE` с [конфигурацией workflow](../.github/workflows/team-pulse.yml), затем откройте URL из вывода шага. Эта же конфигурация записывает URL в **Summary**.
3. Сверьте название окна и время в заголовке комментария. Если заголовок изменился, проверьте `created_at` и `updated_at` через API. Для обеденного примера команда выглядит так.

   ```powershell
   Invoke-RestMethod 'https://api.github.com/repos/Richbanker/team-lead-lab/issues/comments/7115146901' |
     Select-Object html_url, created_at, updated_at
   ```
