# Soniox for Home Assistant

Custom Home Assistant integration for [Soniox](https://soniox.com) speech-to-text and text-to-speech. It registers as a cloud service and is meant to be selected as the STT/TTS engine in an Assist pipeline.

After setup, pick **Soniox** as the Speech-to-text and Text-to-speech engine in **Settings → Voice assistants**.

This is a **community custom integration**. It is **not** an official Home Assistant add-on, **not** an official Soniox product, and is **not affiliated with, endorsed by, or maintained by Soniox**. The GitHub repository is **public** ([alisaitteke/ha-soniox](https://github.com/alisaitteke/ha-soniox)); HACS only tracks public repositories.

## Requirements

- Home Assistant 2025.6 or newer
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

Minimum Home Assistant version is `hacs.json` `homeassistant` (`2025.6.0`).

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

## Security

The API key is stored in Home Assistant's `.storage/core.config_entries`. It is
never written to logs, and diagnostics redact both the key and the entry's
unique id.

Use a dedicated Soniox project and a key scoped to only what this integration
needs. In the Soniox console, on **API keys**, grant:

| Permission | Needed for |
| --- | --- |
| Speech-to-text, real-time | Assist speech-to-text |
| Text-to-speech, real-time | Assist text-to-speech |
| Model listing | Model and voice dropdowns in **Configure** |
| Cloned voices | Listing cloned voices (optional) |

Also set a **monthly budget** on the project so an unexpected usage loop cannot
run up the bill. Soniox rejects requests over the budget with
`project_monthly_budget_exhausted`; this integration reports that as a repair
issue instead of retrying silently.

Temporary API keys are **not** needed here: Home Assistant is the trusted
backend that holds the long-lived key. Protect your `.storage` directory and
any backups of it.

Soniox states that audio and transcripts are never used to train its models and
are not retained unless you use a service that stores data. Audio is processed
and stored in the region you select.

## Known limitations

- **Endpoint detection vs diarization.** Soniox notes that endpoint detection
  forces earlier finalization, which lowers speaker-diarization accuracy. For
  the best diarization, turn endpoint detection off.
- **Python 3.13.6.** That CPython release has an `ssl` regression
  ([CPython/gh-137583](https://github.com/python/cpython/issues/137583)) that
  makes the realtime STT/TTS WebSocket handshakes hang with no error. If your
  Home Assistant runs on 3.13.6, the integration raises a repair issue and
  Assist will appear to do nothing. Update Home Assistant Core.
- **No proxy or custom CA support.** The official SDK builds its own HTTP
  client, so Home Assistant's `http.proxy` setting and custom certificates do
  not apply.
- **Assist audio format.** The entity advertises 16 kHz, 16-bit mono PCM, which
  is what Assist uses.
- **Concurrency.** Soniox limits simultaneous realtime sessions per project.
  Several people speaking at once can exceed it; the request then fails with a
  rate-limit error.

## Logging

Failures and configuration events are logged under `custom_components.soniox`.
At the default `info` level you get setup results and every error:

```
ERROR custom_components.soniox: Soniox API key lacks a required permission; grant it in the Soniox console: permission_denied HTTP 403 (request_id=req-8f2c…) [region=us]
INFO  custom_components.soniox: Soniox entry 01J… ready (region=us, stt_model=stt-rt-v5, tts_model=tts-rt-v2)
```

Set `custom_components.soniox: debug` in `configuration.yaml` to also see which
model, voice, language and endpoint settings each request used. This is the
fastest way to confirm a language hint or voice is actually being applied.

Every failure line carries the Soniox `error_type`, the HTTP status and the
`request_id`. Quote the `request_id` when contacting Soniox support, since it is
the only way they can trace a request. The API key is never logged.

Enable debug logging from **Settings → System → Logs**, or add this to
`configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.soniox: debug
    httpx: warning
    httpcore: warning
```

Keeping `httpx` and `httpcore` at `warning` avoids logging full request and
response frames.

## Troubleshooting

- **"Soniox API key is missing a permission" repair issue** — the key works but
  lacks a permission. Grant it in the Soniox console and reload the integration.
- **"Soniox quota exhausted" repair issue** — the project balance or budget is
  exhausted. Top up or raise the budget, then reload.
- **Empty model or voice dropdown** — enable **Model listing** for the key, or
  type the value manually (`stt-rt-v5`, `tts-rt-v2`, `Adrian`).
- **Nothing happens in Assist** — check the Home Assistant log for
  `Soniox STT error` or `Soniox TTS request failed`, and confirm Python is not
  3.13.6.
- **Report a problem** — download diagnostics from the Soniox entry. They
  include the region, resolved endpoints and versions, and redact the key.

## Removal

Remove the integration from **Settings → Devices & services**. No extra cleanup is required.

## Development

Local Home Assistant follows the [integration_blueprint](https://github.com/ludeeus/integration_blueprint) pattern: `PYTHONPATH` points at `custom_components/` so you do not symlink into `config/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest
ruff check .
mypy
./scripts/develop
```

`requirements_test.txt` pins `pytest-homeassistant-custom-component` on purpose:
the suite must run against a Home Assistant that uses Pydantic v2 so the real
`soniox` SDK is imported and its validation is exercised.

Then open http://localhost:8123, finish onboarding, and add **Soniox** from the UI. After changing Python files, restart Core; a frontend reload is not enough.

### Live instance (HAOS / Supervised)

Do not install this as an add-on. Copy only `custom_components/soniox` to `/config/custom_components/soniox` (Samba share or Terminal & SSH), then restart Core. HACS download is a snapshot; use rsync/symlink while iterating.

Studio Code Server is for editing `/config` YAML. Keep this repository in Cursor on the workstation; do not open `/` as the add-on workspace.

## Tests

```bash
pytest
ruff check .
mypy
python3 scripts/check_version.py
```

CI runs all of these on every push and pull request.

Quality-scale progress is tracked in [`custom_components/soniox/quality_scale.yaml`](custom_components/soniox/quality_scale.yaml).

## License

MIT
