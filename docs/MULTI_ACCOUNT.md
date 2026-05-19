# Multi-account runtime (Phase D)

FinalMacro persists configuration for multiple accounts today, but only **one** Discord connection runs at a time. This document describes how to extend runtime without repeating the old MudaeBot bug where one account used the wrong preset across channels.

## Persisted model

| Layer | Store | Role |
|-------|--------|------|
| Who | `accounts[]` | Token, name, type, `enabled_channel_ids` |
| Where | `servers[]` / `channels[]` | Discord channel IDs, parsed `$settings` / `$bonus` |
| How | `presets{}` | `MacroConfig` per preset id |
| Binding | `targets[]` | `{ account_id, channel_profile_id, preset_id }` |

Resolution for a single run is implemented in `gui/run_target.py` → `resolve_run_target()`.

## Rules for multi-account implementation

1. **Never collapse presets per account.** Each running instance must resolve `(account_id, channel_profile_id)` → `preset_id` via `TargetStore`, same as single-account mode.

2. **One monitor per connected account**, keyed by `account_id`:
   - `ChannelMonitor(token=account.token, channel_id=…)` per active deployment.
   - Do not share `AccountState` across accounts.

3. **Scheduler enqueues work on targets**, not accounts alone:
   - Iterate `targets[]` (or enabled subset).
   - Skip targets whose account is on cooldown / `rolling: false` (when that field exists).
   - Round-robin **channels** (servers), then accounts assigned to each channel.

4. **Connection pool** (sketch):

```text
AccountManager
  clients: dict[account_id, ChannelMonitor]
  deploy(target: RunTarget) -> connect monitor to channel snowflake
  schedule() -> for each target: resolve preset, run roll cycle on that client
```

5. **GUI**: Run tab can stay “single target” for manual testing; add optional “Deploy all configured targets” that uses every `targets[]` row whose account has a token and channel exists.

## Migration from old MudaeBot

Old `channel_presets` string keys map to `targets[]` with internal `channel_profile_id` (see `gui/import_legacy.py`). Old `create_coordinator_from_deployments` “first preset per account” behavior must **not** be ported.

## Files to extend

- `mudae/discord_reader.py` — already one channel per monitor; reuse per account.
- `macro/roll_cycle.py` — one engine per monitor; pass resolved `MacroConfig` from target.
- New `macro/coordinator.py` (future) — schedule targets, own `AccountManager`.
- `gui/bridge.py` — `connect()` stays single-target; add `deployAll()` later.
