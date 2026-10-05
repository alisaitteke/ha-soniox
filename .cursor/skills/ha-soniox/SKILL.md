---
name: ha-soniox
description: >-
  Develop and maintain the Home Assistant Soniox custom integration (STT/TTS,
  config flow, Assist pipeline, HACS). Use when working in ha-soniox, editing
  custom_components/soniox, Assist speech engines, Soniox API/SDK, or when the
  user mentions Soniox, speech-to-text, text-to-speech, or HACS for this repo.
---

# ha-soniox

Public Home Assistant custom integration for Soniox cloud speech-to-text and text-to-speech.

Repository: https://github.com/alisaitteke/ha-soniox (public GitHub; HACS requires this)
Domain: `soniox`
Type: HACS custom integration (`custom_components/soniox`). Not an add-on. Not Wyoming. Do not treat the repo as private.

## File map

| Path | Role |
| --- | --- |
| `custom_components/soniox/manifest.json` | Domain, SemVer `version` (no `v`; HA/HACS source of truth), `soniox==2.10.0`, loggers |
| `custom_components/soniox/__init__.py` | Config-entry setup/unload, `runtime_data` |
| `custom_components/soniox/config_flow.py` | API key + region, reauth, reconfigure, options skeleton |
| `custom_components/soniox/client.py` | `AsyncSonioxClient` factory, credential check, random unique id |
| `custom_components/soniox/const.py` | Regions, default models, option keys, timeouts, error types |
| `custom_components/soniox/catalog.py` | Models/voices from the API, permission-tolerant |
| `custom_components/soniox/exceptions.py` | `error_type` helpers + `log_error`/`log_api_error`/`log_realtime_error` |
| `custom_components/soniox/repairs.py` | Quota, permission and Python-version repair issues |
| `custom_components/soniox/stt.py` / `tts.py` | Realtime STT and REST/streaming TTS entities |
| `custom_components/soniox/quality_scale.yaml` | Bronze/Silver/Gold tracking |
| `custom_components/soniox/brand/` | HA 2026.3+ icon/logo (official Soniox mark) |
| `scripts/develop` | Local `hass --debug` with `PYTHONPATH` |
| `scripts/check_version.py` | Lockstep check: manifest == pyproject; on release, tag (strip `v`) must match |
| `config/configuration.yaml` | Debug logger for `custom_components.soniox` |

## Hard rules

- Config flow UI only. Secrets in `entry.data`, non-connection settings in `entry.options`.
- Thin wrapper: official `AsyncSonioxClient`. Do not write a second WebSocket stack.
- `entry.runtime_data` for the client. Unique id is random, never derived from the API key.
- Never log or commit API keys. Redact the key AND the unique id in diagnostics.
- Do not create a Supervisor add-on or Wyoming proxy for this cloud API.
- Branch on Soniox `error_type`, not on exception class: `SonioxPermissionDeniedError` is a
  sibling of `SonioxAuthenticationError`, not a subclass, and both are HTTP 403.
  403 permission_denied means the key works; never trigger reauth for it.
- Core restart after Python edits. Frontend reload is not enough.
- Do not push unless asked. Do not commit `.venv`, caches, or `config/` except `configuration.yaml`.
- Bump `manifest.json` `version` and `pyproject.toml` together. Publish a GitHub Release (not a tag-only push) so HACS can version-check. Tag `vX.Y.Z` must match the manifest without the `v`.

## Assist / Soniox mapping

Assist STT audio is 16 kHz, 16-bit, mono PCM. Soniox raw: `pcm_s16le` + `sample_rate` + `num_channels`. Map HA BCP-47 (`tr-TR`) to ISO 639-1 (`tr`).

STT and TTS are implemented. Options cover hints, context, translation, diarization
prefix, endpoint detection and speed. `max_endpoint_delay_ms` is only sent when the
cached catalog says the model supports it.

Regions: `us`, `eu`, `jp`, `in` in `REGION_ENDPOINTS`.

## Local HA

```bash
pip install -r requirements_test.txt
./scripts/develop
```

Open http://localhost:8123 and add the integration from the UI.

On HAOS, copy only `custom_components/soniox` to `/config/custom_components/soniox` (Samba or SSH). Do not use HACS download as a live edit loop.

## Tests

```bash
pytest
ruff check .
python3 scripts/check_version.py
```

Config flow tests mock `async_validate_api_credentials`. Setup tests mock the client. `requirements_test.txt` pins `pytest-homeassistant-custom-component` to a Home Assistant that
uses Pydantic v2 so the suite exercises the real SDK. Do not float that pin or
reintroduce stubs: they silently skip all pydantic validation.

## Templates

Mirror core [elevenlabs](https://github.com/home-assistant/core/tree/dev/homeassistant/components/elevenlabs) for STT+TTS + options. Quality scale: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules
