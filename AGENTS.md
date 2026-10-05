# AGENTS.md

Public contributor notes for [ha-soniox](https://github.com/alisaitteke/ha-soniox).

## What this is

Home Assistant **custom integration** (`custom_components/soniox`) for Soniox cloud STT and TTS. Users pick the engines in an Assist pipeline.

The GitHub repository is **public**. HACS custom repositories must be public; do not treat this as a private repo.

It is **not** a Supervisor add-on, not a Wyoming server, and not a conversation/LLM agent. Do not package it as an add-on.

## Layout

- `custom_components/soniox/` — integration (required HACS layout)
- `config/configuration.yaml` — local `hass` debug config only (`scripts/develop`)
- `scripts/develop` — start local HA with `PYTHONPATH` to this repo
- `scripts/check_version.py` — HACS/HA version lockstep (`manifest.json` == `pyproject.toml`)
- `tests/` — pytest via a **pinned** `pytest-homeassistant-custom-component` (Pydantic v2, real SDK)
- `.cursor/skills/ha-soniox/` — project skill for Cursor agents

## Rules

- UI config flow only. No YAML setup (`config_entry_only_config_schema`).
- `ConfigEntry.data`: `api_key`, `region`. `ConfigEntry.options`: STT/TTS settings.
- Thin wrapper around official `soniox` SDK (`AsyncSonioxClient`). No raw WebSocket clients.
- Branch on Soniox `error_type`, never on exception class alone. `SonioxPermissionDeniedError`
  is a sibling of `SonioxAuthenticationError`; both are HTTP 403.
- Config entry `unique_id` is random. Never derive it from the API key, or key rotation
  will lock users out of reauthentication.
- Store the client on `entry.runtime_data`, not `hass.data`.
- Never log API keys. Redact the API key AND the unique id in diagnostics.
- Quota/permission problems become repair issues, never silent retry loops.
- Log every failure through `exceptions.log_error` / `log_api_error` /
  `log_realtime_error` so each line carries `error_type`, HTTP status and
  `request_id`. Never log the API key. `info` for lifecycle, `debug` for
  per-request settings, `error` only for real failures.
- STT/TTS platforms are forwarded; entities exist and are Assist-ready.
- Python changes require a Home Assistant Core restart.
- Do not commit `.env`, `secrets.yaml`, `.venv/`, or anything under `config/` except `configuration.yaml`.
- Do not `git push` or force-push unless the user asked.
- Version source of truth is `custom_components/soniox/manifest.json` (`version`, SemVer, no `v` prefix). Keep `pyproject.toml` in lockstep. HACS installed version comes from that field; available versions come from **GitHub Releases**, not tags alone.
- To ship: bump both version fields on `main`, then publish a GitHub Release whose tag is `vX.Y.Z` (or `X.Y.Z`) matching the manifest. Do not rewrite tags. Do not use `zip_release`.

## Local commands

```bash
pip install -r requirements_test.txt
pytest
ruff check .
mypy
python3 scripts/check_version.py
./scripts/develop
```

Local UI: http://localhost:8123

## Next implementation order

1. Proxy / custom CA support (blocked: the SDK builds its own HTTP client)
2. Optional usage and cost sensors (`client.usage.summary`, `concurrency_limits`)
3. Voice cloning (later)
