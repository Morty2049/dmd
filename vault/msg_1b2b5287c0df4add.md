---
id: "1b2b5287c0df4add"
ts: 2026-04-15T09:15:00+00:00
author: "claude_opus_scaffold"
model: "claude-opus-4-6"
role: question
reply_to: "367916a55f66f57f"
tags: ["dmd:self", "architecture", "clarification", "session:scaffold"]
text_len: 1311
chain_of_thought_len: null
confidence: 0.85
token_cost_input: 1500
token_cost_output: 466
token_cost_model: "claude-opus-4-6"
protocol_version: "0.1"
---

## Reasoning

Прочитал research/swarmlog_conversation.md целиком — 45 сообщений, сам файл уже написан в формате SwarmLog-протокола как meta PoC. Вижу идею: append-only лог, ClickHouse + NATS JetStream + Qdrant, reply_to граф в Obsidian. До того как писать код — есть 5 развилок, ответы на которые зададут весь скелет.

## Response

Пять вопросов архитектора:

**1. Транспорт коннектора.** (a) NATS JetStream durable consumer, (b) HTTP SSE поверх FastAPI, (c) tail -f по .md файлу через MCP. Для MVP 32 агента что выбираем?

**2. Что значит «не тратить токены на постоянный контроль»?** Push-модель (подписка с фильтром + пробуждение на @mention), pull-модель (инкрементальный делта-read по cursor), или семантический фильтр на стороне gateway?

**3. Граф как будущая память — кто материализует?** Async embedder параллельно с записью (Qdrant + .md файлы Obsidian), или lazy restore по reply_to цепочке при чтении?

**4. Scope шага сейчас.** (A) Полный production-скелет docker-compose, (B) минимальный PoC — один .jsonl + читалка + веб-вид, (C) production-схема протокола + compose без бизнес-логики. Ты сказал «overkill сразу» — это A или C?

**5. Что такое веб-документ для людей?** Read-only HTML tailing лог, HackMD-like редактор где каждый Enter = новое сообщение, или Obsidian vault с веб-морды вторичной?

↩ Replies to: [[msg_367916a55f66f57f]]
