import os
from pathlib import Path

from dotenv import load_dotenv

# Folder that contains this file (the backend package).
PACKAGE_DIR = Path(__file__).resolve().parent
# Project root: where .env, templates/, static/, and database/ live.
PROJECT_ROOT = PACKAGE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env", override=True)


def use_sqlite():
    v = os.getenv("USE_SQLITE", "").strip().lower()
    return v in ("1", "true", "yes")


def sqlite_path():
    raw = os.getenv("SQLITE_PATH", str(PROJECT_ROOT / "utpb_scheduler.db")).strip()
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return str(p)


def mysql_config():
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "utpb_scheduler"),
    }


CATALOG_YEAR = os.getenv("CATALOG_YEAR", "2025-2026")
SMARTCATALOG_BASE = "https://utpb.smartcatalogiq.com"
CATALOG_JSON_URL = (
    f"{SMARTCATALOG_BASE}/Institutions/The-University-of-Texas-Permian-Basin/json/"
    f"{CATALOG_YEAR}/{CATALOG_YEAR}-Undergraduate-Catalog.json"
)

SCHEDULE_BASE_DEFAULT = "https://general.utpb.edu/schedule/index.php"


def schedule_base_url():
    return os.getenv("SCHEDULE_BASE_URL", SCHEDULE_BASE_DEFAULT).strip().rstrip("/")


def schedule_term():
    v = os.getenv("SCHEDULE_TERM", "").strip()
    return v or None


def schedule_semester_label():
    return os.getenv("SCHEDULE_SEMESTER_LABEL", "Spring 2026").strip()


def schedule_subject():
    return os.getenv("SCHEDULE_SUBJECT", "COSC").strip()


def schedule_term_specs():
    """Reads SCHEDULE_TERM_MAP like 2262:Spring 2026|2265:Summer 2026."""
    raw = os.getenv("SCHEDULE_TERM_MAP", "").strip()
    if raw:
        pairs = []
        for part in raw.split("|"):
            part = part.strip()
            if ":" not in part:
                continue
            code, label = part.split(":", 1)
            code, label = code.strip(), label.strip()
            if code and label:
                pairs.append((code, label))
        if pairs:
            return pairs
    t = schedule_term()
    if t:
        return [(t, schedule_semester_label())]
    return []


def anthropic_api_key():
    v = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return v or None


_OLD_MODEL_NAMES = {
    "claude-3-5-haiku-20241022": "claude-haiku-4-5",
    "claude-3-5-haiku-latest": "claude-haiku-4-5",
}


def anthropic_model():
    raw = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5").strip()
    return _OLD_MODEL_NAMES.get(raw, raw)


def anthropic_base_url():
    v = os.getenv("ANTHROPIC_BASE_URL", "").strip()
    return v or None
