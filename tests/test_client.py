"""Unit tests for the Soniox client helper."""

from custom_components.soniox.client import new_unique_id
from custom_components.soniox.const import REGION_ENDPOINTS, REGIONS


def test_unique_id_is_random_and_not_derived_from_the_key() -> None:
    """The unique id must not depend on, or reveal, the API key."""
    first = new_unique_id()
    second = new_unique_id()
    assert first != second, "a key-derived id would be stable across calls"
    assert "secret-key" not in first
    assert len(first) == 32


def test_region_endpoints_cover_all_regions() -> None:
    """Every supported region has a complete endpoint set."""
    required = {
        "api_base_url",
        "websocket_base_url",
        "tts_api_base_url",
        "tts_websocket_base_url",
    }
    assert set(REGION_ENDPOINTS) == set(REGIONS)
    for region, endpoints in REGION_ENDPOINTS.items():
        assert set(endpoints) == required
        assert endpoints["api_base_url"].startswith("https://")
        assert endpoints["websocket_base_url"].startswith("wss://")
        if region == "us":
            assert "api.soniox.com" in endpoints["api_base_url"]
        else:
            assert f"api.{region}.soniox.com" in endpoints["api_base_url"]
