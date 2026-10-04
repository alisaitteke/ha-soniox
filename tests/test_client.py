"""Unit tests for the Soniox client helper."""

from custom_components.soniox.client import unique_id_from_api_key
from custom_components.soniox.const import REGION_ENDPOINTS, REGIONS


def test_unique_id_is_stable_and_not_the_raw_key() -> None:
    """The unique id must be deterministic and must not leak the API key."""
    first = unique_id_from_api_key("secret-key")
    second = unique_id_from_api_key("secret-key")
    assert first == second
    assert first != "secret-key"
    assert "secret-key" not in first
    assert len(first) == 64


def test_unique_id_differs_per_key() -> None:
    """Different API keys produce different unique ids."""
    assert unique_id_from_api_key("key-a") != unique_id_from_api_key("key-b")


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
