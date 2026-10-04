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

Repository: https://github.com/alisaitteke/ha-soniox
Domain: `soniox`
Type: HACS custom integration (`custom_components/soniox`). Not an add-on. Not Wyoming.

## File map

| Path | Role |
| --- | --- |
| `custom_components/soniox/manifest.json` | Domain, version, `soniox==2.10.0`, loggers |
| `custom_components/soniox/__init__.py` | Config-entry setup/unload, `runtime_data` |
| `custom_components/soniox/config_flow.py` | API key + region, reauth, reconfigure, options skeleton |
| `custom_components/soniox/client.py` | `AsyncSonioxClient` factory, credential check |
| `custom_components/soniox/const.py` | Regions, default models, option keys |
| `custom_components/soniox/stt.py` / `tts.py` | Placeholders; platforms not forwarded yet |
| `custom_components/soniox/quality_scale.yaml` | Bronze/Silver/Gold tracking |
| `scripts/develop` | Local `hass --debug` with `PYTHONPATH` |
| `config/configuration.yaml` | Debug logger for `custom_components.soniox` |

## Hard rules

- Config flow UI only. Secrets in `entry.data`, non-connection settings in `entry.options`.
- Thin wrapper: official `AsyncSonioxClient`. Do not write a second WebSocket stack.
- `entry.runtime_data` for the client. Unique id is SHA-256 of the API key.
- Never log or commit API keys. Redact in diagnostics.
- Do not create a Supervisor add-on or Wyoming proxy for this cloud API.
- Do not forward `Platform.STT` / `Platform.TTS` until the entities are implemented.
- Core restart after Python edits. Frontend reload is not enough.
- Do not push unless asked. Do not commit `.venv`, caches, or `config/` except `configuration.yaml`.

## Assist / Soniox mapping

Assist STT audio is 16 kHz, 16-bit, mono PCM. Soniox raw: `pcm_s16le` + `sample_rate` + `num_channels`. Map HA BCP-47 (`tr-TR`) to ISO 639-1 (`tr`).

Implementation order: STT stream (`stt-rt-v5`, endpoint detection) → TTS (`tts-rt-v2`, one-shot then `async_stream_tts_audio`) → options (hints, context, translation, diarization prefix, speed).

Regions: `us`, `eu`, `jp`, `in` in `REGION_ENDPOINTS`.

## Local HA

```bash
pip install homeassistant -r requirements_test.txt
./scripts/develop
```

Open http://localhost:8123 and add the integration from the UI.

On HAOS, copy only `custom_components/soniox` to `/config/custom_components/soniox` (Samba or SSH). Do not use HACS download as a live edit loop.

## Tests

```bash
pytest
ruff check .
```

Config flow tests mock `async_validate_api_credentials`. Setup tests mock the client. `tests/soniox_stubs.py` exists because older `pytest-homeassistant-custom-component` pins Pydantic v1; production HA 2025.2+ uses the real SDK.

## Templates

Mirror core [elevenlabs](https://github.com/home-assistant/core/tree/dev/homeassistant/components/elevenlabs) for STT+TTS + options. Quality scale: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules
