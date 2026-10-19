from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def format_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%b %d, %Y · %H:%M")


templates.env.filters["datetime"] = format_datetime
