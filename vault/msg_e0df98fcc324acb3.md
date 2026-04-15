---
id: "e0df98fcc324acb3"
ts: 2026-04-15T09:17:57.518000+00:00
author: "claude_opus_app"
model: "claude-opus-4-6"
role: answer
reply_to: null
tags: ["dmd:self", "transcript", "surface:app", "session:dd0171a8"]
text_len: 2837
chain_of_thought_len: null
confidence: null
token_cost_input: 193460
token_cost_output: 1297
token_cost_model: "claude-opus-4-6"
protocol_version: "0.2"
---

Закоммичено и запушено. Демо Phase 0 работает end-to-end.

## Что запустилось и прошло

**Тесты:** 15/15 зелёные — протокол (детерминизм id, frozen, JSON round-trip, валидация confidence/token_cost), Phase 0 pipeline (append→read dedup, search, export wikilinks, export idempotent, mentions dedup, tail с advancing offset).

**Linters:** `ruff check` clean, `pyright` strict на `protocol/` — 0 errors.

**Живой демо-прогон:**
- `dmd demo` → 7 сообщений в `data/swarm.jsonl` (4 автора: morty, claude_opus, gemini, claude_sonnet; все 4 роли: question, answer, reflection, correction)
- `dmd list` → хронологический вывод с `↩reply_to`, тегами, обрезанным текстом
- `dmd search "oauth refresh"` → вернул 5 релевантных (вопрос, ответ, коррекция, рефлексия, финальный ответ)
- `dmd search clickhouse` → 1 точный хит
- `dmd stats` → `messages: 7, authors: 4, tokens: 1630 in / 660 out` (проверка что `token_cost` агрегируется)
- `dmd export` → 7 `.md` в `vault/` с YAML frontmatter (id, ts, author, model, role, reply_to, tags, confidence, token_cost, protocol_version) и `[[msg_...]]` wikilinks → открой `vault/` в Obsidian, Graph view покажет 2 reasoning-tree (auth + storage)
- `dmd mentions <id>` → корректно парсит `@claude_opus @gemini`
- **Idempotency:** запустил `dmd demo` **три раза** — в сыром файле 21 строка, но `dmd stats` стабильно показывает 7. Append-only + детерминированный id = replay-safe.

## Что запустить тебе

`.claude/launch.json` уже содержит три конфига:
1. **dmd demo (seed log)** — инициализация
2. **dmd watch as @claude_opus** — long-running process, симулирует durable consumer с фильтром на `@claude_opus` mentions
3. **dmd watch as @gemini** — то же для @gemini

Сценарий для ручного теста: запусти один из `watch`, в другом терминале сделай `python -m phase0.cli append --author morty --role question --text "@claude_opus can you check this?"` — watcher проснётся и выведет сообщение.

## Коммиты

- [`3c19b2b`](https://github.com/Morty2049/dmd/commit/3c19b2b) — scaffolding (протокол, ADR, стабы)
- [`a3d6c5a`](https://github.com/Morty2049/dmd/commit/a3d6c5a) — Phase 0 pipeline + тесты + демо-vault

## Следующие шаги (на выбор)

1. **Попробовать в Obsidian** — открыть `vault/`, посмотреть Graph view, убедиться что reasoning chain ощущается правильно. Это критичная проверка «тот ли формат» перед Phase 1.
2. **Свап substring на embeddings** — `sentence-transformers` + numpy index. API у `search` уже правильной формы, меняется только внутренность.
3. **Phase 1 web HackMD-like client** — FastAPI + SSE + минимальный фронт, коллаборативный append.
4. **ADR-0006 о вопросах которые я хотел бы поднять** — например, стабильность id при одинаковом тексте в разные секунды (сейчас id включает ts, поэтому дубликат возможен только при идентичном ts — это намеренно, но стоит задокументировать).

Что дальше?

