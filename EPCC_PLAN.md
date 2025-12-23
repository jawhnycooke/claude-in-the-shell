# Plan: Reachy Agent - Embodied AI System

**Created**: December 2024 | **Effort**: ~200h across 4 phases | **Complexity**: Complex

---

## 1. Objective

**Goal**: Transform Reachy Mini into an autonomous Claude-powered AI agent with perception, memory, expression, and external service integration.

**Why**: Create an open-source reference implementation of embodied AI that bridges cloud intelligence with physical robotics, while documenting the journey for the developer community.

**Success Criteria**:
1. Agent responds to "Hey Reachy" wake word and executes multi-step tasks via MCP
2. Reliable 8+ hour continuous operation with <1% crash rate
3. 5+ working MCP integrations (Reachy body, Home Assistant, Calendar, GitHub, Weather)
4. Graceful degradation when offline (Ollama + Piper fallback functional)
5. Privacy indicators via antenna states visible to user

---

## 2. Approach

### Architecture Summary

**From TECH_REQ.md**: Layered monolith with MCP sidecar pattern, single asyncio process for MVP.

```
Claude API (cloud)
       │
       ▼
┌──────────────────────────────┐
│     Claude Agent SDK         │
│  (Agent Loop + Hooks)        │
└──────────────────────────────┘
       │ MCP Protocol
       ▼
┌──────────────────────────────┐
│     Reachy Agent Core        │
│  Perception│Memory│Privacy   │
└──────────────────────────────┘
       │ HTTP :8000
       ▼
┌──────────────────────────────┐
│     Reachy Daemon (Pollen)   │
│  Motors│Camera│Audio│IMU     │
└──────────────────────────────┘
```

### Key Technology Decisions (from TECH_REQ.md)

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Wake word | OpenWakeWord | Open source, no license, customizable |
| Memory | ChromaDB + SQLite | Lightweight, persistent, Python native |
| Embeddings | Hybrid (local + API) | Real-time local, quality from reindexing |
| Offline LLM | Ollama + Llama 3.2 3B | Easy setup, fits Pi RAM |
| TTS fallback | Piper | Neural quality, Pi optimized |
| Config | YAML + JSON Schema | Human-readable, machine-validatable |
| Process | Single asyncio | Lower memory, simpler debugging |

### Integration Points

- **Reachy Daemon** (Pollen): HTTP API on localhost:8000
- **Claude API**: HTTPS to api.anthropic.com
- **Home Assistant**: REST API via MCP server
- **Google Calendar**: OAuth2 + Calendar API
- **GitHub**: Personal access token + REST API

### Trade-offs Made

| Decision | Chosen | Alternative | Rationale |
|----------|--------|-------------|-----------|
| Process model | Single asyncio | systemd services | Simpler for MVP, can migrate later |
| Config format | YAML | JSON | Human-readable for users |
| Wake word | OpenWakeWord | Porcupine | No license cost, open source |

---

## 3. Tasks

### Phase 1: Foundation (~50h)

*Goal: Validate architecture in simulation before hardware arrives*

#### 1.1 Project Scaffolding (~8h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **1.1.1** Create project structure | 2h | Set up `src/`, `config/`, `tests/`, `scripts/` per TECH_REQ directory layout | None | L |
| **1.1.2** Configure pyproject.toml | 1h | Dependencies, dev tools, entry points | 1.1.1 | L |
| **1.1.3** Create requirements files | 1h | Split prod/dev, pin versions | 1.1.2 | L |
| **1.1.4** Set up config schema | 2h | JSON Schema for config validation, Pydantic models | 1.1.1 | L |
| **1.1.5** Create .env.example | 0.5h | Template for API keys | 1.1.1 | L |
| **1.1.6** Set up logging infrastructure | 1.5h | structlog, JSON format, file rotation | 1.1.1 | L |

