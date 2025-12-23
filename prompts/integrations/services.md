# External Service Integrations

This document provides detailed guidance for using external MCP service integrations.

## Service Overview

| Service | MCP Server | Primary Use | MVP Status |
|---------|------------|-------------|------------|
| Home Assistant | `homeassistant-mcp` | Smart home control | MVP |
| Google Calendar | `gcal-mcp` | Schedule management | MVP |
| GitHub | `github-mcp` | Repository monitoring | MVP |
| Weather | Custom | Weather information | MVP |
| Slack | `slack-mcp` | Team messaging | v1.0 |
| Spotify | `spotify-mcp` | Music control | v1.0 |

## Home Assistant

Control smart home devices through Home Assistant.

### Available Tools

| Tool | Description | Parameters | Permission |
|------|-------------|------------|------------|
| `get_entities` | List all available entities | `domain` (optional filter) | Tier 1 |
| `get_entity_state` | Get current state of an entity | `entity_id` | Tier 1 |
| `turn_on` | Turn on a device | `entity_id`, `brightness` (optional) | Tier 2 |
| `turn_off` | Turn off a device | `entity_id` | Tier 2 |
| `toggle` | Toggle device state | `entity_id` | Tier 2 |
| `set_temperature` | Set thermostat temperature | `entity_id`, `temperature`, `hvac_mode` | Tier 2 |
| `lock_door` | Lock a smart lock | `entity_id` | Tier 3 |
| `unlock_door` | Unlock a smart lock | `entity_id` | Tier 3 |
| `call_service` | Call any HA service | `domain`, `service`, `data` | Tier 3 |

### Entity ID Patterns

- Lights: `light.living_room`, `light.bedroom_lamp`
- Switches: `switch.office_fan`, `switch.porch_light`
- Climate: `climate.thermostat`, `climate.bedroom_ac`
- Locks: `lock.front_door`, `lock.garage`
- Sensors: `sensor.temperature`, `sensor.humidity`
- Binary sensors: `binary_sensor.motion`, `binary_sensor.door`

### Usage Examples

```python
# Check if lights are on
get_entity_state(entity_id="light.living_room")
# Returns: {"state": "on", "brightness": 255, "color_temp": 370}

# Turn on lights at 50%
turn_on(entity_id="light.living_room", brightness=127)

# Set thermostat
set_temperature(entity_id="climate.thermostat", temperature=72, hvac_mode="cool")

# Security action (requires confirmation)
lock_door(entity_id="lock.front_door")
```

### Permission Rules

- **Tier 2 (Notify)**: `turn_on`, `turn_off`, `toggle`, `set_temperature`
- **Tier 3 (Confirm)**: `lock_door`, `unlock_door`, `call_service`
- **Tier 4 (Forbidden)**: `disarm_security`, any alarm disarm actions

## Google Calendar

Manage calendar events and scheduling.

### Available Tools

| Tool | Description | Parameters | Permission |
|------|-------------|------------|------------|
| `get_events` | List events in a time range | `calendar_id`, `start`, `end`, `max_results` | Tier 1 |
| `get_event_details` | Get full event details | `calendar_id`, `event_id` | Tier 1 |
| `create_event` | Create a new event | `calendar_id`, `summary`, `start`, `end`, `description`, `attendees` | Tier 3 |
| `update_event` | Modify an existing event | `calendar_id`, `event_id`, `updates` | Tier 3 |
| `delete_event` | Remove an event | `calendar_id`, `event_id` | Tier 3 |
| `quick_add` | Natural language event creation | `calendar_id`, `text` | Tier 3 |

### Usage Examples

```python
# Get today's events
get_events(calendar_id="primary", start="today", end="tomorrow")
# Returns: [{"id": "abc123", "summary": "Team standup", "start": "09:00", ...}]

# Get event details
get_event_details(calendar_id="primary", event_id="abc123")

# Create event (requires confirmation)
create_event(
    calendar_id="primary",
    summary="Project review",
    start="2024-12-20T14:00:00",
    end="2024-12-20T15:00:00",
    description="Review Q4 progress"
)

# Quick add (natural language, requires confirmation)
quick_add(calendar_id="primary", text="Lunch with Sarah tomorrow at noon")
```

### Context Integration

When discussing schedules, proactively check the calendar:
- "You have 3 meetings today, starting with Team standup at 9 AM"
- "Your afternoon is free after the 2 PM review"
- "Should I schedule this for your next available slot?"

## GitHub

Monitor and interact with GitHub repositories.

