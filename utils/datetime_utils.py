"""Timezone-aware helpers for server-generated timestamps."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def app_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("APP_TIMEZONE", "America/Sao_Paulo"))


def now_local() -> datetime:
    return datetime.now(app_timezone())