#### 1.2 Reachy MCP Server (~16h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **1.2.1** Create MCP server skeleton | 3h | Use `mcp` SDK, `create_sdk_mcp_server` | 1.1.1 | M |
| **1.2.2** Implement move_head tool | 2h | Direction enum, speed control, daemon HTTP call | 1.2.1 | M |
| **1.2.3** Implement speak tool | 2h | Text-to-speech via daemon, queue management | 1.2.1 | M |
| **1.2.4** Implement play_emotion tool | 3h | Emotion sequences, antenna coordination | 1.2.1 | M |
| **1.2.5** Implement capture_image tool | 2h | Camera frame capture, optional analysis | 1.2.1 | M |
| **1.2.6** Implement remaining body tools | 3h | set_antenna_state, get_sensor_data, look_at_sound, dance | 1.2.2-1.2.5 | L |
| **1.2.7** Create daemon mock for testing | 1h | FastAPI mock of Reachy daemon for local dev | 1.2.1 | L |

#### 1.3 Claude Agent SDK Integration (~12h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **1.3.1** Install and configure SDK | 2h | ARM64 considerations, validate on dev machine | 1.1.2 | M |
| **1.3.2** Create agent options module | 2h | ClaudeAgentOptions, model selection, permissions | 1.3.1 | L |
| **1.3.3** Implement main agent loop | 3h | Perceive → Think → Act cycle, asyncio integration | 1.3.2 | M |
| **1.3.4** Register MCP server with agent | 2h | In-process MCP connection, tool discovery | 1.2.1, 1.3.3 | M |
| **1.3.5** Create CLAUDE.md personality | 2h | System prompt per Appendix A in PRD | 1.3.3 | L |
| **1.3.6** Implement context building | 1h | Inject current time, state, memories into prompt | 1.3.5 | L |

#### 1.4 Permission System (~8h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **1.4.1** Create permission tier models | 2h | Pydantic models from TECH_REQ schema | 1.1.4 | L |
| **1.4.2** Implement PreToolUse hook | 3h | Pattern matching, tier evaluation | 1.4.1, 1.3.3 | M |
| **1.4.3** Create permissions.yaml config | 1h | Default rules per TECH_REQ | 1.4.1 | L |
| **1.4.4** Implement permission audit logging | 2h | SQLite, ToolExecution schema | 1.4.2 | L |

#### 1.5 Simulation Testing (~6h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **1.5.1** Set up MuJoCo environment | 2h | Install MuJoCo, Reachy model | None | M |
| **1.5.2** Create simulation adapter | 2h | Bridge MCP server to MuJoCo instead of daemon | 1.2.7, 1.5.1 | M |
| **1.5.3** Validate end-to-end in simulation | 2h | Multi-turn conversation, tool execution | 1.5.2, 1.3.4 | M |

**Phase 1 Exit Criteria**:
- [x] Agent controls simulated Reachy via MCP
- [x] Multi-turn conversations work
- [x] Permissions enforced (Tier 1 auto, Tier 4 blocked)

**Phase 1 Status: ✅ COMPLETE** (December 2024)

---

### Phase 2: Hardware Integration (~50h)

*Goal: Running on physical Reachy Mini with voice activation*

#### 2.1 Pi Environment Setup (~8h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **2.1.1** Install Raspberry Pi OS | 1h | 64-bit, configure WiFi, SSH | None | L |
| **2.1.2** Install Reachy daemon | 2h | Pollen SDK, verify daemon startup | 2.1.1 | M |
| **2.1.3** Install Claude Code CLI | 2h | Native installer, ARM64 validation | 2.1.1 | M |
| **2.1.4** Install Python dependencies | 2h | uv, requirements, verify ARM64 wheels | 2.1.3 | M |
| **2.1.5** Configure systemd service | 1h | reachy-agent.service per TECH_REQ | 2.1.4 | L |

