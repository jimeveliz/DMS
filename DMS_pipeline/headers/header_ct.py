import os
import json
import logging
import pyorthanc
from config import STUDY_DESCRIPTION
from typing import Dict, Set


logger = logging.getLogger(__name__)


def exportar_series_ct(client, output_dir="./header_ct"):
    """
    Recorre todos los pacientes en Orthanc y exporta un JSON por cada serie CT
    (sólo la primera instancia) de los estudios cuyo StudyDescription contenga
    'PET CUERPO COMPLETO-FD'.

    Parámetros:
        client (pyorthanc.Orthanc): cliente conectado a Orthanc
        output_dir (str): carpeta donde guardar los JSON
    """
    os.makedirs(output_dir, exist_ok=True) #crear carpeta de salida si no existe
    total_json = 0

    try:
        patient_ids = client.get_patients() #obtener IDs de pacientes desde orthanc
    except Exception as exc:
        logger.exception("No se pudieron obtener pacientes desde Orthanc: %s", exc)
        return

    if not patient_ids:
        logger.warning("Orthanc no devolvió pacientes. Verifique filtros, URL o credenciales.")
        return

    logger.info("[CT] Pacientes a revisar: %d | Filtro StudyDescription: '%s'", len(patient_ids), STUDY_DESCRIPTION)

    target_desc_lower = (STUDY_DESCRIPTION or "").lower()

    for pid in patient_ids:
        patient = pyorthanc.Patient(id_=pid, client=client) #crear objeto paciente para consultar estudios/series

        for study in patient.studies: #itera cada estudio del paciente
            try:
                desc = study.description or ""
            except Exception:
                desc = ""

            if target_desc_lower not in desc.lower():
                continue

            for series in study.series:
                try:
                    modality = series.modality
                except Exception:
                    modality = None

                if not modality or str(modality).upper() != "CT":
                    continue

                if len(series.instances) == 0: #descarta series sin instancias
                    continue

                serie_num_str = series._get_main_dicom_tag_value("SeriesNumber") #lee el tag "SeriesNumber"
                serie_num = int(serie_num_str) if (serie_num_str and serie_num_str.isdigit()) else None #convierte a entero si es posible

                inst = series.instances[0]  # primera instancia

                out = {
                    "patient": {
                        "patient_name": getattr(patient, "name", None)
                    },
                    "study": {
                        "study_instance_uid": getattr(study, "uid", None),
                        "study_description": desc
                    },
                    "series": {
                        "series_instance_uid": getattr(series, "uid", None),
                        "modality": str(modality) if modality else None,
                        "series_number": serie_num
                    },
                    "first_instance": {
                        "sop_instance_uid": getattr(inst, "uid", None),
                        "dicom_tags": inst.tags
                    }
                }

                fn_series = f"{serie_num:03d}" if isinstance(serie_num, int) else "NA"
                out_path = os.path.join(
                    output_dir,
                    f"Series-{fn_series}_CT_{patient.name}_{study.id_}.json"
                )
                # Comprobar si el archivo JSON ya existe antes de procesar
                if os.path.exists(out_path):  # Si el archivo ya existe, saltarlo
                    continue

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)

                total_json += 1

    logger.info(f"[CT] JSON exportados: {total_json} en '{output_dir}'.")