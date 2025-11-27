import pyorthanc
import numpy as np
import easyocr
import cv2
from pathlib import Path
from PIL import Image, ImageOps
import logging

from ocr.ocr_utils import (
    extraer_encabezado_desde_lineas,
    extraer_tabla_dosimetrica,
    guardar_json_completo
)
from config import (
    ORTHANC_URL,
    ORTHANC_USER,
    ORTHANC_PASS,
    STUDY_DESCRIPTION,
    DOSE_SERIES_NUMBER,
)
OUTPUT_DIR = Path("ocr_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Inicializar cliente y OCR
client = pyorthanc.Orthanc(ORTHANC_URL, ORTHANC_USER, ORTHANC_PASS, timeout=60, trust_env=False)
reader = easyocr.Reader(['en'], gpu=False)
logger = logging.getLogger(__name__)

def main():
    logger.info("Iniciando OCR de reportes de dosis (Orthanc: %s)", ORTHANC_URL)
    # Obtener lista de pacientes
    try:
        patient_ids = client.get_patients()
    except Exception as exc:
        logger.exception("No se pudo obtener pacientes desde Orthanc: %s", exc)
        return

    if not patient_ids:
        logger.warning("Orthanc no devolvió pacientes. Verifique filtros, URL o credenciales.")
        return

    target_desc_lower = (STUDY_DESCRIPTION or "").lower()
    total_json = 0
    estudios_filtrados = 0
    estudios_procesados = 0
    logger.info("Pacientes a revisar: %d | Filtro StudyDescription: '%s'", len(patient_ids), STUDY_DESCRIPTION)

    for pid in patient_ids:
        patient = pyorthanc.Patient(id_=pid, client=client)

        for study in patient.studies:
            try:
                desc = study.description or ""
            except Exception:
                desc = ""

            if target_desc_lower not in desc.lower():
                continue
            estudios_filtrados += 1
            procesado_estudio = False
            
            # Si el estudio ya fue procesado previamente, omitir para no repetir OCR
            ruta_json = OUTPUT_DIR / f"{patient.name}_{study.id_}.json"
            if ruta_json.exists():
                logger.debug("[SKIP] OCR existente: %s", ruta_json.name)
                continue  # Procesar solo la primera serie que coincide

            available_series_numbers = []
            for series in study.series:
                serie_numero_str = series._get_main_dicom_tag_value("SeriesNumber")
                if not (serie_numero_str and serie_numero_str.isdigit()):
                    continue

                serie_num = int(serie_numero_str)
                available_series_numbers.append(serie_num)
                if int(serie_num) != int(DOSE_SERIES_NUMBER):
                    continue

                if not series.instances:
                    logger.debug("[SKIP] Serie sin instancias en estudio %s", getattr(study, 'id_', 'unknown'))
                    continue

                ins = series.instances[0]
                try:
                    ds = ins.get_pydicom()
                except Exception as exc:
                    logger.warning("[SKIP] No se pudo leer pydicom de la instancia %s: %s", getattr(ins, 'id_', 'unknown'), exc)
                    continue
                if 'PixelData' not in ds:
                    logger.debug("[SKIP] Instancia sin PixelData para %s", ruta_json.name)
                    continue

                # Preprocesamiento de la imagen
                imagen = ds.pixel_array
                if imagen.dtype != np.uint8:
                    imagen = (255 * (imagen - np.min(imagen)) / np.ptp(imagen)).astype(np.uint8)
                imagen_grande = cv2.resize(imagen, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

                #Preprocesamiento de la imagen (tabla invertida)
                imagen_header = imagen_grande
                img_pil = Image.fromarray(imagen_grande).convert("L")
                img_inv_pil = ImageOps.invert(img_pil)
                imagen_tabla = np.array(img_inv_pil)

                # OCR para encabezado
                header_result = reader.readtext(
                    imagen_header,
                    width_ths=1.75,
                    ycenter_ths=0.7
                )
                header_lines = [d[1].strip() for d in header_result if d[1].strip()]

                # OCR para tabla dosimétrica
                table_result = reader.readtext(
                    imagen_tabla,
                    width_ths=10,
                    ycenter_ths=0.8
                )
                table_lines = [d[1].strip() for d in table_result if d[1].strip()]

                # Procesamiento
                encabezado = extraer_encabezado_desde_lineas(header_lines)
                df_tabla = extraer_tabla_dosimetrica(table_lines)

                dicom_header = ins.tags

                # Guardar JSON en subcarpeta
                #ruta_json = OUTPUT_DIR / f"paciente_{study.id_}.json"
                guardar_json_completo(
                    encabezado,
                    df_tabla.to_dict(orient="records"),
                    ruta_json,
                    dicom_header=dicom_header,
                )
                logger.info("[OK] OCR guardado: %s", ruta_json.name)
                total_json += 1
                estudios_procesados += 1
                procesado_estudio = True
                break

            if not procesado_estudio:
                logger.debug(
                    "[SKIP] Estudio %s del paciente %s no coincidió con DOSE_SERIES_NUMBER=%s. Disponibles: %s",
                    getattr(study, 'id_', 'unknown'), getattr(patient, 'name', ''), DOSE_SERIES_NUMBER, sorted(set(available_series_numbers))
                )

    logger.info(
        "[OCR] Estudios filtrados por descripcion: %d | Procesados: %d | JSON exportados: %d en '%s'",
        estudios_filtrados, estudios_procesados, total_json, str(OUTPUT_DIR)
    )
            
if __name__ == "__main__":
    main()

