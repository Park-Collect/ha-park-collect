"""Shared fixtures."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.park_collect.const import API_BASE_URL, DOMAIN

API_KEY = "pcr_test"
UPLOAD_URL = "https://s3.example.test/upload"
LOTS = [
    {
        "id": 5563,
        "name": "Einfahrt",
        "adresse": "Musterstraße 1, 74177 Bad Friedrichshall",
        "vertragsstrafe": 15,
        "abmahnen": False,
    },
    {
        "id": 31115,
        "name": "Pleinstraat",
        "adresse": "Pleinstraat 22, 6446 Kerkrade",
        "vertragsstrafe": 10,
        "abmahnen": True,
    },
]
REPORT = {
    "id": 459123,
    "aktenzeichen": "PC459123",
    "status": "offen",
    "eingegangen_am": "2026-11-02T08:05:12.000Z",
    "wiederholt": False,
    "hinweise": [],
}
STATUS = {
    "id": 459123,
    "aktenzeichen": "PC459123",
    "status": "offen",
    "aktualisiert_am": "2026-11-02T08:05:12.000Z",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading from custom_components."""


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Do not wait between retries."""
    with patch("custom_components.park_collect.api.RETRY_BASE_SECONDS", 0), patch(
        "custom_components.park_collect.api.RETRY_MAX_SECONDS", 0
    ):
        yield


@pytest.fixture
def api(aioclient_mock):
    """Mock the happy path of the API."""
    aioclient_mock.get(f"{API_BASE_URL}/parkplaetze", json={"parkplaetze": LOTS})
    aioclient_mock.post(
        f"{API_BASE_URL}/uploads",
        status=201,
        json={"upload_id": "upl_test", "upload_url": UPLOAD_URL, "gueltig_bis": "x"},
    )
    aioclient_mock.put(UPLOAD_URL, status=200, text="")
    aioclient_mock.post(f"{API_BASE_URL}/meldungen", status=201, json=REPORT)
    aioclient_mock.get(f"{API_BASE_URL}/meldungen/459123", json=STATUS)
    return aioclient_mock


@pytest.fixture
async def entry(hass, api):
    """Set up the integration."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data={"api_key": API_KEY}, unique_id="abc"
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def photos(hass, tmp_path):
    """Two real photo files in an allowed folder."""
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    jpeg = tmp_path / "einfahrt.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0jpeg")
    png = tmp_path / "ausfahrt.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\npng")
    return [str(jpeg), str(png)]
