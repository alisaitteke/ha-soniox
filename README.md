# Soniox for Home Assistant

Custom Home Assistant integration for [Soniox](https://soniox.com) speech-to-text and text-to-speech. It registers as a cloud service and is meant to be selected as the STT/TTS engine in an Assist pipeline.

This repository currently contains the **infrastructure** (config flow, client wrapper, quality-scale skeleton). Streaming STT/TTS is the next implementation phase and is not forwarded as platforms yet.

This is a **custom integration**, not a Home Assistant add-on.

## Requirements

- Home Assistant 2025.2 or newer
- A [Soniox API key](https://soniox.com) for the region that matches your project (US, EU, Japan, or India)

## Installation (HACS)

1. In HACS, add [this repository](https://github.com/alisaitteke/ha-soniox) as a custom integration.
2. Download **Soniox**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Soniox**.
5. Enter your API key and region. The integration validates the key before it is saved.

After STT/TTS platforms are implemented, pick the Soniox engines in **Settings → Voice assistants**.

## Configuration

| Field | Stored in | Description |
| --- | --- | --- |
| API key | Config entry data | Soniox project API key. Never logged. |
| Region | Config entry data | Data-residency endpoint: `us`, `eu`, `jp`, or `in`. |
| STT/TTS options | Config entry options | Reserved for model, voice, language hints, context, endpointing, and translation. |

YAML setup is not supported. Use the UI. Reauthentication and reconfigure flows are available if the key expires or you need to change region.

## Removal

Remove the integration from **Settings → Devices & services**. No extra cleanup is required.

## Development

Local Home Assistant follows the [integration_blueprint](https://github.com/ludeeus/integration_blueprint) pattern: `PYTHONPATH` points at `custom_components/` so you do not symlink into `config/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install homeassistant -r requirements_test.txt
pytest
ruff check .
./scripts/develop
```

Then open http://localhost:8123, finish onboarding, and add **Soniox** from the UI. After changing Python files, restart Core; a frontend reload is not enough.

### Live instance (HAOS / Supervised)

Do not install this as an add-on. Copy only `custom_components/soniox` to `/config/custom_components/soniox` (Samba share or Terminal & SSH), then restart Core. HACS download is a snapshot; use rsync/symlink while iterating.

Studio Code Server is for editing `/config` YAML. Keep this repository in Cursor on the workstation; do not open `/` as the add-on workspace.

## Tests

```bash
pytest
ruff check .
```

Quality-scale progress is tracked in [`custom_components/soniox/quality_scale.yaml`](custom_components/soniox/quality_scale.yaml).

## License

MIT
