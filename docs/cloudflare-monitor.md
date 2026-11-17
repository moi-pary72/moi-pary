# Независимый монитор «Мои пары 72»

Cloudflare `moi-pary-monitor` проверяет опубликованный `data/sync-status.json` каждые 30 минут. Когда последняя попытка проверки источника старше 90 минут, он сначала проверяет историю `Refresh timetables from Yandex Disk` в GitHub. Если задание идёт или запускалось в предыдущие 60 минут, не создаёт дубликат. В противном случае запускает имеющийся workflow `repository_dispatch: refresh-timetables`.

Монитор не скачивает XLS, не редактирует сайт и не публикует страницы. За это отвечает прежний GitHub Actions. Старый GitHub cron оставлен как дополнительный источник обновлений. При ошибках источника монитор пишет диагностическое сообщение, не перезаписывает расписание и не устраивает цикл повторов.

## Настройка Cloudflare

1. Использовать **существующий Worker** `moi-pary-monitor`; Git account `moi-pary72`, repository `moi-pary`, branch `main`, deploy command `npx wrangler deploy`, root `/`, build command пустой.
2. Secret Worker (не Build secret) `GITHUB_TOKEN`: fine-grained PAT, выданный **только** репозиторию `moi-pary72/moi-pary`, с **Contents: Read and write**, **Actions: Read** и **Metadata: Read**. Не вставлять значение ни в GitHub-код, ни в чат. Название обязательно такое, как указано в коде. GitHub API `repository_dispatch` требует Contents write.
3. Проверить `/health` на домене Worker: `configured: true`. Если false — секрет не установлен в среде Worker.
4. В настройках Builds → Build watch paths → Include paths указать отдельными правилами `cloudflare/*`, `wrangler.jsonc`, `package.json`. Данные `data/**` не должны вызывать развёртывание Worker при каждой проверке расписания.
5. Проверить в Cloudflare Triggers один Cron `*/30 * * * *` и успешные логи Cron; сверить `data/sync-status.json` и GitHub Actions. **Проверка здоровья `/health` не запускает синхронизацию** и не подтверждает успешные Cron.

Существующие GitHub Pages, workflow sync.yml и XLS-парсер намеренно не изменены. На бесплатном тарифе выделен ровно 1 Cron. Если аккаунт уже использует 5 Cron, необходимо объединить расписания, а не докупать ресурсы автоматически.

Важная граница: если сам официальный источник недоступен, повторный запуск не гарантирует исправления. Для самостоятельных уведомлений о долгом сбое потребуется отдельный канал уведомлений/Cloudflare Alerts.
