"""Tests for the config flow."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.park_collect.const import API_BASE_URL, DOMAIN


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_valid_key_creates_entry(hass, api):
    flow = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_key": " pcr_ok "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"api_key": "pcr_ok"}


async def test_invalid_key_shows_error(hass, aioclient_mock):
    aioclient_mock.get(
        f"{API_BASE_URL}/parkplaetze", status=401, json={"error": "Unauthorized"}
    )
    flow = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_key": "falsch"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_missing_power_of_attorney_shows_error(hass, aioclient_mock):
    aioclient_mock.get(
        f"{API_BASE_URL}/parkplaetze", status=403, json={"error": "Vollmacht fehlt"}
    )
    flow = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_key": "pcr_ok"}
    )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_unreachable_api_shows_error(hass, aioclient_mock):
    aioclient_mock.get(f"{API_BASE_URL}/parkplaetze", status=500, json={"error": "x"})
    flow = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_key": "pcr_ok"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_same_key_only_once(hass, api):
    for expected in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT):
        flow = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"api_key": "pcr_ok"}
        )
        await hass.async_block_till_done()
        assert result["type"] is expected
