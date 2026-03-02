# version_check.py
from fastapi import APIRouter, Query
from auth import RequireAPIKey
from models import VersionCheckModel

MIN_SUPPORTED_VERSION = "1.1"
LATEST_VERSION = "1.1"
STORE_URL = "https://apps.apple.com/app/biblegarden/id123456789"

MESSAGES = {
    "soft": {
        "en": "A new version of Bible Garden is available. Please update for the best experience.",
        "ru": "Доступна новая версия Bible Garden. Пожалуйста, обновите приложение.",
        "uk": "Доступна нова версія Bible Garden. Будь ласка, оновіть додаток."
    },
    "hard": {
        "en": "This version of Bible Garden is no longer supported. Please update to continue using the app.",
        "ru": "Эта версия Bible Garden больше не поддерживается. Пожалуйста, обновите приложение для продолжения работы.",
        "uk": "Ця версія Bible Garden більше не підтримується. Будь ласка, оновіть додаток для продовження роботи."
    }
}


def parse_version(version: str) -> tuple[int, ...]:
    """Parses a semver string into a tuple of integers for comparison"""
    return tuple(int(x) for x in version.split("."))


router = APIRouter()


@router.get('/version-check', response_model=VersionCheckModel, operation_id="versionCheck", tags=["Version"])
def version_check(
    app_version: str = Query(..., description="Current app version (semver, e.g. 1.2)"),
    api_key: str = RequireAPIKey
):
    """Check whether the app version is up to date"""
    v = parse_version(app_version)

    if v < parse_version(MIN_SUPPORTED_VERSION):
        update_type = "hard"
    elif v < parse_version(LATEST_VERSION):
        update_type = "soft"
    else:
        update_type = "none"

    return {
        "update_type": update_type,
        "latest_version": LATEST_VERSION,
        "store_url": STORE_URL,
        "message": MESSAGES.get(update_type)
    }
