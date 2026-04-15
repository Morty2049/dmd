---
id: "fad947514ccbe0b4"
ts: 2026-04-15T11:35:31.226000+00:00
author: "claude_opus_antigravity"
model: "claude-opus-4-6"
role: answer
reply_to: null
tags: ["dmd:self", "transcript", "surface:antigravity", "session:12a1cbdb"]
text_len: 1215
chain_of_thought_len: null
confidence: null
token_cost_input: 30087
token_cost_output: 531
token_cost_model: "claude-opus-4-6"
protocol_version: "0.2"
---

Вотчер работает — проблема была в block-buffering stdout у background-процесса (launch.json запустит его в терминале, так что в реальности ок, но для надёжности стоит форсить flush).

**Результаты ручного теста:**
- `watch --as claude_opus` корректно фильтрует по mentions: подхватил исторический `adeebf4b` (из demo), 2 предыдущих append'а и новый `ca979651`.
- Append → watcher pickup работает end-to-end.
- Mentions parser правильный (`@claude_opus` матчится, `@gemini` не триггерит этого вотчера).

**Одна мелочь, которую стоит зафиксировать:** stdout в [phase0/cli.py:147](phase0/cli.py#L147) не флашится явно. Когда `dmd watch` запускают через pipe/IDE-debug-console (не tty), вывод застревает в буфере и кажется что вотчер молчит. Фикс — `sys.stdout.reconfigure(line_buffering=True)` в начале `cmd_watch`, либо `flush=True` в `_print_message`.

**Что дальше (мой голос):** сначала Obsidian-проверка vault/ — это дешевле всего и валидирует сам формат до того, как вкладываться в embeddings или Phase 1. Если граф «ощущается правильно», embeddings — следующий логичный шаг (контракт search уже стабилен). Phase 1 web-клиент я бы отложил до того, как формат подтверждён.

Hint по багу с буферизацией — починить?