#### 2.2 Wake Word Detection (~10h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **2.2.1** Install OpenWakeWord | 2h | pip install, model download | 2.1.4 | M |
| **2.2.2** Create audio capture module | 3h | PyAudio, 4-mic array handling | 2.1.4 | M |
| **2.2.3** Implement wake word detector | 3h | "Hey Reachy" detection, callback | 2.2.1, 2.2.2 | M |
| **2.2.4** Tune sensitivity | 2h | False positive < 1/hour, latency < 500ms | 2.2.3 | M |

#### 2.3 Attention State Machine (~8h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **2.3.1** Create attention state model | 2h | Passive/Alert/Engaged enum, transitions | 1.1.1 | L |
| **2.3.2** Implement passive mode | 2h | Wake word only, minimal CPU | 2.2.3, 2.3.1 | L |
| **2.3.3** Implement alert mode | 2h | Motion/face detection triggers | 2.3.2 | M |
| **2.3.4** Implement engaged mode | 2h | Full agent loop, timeout to alert | 2.3.3 | L |

#### 2.4 Privacy Indicators (~4h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **2.4.1** Map antenna positions to states | 1h | down=passive, mid=alert, up=engaged | 1.2.4 | L |
| **2.4.2** Implement indicator controller | 2h | Async antenna updates on state change | 2.3.1, 2.4.1 | L |
| **2.4.3** Add smooth transitions | 1h | Easing functions, no jarring movements | 2.4.2 | L |

#### 2.5 Graceful Degradation (~12h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **2.5.1** Create health monitor | 3h | CPU temp, memory, API latency checks | 2.1.4 | M |
| **2.5.2** Implement degradation modes | 3h | Full → Offline → Thermal → Safe | 2.5.1 | M |
| **2.5.3** Install Piper TTS | 2h | Local neural TTS for offline speech | 2.1.4 | L |
| **2.5.4** Install Ollama + Llama 3.2 | 3h | Local LLM for offline mode | 2.1.4 | M |
| **2.5.5** Implement mode switching | 1h | Detect network loss, switch to fallbacks | 2.5.2-2.5.4 | M |

#### 2.6 Hardware Validation (~8h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **2.6.1** Test head movement range | 2h | Verify all 6 DOF, speed control | 1.2.2 | M |
| **2.6.2** Test audio pipeline | 2h | Wake word → STT → agent → TTS | 2.2.3, 1.3.3 | M |
| **2.6.3** Test camera capture | 1h | Verify capture_image tool | 1.2.5 | L |
| **2.6.4** Stress test 8-hour operation | 3h | Monitor crash rate, memory leaks | All Phase 2 | H |

**Phase 2 Exit Criteria**:
- [ ] Voice-activated agent on physical robot
- [ ] Reliable 8-hour operation
- [ ] Graceful handling of WiFi disconnection

---

### Phase 3: Intelligence Layer (~50h)

*Goal: Rich perception, memory, and expression*

#### 3.1 Memory System (~16h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **3.1.1** Install ChromaDB | 1h | pip install, persistent storage path | 2.1.4 | L |
| **3.1.2** Create memory models | 2h | Memory, MemoryMetadata per TECH_REQ schema | 1.1.4 | L |
| **3.1.3** Implement short-term memory | 2h | Session buffer, last N interactions | 3.1.2 | L |
| **3.1.4** Implement long-term memory | 4h | ChromaDB storage, semantic retrieval | 3.1.1, 3.1.2 | M |
| **3.1.5** Install sentence-transformers | 1h | all-MiniLM-L6-v2 model | 2.1.4 | L |
| **3.1.6** Implement hybrid embedding | 3h | Local for real-time, API for reindexing | 3.1.5 | M |
| **3.1.7** Integrate memory with agent | 3h | Context building from relevant memories | 3.1.4, 1.3.6 | M |

