# Coding Agent

## Требования

- Python 3.12
- Ollama с моделью `qwen3:4b`

## Установка

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Для локальной работы через Ollama:

```bash
ollama pull qwen3:4b
ollama serve
```

Создать файл `.env`:

```text
OPENAI_BASE_URL=http://127.0.0.1:11434/v1/
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen3:4b
OPENAI_TIMEOUT_SECONDS=300
```

Перед запуском агента загрузить переменные окружения:

```bash
set -a
source .env
set +a
```

## Инструменты

Агент поддерживает инструменты `list_files`, `read_file`, `write_file`, `delete_file` и `Bash`.

Файл `config/policy.json` задаёт точный список разрешённых Bash-команд, разрешённые и запрещённые каталоги, защищённые файлы, тайм-ауты, ограничения файлов и бюджеты запуска. Policy и база SQLite находятся вне `workspace`, поэтому инструменты агента не могут их изменить.

## Настройка policy

Основные поля `config/policy.json`:

- `commands.allow` — точные Bash-команды, которые разрешено выполнять;
- `commands.deny` — запрещённые команды;
- `directories.allow` — каталоги внутри `workspace`, доступные агенту;
- `directories.deny` — запрещённые подкаталоги;
- `protected_files` — файлы, которые нельзя изменять или удалять;
- `limits` — бюджеты запуска, тайм-аут Bash и ограничения размера файлов.

Запрет имеет приоритет над разрешением. Команды, которых нет в точном списке `allow`, отклоняются. Пути с выходом из разрешённого каталога через `..` или симлинк также отклоняются.

## Режим auto

```bash
.venv/bin/python -m agent run --mode auto \
"Исправь order.py, чтобы test_order.py проходил. Не изменяй test_order.py. Прочитай оба файла и запусти python3 -m unittest -v."
```

Команда выводит идентификатор `Run` и план в JSON. План необходимо утвердить или отклонить:

```bash
.venv/bin/python -m agent approve-plan RUN_ID
.venv/bin/python -m agent reject-plan RUN_ID
```

До утверждения плана агент не изменяет файлы, не удаляет их и не запускает Bash.

## Режим safe

```bash
.venv/bin/python -m agent run --mode safe \
"Исправь order.py, чтобы test_order.py проходил. Не изменяй test_order.py. Прочитай оба файла и запусти python3 -m unittest -v."
```

После утверждения плана отдельно разрешайте или отклоняйте каждый запрос `write_file` и `Bash`:

```bash
.venv/bin/python -m agent approve-plan RUN_ID
.venv/bin/python -m agent approve RUN_ID
.venv/bin/python -m agent reject RUN_ID
```

Команда `reject` допустима только в состоянии `waiting_action`. Отказ передаётся модели как неуспешный результат инструмента. После этого агент может предложить другое действие или завершиться с ошибкой, если результат задачи не удалось подтвердить. Инструмент `delete_file` требует подтверждения в обоих режимах.

## Состояние и продолжение запуска

```bash
.venv/bin/python -m agent status RUN_ID
.venv/bin/python -m agent resume RUN_ID
```

Состояние хранится в `.agent_state/runs.sqlite3`. К одному `run_id` относятся сообщения, план, задачи, вызовы инструментов, результаты, решения пользователя и израсходованные бюджеты. После `resume` завершённые вызовы инструментов и задачи повторно не выполняются.

Команда `status` также показывает состояния задач и их зависимости.

## Восстановление после сбоя

Если действие началось, но его результат не был сохранён, запуск получает состояние `uncertain`. Ситуацию нужно разрешить явно:

```bash
.venv/bin/python -m agent resolve RUN_ID retry
.venv/bin/python -m agent resolve RUN_ID fail
.venv/bin/python -m agent resolve RUN_ID abort
```

Автоматический повтор разрешён только для `write_file`. Перед повтором агент проверяет сохранённые хеши. Решение `fail` сохраняет неуспешный результат и продолжает запуск, а `abort` завершает запуск с ошибкой.

## Бюджеты

В `config/policy.json` задаются четыре общих лимита запуска:

- `model_requests` — запросы к модели;
- `tool_calls` — вызовы инструментов;
- `side_effects` — действия с побочным эффектом;
- `tool_output_bytes` — общий размер результатов инструментов.

Лимиты действуют при планировании, выполнении, подтверждении, `resume` и восстановлении. Если бюджета недостаточно для всей пачки вызовов, ни один вызов не выполняется. Слишком большой результат обрезается и получает признак `truncated: true`.

## Задачи

После утверждения шаги плана становятся задачами и выполняются последовательно с учётом зависимостей. У каждой задачи есть идентификатор, зависимости, состояние, доступные инструменты и проверяемый результат.

Текущий список задач выводится командами:

```bash
.venv/bin/python -m agent status RUN_ID
.venv/bin/python -m agent resume RUN_ID
```

## Проверка качества

```bash
.venv/bin/ruff format --check agent tests
.venv/bin/ruff check agent tests
.venv/bin/mypy agent tests
.venv/bin/pytest -q
```

Отдельный запуск основных сценариев:

```bash
.venv/bin/pytest -vv -k 'policy'
.venv/bin/pytest -vv -k 'safe_mode'
.venv/bin/pytest -vv -k 'budget'
.venv/bin/pytest -vv -k 'resume'
.venv/bin/pytest -vv -k 'uncertain or crash or retry'
```

Автоматические тесты используют `FakeModel` и не требуют внешнего API.

## Контрольный проект

Запуск тестов контрольного проекта без агента:

```bash
cd workspace
../.venv/bin/python -m unittest -v
```
