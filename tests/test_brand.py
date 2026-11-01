"""Home Assistant serves the bundled brand images."""

import pytest

from homeassistant.setup import async_setup_component


@pytest.mark.parametrize(
    "image", ["icon.png", "icon@2x.png", "logo.png", "logo@2x.png", "dark_icon.png"]
)
async def test_brand_image_is_served(hass, hass_client, image):
    assert await async_setup_component(hass, "brands", {})
    await hass.async_block_till_done()

    client = await hass_client()
    response = await client.get(f"/api/brands/integration/park_collect/{image}")

    assert response.status == 200
    assert response.content_type == "image/png"
    assert (await response.read()).startswith(b"\x89PNG")