#### 3.2 Spatial Audio (~10h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **3.2.1** Install pyroomacoustics | 1h | DOA estimation library | 2.1.4 | L |
| **3.2.2** Calibrate mic positions | 2h | Map physical array to algorithm | 3.2.1, 2.2.2 | M |
| **3.2.3** Implement DOA estimation | 3h | Direction of arrival, ±15° accuracy | 3.2.2 | M |
| **3.2.4** Implement look_at_sound | 2h | Map DOA to head movement | 3.2.3, 1.2.2 | M |
| **3.2.5** Multi-speaker tracking | 2h | Track active speaker in room | 3.2.3 | H |

#### 3.3 IMU Interaction (~8h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **3.3.1** Read IMU via daemon API | 2h | Accelerometer sampling at 50Hz | 2.1.2 | L |
| **3.3.2** Implement tap detection | 2h | Threshold-based event detection | 3.3.1 | M |
| **3.3.3** Implement pickup detection | 2h | Sustained acceleration change | 3.3.1 | M |
| **3.3.4** Create IMU event responses | 2h | Agent reactions to physical touch | 3.3.2, 3.3.3 | L |

#### 3.4 Antenna Expression Language (~10h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **3.4.1** Create expression schema | 2h | YAML format per TECH_REQ Expression schema | 1.1.4 | L |
| **3.4.2** Define 10+ expressions | 2h | happy, sad, curious, thinking, etc. | 3.4.1 | L |
| **3.4.3** Implement expression engine | 3h | Play sequences, blend expressions | 3.4.2 | M |
| **3.4.4** Add easing functions | 1h | Natural motion curves | 3.4.3 | L |
| **3.4.5** Integrate with agent emotions | 2h | Auto-expression based on response tone | 3.4.3, 1.3.3 | M |

#### 3.5 Personality Engine (~6h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **3.5.1** Create personality state model | 2h | Mood, energy per TECH_REQ schema | 1.1.4 | L |
| **3.5.2** Implement state persistence | 2h | SQLite storage, load on startup | 3.5.1 | L |
| **3.5.3** Inject personality into prompt | 2h | Dynamic CLAUDE.md context section | 3.5.2, 1.3.5 | L |

**Phase 3 Exit Criteria**:
- [ ] Robot remembers context across sessions
- [ ] Responds to physical interaction (tap, pickup)
- [ ] Expressive antenna behavior matches conversation tone

---

### Phase 4: Polish & Extensibility (~50h)

*Goal: Ready for users and community*

#### 4.1 Setup Wizard (~10h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **4.1.1** Install Rich library | 0.5h | Terminal UI framework | 2.1.4 | L |
| **4.1.2** Create wizard flow | 3h | Welcome, API key, integrations, test | 4.1.1 | L |
| **4.1.3** Implement API key validation | 1h | Test Claude API connectivity | 4.1.2 | L |
| **4.1.4** Implement hardware tests | 2h | Test motors, camera, audio | 4.1.2 | M |
| **4.1.5** Generate config from wizard | 2h | Write config.yaml from answers | 4.1.2 | L |
| **4.1.6** Create install.sh script | 1.5h | One-line install for Pi | All previous | L |

#### 4.2 External MCP Integrations (~18h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **4.2.1** Implement Weather MCP | 2h | Simple read-only, OpenWeather API | 1.2.1 | L |
| **4.2.2** Implement Home Assistant MCP | 4h | Entity control, state reading | 1.2.1 | M |
| **4.2.3** Implement Google Calendar MCP | 4h | OAuth2 flow, event reading, creation | 1.2.1 | M |
| **4.2.4** Implement GitHub MCP | 4h | Notifications, PR status, issues | 1.2.1 | M |
| **4.2.5** Create integration registry | 2h | Dynamic MCP server loading | 4.2.1-4.2.4 | L |
| **4.2.6** Add permissions for integrations | 2h | Per-integration tier config | 4.2.5, 1.4.1 | L |

