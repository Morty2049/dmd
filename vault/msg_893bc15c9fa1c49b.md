---
id: "893bc15c9fa1c49b"
ts: 2026-04-15T17:35:40.353000+00:00
author: "claude_opus_antigravity"
model: "claude-opus-4-6"
role: answer
reply_to: null
tags: ["dmd:self", "transcript", "surface:antigravity", "session:3e8336ea"]
text_len: 1935
chain_of_thought_len: null
confidence: null
token_cost_input: 32393
token_cost_output: 931
token_cost_model: "claude-opus-4-6"
protocol_version: "0.2"
---

# Транскрипт Claude Code — устройство

Полная спецификация лежит в [docs/adr/0008-transcript-native-format.md](docs/adr/0008-transcript-native-format.md). Кратко:

**Где живёт.** Каждая сессия каждой Claude-поверхности (app / Antigravity / CLI) пишется на диск в:
```
~/.claude/projects/<slug>/<session-uuid>.jsonl
```
где `<slug>` — абсолютный `cwd` с заменой `/` → `-`. Для этого репо:
`-Users-leks-codeRepo-my-projects-dynamic-markdown`.

**Формат — JSONL, одна строка = одно событие.** Ключевые поля ([0008:63-88](docs/adr/0008-transcript-native-format.md#L63-L88)):

- `type`: `user` | `assistant` | `system` | `queue-operation` | `attachment` | `file-history-snapshot` | `ai-title`
- `uuid` / `parentUuid` — образуют дерево (родитель → потомок)
- `timestamp`, `sessionId`, `cwd`, `gitBranch`, `version`
- `entrypoint` — дискриминатор поверхности (`claude-desktop` / `claude-vscode` / `claude-cli`)
- `isSidechain` — `true` для запусков субагентов
- `message` — `{role, content, model?, usage?, stop_reason?}`, где `content` либо строка, либо список блоков:
  - `{type:"text", text}`
  - `{type:"thinking", thinking, signature}` — внутренние рассуждения
  - `{type:"tool_use", name, input, id}`
  - `{type:"tool_result", tool_use_id, content, is_error?}`
- `usage` (только на assistant): `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`

**Как мы это маппим в dmd.** Детерминированно, без LLM-в-петле ([scripts/ingest_claude_transcript.py](scripts/ingest_claude_transcript.py)): пропускаем инфраструктурные типы и сайдчейны, одну строку → одно `Message`, `thinking`-блоки уезжают в `chain_of_thought` (v0.2, [ADR-0006](docs/adr/0006-chain-of-thought-field.md)), `parentUuid` → `reply_to`, `usage` → `token_cost`, автор выводится из `entrypoint` по [ADR-0007](docs/adr/0007-author-namespace.md). Маппер идемпотентен: `Message.create` хеширует `(author, ts, text)`, повторный прогон — no-op.

