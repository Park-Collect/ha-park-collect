"""Tests for the submit_report service and the entities."""

from datetime import datetime
import json

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
import voluptuous as vol

from custom_components.park_collect.const import (
    API_BASE_URL,
    DOMAIN,
    EVENT_REPORT_SUBMITTED,
    SERVICE_SUBMIT_REPORT,
)
from pytest_homeassistant_custom_component.common import async_capture_events

from .conftest import API_KEY, REPORT, UPLOAD_URL


def _call(hass, photos, **extra):
    data = {
        "parkplatz_id": 5563,
        "kennzeichen": "HN-AB 1234",
        "beginn": "2026-11-01T08:14:00+01:00",
        "bilder": photos,
        **extra,
    }
    return hass.services.async_call(
        DOMAIN, SERVICE_SUBMIT_REPORT, data, blocking=True, return_response=True
    )


def _requests(api, method, url):
    return [c for c in api.mock_calls if c[0] == method and str(c[1]) == url]


async def test_submit_report(hass, entry, api, photos):
    events = async_capture_events(hass, EVENT_REPORT_SUBMITTED)

    result = await _call(
        hass,
        photos,
        ende="2026-11-01T09:02:00+01:00",
        abmahnen=False,
        vertragsstrafe=15,
        fahrzeug="VW Golf",
        bemerkung="Blockierte die Einfahrt.",
    )
    await hass.async_block_till_done()

    assert result["aktenzeichen"] == "PC459123"
    assert len(events) == 1

    uploads = _requests(api, "POST", f"{API_BASE_URL}/uploads")
    assert [c[2] for c in uploads] == [
        {"content_type": "image/jpeg"},
        {"content_type": "image/png"},
    ]
    puts = _requests(api, "PUT", UPLOAD_URL)
    assert len(puts) == 2
    assert puts[0][2] == b"\xff\xd8\xff\xe0jpeg"
    assert "Authorization" not in (puts[0][3] or {})

    call = _requests(api, "POST", f"{API_BASE_URL}/meldungen")[0]
    body, headers = call[2], call[3]
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    assert headers["Idempotency-Key"].startswith("ha-")
    assert body["parkplatz_id"] == 5563
    assert body["beginn"] == "2026-11-01T08:14:00+01:00"
    assert body["ende"] == "2026-11-01T09:02:00+01:00"
    assert body["grund"] == "privatparkplatz"
    assert body["abmahnen"] is False
    assert len(body["fotos"]) == 2


async def test_photo_with_own_timestamp(hass, entry, api, photos):
    await _call(
        hass,
        [{"pfad": photos[0], "aufgenommen_am": "2026-11-01T08:14:03+01:00"}],
    )
    body = _requests(api, "POST", f"{API_BASE_URL}/meldungen")[0][2]
    assert body["fotos"][0]["aufgenommen_am"] == "2026-11-01T08:14:03+01:00"


async def test_photo_without_timestamp_uses_file_time(hass, entry, api, photos):
    await _call(hass, photos[:1])
    body = _requests(api, "POST", f"{API_BASE_URL}/meldungen")[0][2]
    assert datetime.fromisoformat(body["fotos"][0]["aufgenommen_am"]).tzinfo


async def test_naive_time_gets_home_assistant_timezone(hass, entry, api, photos):
    await hass.config.async_set_time_zone("Europe/Berlin")
    await _call(hass, photos[:1], beginn="2026-11-01T08:14:00")
    body = _requests(api, "POST", f"{API_BASE_URL}/meldungen")[0][2]
    assert body["beginn"] == "2026-11-01T08:14:00+01:00"


async def test_same_event_is_not_sent_twice(hass, entry, api, photos):
    await _call(hass, photos)
    again = await _call(hass, photos)

    assert again["wiederholt"] is True
    assert again["id"] == REPORT["id"]
    assert len(_requests(api, "POST", f"{API_BASE_URL}/meldungen")) == 1
    assert len(_requests(api, "POST", f"{API_BASE_URL}/uploads")) == 2


async def test_vorgang_id_decides_the_key(hass, entry, api, photos):
    await _call(hass, photos, vorgang_id="a")
    await _call(hass, photos, vorgang_id="b")
    keys = {
        c[3]["Idempotency-Key"]
        for c in _requests(api, "POST", f"{API_BASE_URL}/meldungen")
    }
    assert len(keys) == 2


