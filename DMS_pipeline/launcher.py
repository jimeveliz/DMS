"""Punto de entrada del pipeline de ingesta (OCR + headers + Mongo)."""
import logging
import sys

from ocr.run_ocr import main as run_ocr_main
from headers.run_header import main as run_header_main
from mongo.mongo_uploader import (
    cargar_jsons_ocr,
    cargar_jsons_ct_headers,
    cargar_jsons_pet_headers,
)


logger = logging.getLogger(__name__)


def _configure_logging():
    # Fuerza la configuración aunque ya existan handlers
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    # Silenciar verbosidad de libs HTTP
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    _configure_logging()

    # 1) OCR
    try:
        logger.info("Iniciando OCR de reportes de dosis…")
        run_ocr_main()
        logger.info("OCR finalizó correctamente")
    except Exception:
        logger.exception("OCR finalizó con errores")

    # 2) Subir OCR a Mongo
    try:
        logger.info("Subiendo resultados OCR a MongoDB…")
        cargar_jsons_ocr("ocr_output")
        logger.info("Carga OCR a MongoDB finalizada")
    except Exception:
        logger.exception("Carga de resultados OCR en MongoDB falló")

    # 3) Headers DICOM (CT + PET)
    try:
        logger.info("Ejecutando extracción de headers DICOM…")
        run_header_main()
        logger.info("Extracción de headers DICOM finalizó correctamente")
    except Exception:
        logger.exception("Extracción de headers DICOM finalizó con errores")

    # 4) Subir headers a Mongo
    try:
        logger.info("Subiendo headers DICOM a MongoDB…")
        cargar_jsons_ct_headers("header_ct")
        cargar_jsons_pet_headers("header_pet")
        logger.info("Carga de headers a MongoDB finalizada")
    except Exception:
        logger.exception("Carga de headers en MongoDB falló")


if __name__ == "__main__":
    main()