#### 4.3 Testing & Quality (~12h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **4.3.1** Write unit tests | 4h | 80% coverage target, pytest | All modules | L |
| **4.3.2** Write integration tests | 4h | MCP → daemon mock, agent loop | 4.3.1 | M |
| **4.3.3** Create test fixtures | 2h | conftest.py, mock responses | 4.3.1 | L |
| **4.3.4** Set up CI pipeline | 2h | GitHub Actions, lint + test | 4.3.1-4.3.3 | L |

#### 4.4 Documentation (~10h)

| Task | Effort | Description | Deps | Risk |
|------|--------|-------------|------|------|
| **4.4.1** Write README.md | 2h | Quick start, architecture overview | All | L |
| **4.4.2** Write setup guide | 2h | Detailed installation for Pi | 4.1.6 | L |
| **4.4.3** Document permissions system | 2h | Tier explanation, customization | 1.4.3 | L |
| **4.4.4** Document expression library | 2h | How to create custom expressions | 3.4.2 | L |
| **4.4.5** Create troubleshooting guide | 2h | Common issues, solutions | All | L |

**Phase 4 Exit Criteria**:
- [ ] New user can set up in 30 minutes using wizard
- [ ] 3+ external services connected (Home Assistant, Calendar, GitHub)
- [ ] 80% test coverage
- [ ] Public documentation complete

---

## 4. Quality Strategy

### Test Coverage

| Level | Target | Focus Areas |
|-------|--------|-------------|
| Unit | 80% | MCP tools, permission hooks, memory system |
| Integration | Key paths | Agent loop → MCP → daemon mock |
| E2E (simulation) | Happy paths | Multi-turn conversation, tool execution |
| E2E (hardware) | Manual | Voice activation, expression, degradation |

### Key Test Cases

1. **Wake word detection**: "Hey Reachy" activates within 500ms
2. **Permission enforcement**: Tier 4 tools always blocked
3. **Memory retrieval**: Relevant memories returned for context
4. **Degradation**: WiFi disconnect triggers Ollama fallback
5. **Expression sync**: Antenna state matches attention level

### Acceptance Criteria (from PRD)

- G1: Voice response, multi-step tasks via MCP, context maintained
- G2: <1% crash rate, 8+ hour continuous operation
- G3: 5+ MCP integrations working
- G5: Antenna state visibly indicates listening mode

---

## 5. Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| ARM64 Claude SDK issues | H | M | Test early (1.3.1), have Docker fallback |
| Thermal throttling on Pi | M | M | Health monitor (2.5.1), heatsink, throttle detection |
| OpenWakeWord accuracy | M | M | Tune sensitivity (2.2.4), add confirmation option |
| ChromaDB corruption | H | L | Regular backups, external SSD |
| Reachy daemon API changes | H | L | Pin SDK version, integration tests |
| Memory leaks in 8h run | M | M | Profile during stress test (2.6.4), fix before Phase 3 |

### Assumptions

1. Reachy Mini hardware arrives before Phase 2 starts
2. Claude Agent SDK stable for ARM64 (v0.2.114+ or native installer)
3. Reachy daemon provides stable HTTP API at localhost:8000
4. 4GB Pi RAM sufficient with memory budgets from TECH_REQ

### Out of Scope (Deferred)

- Web dashboard (P2 feature, post v1.0)
- Slack/Spotify integrations (v1.0, not MVP)
- Multi-robot coordination (v2.0+)
- LeRobot integration (v3.0+)

---

## Summary

| Phase | Focus | Effort | Key Deliverable |
|-------|-------|--------|-----------------|
| **1** | Foundation | ~50h | Agent controls simulated Reachy via MCP |
| **2** | Hardware | ~50h | Voice-activated agent on physical robot |
| **3** | Intelligence | ~50h | Memory, spatial audio, expressions |
| **4** | Polish | ~50h | Setup wizard, integrations, docs |
| **Total** | | **~200h** | Production-ready embodied AI agent |

---

**Plan Status**: Draft - Awaiting Approval

Ready for `/epcc-code` when approved.
