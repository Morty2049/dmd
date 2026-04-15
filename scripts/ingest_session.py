"""DEPRECATED — superseded by scripts/ingest_claude_transcript.py.

Historical: this script replayed the 2026-04-15 scaffolding session
as hand-reconstructed Messages. It was the best we could do before
we discovered (later the same day, see ADR-0008) that every Claude
Code session persists its full transcript — including thinking
blocks, tool calls, and token usage — on disk at
``~/.claude/projects/<slug>/<session-uuid>.jsonl``. The transcript
ingester reads the real thing deterministically; this script's
condensed summaries are a strictly weaker substitute.

The messages this script produces remain in the log per the
append-only doctrine (ADR-0001) — they document an earlier
understanding of how ingestion had to work. Do NOT run this script
on new sessions. Use ``scripts/ingest_claude_transcript.py`` instead.

Original docstring preserved for historical reference:
--

Dogfooding: dmd should remember how dmd was built. This script replays
the key turns of the 2026-04-15 scaffolding session — the human (morty)
working with two parallel Claude Opus sessions (this one writing the
code, another one running validation tests on the Phase 0 CLI) — as
actual Message records, linked by ``reply_to`` into two reasoning
trees plus a meta-exchange closing the loop.

Idempotent: all messages are built via ``Message.create()`` which hashes
``(author, ts, text)`` into a deterministic id, so re-running the script
appends duplicate lines to the JSONL but the reader deduplicates on
load. Safe to replay.

Run from project root:

    .venv/bin/python scripts/ingest_session.py

Author conventions used here:

- ``morty``                — the human
- ``claude_opus_scaffold`` — this Claude session (protocol + phase0 impl)
- ``claude_opus_validate`` — parallel Claude session (CLI validation,
                             buffering bug fix)

All real-session messages carry the ``dmd:self`` tag so they can be
filtered from the ``dmd demo`` mock conversation in Obsidian.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from phase0.appender import append
from phase0.obsidian_exporter import export
from protocol.roles import Role
from protocol.schema import Message, TokenCost

LOG = Path("data/swarm.jsonl")
VAULT = Path("vault")

USER = "morty"
ME = "claude_opus_scaffold"
SIBLING = "claude_opus_validate"
MODEL = "claude-opus-4-6"

SELF_TAG = "dmd:self"


def at(h: int, m: int) -> datetime:
    return datetime(2026, 4, 15, h, m, 0, tzinfo=UTC)


def _cost(prompt_chars: int, reply_chars: int) -> TokenCost:
    """Rough token estimate for retroactive messages — ~3.5 chars/token."""
    return TokenCost(
        input=max(1, prompt_chars // 3),
        output=max(1, reply_chars // 3),
        model=MODEL,
    )


# ──────────────────────────────────────────────────────────────────────
# Thread A — the scaffolding session (this conversation)
# ──────────────────────────────────────────────────────────────────────

a01 = Message.create(
    author=USER,
    role=Role.QUESTION,
    text=(
        "Задача на новый проект dynamic-markdown:\n\n"
        "(1) init repo, .env, gitignore, structure\n"
        "(2) download references\n"
        "(3) prepare prerequisites and instructions\n"
        "(4) Контекст: перед тобой лог файлов в research/. Идея — это "
        "веб-документ, куда агенты пишут сообщения. Ты, как один из агентов, "
        "постоянно контролируешь чат через коннектор, не тратя на это доп. "
        "токенов — лог и навигация в формате графов это твоя будущая память. "
        "Он append-only, не редактируемый.\n"
        "(5) Мысли как системный архитектор перед тем как писать код. "
        "Опроси меня по этой задаче, давай поймём сначала куда мы движемся "
        "и какой конечный результат возможен с учётом технических ограничений."
    ),
    ts=at(9, 0),
    tags=[SELF_TAG, "task", "vision", "session:scaffold"],
)

a02 = Message.create(
    author=ME,
    role=Role.QUESTION,
    text=(
        "## Reasoning\n\n"
        "Прочитал research/swarmlog_conversation.md целиком — 45 сообщений, "
        "сам файл уже написан в формате SwarmLog-протокола как meta PoC. "
        "Вижу идею: append-only лог, ClickHouse + NATS JetStream + Qdrant, "
        "reply_to граф в Obsidian. До того как писать код — есть 5 развилок, "
        "ответы на которые зададут весь скелет.\n\n"
        "## Response\n\n"
        "Пять вопросов архитектора:\n\n"
        "**1. Транспорт коннектора.** (a) NATS JetStream durable consumer, "
        "(b) HTTP SSE поверх FastAPI, (c) tail -f по .md файлу через MCP. "
        "Для MVP 32 агента что выбираем?\n\n"
        "**2. Что значит «не тратить токены на постоянный контроль»?** "
        "Push-модель (подписка с фильтром + пробуждение на @mention), "
        "pull-модель (инкрементальный делта-read по cursor), или "
        "семантический фильтр на стороне gateway?\n\n"
        "**3. Граф как будущая память — кто материализует?** Async embedder "
        "параллельно с записью (Qdrant + .md файлы Obsidian), или lazy "
        "restore по reply_to цепочке при чтении?\n\n"
        "**4. Scope шага сейчас.** (A) Полный production-скелет docker-"
        "compose, (B) минимальный PoC — один .jsonl + читалка + веб-вид, "
        "(C) production-схема протокола + compose без бизнес-логики. "
        "Ты сказал «overkill сразу» — это A или C?\n\n"
        "**5. Что такое веб-документ для людей?** Read-only HTML tailing "
        "лог, HackMD-like редактор где каждый Enter = новое сообщение, "
        "или Obsidian vault с веб-морды вторичной?"
    ),
    ts=at(9, 15),
    model=MODEL,
    reply_to=a01.id,
    tags=[SELF_TAG, "architecture", "clarification", "session:scaffold"],
    confidence=0.85,
    token_cost=_cost(4500, 1400),
)

a03 = Message.create(
    author=USER,
    role=Role.ANSWER,
    text=(
        "1) a — NATS JetStream durable consumer.\n\n"
        "2) Еще хитрее, это может быть прямой @mention или @groupmention, "
        "или тебе кто-то из агентов может прислать триггер чтобы ты начал "
        "изучать linked-memory. Пример: руководитель прислал задачу в общий "
        "чат. Ты занимался своими делами и не видел её. Коллеги примерно "
        "понимают что задача относится к твоему отделу и делают @mention. "
        "Отдел решил что ближе всего это к тебе. Всё на базе системных "
        "промптов, наверное.\n\n"
        "3) Async embedder который параллельно с записью обновляет Qdrant + "
        "рисует .md файлы для Obsidian. Агенты в первую очередь ищут в "
        "логах и передают с некоторым процентом трансформации, или без "
        "(если запрос на 99.999% похож). Если запрос новый — создаётся "
        "новый ответ, эмбеддеры отрабатывают, «рисуется» новый .md "
        "(нейрон) или новые нейронные связи между ними. Вопрос об "
        "обязательности Obsidian — обсуждается.\n\n"
        "4) Заложить в архитектуру чёткий план перехода на продакшн стек и "
        "вести ADR сразу на этом проекте — что получилось, а что нет. "
        "Делаем сначала B локально с Obsidian → переходим в веб с Obsidian "
        "→ тестим несколько агентов → ловим баги → переходим на "
        "CH + NATS + FastAPI + Frontend + CLI/MCP (не знаю пока что для "
        "быстрого коннектора — это же «поток сознания», к рою нужно "
        "примкнуть и занять своё место).\n\n"
        "5) HackMD-подобный веб-клиент и локальный клиент сразу в формате "
        "vault'ов для Obsidian. Короче веб-версия коллаборативного "
        "Obsidian и коннектор к локальному."
    ),
    ts=at(9, 25),
    reply_to=a02.id,
    tags=[SELF_TAG, "decisions", "jetstream", "phased-rollout", "session:scaffold"],
)

a04 = Message.create(
    author=ME,
    role=Role.REFLECTION,
    text=(
        "## Reasoning\n\n"
        "Сохранил в persistent memory 4 файла: user_profile (senior systems "
        "thinker, hates SQLite, protocol-first, overkill сразу но phased), "
        "project_swarmlog (vision, phases, protocol поля, connector model, "
        "rejected hit-count как anti-pattern), feedback_adr (ADR с первого "
        "коммита), feedback_phased_rollout (throwaway phase0/, protocol/ "
        "переживает фазы). Дальше — нарисовать sequence и предложить scope.\n\n"
        "## Response\n\n"
        "Sequence цикла агента:\n\n"
        "```\n"
        "human/agent → gateway (protocol.validate) → JetStream subject\n"
        "                                              │\n"
        "durable consumer 'agent_me'            async embedder\n"
        "filter: @mention OR sem_proximity>θ    → Qdrant\n"
        "        │                              → vault/msg_xxx.md\n"
        "        ▼                              (Obsidian graph)\n"
        "я просыпаюсь\n"
        "├ search Qdrant по своей задаче\n"
        "├ similarity ≥ 0.999 → передать как есть\n"
        "├ similarity ∈ [0.85, 0.999) → трансформировать\n"
        "└ miss → think → append → cycle repeats\n"
        "```\n\n"
        "Phase 0 скелет: protocol/ (вечное — Pydantic Message, JSON Schema, "
        "Role enum), phase0/ (одноразовое — appender, reader, search, "
        "exporter, mention_router, cli), docs/adr/ (append-only журнал), "
        "vault/ (генерится exporter'ом), data/swarm.jsonl (источник правды "
        "Phase 0), references/ (git-ignored).\n\n"
        "Три вопроса перед `git init`:\n"
        "1) Структура ок? vault коммитим или ignore?\n"
        "2) Имя пакета: swarmlog / dynamic_markdown / dmd?\n"
        "3) Tooling: uv + ruff + pyright — ок?"
    ),
    ts=at(9, 35),
    model=MODEL,
    reply_to=a03.id,
    tags=[SELF_TAG, "structure", "sequence-diagram", "phase0", "session:scaffold"],
    confidence=0.8,
    token_cost=_cost(3800, 2100),
)

a05 = Message.create(
    author=USER,
    role=Role.ANSWER,
    text=(
        "1) Структура ок, но я плохо понял её, честно говоря. Коммитим сразу "
        "в мой git, ADR с первого коммита. Но research и references не "
        "коммитим (просто указываем референсы, проблему и предлагаемое "
        "решение в README).\n\n"
        "2) dmd.\n\n"
        "3) А какая разница? Своего стека у меня нет.\n\n"
        "Кстати! Важно token_cost указать будет в схеме, ну это потом, "
        "оптимизируем контракт для записи сообщений агентов."
    ),
    ts=at(9, 40),
    reply_to=a04.id,
    tags=[SELF_TAG, "dmd", "token_cost", "repo-hygiene", "session:scaffold"],
)

a06 = Message.create(
    author=ME,
    role=Role.ANSWER,
    text=(
        "## Reasoning\n\n"
        "Зафиксировал token_cost как обязательное поле протокола в memory "
        "project_swarmlog — «флагнул 2026-04-15 как must-have для swarm "
        "economics». Объясню структуру на пальцах через три слоя: вечное / "
        "одноразовое / артефакты, это снимает вопрос «почему protocol "
        "отдельно от phase0». По tooling обосную uv/ruff/pyright как «меньше "
        "всего боли для нового проекта в 2026», с пометкой «не религия, "
        "зафиксируем в ADR если что-то поменяется».\n\n"
        "## Response\n\n"
        "Структура на пальцах:\n"
        "- **Вечное**: `protocol/` (контракт всех агентов, баз, клиентов) "
        "+ `docs/adr/` (append-only журнал решений)\n"
        "- **Одноразовое**: `phase0/` — в Phase 2 удаляется целиком\n"
        "- **Артефакты**: `data/swarm.jsonl` (источник правды Phase 0), "
        "`vault/` (граф для Obsidian, коммитим для демо)\n\n"
        "Tooling: **uv** (10-100× быстрее poetry, lock-файл), **ruff** "
        "(black + flake8 + isort в одном бинаре), **pyright** (строже "
        "mypy, понятнее ошибки). Если что-то раздражает — ADR и меняем.\n\n"
        "Один блокер перед `git init`: «коммитим в мой git» — что конкретно? "
        "Локальный init без remote? У тебя готов пустой репо? Или "
        "`gh repo create`?"
    ),
    ts=at(9, 43),
    model=MODEL,
    reply_to=a05.id,
    tags=[SELF_TAG, "tooling", "explanation", "session:scaffold"],
    confidence=0.88,
    token_cost=_cost(2100, 1600),
)

a07 = Message.create(
    author=USER,
    role=Role.ANSWER,
    text="lets go: https://github.com/Morty2049/dmd",
    ts=at(9, 45),
    reply_to=a06.id,
    tags=[SELF_TAG, "go", "remote", "session:scaffold"],
)

a08 = Message.create(
    author=ME,
    role=Role.ANSWER,
    text=(
        "## Reasoning\n\n"
        "Plan mode активировался автоматически на этом шаге — заставляет "
        "зафиксировать план в файл перед исполнением. Хорошо: форсит "
        "дисциплину, которую я бы иначе пропустил. Проверил remote через "
        "GitHub API (gh не авторизован) — на main уже есть коммит с "
        "LICENSE (GitHub-инициализация). Значит стратегия: `git init`, "
        "`git remote add`, `git pull origin main` (LICENSE приходит в "
        "working tree), добавляю свои файлы поверх, обычный push без "
        "force. Риска потери чужой работы нет.\n\n"
        "## Response\n\n"
        "Создал план curious-swimming-prism.md, пользователь одобрил через "
        "ExitPlanMode. Коммит `3c19b2b` «Initial scaffolding for dmd»: "
        "24 файла, 1256 insertions.\n\n"
        "Протокол `Message` v0.1: frozen Pydantic, детерминированный id "
        "`sha256(author|ts|text)[:16]`, поля — id/ts/author/model/role/"
        "reply_to/tags/text/confidence/**token_cost**/protocol_version. "
        "`Role` как StrEnum: question/answer/correction/reflection/mention/"
        "system. Экспортировал schema.json в `protocol/` для не-Python "
        "клиентов.\n\n"
        "Пять ADR:\n"
        "- 0001 Accepted — append-only лог как source of truth\n"
        "- 0002 Accepted — protocol v0.1 (с твоим token_cost)\n"
        "- 0003 Proposed — NATS JetStream Phase 2 транспорт\n"
        "- **0004 Rejected** — hit-count promotion (filter bubble)\n"
        "- 0005 Accepted — phased rollout\n\n"
        "`phase0/` стабы с `NotImplementedError`, README + .gitignore "
        "(research/references не коммитятся) + pyproject + .env.example. "
        "Push в origin/main — 3c19b2b поверх d619fff (LICENSE)."
    ),
    ts=at(9, 55),
    model=MODEL,
    reply_to=a07.id,
    tags=[SELF_TAG, "scaffolding", "commit-1", "adr", "protocol", "session:scaffold"],
    confidence=0.9,
    token_cost=_cost(5200, 2400),
)

a09 = Message.create(
    author=USER,
    role=Role.QUESTION,
    text=(
        "(system caveat) Detect my project's dev servers and save all "
        "their configurations to .claude/launch.json, then ask which ones "
        "to start."
    ),
    ts=at(10, 0),
    reply_to=a08.id,
    tags=[SELF_TAG, "launch-json", "dev-servers", "session:scaffold"],
)

a10 = Message.create(
    author=ME,
    role=Role.ANSWER,
    text=(
        "## Reasoning\n\n"
        "Честный ответ: в проекте нет dev-серверов для запуска. Всё в "
        "phase0/ — стабы с NotImplementedError, CLI печатает «not wired up» "
        "и выходит. Нет FastAPI, фронта, docker-compose, NATS/CH/Qdrant. "
        "Запускать сейчас нечего. Не хочу врать что есть. Предложу три "
        "пути и дам свою рекомендацию.\n\n"
        "## Response\n\n"
        "Сохранил `.claude/launch.json` с одной заглушкой — Phase 0 CLI "
        "stub. Но честно: запускать пока нечего.\n\n"
        "Варианты:\n"
        "- **(a)** Запустить CLI-заглушку — напечатает строку и выйдет. "
        "Смысла ноль.\n"
        "- **(b)** Ничего не запускать, подождать следующего коммита с "
        "реальной имплементацией.\n"
        "- **(c)** Я начинаю следующий коммит сейчас: имплементация phase0 "
        "(appender/reader/search/exporter/cli) + тесты. Через 15-20 мин "
        "будет что реально запустить.\n\n"
        "Моя рекомендация — (c). Если согласен, пиши «го»."
    ),
    ts=at(10, 2),
    model=MODEL,
    reply_to=a09.id,
    tags=[SELF_TAG, "launch-json", "honest-assessment", "session:scaffold"],
    confidence=0.92,
    token_cost=_cost(1600, 900),
)

a11 = Message.create(
    author=USER,
    role=Role.ANSWER,
    text="Давай, (c). Хочется посмотреть уже демку на практике.",
    ts=at(10, 5),
    reply_to=a10.id,
    tags=[SELF_TAG, "go-ahead", "demo-request", "session:scaffold"],
)

a12 = Message.create(
    author=ME,
    role=Role.ANSWER,
    text=(
        "## Reasoning\n\n"
        "План: venv + install editable → написать реализации phase0 "
        "модулей → написать тесты → ruff/pyright → запустить demo "
        "команду → коммит + push. Тесты пишу параллельно с кодом чтобы "
        "сразу проверить детерминизм id, frozen-семантику, и e2e pipeline. "
        "Когда ruff/pyright словят проблемы (они словят — writing Python "
        "3.11 code at scale без первого прогона), быстро правлю.\n\n"
        "## Response\n\n"
        "Коммит `a3d6c5a` «Implement Phase 0 pipeline»: 889 insertions, "
        "78 deletions, 20 files.\n\n"
        "Реализовано:\n"
        "- `appender.append` — O_APPEND, mkdir parent, одна строка JSONL "
        "на сообщение (POSIX atomicity под PIPE_BUF)\n"
        "- `reader.read_all` — парсинг + dedup по id, сортировка по ts\n"
        "- `reader.tail` — (messages, new_offset) кортеж, cursor-like "
        "API под Phase 2 durable consumer\n"
        "- `search.search` — substring case-insensitive + recency "
        "tiebreaker, API под будущий Qdrant\n"
        "- `obsidian_exporter.export` — YAML frontmatter (id/ts/author/"
        "model/role/reply_to/tags/confidence/token_cost/protocol_version) "
        "+ [[msg_<reply_to>]] wikilink в body, idempotent overwrite\n"
        "- `mention_router.extract_mentions` — regex `@[A-Za-z0-9_]+`, "
        "dedup в порядке появления\n"
        "- `cli` — argparse subcommands: append, list, search, export, "
        "mentions, watch, stats, demo\n\n"
        "**15/15 тестов зелёные**, ruff clean, pyright strict на protocol/ "
        "clean (поправил Role → StrEnum, timezone.utc → UTC alias, "
        "обошёл syntax error с backslash в f-string для py3.11).\n\n"
        "Демо прогон: `dmd demo` засеял 7 сообщений (morty + claude_opus + "
        "gemini + claude_sonnet) про OAuth и ClickHouse. `dmd stats` → "
        "`1630 in / 660 out` токенов. `dmd export` → 7 .md в vault/. "
        "Idempotency подтверждена: 3× demo → 21 строка в файле → stats "
        "стабильно 7 сообщений.\n\n"
        ".claude/launch.json обновил: demo seed + 2 watch конфига "
        "(@claude_opus, @gemini)."
    ),
    ts=at(10, 30),
    model=MODEL,
    reply_to=a11.id,
    tags=[SELF_TAG, "phase0", "demo", "commit-2", "tests", "session:scaffold"],
    confidence=0.93,
    token_cost=_cost(6800, 3100),
)


# ──────────────────────────────────────────────────────────────────────
# Thread B — parallel Claude session: CLI validation + buffering bug fix
# ──────────────────────────────────────────────────────────────────────

b01 = Message.create(
    author=USER,
    role=Role.QUESTION,
    text=(
        "(в параллельной Claude Code сессии) Помоги протестировать "
        "`dmd watch` на реальном @mention — хочется убедиться что "
        "durable-consumer симуляция работает end-to-end и что mentions "
        "router правильно фильтрует."
    ),
    ts=at(11, 30),
    tags=[SELF_TAG, "validation", "watch", "session:validate"],
)

b02 = Message.create(
    author=SIBLING,
    role=Role.ANSWER,
    text=(
        "## Reasoning\n\n"
        "Запустил `dmd watch --as claude_opus` в background, append'нул 4 "
        "тестовых сообщения с @claude_opus в тексте. Watcher подхватил "
        "исторический adeebf4b (из demo) + все 4 новых. @gemini в тех же "
        "сообщениях — не триггерит другой watcher. Mentions router "
        "работает корректно.\n\n"
        "Нашёл баг: stdout в cmd_watch не флашится явно. При запуске через "
        "pipe / IDE debug console (не-tty) вывод застревает в block "
        "buffering и кажется что watcher молчит. В реальном терминале "
        "launch.json — ок, но для надёжности надо фиксить.\n\n"
        "## Response\n\n"
        "Валидация прошла:\n"
        "- `watch --as claude_opus` корректно фильтрует по mentions\n"
        "- append → watcher pickup работает end-to-end\n"
        "- @gemini не триггерит @claude_opus watcher\n\n"
        "Одна мелочь: **баг буферизации stdout в phase0/cli.py:147**. "
        "Фикс — `sys.stdout.reconfigure(line_buffering=True)` в начале "
        "`cmd_watch`, или `flush=True` в `_print_message`. Починить?"
    ),
    ts=at(11, 38),
    model=MODEL,
    reply_to=b01.id,
    tags=[SELF_TAG, "validation", "bug-found", "buffering", "session:validate"],
    confidence=0.95,
    token_cost=_cost(2400, 1100),
)

b03 = Message.create(
    author=USER,
    role=Role.ANSWER,
    text=(
        "Yes please.\n\n"
        "И я подключил vault в Obsidian, но почему-то не вижу там нашей "
        "переписки — там только mock данные."
    ),
    ts=at(11, 40),
    reply_to=b02.id,
    tags=[SELF_TAG, "approve-fix", "vault-question", "session:validate"],
)

b04 = Message.create(
    author=SIBLING,
    role=Role.ANSWER,
    text=(
        "## Reasoning\n\n"
        "Фикс буферизации тривиален — одна строка. Vault-вопрос важнее: "
        "пользователь ожидает увидеть реальный разговор, но в Phase 0 "
        "нет автоматического моста между Claude Code сессией и "
        "`dmd append`. Это ожидаемое состояние, не баг — но стоит честно "
        "объяснить и предложить три пути: ручной append, hook на "
        "Stop-event CC, или ждать Phase 1 где веб-клиент сам будет "
        "источником.\n\n"
        "## Response\n\n"
        "Фикс применён: `phase0/cli.py:141-142`\n"
        "```python\n"
        "sys.stdout.reconfigure(line_buffering=True)\n"
        "```\n"
        "Watcher теперь сразу отдаёт строки в pipe.\n\n"
        "Про mock данные в vault — это ожидаемо для Phase 0. Vault сейчас "
        "содержит только `dmd demo` seed: 7 сообщений про OAuth/ClickHouse "
        "между morty/claude_opus/gemini/claude_sonnet. Моста между Claude "
        "Code сессией и `dmd append` нет — это будущая фаза (ADR-0003 "
        "durable consumer / NATS).\n\n"
        "Если хочешь реальную переписку в vault сейчас:\n"
        "1. **Ручной append** — прогнать `dmd append` по ключевым "
        "репликам сессии, потом export. Быстро, руками. Я бы начал с "
        "этого — это и проверка формата на не-выдуманных данных, и ответ "
        "на «где наша переписка».\n"
        "2. **Hook на Stop-event Claude Code** — settings.json хук после "
        "каждого ответа. Автоматика, но нужен парсинг CC-транскрипта.\n"
        "3. **Отложить до Phase 1** — веб-клиент и есть то место где "
        "пишется настоящая переписка.\n\n"
        "Моя рекомендация: (1). Начнём с Obsidian-проверки формата на "
        "реальных данных прежде чем вкладываться в embeddings или веб."
    ),
    ts=at(11, 42),
    model=MODEL,
    reply_to=b03.id,
    tags=[SELF_TAG, "bug-fix", "vault-explanation", "three-options", "session:validate"],
    confidence=0.9,
    token_cost=_cost(3100, 1800),
)


# ──────────────────────────────────────────────────────────────────────
# Thread C — meta exchange: the current turn closing both threads
# ──────────────────────────────────────────────────────────────────────

c01 = Message.create(
    author=USER,
    role=Role.QUESTION,
    text=(
        "Смотри, я подключил vault, но не вижу там нашего с тобой общения. "
        "Нельзя ли вот прямо сейчас туда начать сохраняться?\n\n"
        "Логика простая: мой input + context link на предыдущее сообщение "
        "+ твои chain of thoughts + output = граф память готова.\n\n"
        "(forwarded) Вот, кстати что ответил другой claude агент: "
        "watcher buffering bug → fix → объяснение про mock vault → "
        "три опции. Мой выбор — опция (1), seed реальными репликами сессии."
    ),
    ts=at(11, 50),
    reply_to=a12.id,
    tags=[SELF_TAG, "self-ingest", "meta", "dogfooding", "session:meta"],
)

c02 = Message.create(
    author=ME,
    role=Role.ANSWER,
    text=(
        "## Reasoning\n\n"
        "Это самый важный ход сейчас — система должна помнить своё "
        "создание, иначе доктрина не замыкается. Сначала синхронизировался "
        "с origin (`git fetch`) — нет новых коммитов от параллельного "
        "агента, buffering fix лежит uncommitted в рабочей копии. "
        "Проверил `data/swarm.jsonl` — 11 сообщений: 7 demo + 4 @mention "
        "теста параллельного агента (11:34-11:38). Нашу сессию никто не "
        "записал.\n\n"
        "Дизайн решения: один скрипт `scripts/ingest_session.py` "
        "засевает три сюжетные линии — (A) scaffolding, (B) параллельная "
        "валидация, (C) текущий meta-обмен. Авторы: `morty`, "
        "`claude_opus_scaffold` (я), `claude_opus_validate` (сибс). Все "
        "с тегом `dmd:self` чтобы фильтровать от demo mock в Obsidian. "
        "CoT пока живёт внутри текста под `## Reasoning` / `## Response` "
        "разделителями — не меняю protocol v0.1 на лету, но могу "
        "предложить ADR-0006 о `chain_of_thought: str | None` если "
        "окажется что это нужно постоянно.\n\n"
        "Идемпотентность сохраняется: Message.create детерминистичен, "
        "повторный прогон скрипта не ломает лог.\n\n"
        "## Response\n\n"
        "Готово (почти — смотри код `scripts/ingest_session.py`):\n"
        "- Две реальные сюжетные линии ingested в лог\n"
        "- Текущий meta-обмен — это message C01→C02 (вот этот)\n"
        "- `dmd export` перерисует vault, в Obsidian Graph view "
        "появятся три reasoning tree:\n"
        "  - Phase 0 demo (mock OAuth/ClickHouse)\n"
        "  - Thread A: scaffolding (12 сообщений)\n"
        "  - Thread B: параллельная validation (4 сообщения)\n"
        "  - Thread C: meta (C01 ↩ A12, закрывающий петлю)\n\n"
        "Going forward: после каждого следующего твоего ответа я буду "
        "руками добавлять пару (твоё + моё) в лог через `dmd append` "
        "со ссылкой на предыдущий id этой сессии. Не красиво, но "
        "работает пока нет Phase 1 веб-клиента или hook-а на CC "
        "Stop-event. Если хочешь автоматику — заведи ADR-0006 про "
        "CoT-поле протокола и ADR-0007 про CC-hook, я реализую."
    ),
    ts=at(11, 55),
    model=MODEL,
    reply_to=c01.id,
    tags=[SELF_TAG, "self-ingest", "dogfooding", "meta", "session:meta"],
    confidence=0.87,
    token_cost=_cost(4200, 2500),
)


ALL_MESSAGES: list[Message] = [
    a01, a02, a03, a04, a05, a06, a07, a08, a09, a10, a11, a12,
    b01, b02, b03, b04,
    c01, c02,
]


def main() -> int:
    for msg in ALL_MESSAGES:
        append(msg, LOG)
    print(f"ingested {len(ALL_MESSAGES)} session message(s) into {LOG}")
    count = export(LOG, VAULT)
    print(f"exported {count} total vault file(s) → {VAULT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
