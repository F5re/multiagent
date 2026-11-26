# Coding Agent

Консольный coding agent на Python 3.12. Заявленный уровень домашнего задания — **9 баллов, без UI**.

Репозиторий: https://github.com/F5re/multiagent

Агент строит план, вызывает файловые инструменты, Bash и MCP, применяет policy, сохраняет состояние в SQLite и продолжает запуск после сбоя. Skills выбираются моделью динамически. События хранятся в JSONL, а в терминале показываются коротко и понятно.

## Установка

```bash
cd /Users/amir/PycharmProjects/multiagent/hw1
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
ollama pull qwen3.5:9b
curl http://127.0.0.1:11434/v1/models
set -a
source .env
set +a
```

## Быстрая проверка

```bash
.venv/bin/ruff format --check agent tests
.venv/bin/ruff check agent tests
.venv/bin/mypy agent tests
.venv/bin/pytest -q
```

Все положительные и отрицательные демонстрации одной командой:

```bash
bash scripts/demo_checks.sh
```

Тесты используют `FakeModel`, поэтому Ollama для них не нужна.

## Интерактивная сессия и события

```bash
.venv/bin/python -m agent chat --mode auto
```

Внутри доступны `/stats`, `/events` и `/exit`. Пример читаемого вывода:

```text
[agent] Run started: f787cfc4a5284df6928c98dc40f40f23
[skill] Loaded: investigate-test-failure
[skill] Routing decision: investigate-test-failure
[tool] read_file: success
[tool] write_file: success
[tool] Bash: success
[usage] input=905; output=29
```

Полный журнал остаётся машиночитаемым:

```bash
.venv/bin/python -m agent events SESSION_ID --jsonl events.jsonl
.venv/bin/python -m agent stats SESSION_ID
```

Каждая строка JSONL имеет одинаковую оболочку:

```json
{"id":"event-id","time":"2026-11-26T12:00:00+03:00","session_id":"session-id","run_id":"run-id","type":"tool_call","data":{}}
```

## Запуск и Plan Mode

```bash
.venv/bin/python -m agent run --mode auto \
  "Исправь order.py, чтобы test_order.py проходил. Не изменяй test_order.py. Прочитай оба файла и запусти python3 -m unittest -v."
```

Агент печатает `Run`, `Session` и читаемый список шагов. До утверждения плана запрещены Bash и изменения файлов:

```bash
.venv/bin/python -m agent approve-plan RUN_ID
.venv/bin/python -m agent reject-plan RUN_ID
```

В `safe` режиме `write_file` и Bash требуют решения пользователя:

```bash
.venv/bin/python -m agent run --mode safe "ЗАДАЧА"
.venv/bin/python -m agent approve-plan RUN_ID
.venv/bin/python -m agent approve RUN_ID
.venv/bin/python -m agent reject RUN_ID
```

`delete_file` требует подтверждения и в `safe`, и в `auto`. Чтение выполняется без подтверждения. Любой вызов всё равно проходит policy и проверку бюджета.

## Resume и recovery

```bash
.venv/bin/python -m agent status RUN_ID
.venv/bin/python -m agent resume RUN_ID
```

`resume` продолжает сохранённый запуск. Завершённые задачи и tool calls не повторяются, бюджеты не обнуляются.

Если процесс упал между действием и сохранением результата, вызов становится `uncertain`:

```bash
.venv/bin/python -m agent resolve RUN_ID retry
.venv/bin/python -m agent resolve RUN_ID fail
.venv/bin/python -m agent resolve RUN_ID abort
```

`retry` разрешён только там, где runtime может безопасно проверить хеши. `fail` сохраняет ошибочный результат и продолжает loop. `abort` завершает запуск.

## Policy и бюджеты

`config/policy.json` содержит точный allowlist Bash, запрещённые каталоги, защищённые файлы, разрешённые MCP tools и лимиты. Четыре бюджета ограничивают запросы модели, tool calls, побочные эффекты и байты результатов.

Запрет имеет приоритет. Неизвестная команда, shell-синтаксис, запрещённый `cwd`, `..` и симлинк за пределы workspace отклоняются до выполнения. Бюджет пачки списывается атомарно: если лимита не хватает на всю пачку, не выполняется ни один вызов.

```bash
.venv/bin/pytest -vv -k 'policy_allows_exact_command or policy_rejects_command or policy_rejects_path or protected_file_and_symlink'
.venv/bin/pytest -vv -k 'budget or output_budget'
```

## Skills

Исходные skills:

- `investigate-test-failure` — исправление падающих тестов;
- `python-code-review` — review Python-файла;
- `release-notes` — намеренно неподходящий для контрольных задач skill.

Сначала модель видит только `name`, `description`, `version`. Затем вызывает `load_skill` для подходящего skill или отвечает `NO_SKILL`. Полный `SKILL.md` загружается только после выбора.

