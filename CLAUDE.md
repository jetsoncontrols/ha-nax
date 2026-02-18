# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Home Assistant custom integration (HACS-compatible) for **Crestron NAX audio devices**. Communicates over a local WebSocket API (`cresnextws` library) using push-based events — no polling.

## Architecture

All code lives in `custom_components/nax/`. Key design:

- **DataEventManager** (`__init__.py`): Wraps `CresNextWSClient`, manages WebSocket connection lifecycle. Created during `async_setup_entry`, stored on `entry.runtime_data`.
- **NaxEntity** (`nax_entity.py`): Base entity class. Sets `_attr_should_poll = False`, provides shared `DeviceInfo`, and registers connection status callbacks. All entities inherit from this.
- **Platform files** (`media_player.py`, `select.py`, `binary_sensor.py`, `switch.py`, `number.py`, `siren.py`): Each follows the same pattern — read device metadata from the client, create entities per-zone or per-device, register push event handlers.
- **HA Store** (`const.py`): Persists last-selected input and AES67 stream selections per config entry using `homeassistant.helpers.storage.Store`.
- **Config flow** (`config_flow.py`): Standard HA config flow with host/username/password. Supports initial setup and reconfigure.

## Entity organization

- Per-zone entities: media_player, select (input, AES67), binary_sensor (signal), switch (test tone), number (volume limits, test tone volume)
- Per-device entities: binary_sensor (connection), select (tone gen mode), switch (tone gen L/R channels), number (tone gen frequency), siren (door chime)
- Entity categories: standard (main controls), configuration (limits/settings), diagnostic (testing tools, hidden by default)

## Dependencies

- `cresnextws==0.1.9` — WebSocket client for CresNext protocol
- `deepmerge>=1.1.0,<2.0.0` — deep dict merging for state updates
- Requires Home Assistant 2025.8+

## Development

No local test harness, linter config, or build tooling exists in this repo. To test, install into a Home Assistant dev environment. The integration is configured through the HA UI (Settings → Devices & Services → Add Integration → NAX).

Version is tracked in `custom_components/nax/manifest.json`.
