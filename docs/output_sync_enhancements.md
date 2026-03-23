# Output Sync Enhancements

## Overview

The output sync system (`api/sync.py`) has been enhanced with three capabilities for the provider-facing server:

1. WebSocket-triggered on-demand sync
2. Incremental sync with `If-Modified-Since` headers
3. Configurable conflict resolution

These work alongside the existing periodic config sync (`start_config_sync`).

## WebSocket On-Demand Sync

`OutputSyncWebSocket` connects to the Pipeline Server's WebSocket endpoint and listens for `pipeline.complete` events. When received, it immediately fetches the generated note and transcript.

If the WebSocket connection drops, it falls back to periodic polling and retries after a configurable interval (default 30s). If the `websockets` library isn't installed, it starts in polling-only mode.

### Lifecycle

```python
from api.sync import start_output_sync, stop_output_sync

# In FastAPI lifespan:
await start_output_sync()   # connects WebSocket (provider-facing only)
await stop_output_sync()    # clean shutdown
```

### WebSocket URL

Derived automatically from the pipeline API URL:
- `http://pipeline:8100` → `ws://pipeline:8100/ws/events`
- `https://pipeline:8100` → `wss://pipeline:8100/ws/events`

## Incremental Sync

`IncrementalSync` avoids re-downloading unchanged files using HTTP conditional requests.

- `should_fetch(local_path, remote_last_modified)` — compares timestamps, returns True only when remote is strictly newer
- `fetch_if_newer(client, url, local_path)` — sends `If-Modified-Since` header, writes file only on 200, skips on 304

## Conflict Resolution

`ConflictResolver` handles cases where both local and remote versions have been modified.

| Strategy | Behavior |
|----------|----------|
| `keep_both` (default) | Renames local to `.local` suffix, writes remote at original path |
| `keep_remote` | Overwrites local with remote |
| `keep_local` | Keeps local unchanged, skips remote |

## Configuration

Add to `config/deployment.yaml`:

```yaml
output_sync_enhanced:
  websocket_enabled: true
  websocket_reconnect_interval: 30    # seconds
  incremental: true
  conflict_strategy: "keep_both"      # keep_both | keep_remote | keep_local
```

The `OutputSyncEnhanced` Pydantic model in `config/deployment.py` provides typed access to these settings.
