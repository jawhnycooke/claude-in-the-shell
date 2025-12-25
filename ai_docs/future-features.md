# Future Features

Potential enhancements for the Reachy Agent, logged for future consideration.

---

## Multi-LLM Backend Architecture

**Status**: Planned
**Priority**: Medium
**Estimated Effort**: ~32 hours

### Overview

Add pluggable LLM backend support with rule-based routing to enable multiple LLMs working together, each handling what it does best.

### Use Cases

- **Amazon Nova Sonic** for voice I/O (STT/TTS with streaming)
- **Claude** for reasoning and tool calling
- **Ollama** for offline fallback when API unavailable

### Architecture

```
User Input → Task Type Detection → LLM Router
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              ClaudeBackend    NovaSonicBackend   OllamaBackend
              (reasoning,      (voice I/O,        (offline
               tools)           streaming)         fallback)
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `LLMBackend` ABC | Abstract interface all providers implement |
| `LLMRouter` | Rule-based selection with fallback chain |
| `LLMConfig` | Config-driven provider settings and routing rules |

### Proposed Module Structure

```
src/reachy_agent/llm/
    __init__.py          # Public exports
    schemas.py           # LLMRequest, LLMResponse, TaskType
    router.py            # Rule-based routing
    config.py            # Provider configurations
    backends/
        base.py          # LLMBackend ABC
        claude.py        # Anthropic Claude
        nova.py          # Amazon Nova Sonic (Bedrock)
        ollama.py        # Ollama local
```

### Config Example

```yaml
llm:
  default_backend: claude
  fallback_chain: [claude, ollama]

  routing_rules:
    - name: voice_to_nova
      task_types: [voice_input, voice_output]
      backend: nova
      priority: 100

    - name: tools_to_claude
      has_tools: true
      backend: claude
      priority: 90
```

### Architectural Considerations

1. **Tool Calling Compatibility**: Different LLMs have different tool support (Claude full, Ollama limited)
2. **Context Window Differences**: Claude 200K, Nova ~128K, Ollama 4-8K
3. **Streaming Behavior**: Nova Sonic has bidirectional streaming for voice
4. **Credential Management**: Three different auth patterns (API key, AWS, none)
5. **Error Handling**: Different failure modes require different recovery strategies

### Prerequisites

- Complete Phase 2 (Hardware Integration) first
- Perception layer for voice I/O (wake word, STT pipeline)
- AWS account for Nova Sonic access

### Dependencies

```txt
boto3>=1.35.0      # AWS SDK for Nova Sonic
botocore>=1.35.0   # AWS core
```

### Related Files

- `src/reachy_agent/agent/agent.py` - Current Claude-only implementation
- `src/reachy_agent/utils/config.py` - Already has `offline_llm_model` field
- `config/default.yaml` - Would add `llm:` section

### References

- [Amazon Nova Sonic](https://aws.amazon.com/bedrock/nova/) - AWS voice LLM
- [Ollama](https://ollama.ai/) - Local LLM runner
- [Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) - AWS tool calling

---

## Additional Future Ideas

### Perception Pipeline (Phase 2 Prerequisite)

- Wake word detection with OpenWakeWord
- Local STT with whisper.cpp
- Local TTS with Piper
- Spatial audio localization

### Memory System (Phase 3)

- ChromaDB for semantic memory
- SQLite for structured storage
- Conversation summarization

### External Integrations (Phase 4)

- Home Assistant MCP
- Google Calendar MCP
- GitHub MCP