### Available Tools

| Tool | Description | Parameters | Permission |
|------|-------------|------------|------------|
| `get_issues` | List repository issues | `repo`, `state`, `labels`, `assignee` | Tier 1 |
| `get_issue_details` | Get full issue details | `repo`, `issue_number` | Tier 1 |
| `get_pull_requests` | List open PRs | `repo`, `state`, `author` | Tier 1 |
| `get_pr_details` | Get PR details with diff | `repo`, `pr_number` | Tier 1 |
| `get_notifications` | Get user notifications | `all`, `participating` | Tier 1 |
| `get_repo_info` | Get repository metadata | `repo` | Tier 1 |
| `create_issue` | Open a new issue | `repo`, `title`, `body`, `labels` | Tier 3 |
| `create_pull_request` | Open a new PR | `repo`, `title`, `body`, `head`, `base` | Tier 3 |
| `add_comment` | Comment on issue/PR | `repo`, `number`, `body` | Tier 3 |
| `close_issue` | Close an issue | `repo`, `issue_number` | Tier 3 |
| `merge_pull_request` | Merge a PR | `repo`, `pr_number`, `merge_method` | Tier 3 |

### Repository Format

Use `owner/repo` format: `jawhnycooke/reachy-agent`

### Usage Examples

```python
# Check for open issues
get_issues(repo="jawhnycooke/reachy-agent", state="open")
# Returns: [{"number": 42, "title": "Add wake word detection", "labels": ["feature"]}]

# Get PR details
get_pr_details(repo="jawhnycooke/reachy-agent", pr_number=15)

# Check notifications
get_notifications(participating=True)

# Create issue (requires confirmation)
create_issue(
    repo="jawhnycooke/reachy-agent",
    title="Bug: Memory leak in perception loop",
    body="Steps to reproduce:\n1. Run for 2+ hours\n2. Observe memory growth",
    labels=["bug", "memory"]
)
```

### Context Integration

- "You have 2 new PR reviews requested on reachy-agent"
- "Issue #42 was closed yesterday by the fix in PR #45"
- "The CI is failing on your latest push—want me to show the errors?"

## Weather

Get weather information and forecasts.

### Available Tools

| Tool | Description | Parameters | Permission |
|------|-------------|------------|------------|
| `get_current_weather` | Current conditions | `location` (city or coords) | Tier 1 |
| `get_forecast` | Multi-day forecast | `location`, `days` | Tier 1 |
| `get_hourly_forecast` | Hour-by-hour forecast | `location`, `hours` | Tier 1 |
| `get_alerts` | Active weather alerts | `location` | Tier 1 |

### Usage Examples

```python
# Current weather
get_current_weather(location="San Francisco, CA")
# Returns: {"temp": 65, "condition": "Partly cloudy", "humidity": 72}

# 5-day forecast
get_forecast(location="current", days=5)

# Weather alerts
get_alerts(location="current")
```

### Context Integration

Proactively mention relevant weather:
- "Good morning! It's 65°F and partly cloudy. Perfect for your 9 AM outdoor meeting."
- "Heads up—there's a rain alert for this afternoon. You might want to bring an umbrella."
- "The weekend looks great—sunny and 75°F both days."

## Combining Services with Body Expression

### Morning Briefing Pattern

```
1. wake_up()
2. play_emotion("happy", 0.5)
3. speak("Good morning!")
4. get_current_weather(location="current")
5. get_events(calendar_id="primary", start="today", end="tomorrow")
6. get_notifications()
7. Synthesize and speak summary with appropriate emotions
```

### Alert Pattern

```
1. play_emotion("alert", 0.7)
2. set_antenna_state(left_angle=80, right_angle=80)
3. speak("I noticed something that needs your attention...")
4. Deliver the alert (weather, calendar reminder, PR review request)
5. rest()
```

### Task Completion Pattern

```
1. nod(times=1)  # Acknowledge
2. play_emotion("thinking", 0.4)  # Show working
3. Execute service calls
4. dance("celebrate") if success, play_emotion("sad", 0.3) if failure
5. speak(result)
6. rest()
```

## Permission Summary

| Tier | Service Actions |
|------|-----------------|
| **Tier 1** | All read operations: `get_*` for all services |
| **Tier 2** | HA device control: `turn_on`, `turn_off`, `set_temperature` |
| **Tier 3** | Create/modify: calendar events, GitHub issues/PRs, HA locks |
| **Tier 4** | Security-critical: HA disarm, email sending, banking |