Новый skill создаётся в `skills/NAME/SKILL.md` с frontmatter-полями `name`, `description`, `version` и инструкцией после frontmatter. Повреждённый skill изолируется и не скрывает остальные:

```bash
.venv/bin/pytest -vv -k 'skill_is_discovered or invalid_skill or explicitly_choose_no_skill'
```

## MCP

`config/mcp.json` подключает локальный stdio MCP-сервер `project_tracker`. Клиент использует JSON-RPC lifecycle `initialize`, `tools/list`, `tools/call`. Policy отдельно разрешает сервер и конкретные tools.

```bash
.venv/bin/pytest -vv -k 'mcp_discovers or mcp_error_and_timeout or mcp_policy_can_deny or exposes_and_logs_mcp'
```

Проверяются успех, ошибка сервера, timeout и отказ policy. Ошибка MCP возвращается модели и не ломает runtime.

## Doctor

```bash
.venv/bin/python -m agent doctor SESSION_ID
.venv/bin/python -m agent doctor SESSION_ID --json
.venv/bin/pytest -vv -k 'doctor_finds or doctor_does_not_flag'
```

Doctor показывает event ID, run ID, счётчики, интерпретацию и рекомендацию. Он находит повторяющуюся ошибку инструмента, завершение без подтверждённого результата и загруженный, но не использованный skill. Отдельный тест доказывает отсутствие ложного срабатывания на нормальной сессии.

## Воспроизводимый A/B eval

Набор `evals/cases.json` содержит пять сценариев: успешное исправление, code review, задачу без подходящего skill, отсутствующие данные и ошибку MCP.

```bash
OPENAI_MODEL=qwen3.5:9b .venv/bin/python -m agent eval run --trials 3 --output results/baseline
.venv/bin/python -m agent eval summary --output results/baseline
```

Это 5 сценариев × A/B × 3 повтора = 30 запусков. В A skills отключены, в B включены; остальные условия одинаковы. Повтор команды пропускает сохранённые trials.

Артефакты: `results/baseline/results.jsonl`, `summary.json`, `summary.md`, `experiment.json`, `analysis.md` и 30 журналов `events.jsonl`. На модели `qwen3.5:9b` skills улучшили code review с 1/3 до 3/3 и missing-data с 1/3 до 2/3, но снизили MCP-failure с 3/3 до 2/3. Гипотеза подтверждена частично; неудачи не удалялись.

## Локальный market

```bash
.venv/bin/python -m agent market list
.venv/bin/python -m agent market search security
.venv/bin/python -m agent market check
```

Каталог содержит новую версию, новый валидный skill и повреждённый пакет. Проверяются revision, структура и метаданные. Автообновление делает только staging кандидата, не заменяя активную версию.

Отрицательный пример:

```bash
.venv/bin/python -m agent market install broken-skill
```

Он должен завершиться ошибкой, а рабочие skills остаться нетронутыми.

## Eval-gated update и rollback

```bash
.venv/bin/python -m agent update evaluate investigate-test-failure --trials 3
.venv/bin/python -m agent update status investigate-test-failure
```

Сравниваются 5 сценариев × old/new × 3 повтора = 30 запусков. Skills включены в обеих группах, отличается только целевая версия. Кандидат принимается, только если нет регрессии успешности, routing корректен везде, пройдены missing-data и MCP-failure, usage полный, рост токенов не выше 20%.

Реальный эксперимент отклонил 2.0 из-за ошибок routing и обязательного limitation-сценария, поэтому активной осталась 1.0:

```bash
cat results/update/investigate-test-failure/decision.json
.venv/bin/pytest -vv -k 'update_decision or skill_update_applies_atomically_and_rolls_back'
```

Тесты детерминированно показывают принятие, отказ, атомарное применение и rollback. Ручные команды для проверенного кандидата:

```bash
.venv/bin/python -m agent update apply SKILL_NAME
.venv/bin/python -m agent update rollback SKILL_NAME
```

## Что показать на защите

1. `bash scripts/demo_checks.sh` — детерминированные положительные и отрицательные случаи.
2. `python -m agent chat --mode auto` — живая сессия и читаемый вывод.
3. `/stats` и `/events` — статистика и журнал.
4. `agent events SESSION_ID --jsonl events.jsonl` — полный JSONL.
5. `agent market list/search/check` и неуспешный `install broken-skill`.
6. `agent eval summary --output results/baseline` и `wc -l results/baseline/results.jsonl` — 30 trials.
7. `cat results/update/investigate-test-failure/decision.json` — автоматический отказ плохому обновлению.

## Ограничения

- Bash защищён policy, но не изолирован контейнером или VM.
- MCP рассчитан на локальные stdio-серверы.
- SQLite подходит для учебного агента; параллельная запись в один run защищена optimistic locking.
- Реальные trials зависят от модели, поэтому выполняются повторы и сохраняются все результаты.
- UI, deployment и функциональность уровня 10 не реализованы.
