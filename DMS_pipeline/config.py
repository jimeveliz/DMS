"""
Configuracion global del proyecto.
Define conexiones y parametros por defecto, tomando valores desde
variables de entorno (.env/OS) cuando esten presentes.
"""

import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Cargar variables desde .env si existe (desarrollo)
load_dotenv()


def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "yes", "y", "on")


def as_int(value, default):
    try:
        return int(str(value).strip())
    except Exception:
        return default


# Parametros de filtrado de estudios
STUDY_DESCRIPTION = os.getenv("STUDY_DESCRIPTION", "PET CUERPO COMPLETO-FD")
DOSE_SERIES_NUMBER = as_int(os.getenv("DOSE_SERIES_NUMBER", None), 999)


# Parámetros de calidad
QUALITY_METRICS_ENABLED = os.getenv("QUALITY_METRICS_ENABLED", "true").lower() == "true"
QUALITY_THR_SUV = float(os.getenv("QUALITY_THR_SUV", 0.07))
QUALITY_BLOCK = int(os.getenv("QUALITY_BLOCK", 6))
QUALITY_MIN_VALID = int(os.getenv("QUALITY_MIN_VALID", 12))
QUALITY_BINS = os.getenv("QUALITY_BINS", "fd")
SKIP_DYNAMIC_PET = os.getenv("SKIP_DYNAMIC_PET", "true").lower() == "true"

# Orthanc
ORTHANC_URL = os.getenv("ORTHANC_URL", "http://10.73.161.56:8042")
ORTHANC_USER = os.getenv("ORTHANC_USER", "fisica")
ORTHANC_PASS = os.getenv("ORTHANC_PASS", "Fisica4518")

# MongoDB (preferir MONGO_URI completa; si no, construir con partes)
DB_NAME = os.getenv("DB_NAME", "CondorDB")
_MONGO_URI_ENV = os.getenv("MONGO_URI")
_MONGO_HOST = os.getenv("MONGO_HOST", "10.73.173.21")
_MONGO_PORT = as_int(os.getenv("MONGO_PORT", None), 27017)
_MONGO_USERNAME = os.getenv("MONGO_USERNAME", "fisica")
_MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "F1s1c44518")
_MONGO_AUTHSOURCE = os.getenv("MONGO_AUTHSOURCE", "admin")

if _MONGO_URI_ENV:
    MONGO_URI = _MONGO_URI_ENV
else:
    MONGO_URI = (
        f"mongodb://{quote_plus(_MONGO_USERNAME)}:{quote_plus(_MONGO_PASSWORD)}@"
        f"{_MONGO_HOST}:{_MONGO_PORT}/{DB_NAME}?authSource={quote_plus(_MONGO_AUTHSOURCE)}"
    )

# Colecciones
COL_OCR = os.getenv("MONGO_COL_OCR", "dose_report")
COL_CT = os.getenv("MONGO_COL_CT", "series_ct")
COL_PET = os.getenv("MONGO_COL_PET", "series_pet1")

# Scheduler
SCHEDULER_INTERVAL_MINUTES = as_int(os.getenv("SCHEDULER_INTERVAL_MINUTES", None), 5)
SCHEDULER_RUN_ON_START = as_bool(os.getenv("SCHEDULER_RUN_ON_START", None), True)

# Config dict de compatibilidad para usos existentes
config = {
    "orthanc": {
        "url": ORTHANC_URL,
        "user": ORTHANC_USER,
        "password": ORTHANC_PASS,
    },
    "mongo": {
        "host": _MONGO_HOST,
        "port": _MONGO_PORT,
        "database": DB_NAME,
        "username": _MONGO_USERNAME,
        "password": _MONGO_PASSWORD,
        "authSource": _MONGO_AUTHSOURCE,
        "url": _MONGO_URI_ENV,
    },
    "study": {
        "description": STUDY_DESCRIPTION,
        "dose_series": DOSE_SERIES_NUMBER,
    },
    "scheduler": {
        "interval_minutes": SCHEDULER_INTERVAL_MINUTES,
        "run_on_start": SCHEDULER_RUN_ON_START,
    },
    "collections": {
        "ocr": COL_OCR,
        "ct": COL_CT,
        "pet": COL_PET,
    },
}