async def test_default_parking_lot_from_select(hass, entry, api, photos):
    with pytest.raises(ServiceValidationError, match="Choose a parking lot"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SUBMIT_REPORT,
            {
                "kennzeichen": "HN-AB 1234",
                "beginn": "2026-11-01T08:14:00+01:00",
                "bilder": photos,
            },
            blocking=True,
            return_response=True,
        )

    state = hass.states.get("select.park_collect_standard_parkplatz") or hass.states.get(
        "select.park_collect_default_parking_lot"
    )
    assert state.attributes["options"] == ["Einfahrt (5563)", "Pleinstraat (31115)"]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": state.entity_id, "option": "Pleinstraat (31115)"},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SUBMIT_REPORT,
        {
            "kennzeichen": "HN-AB 1234",
            "beginn": "2026-11-01T08:14:00+01:00",
            "bilder": photos,
        },
        blocking=True,
        return_response=True,
    )
    body = _requests(api, "POST", f"{API_BASE_URL}/meldungen")[0][2]
    assert body["parkplatz_id"] == 31115


async def test_foreign_parking_lot(hass, entry, photos):
    with pytest.raises(ServiceValidationError, match="not in this account"):
        await _call(hass, photos, parkplatz_id=1)


async def test_path_outside_allowed_folders(hass, entry, photos):
    with pytest.raises(ServiceValidationError, match="not allowed"):
        await _call(hass, ["/etc/passwd"])


async def test_file_is_no_photo(hass, entry, photos, tmp_path):
    text = tmp_path / "notiz.txt"
    text.write_text("hallo")
    with pytest.raises(ServiceValidationError, match="not a JPEG or PNG"):
        await _call(hass, [str(text)])


async def test_too_large_photo(hass, entry, photos, tmp_path):
    big = tmp_path / "gross.jpg"
    big.write_bytes(b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024))
    with pytest.raises(ServiceValidationError, match="larger than 10 MB"):
        await _call(hass, [str(big)])


async def test_too_many_photos(hass, entry, photos):
    with pytest.raises(vol.Invalid):
        await _call(hass, photos * 2)


async def test_unknown_reason(hass, entry, photos):
    with pytest.raises(vol.Invalid):
        await _call(hass, photos, grund="irgendwas")


async def test_api_rejection_shows_the_reason(hass, entry, api, photos):
    api.clear_requests()
    api.get(f"{API_BASE_URL}/parkplaetze", json={"parkplaetze": []})
    api.post(
        f"{API_BASE_URL}/uploads",
        status=201,
        json={"upload_id": "upl_test", "upload_url": UPLOAD_URL},
    )
    api.put(UPLOAD_URL, status=200, text="")
    api.post(
        f"{API_BASE_URL}/meldungen",
        status=400,
        json={
            "status": "fehler",
            "fehler": [{"feld": "kennzeichen", "meldung": "steht auf der Whitelist"}],
        },
    )
    with pytest.raises(HomeAssistantError, match="kennzeichen: steht auf der Whitelist"):
        await _call(hass, photos)
    # A rejected report is not retried and not remembered.
    assert len(_requests(api, "POST", f"{API_BASE_URL}/meldungen")) == 1
    assert entry.runtime_data.store.reports == {}


async def test_server_error_is_retried_with_same_body(hass, entry, api, photos):
    api.clear_requests()
    api.post(
        f"{API_BASE_URL}/uploads",
        status=201,
        json={"upload_id": "upl_test", "upload_url": UPLOAD_URL},
    )
    api.put(UPLOAD_URL, status=200, text="")
    api.post(f"{API_BASE_URL}/meldungen", status=500, json={"error": "x"})
    api.get(f"{API_BASE_URL}/parkplaetze", json={"parkplaetze": []})

    with pytest.raises(HomeAssistantError):
        await _call(hass, photos)

    calls = _requests(api, "POST", f"{API_BASE_URL}/meldungen")
    assert len(calls) == 3
    assert len({json.dumps(c[2], sort_keys=True) for c in calls}) == 1
    assert len({c[3]["Idempotency-Key"] for c in calls}) == 1


async def test_sensor_shows_status_after_report(hass, entry, api, photos):
    sensor = "sensor.park_collect_letzte_meldung"
    alternative = "sensor.park_collect_last_report"
    state = hass.states.get(sensor) or hass.states.get(alternative)
    assert state.state == "unknown"

    await _call(hass, photos)
    await entry.runtime_data.report.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(sensor) or hass.states.get(alternative)
    assert state.state == "offen"
    assert state.attributes["aktenzeichen"] == "PC459123"


async def test_revoked_key_starts_reauth(hass, entry, api):
    api.clear_requests()
    api.get(f"{API_BASE_URL}/parkplaetze", status=401, json={"error": "Unauthorized"})
    await entry.runtime_data.parking.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["step_id"] for f in flows] == ["reauth_confirm"]


async def test_unload(hass, entry):
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
