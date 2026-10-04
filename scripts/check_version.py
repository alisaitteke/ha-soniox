#!/usr/bin/env python3
"""Keep HA/HACS version fields in lockstep.

manifest.json version is the source of truth (HA installed version, HACS 2+
semver, no ``v`` prefix). pyproject.toml must match. When RELEASE_TAG is set
(GitHub Release publish), the tag with a leading ``v`` stripped must match too.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "soniox" / "manifest.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"

# AwesomeVersion accepts CalVer/SemVer; HACS 2+ rejects a leading v.
VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$"
)


def fail(message: str) -> None:
    print(f"version-check: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_manifest_version() -> str:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        fail(f"cannot read {MANIFEST_PATH}: {err}")
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        fail(f"{MANIFEST_PATH} is missing a string version")
    return version


def load_pyproject_version() -> str:
    try:
        text = PYPROJECT_PATH.read_text(encoding="utf-8")
    except OSError as err:
        fail(f"cannot read {PYPROJECT_PATH}: {err}")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if match is None:
        fail(f"{PYPROJECT_PATH} is missing project.version")
    return match.group(1)


def normalize_tag(tag: str) -> str:
    tag = tag.strip()
    if tag.startswith("refs/tags/"):
        tag = tag.removeprefix("refs/tags/")
    return tag[1:] if tag.startswith("v") else tag


def main() -> None:
    manifest_version = load_manifest_version()
    pyproject_version = load_pyproject_version()

    if manifest_version.startswith("v"):
        fail(
            f"manifest version {manifest_version!r} must not use a v prefix "
            "(HACS 2+ / Home Assistant custom integrations)"
        )
    if VERSION_RE.fullmatch(manifest_version) is None:
        fail(f"manifest version {manifest_version!r} is not SemVer")

    if pyproject_version != manifest_version:
        fail(
            f"pyproject.toml version {pyproject_version!r} != "
            f"manifest.json version {manifest_version!r}"
        )

    release_tag = os.environ.get("RELEASE_TAG", "").strip()
    if release_tag:
        tag_version = normalize_tag(release_tag)
        if tag_version != manifest_version:
            fail(
                f"release tag {release_tag!r} (normalized {tag_version!r}) != "
                f"manifest.json version {manifest_version!r}"
            )

    extra = f", tag {release_tag}" if release_tag else ""
    print(f"version-check: ok {manifest_version}{extra}")


if __name__ == "__main__":
    main()
