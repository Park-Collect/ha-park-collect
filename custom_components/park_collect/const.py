"""Constants for the Park & Collect integration."""

from datetime import timedelta

DOMAIN = "park_collect"
API_BASE_URL = "https://app.park-collect.de/api/v1"

SERVICE_SUBMIT_REPORT = "submit_report"
EVENT_REPORT_SUBMITTED = "park_collect_report_submitted"

PARKING_UPDATE_INTERVAL = timedelta(hours=1)
# The API documentation asks for at most one status request per report and hour.
STATUS_UPDATE_INTERVAL = timedelta(hours=1)

MAX_PHOTOS = 3
MAX_PHOTO_BYTES = 10 * 1024 * 1024

REASONS = [
    "privatparkplatz",
    "kundenparkplatz",
    "ausfahrt",
    "parkplatz_blockiert",
    "zugang",
    "leistungsbetrug",
    "ladesaeule",
]
