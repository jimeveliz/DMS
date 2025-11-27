"""
Carga archivos JSON desde un directorio y los inserta/actualiza 
en MongoDB usando upsert para evitar duplicados.

OCR se deduplica por encabezado.Exam no.
CT headers se deduplican por series.orthanc_series_id 
"""

import json
import logging
from pathlib import Path

import pymongo

from config import MONGO_URI, DB_NAME, COL_OCR, COL_CT, COL_PET


# Logger y cliente reutilizable
logger = logging.getLogger(__name__)

# Reusable client/DB
client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]


def cargar_jsons_ocr(directorio: str):
    """Insertar/actualizar documentos OCR en COL_OCR, garantizando unicidad por encabezado.Exam no."""
    col = db[COL_OCR]  # Colección de OCR
    archivos = list(Path(directorio).glob("*.json"))
    total_insertados = 0

    for archivo in archivos:
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)

        exam_no = data.get("encabezado", {}).get("Exam no")
        if not exam_no:
            logger.warning("[SKIP] Sin Exam no en %s", archivo.name)
            continue

        # Upsert by exam number
        col.replace_one({"encabezado.Exam no": exam_no}, data, upsert=True)
        total_insertados += 1

    logger.info("[OK] Insertados/actualizados %d documentos en '%s'", total_insertados, COL_OCR)


def cargar_jsons_ct_headers(directorio: str):
    """Insertar/actualizar documentos CT headers en COL_CT, 
    garantizando unicidad por series.orthanc_series_id 
    (si falta, por study.orthanc_study_id).
    """
    col = db[COL_CT]
    archivos = list(Path(directorio).glob("*.json"))
    total_insertados = 0

    for archivo in archivos:
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)

        series_id = data.get("series", {}).get("series_instance_uid")
        if not series_id:
            study_id = data.get("study", {}).get("study_instance_uid")
            if not study_id:
                logger.warning("[SKIP] Sin series_id/study_id en %s", archivo.name)
                continue
            filtro = {"study.study_instance_uid": study_id}
        else:
            filtro = {"series.series_instance_uid": series_id}

        col.replace_one(filtro, data, upsert=True)
        total_insertados += 1

    logger.info("[OK] Insertados/actualizados %d documentos en '%s'", total_insertados, COL_CT)


def cargar_jsons_pet_headers(directorio: str):
    """Insertar/actualizar documentos PET headers en COL_PET, 
    garantizando unicidad por series.orthanc_series_id 
    (si falta, por study.orthanc_study_id).
    """
    col = db[COL_PET]
    archivos = list(Path(directorio).glob("*.json"))
    total_insertados = 0

    for archivo in archivos:
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)

        series_id = data.get("series", {}).get("series_instance_uid")
        if not series_id:
            study_id = data.get("study", {}).get("study_instance_uid")
            if not study_id:
                logger.warning("[SKIP] Sin series_id/study_id en %s", archivo.name)
                continue
            filtro = {"study.study_instance_uid": study_id}
        else:
            filtro = {"series.series_instance_uid": series_id}

        col.replace_one(filtro, data, upsert=True)
        total_insertados += 1

    logger.info("[OK] Insertados/actualizados %d documentos en '%s'", total_insertados, COL_PET)
