# Anthropic Claude API Integration into AI Assistant Panel

**Date:** 2026-08-25
**Status:** Approved
**Scope:** Backend LLM dispatch + frontend config UI

## Goal

Enable the AI Assistant Panel (floating chat widget) to use Claude models via the Anthropic API directly, with native tool calling support.

## Background

The AI Assistant Panel (`apps/ai_assistant/`) currently calls any OpenAI-compatible endpoint via `httpx`. The `anthropic==0.75.0` SDK is already installed. The `AIModelConfig` model manages LLM configurations centrally. This change adds a new model type `anthropic_claude` and wires it into the assistant's tool-calling loop.

## Architecture

### Dispatch Flow

```
call_llm_with_tools(messages, tools)
  ├─ config.model_type == 'anthropic_claude'
  │    → call_anthropic(config, messages, tools)
  │        uses: anthropic.Anthropic(api_key=...)
  ├─ config.model_type == 'bedrock_claude'
  │    → call_anthropic_bedrock(config, messages, tools)
  │        uses: anthropic.AnthropicBedrock(aws_access_key=...)
  └─ otherwise
       → call_openai_compatible(config, messages, tools)  [existing logic]
```

### Format Conversion

Three conversions, all in `base.py`:

**1. Tools: OpenAI → Anthropic**

```
OpenAI:     {"type": "function", "function": {"name": N, "description": D, "parameters": P}}
Anthropic:  {"name": N, "description": D, "input_schema": P}
```

**2. Messages: OpenAI → Anthropic**

- Extract messages with `role == 'system'` → join into the `system` parameter string.
- `role == 'user'` / `role == 'assistant'` → pass through as-is (content as string).
- `role == 'assistant'` with `tool_calls` → convert to Anthropic's `tool_use` content blocks.
- `role == 'tool'` → convert to `role: 'user'` with `tool_result` content block, matching `tool_use_id`.

**3. Response: Anthropic → normalized dict**

Anthropic returns `message.content` as a list of content blocks (`TextBlock`, `ToolUseBlock`). Normalize to the same dict shape `run_tool_loop` already expects:

```python
{
    "choices": [{
        "message": {
            "content": "<text or empty>",
            "tool_calls": [
                {"id": "toolu_xxx", "function": {"name": N, "arguments": "{...}"}, "type": "function"}
            ]  # omitted if no tool use
        },
        "finish_reason": "tool_calls" if stop_reason == "tool_use" else "stop"
    }]
}
```

This keeps `run_tool_loop()` completely unchanged.

### Model Config

Add `('anthropic_claude', 'Anthropic Claude')` to `AIModelConfig.MODEL_CHOICES`.

For `anthropic_claude` type, required fields:
- `api_key`: Anthropic API key
- `model_name`: e.g. `claude-sonnet-4-20250514`

Optional fields:
- `base_url`: for proxy setups (defaults to `https://api.anthropic.com`)
- `max_tokens`, `temperature`: respected as-is

### Error Handling

| Anthropic Exception | HTTP Status | User Message |
|---|---|---|
| `AuthenticationError` | 503 | API Key 无效，请检查配置 |
| `RateLimitError` | 503 | 请求频率超限，请稍后重试 |
| `BadRequestError` | 503 | 请求参数异常 |
| `APIError` (other) | 500 | AI 服务异常 + error message |

Timeout: 120 seconds (tool calling can be slow).

## Files Changed

| File | Change |
|---|---|
| `apps/requirement_analysis/models.py:203` | Add `anthropic_claude` to `MODEL_CHOICES` |
| `apps/ai_assistant/tools/base.py` | Add `call_anthropic()`, `call_anthropic_bedrock()`, format converters; refactor `call_llm_with_tools()` to dispatch |
| `frontend/src/views/requirement-analysis/AIModelConfig.vue` | Conditional field display for anthropic_claude type |

No database migration needed — Django CharField choices are app-level only.

## Out of Scope

- Streaming responses (can be added later)
- Anthropic prompt caching (future optimization)
- Modifying the Dify assistant or requirement analysis flows
