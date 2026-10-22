## 2026-10-22

### Ревью покрытия

| TC-ID | REQ-ID | Статус | Существующий тест | Комментарий |
|---|---|---|---|---|
| TC-001 | REQ-JKPUB-001 | Не автоматизирован | — | Нужна проверка содержимого Kafka-сообщения, этого никто не читает |
| TC-002 | REQ-JKPUB-002 | Не автоматизирован | — | task="—" → ничего не публикуется; не проверяется |
| TC-003 | REQ-JKPUB-002 | Не автоматизирован | — | Jira не настроена → нужно переключать конфиг рантайма |
| TC-004 | REQ-JKPUB-003 | Не автоматизирован | — | Нужно управлять контейнером Kafka (сам TC это признаёт) |
| TC-005 | REQ-JKCONS-001 | Не автоматизирован | — | Нужна оркестрация stop/start consumer |
| TC-006 | REQ-JKCONS-002 | Не автоматизирован | — | Unit-тест на `_deliver()` с моками — другой тип теста, не black-box API; вне зоны vinnie-tests |
| TC-007 | REQ-JKCONS-003 | Автоматизирован, неполно → **переписан** | `test_nonexistent_task_returns_not_found` | Было: только локальное сохранение. Стало: + `wait_for_zero_lag` |
| TC-008 | REQ-JKCONS-004 | Не автоматизирован | — | Нужен намеренно невалидный токен |
| TC-009 | REQ-JKCONS-004 | Не автоматизирован | — | Нужно симулировать сетевой сбой/недоступность Jira |
| TC-010 | REQ-JKCONS-005 | Не автоматизирован | — | Проверяли руками при отладке KAN-3, в код не заведено |
| TC-011 | REQ-JKCONS-006 | Автоматизирован, неполно → **переписан** | `test_entry_worklog_appears_in_jira` | Было: только факт появления + точный текст/время. Стало: + `wait_for_zero_lag` |
| TC-012 | REQ-JKCONS-006 | Не автоматизирован → **покрыт** | `test_nonexistent_task_returns_not_found` | lag=0 после give-up — закрыто той же правкой, что TC-007 |
| TC-013 | REQ-JKCONS-007 | Автоматизирован, неполно → **переписан** | `test_invalid_entry_does_not_appear_in_jira[empty_description]` | Было: только "новый worklog не появился". Стало: + `wait_for_zero_lag`, динамический `tc_id` |
| TC-014 | REQ-JKCONS-007 | Не автоматизирован → **добавлен** | `test_invalid_entry_does_not_appear_in_jira[whitespace_only_description]` | Новый параметризованный кейс: `description="   "`, граница на `.strip()` |
| TC-015 | REQ-JKCONS-008 | ⚠️ Автоматизирован, устарел → **переписан** | `test_invalid_entry_does_not_appear_in_jira[empty_time_spent]` | Оракул в TC описывал старое баговое поведение (бесконечный retry, KAN-3). Старый тест не отличал баг от фикса — проверял только "worklog не появился", что было true в обоих случаях. Теперь проверяет `wait_for_zero_lag` — это и ловит регрессию на бесконечный retry |
| TC-016 | REQ-JKREL-001 | Не автоматизирован | — | Инфра-тест, сам TC помечен "частично/скриптуется" |
| TC-017 | REQ-JKREL-002 | Не автоматизирован | — | Нужна проверка интервала между повторами по таймстемпам в логах |

Вне TC-списка (не из `jira-delivery-via-kafka`, не трогали): `test_jira_connection_is_configured_and_reachable`.

Удалён как дубль: `test_create_entry_logs_to_jira` (`TestJiraSyncStatus`) — не покрывал ни один TC, по факту дублировал `test_entry_worklog_appears_in_jira[task_1]` более слабыми проверками, и не мог выполнять заявленную роль класса (проверка статуса со слов ассистента) — такого API давно нет (`jira_status` в `/confirm` всегда `'queued'`, `GET /entries/{id}` не отдаёт финальный статус).

### План

| TC-ID | REQ-ID | Действие | Что меняется | Файл автотеста | Статус |
|---|---|---|---|---|---|
| TC-015 | REQ-JKCONS-008 | Переписать | `empty_time_spent`: заменить `time.sleep(15)` + "нет нового worklog" на `wait_for_zero_lag()` — это и есть настоящий оракул после фикса KAN-3 | tests/api/test_jira_integration.py | Прогнано (pass) |
| TC-007, TC-012 | REQ-JKCONS-003, REQ-JKCONS-006 | Переписать | Добавить `wait_for_zero_lag()` после give-up | tests/api/test_jira_sync.py::test_nonexistent_task_returns_not_found | Прогнано (pass) |
| TC-011 | REQ-JKCONS-006 | Переписать | Добавить `wait_for_zero_lag()` после успешной доставки | tests/api/test_jira_integration.py::test_entry_worklog_appears_in_jira | Прогнано (pass) |
| TC-013 | REQ-JKCONS-007 | Переписать | Та же замена sleep→lag-check, плюс динамический `allure.dynamic.label("tc_id", ...)` по параметрам | tests/api/test_jira_integration.py::test_invalid_entry_does_not_appear_in_jira | Прогнано (pass) |
| TC-014 | REQ-JKCONS-007 | Добавить | Новый параметризованный кейс `whitespace_only_description` | tests/api/test_jira_integration.py::test_invalid_entry_does_not_appear_in_jira | Прогнано (pass) |
| — | — | Исключить | Удалён дубль `test_create_entry_logs_to_jira` | tests/api/test_jira_sync.py | Реализовано |
| TC-001, TC-002, TC-003, TC-004, TC-005, TC-008, TC-009, TC-010, TC-016, TC-017 | разные | Добавить (группа B, отдельный заход) | Нужна новая инфраструктура: чтение сырых Kafka-сообщений, docker stop/start внутри теста, фикстура с невалидным токеном, парсинг таймстемпов логов | tests/api/, возможно новый tests/kafka/ | Предложено |
| TC-006 | REQ-JKCONS-002 | Пропустить (не в этом репо) | Unit-тест на `_deliver()` — рекомендовано сделать в `vinnie-assistant` отдельной задачей, не здесь | — | — |

Новая инфраструктура этого прохода: `utils/kafka_admin.py` — `get_consumer_group_lag()` / `wait_for_zero_lag()`, через `kafka-consumer-groups.sh` внутри брокерского контейнера (без нового Kafka-клиента в зависимостях).
