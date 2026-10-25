# Model watch: Claude Opus 5.5

Verified 2026-09-22 from Anthropic's official model and pricing pages:

- Claude Opus 5.5 launched on 2026-09-22.
- API model ID: `claude-opus-5-5`.
- Standard API pricing: $4 per million input tokens and $20 per million output tokens.
- Anthropic describes typical billed workloads as about 40% cheaper than Opus 5 and performance as comparable to Claude Fable 5.1 on most work.
- Notion's official releases page still listed Opus 5, GPT-5.6 Sol, and Kimi K3 when checked; it did not yet announce Opus 5.5.

Multi-Script therefore ships a future-ready `opus55` Auto profile. It requests the real model only if Notion makes it available to the workspace and chat. Until then it falls back to Standard Auto, never emulates the model, and never claims a model identity Notion does not expose. The request is injected only once at the beginning of each new chat.

Official sources:
- https://www.anthropic.com/claude/opus
- https://platform.claude.com/docs/en/about-claude/pricing
- https://www.notion.com/releases
