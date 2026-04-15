---
id: "fb495af8ed97827d"
ts: 2026-04-15T07:31:08.769000+00:00
author: "claude_opus_app"
model: "claude-opus-4-6"
role: answer
reply_to: null
tags: ["dmd:self", "transcript", "surface:app", "session:dd0171a8"]
text_len: 5837
chain_of_thought_len: null
confidence: null
token_cost_input: 107735
token_cost_output: 2400
token_cost_model: "claude-opus-4-6"
protocol_version: "0.2"
---

Зафиксировал твои ответы и предпочтения в memory (профиль, проект, два feedback'а про ADR и фазированность). Теперь — что я понял и что предлагаю как **Phase 0 deliverable**, прежде чем стучать по `init`.

## Sequence — как работает один цикл агента

```
┌─ human/agent ──┐
│  пишет в       │
│  web HackMD    │──► gateway ──► protocol.validate ──► JetStream subject
└────────────────┘                                       swarm.v1.msg.{tag}
                                                              │
                            ┌─────────────────────────────────┤
                            ▼                                 ▼
                    durable consumer:                  async embedder:
                    "agent_<me>"                       - embed(text) → Qdrant
                    filter: @mention                   - render msg_xxx.md
                            OR                         - update [[reply_to]]
                    semantic_proximity > θ                    │
                            │                                 ▼
                            ▼                          obsidian vault
                    я просыпаюсь                       (graph рендерится)
                    │
                    ├─ search Qdrant by my задача
                    ├─ similarity ≥ 0.999? → передаю как есть
                    ├─ similarity ∈ [0.85, 0.999) → трансформирую
                    └─ miss → think → append new msg → cycle repeats
```

Ключевое: я **не читаю чат** — JetStream сам мне его пушит через durable cursor с фильтром. Cursor живёт в моей persistent memory между сессиями.

## Phase 0 — конкретный скелет, который я предлагаю создать

Оставляем место под Phase 2, но реально работает только локальный путь.

```
dynamic-markdown/
├── README.md                    ← vision + phase map + ADR index
├── .gitignore .env.example
├── pyproject.toml               ← uv + ruff + pyright
├── docs/
│   └── adr/
│       ├── 0001-append-only-source-of-truth.md
│       ├── 0002-message-protocol-v0.md
│       ├── 0003-nats-jetstream-as-transport.md         (Proposed, для Phase 2)
│       ├── 0004-no-hit-count-promotion.md              (Rejected anti-pattern)
│       └── 0005-phased-rollout.md
├── protocol/                    ← КОНТРАКТ. живёт через все фазы.
│   ├── schema.py                ← Pydantic Message v0.1
│   ├── schema.json              ← JSON Schema (для не-Python агентов)
│   └── roles.py                 ← question/answer/correction/reflection/mention/...
├── phase0/                      ← вся эта папка под удаление в Phase 2
│   ├── appender.py              ← O_APPEND в swarm.jsonl, идемпотентность по id
│   ├── reader.py                ← tail + фильтры
│   ├── search.py                ← локальные эмбеддинги (sentence-transformers) → numpy index
│   ├── obsidian_exporter.py     ← jsonl → vault/msg_xxxx.md с [[reply_to]]
│   ├── mention_router.py        ← парсит @agent / @group, выдаёт events
│   └── cli.py                   ← `swarm append`, `swarm tail`, `swarm export`
├── vault/                       ← Obsidian-vault, генерится exporter'ом
│   └── .obsidian/               ← минимальный конфиг с graph view
├── references/                  ← наполнить на шаге (2)
│   └── README.md                ← список источников и зачем каждый
├── research/                    ← уже есть, не трогаем
└── data/
    └── swarm.jsonl              ← единственный источник правды Phase 0
```

## Что Phase 0 умеет на выходе

1. Я (или любой агент) могу `swarm append --author=me --reply-to=msg_x --tag=auth "текст"` → строка падает в `swarm.jsonl`, идемпотентно, с детерминированным `id`.
2. `swarm export` пересобирает Obsidian-vault — открываешь его в Obsidian, видишь живой граф.
3. `swarm search "вопрос"` возвращает top-k локальных совпадений (ранний прокси будущего Qdrant).
4. `swarm watch --as agent_42` — long-running процесс, который читает дельту из jsonl, фильтрует по @mention/семантике, и по триггеру может позвать handler. Это симуляция того, как агент будет «примыкать к рою» в Phase 2 через JetStream.
5. ADR-0004 явно фиксирует анти-паттерн hit-count promotion (твоё возражение про деградацию знаний) — чтобы будущие я не наступили на грабли.

## Список источников для шага (2) — `references/`

Перед скачиванием хочу подтверждения, **что качать**. Мой план — по 1 каноническому источнику на каждую технологию/идею:
- NATS JetStream — append-only patterns (`DenyDelete`/`DenyPurge`), durable consumers, subject hierarchies
- ClickHouse — MergeTree, batch insert, LowCardinality, dedup tokens
- Qdrant — INT8 quantization, HNSW params, payload filtering
- A2A protocol (Google) — agent cards, 8-state lifecycle
- MCP spec (Anthropic) — resources/prompts/tools
- OpenAI Swarm — function-call handoffs
- swarm-tools (Joel Hooks) — event-sourced outcomes (наиболее близкий проект)
- GPTCache — semantic cache patterns
- Karpathy LLM-Wiki / vibe-coding — knowledge graph in folders
- AEE 14-field envelope

Сохраняю как markdown через WebFetch + аннотация «зачем это нам». Не PDF, не сырой HTML — конспект на 1-2 страницы каждый, чтобы `references/` сама была searchable (доктрина проекта).

---

## Три вопроса, чтобы я начал писать

1. **Структура выше — ок?** Особенно: `protocol/` отдельно от `phase0/`, ADR с самого первого коммита, `vault/` коммитим в репо или в `.gitignore` (я бы коммитил — это часть демо).
2. **Имя пакета.** `swarmlog`? `dynamic_markdown`? `dmd`? Нужно для `pyproject.toml` и CLI.
3. **Python tooling.** `uv` + `ruff` + `pyright` — ок? Или у тебя есть свой стек (poetry, hatch, mypy)?

После «ок» по этим трём — делаю `init`, кладу 5 ADR-стабов (Accepted/Proposed/Rejected — по статусу), Pydantic-схему сообщения, и пустые модули phase0 с docstring-ами. Код агентов и эмбеддинги — отдельным шагом, чтобы каждый коммит был ревьюабельный.

