# Soniox for Home Assistant

Custom Home Assistant integration for [Soniox](https://soniox.com) speech-to-text and text-to-speech. It registers as a cloud service and is meant to be selected as the STT/TTS engine in an Assist pipeline.

After setup, pick **Soniox** as the Speech-to-text and Text-to-speech engine in **Settings → Voice assistants**.

This is a **community custom integration**. It is **not** an official Home Assistant add-on, **not** an official Soniox product, and is **not affiliated with, endorsed by, or maintained by Soniox**. The GitHub repository is **public** ([alisaitteke/ha-soniox](https://github.com/alisaitteke/ha-soniox)); HACS only tracks public repositories.

## Requirements

- Home Assistant 2025.2 or newer
- A [Soniox API key](https://soniox.com) for the region that matches your project (US, EU, Japan, or India)

## Installation (HACS)

1. In HACS, add [this public repository](https://github.com/alisaitteke/ha-soniox) as a custom repository (category: Integration).
2. Download **Soniox**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Soniox**.
5. Enter your API key and region. The integration validates the key before it is saved.

Then open **Settings → Voice assistants**, edit an assistant, and choose Soniox for Speech-to-text and Text-to-speech.

HACS shows the installed version from `manifest.json` and available versions from GitHub Releases. Until the first Release is published, HACS falls back to the default branch (a commit hash, not SemVer).

## Releases

Ship from `main` only:

1. Bump `custom_components/soniox/manifest.json` `version` and `pyproject.toml` `version` together (SemVer, no `v` prefix).
2. Merge to `main`.
3. Publish a GitHub Release whose tag is `vX.Y.Z` (or `X.Y.Z`) matching that version. Tags without a Release are not enough for HACS.
4. CI checks the tag against the manifest. Do not force-move tags to rewrite the version.

Minimum Home Assistant version is `hacs.json` `homeassistant` (`2025.2.0`).

## Configuration

Add the integration, then open **Configure** on the Soniox entry. The first step is speech-to-text; the second is text-to-speech. API key and region stay under **Reconfigure**.

| Field | Stored in | Description |
| --- | --- | --- |
| API key | Config entry data | Soniox project API key. Never logged. |
| Region | Config entry data | Data-residency endpoint: `us`, `eu`, `jp`, or `in`. |
| STT model | Config entry options | Realtime model, typically `stt-rt-v5`. |
| Language hints | Config entry options | Extra ISO languages besides the Assist pipeline language. |
| Context / custom terms | Config entry options | Background text and comma-separated words to bias recognition. |
| Endpoint detection | Config entry options | Detect end of speech (default on; delay 500–3000 ms). |
| Speaker diarization | Config entry options | Prefix speaker changes as `[1]`, `[2]`, … |
| One-way translation | Config entry options | Translate the transcript into one target language. |
| TTS model / voice | Config entry options | Realtime model (`tts-rt-v2`) and voice (shared name or cloned id). |
| Speed / reduce silence | Config entry options | Speaking rate 0.7–1.3 and optional pause shortening. |

Model and voice dropdowns come from the Soniox API. If a list is empty, enable **Model listing** in the [Soniox console](https://console.soniox.com) (and **Cloned voices** if you want clones), or type the model / voice name.

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
python3 scripts/check_version.py
```

Quality-scale progress is tracked in [`custom_components/soniox/quality_scale.yaml`](custom_components/soniox/quality_scale.yaml).

## License

MIT
