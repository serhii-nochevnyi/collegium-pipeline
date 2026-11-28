# Жива перевірка епіка A/B → C

Перевірено службовий граф з установленого bundle Collegium. Контролер v22,
джерело `90b289290bcdc0d6bb23c5e14d4315bdd250169c`, root `d19e0950-cbb0-4f9a-98ce-324a3ecfaf87`. Підсумковий стан —
`ready_for_acceptance`, `delivered=false`. Локальний оператор лише подавав ручні Run now
та читав результати; admission, scheduler, workers, якісні перевірки й checkpoints працювали
у встановленому контролері та його native App helpers.

| Вузол | Службовий PR | Прийнятий коміт | База кандидата | Стан |
|---|---|---|---|---|
| A | [#7](https://github.com/serhii-nochevnyi/collegium-pipeline/pull/7) | `3674ddd9de48` | `ed79efbdd3db` | merged |
| B | [#6](https://github.com/serhii-nochevnyi/collegium-pipeline/pull/6) | `cbbd6b4fbc6b` | `ed79efbdd3db` | merged |
| C | [#8](https://github.com/serhii-nochevnyi/collegium-pipeline/pull/8) | `e7a668640b20` | `256a47cb2863` | merged |

A та B реально працювали одночасно: platform turns прочитано у порядку A/B/A зі станом
running та відкритими часовими інтервалами. C залишався queued навіть після готовності
обох PR. Його перша сесія почалася `2026-11-28 17:52:21 (Europe/Kiev)`, після фактичних merge A/B;
база C точно дорівнює спільному merge SHA. Сам C перевіряє суму значень із файлів A та B.

Після перекриття A/B контролер навмисно скасовано. Незалежний підписаний checkpoint
відновив той самий root та ті самі два job/session/turn ID. Інвентар сесій Collegium
підтвердив по одній сесії на кожний deterministic intent. Два фінальні повтори зберегли
всі worker ID, три кандидатні коміти та три PR без нових зовнішніх ефектів.

Усього `20` унікальних сесій цієї ревізії графа:
`17` прийнятих етапів і `3`
відхилені завершені валідації з явно облікованими повторними спробами. Відхилення й токени
збережені в журналі. Початкова ревізія службових фікстур архівована окремо після
підтвердженого завершення її двох планувальників; її acceptance не переписувався.

Спільний SHA `5805b160c9bc147ed2e530158b7b7bea9cd0e4b7` пройшов окремі інтеграційні валідацію та review
різними сесіями, а також [GitHub Actions quality](https://github.com/serhii-nochevnyi/collegium-pipeline/actions/runs/46164109999/job/141037721550).
Службові merge виконані native App helper тільки в ізольовану гілку
`collegium/c5b7d3d9-9db7-4552-8e0e-fbfe99b27001` за підписаними підтвердженнями готовності.

Під час перевірки виправлено:

- Форматування службових фікстур: явна ревізія 2 замість зміни вже прийнятого завдання.
- Великий вивід тестів: повний журнал у файлі, bounded receipt з exit code, розміром і SHA256;
  завершені відхилені валідації повторюються на тому самому кандидаті з обліком токенів.
- Сумісність із GitHub REST 2026, який прибрав `merge_commit_sha`: actual merged lifecycle,
  незмінний прийнятий head, зелений CI та доведене Git ancestry залишаються обов’язковими.
  [Офіційна зміна API](https://docs.github.com/en/rest/about-the-rest-api/breaking-changes?apiVersion=2026-03-10).
- Протокольний збій інтеграційного воркера, який додав прозу після JSON: суворе відхилення,
  обмежений повтор лише після підтвердженого terminal стану та незмінного SHA, облік усіх
  attempts. Регресія перевіряє обрив після drain до збереження нового стану.

Локально пройшло 289 тестів, Ruff та валідація bundle; [CI джерела](https://github.com/serhii-nochevnyi/collegium-pipeline/actions/runs/46164987292/job/141040446183)
зелений. Actual runtime proofs підтвердили claude-opus-5-5/high, claude-sonnet-5-5/low через приватний Claude
connection. Перевірені аргументи процесу й served model; внутрішнє reasoning провайдера
не спостерігається.

Усі `20` автоматизацій paused. Поточні execution/broker flags
залишаються false; worker bindings і MCP ceilings збережені. `main` незмінний:
`dbe5e20955dee07fab2a7bc9ab93aa0bcd1b0451`. PR1 із кодом bundle відкритий і не merged. Тимчасовий CI probe
PR5 закритий без merge. Пілот не обирався, записів до Jira не було.

Перевірка охоплює фіксований службовий text-граф. Для REST 2026 squash/rebase без входження
прийнятого head в історію бази залишається fail-closed до окремого authoritative merge lookup.
Машинні докази: [JSON](/Volumes/KINGSTON/collegium-pipeline/reports/epic-live-service-verification.json); первинні спостереження
та acknowledgement-и збережені у `.local/epic-live-*`.
