import os
import json
import math
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional, Dict, Any, List

import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError
import pyorthanc
from sympy import series
from config import (
    STUDY_DESCRIPTION,
    QUALITY_METRICS_ENABLED,
    QUALITY_THR_SUV,
    QUALITY_BLOCK,
    QUALITY_MIN_VALID,
    QUALITY_BINS,
    SKIP_DYNAMIC_PET,
)

logger = logging.getLogger(__name__)


def exportar_series_pet(client, output_dir="./header_pet"):
    """
    Recorre todos los pacientes en Orthanc y exporta un JSON por cada serie PET
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

    logger.info("[PET] Pacientes a revisar: %d | Filtro StudyDescription: '%s'", len(patient_ids), STUDY_DESCRIPTION)

    target_desc_lower = (STUDY_DESCRIPTION or "").lower()
    quality_params = {
        "thr": QUALITY_THR_SUV,
        "block": QUALITY_BLOCK,
        "min_valid": QUALITY_MIN_VALID,
        "bins": QUALITY_BINS,
    }

    for pid in patient_ids:
        patient = pyorthanc.Patient(id_=pid, client=client) #crear objeto paciente para consultar estudios/series

        for study in patient.studies: #itera cada estudio del paciente
            try:
                desc = study.description or ""
            except Exception:
                desc = ""

            if target_desc_lower not in desc.lower():
                continue

            pt_series = []

            for series in study.series:
                if str(getattr(series, "modality", "")).upper() != "PT":
                    continue

                if not series.instances:
                    continue

                pt_series.append(series)

            if not pt_series:
                logger.debug("[PET] Estudio %s sin series PT", getattr(study, 'id_', 'unknown'))
                continue

            #series_selec = max(pt_series, key=lambda item: len(item.instances))
            # Prioridades de descripción (0 = más alta)
            PRIORITY_MAP = {
                "PET-EANM1": 0,
                "PET-AC-IA": 1,
                "PET-AC-SF_IA": 2,
                "PET-AC": 3,
            }

            def _series_desc_exact(series):
                try:
                    d = series._get_main_dicom_tag_value("SeriesDescription") or ""
                except Exception:
                    d = ""
                return d.strip()

            def _priority(desc: str) -> int:
                # Coincidencia exacta case-insensitive
                return PRIORITY_MAP.get(desc.strip().upper(), 4)

            # Elegir serie por prioridad y luego por #instancias (desc)
            series_selec = min(
                pt_series,
                key=lambda s: (_priority(_series_desc_exact(s)), -len(s.instances))
            )

            try:
                modality_sel = str(series_selec.modality) if series_selec.modality else None
            except Exception:
                modality_sel = None
            
            inst = series_selec.instances[0] #toma la primera instancia de la serie seleccionada

            serie_num_str = series_selec._get_main_dicom_tag_value("SeriesNumber") #lee el tag "SeriesNumber"
            serie_num = int(serie_num_str) if (serie_num_str and serie_num_str.isdigit()) else None #convierte a entero si es posible
            fn_series = f"{serie_num:03d}" if isinstance(serie_num, int) else "NA"
            out_path = os.path.join(
                output_dir,
                f"Serie{fn_series}_PET_{patient.name}_{study.id_}.json"
            ) 
            if os.path.exists(out_path):  # Si el archivo ya existe, saltarlo
                continue

            out = {
                    "patient": {
                        "patient_name": getattr(patient, "name", None)
                    },
                    "study": {
                        "study_instance_uid": getattr(study, "uid", None),
                        "study_description": desc
                    },
                    "series": {
                        "series_instance_uid": getattr(series_selec, "uid", None),
                        "modality": modality_sel,
                        "series_number": serie_num,
                    },
                    "first_instance": {
                        "sop_instance_uid": getattr(inst, "uid", None),
                        "dicom_tags": inst.tags
                    }
                }

                        # Comprobar si el archivo JSON ya existe antes de procesar

            pet_quality = compute_pet_quality_from_orthanc_series(
                series_selec, quality_params
            )
            out["pet_quality"] = pet_quality
 
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)

            total_json += 1

    logger.info(f"[PET] JSON exportados: {total_json} en '{output_dir}'.")

def compute_pet_quality_from_orthanc_series(series, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula la métrica de calidad (GNI) a partir de la serie PET obteniendo
    los DICOM directamente desde Orthanc.
    """
    if not QUALITY_METRICS_ENABLED:
        return {"status": "disabled"}

    instances = getattr(series, "instances", None) or []
    if not instances:
        return {"status": "error", "message": "Serie sin instancias disponibles"}

    try:
        first_ds = _load_instance_dataset(instances[0])
    except RuntimeError as exc:
        return {"status": "error", "message": f"No se pudo leer la primera instancia: {exc}"}

    if SKIP_DYNAMIC_PET:
        frames = _safe_int(getattr(first_ds, "NumberOfFrames", None))
        if frames and frames > 1:
            return {"status": "skipped_dynamic", "reason": "dynamic_series"}

    rows = int(getattr(first_ds, "Rows", 0) or 0)
    cols = int(getattr(first_ds, "Columns", 0) or 0)
    if rows <= 0 or cols <= 0:
        return {"status": "error", "message": "Dimensiones inválidas en la serie"}

    try:
        suv_factor, suv_meta = get_suv_factor_from_dicom(first_ds)
    except Exception as exc:
        return {"status": "error", "message": f"Error calculando SUV: {exc}"}

    noise_vectors: List[np.ndarray] = []
    mask_voxels = 0
    total_voxels = 0
    thr = params["thr"]
    block = params["block"]
    min_valid = params["min_valid"]
    bins = params["bins"]

    for inst in instances:
        try:
            ds = _load_instance_dataset(inst)
        except RuntimeError as exc:
            return {"status": "error", "message": f"No se pudo leer la instancia {inst.id_}: {exc}"}

        slice_rows = int(getattr(ds, "Rows", rows) or rows)
        slice_cols = int(getattr(ds, "Columns", cols) or cols)
        if slice_rows != rows or slice_cols != cols:
            return {"status": "error", "message": f"Dimensiones inconsistentes en la instancia {inst.id_}"}

        try:
            slice_suv = dataset_to_suv_slice(ds, suv_factor)
        except Exception as exc:
            return {"status": "error", "message": f"Pixel data no disponible para {inst.id_}: {exc}"}

        mask = slice_suv > thr
        mask_voxels += int(mask.sum())
        total_voxels += mask.size

        slice_noise = compute_noise_values_from_slice(slice_suv, mask, block, min_valid)
        if slice_noise.size:
            noise_vectors.append(slice_noise)

    if not noise_vectors:
        return {"status": "error", "message": "No se obtuvieron bloques válidos para ruido"}

    all_noise = np.concatenate(noise_vectors)
    gni = compute_gni(all_noise, bins)
    if math.isnan(gni):
        return {"status": "error", "message": "No se pudo calcular GNI"}

    coverage_pct = (100.0 * mask_voxels / total_voxels) if total_voxels else 0.0

    return {
        "status": "ok",
        "gni_suvbw": gni,
        "coverage_mask_pct": coverage_pct,
        "params": {
            "thr_suv": thr,
            "block_size": block,
            "min_valid": min_valid,
            "bins": bins,
        },
        "suv_meta": suv_meta,
    }


def _safe_int(value, default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default


def _load_instance_dataset(instance) -> pydicom.Dataset:
    try:
        return instance.get_pydicom()
    except Exception:
        try:
            raw = instance.get_dicom_file_content()
        except Exception as exc:
            raise RuntimeError(f"descarga DICOM fallida: {exc}") from exc
        try:
            return pydicom.dcmread(BytesIO(raw), force=True)
        except InvalidDicomError as exc:
            raise RuntimeError(f"DICOM inválido: {exc}") from exc


def dataset_to_suv_slice(ds: pydicom.Dataset, suv_factor: float) -> np.ndarray:
    try:
        slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
    except (TypeError, ValueError):
        slope = 1.0
    try:
        intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)
    except (TypeError, ValueError):
        intercept = 0.0

    try:
        arr = ds.pixel_array.astype(np.float32, copy=False)
    except Exception as exc:
        raise RuntimeError(exc) from exc

    return (arr * slope + intercept) * float(suv_factor)


def compute_noise_values_from_slice(
    slice_suv: np.ndarray,
    mask: np.ndarray,
    block: int,
    min_valid: int,
) -> np.ndarray:
    if slice_suv.size == 0:
        return np.empty(0, dtype=np.float32)

    cropped_img, cropped_mask = crop_center_pair(slice_suv, mask, block)
    if cropped_img.size == 0:
        return np.empty(0, dtype=np.float32)

    rows, cols = cropped_img.shape
    nx = rows // block
    ny = cols // block
    noise_vals: List[float] = []

    for i in range(nx):
        for j in range(ny):
            r0 = i * block
            r1 = r0 + block
            c0 = j * block
            c1 = c0 + block
            sub_mask = cropped_mask[r0:r1, c0:c1]
            valid_pixels = int(sub_mask.sum())
            if valid_pixels < min_valid:
                continue
            sub_img = cropped_img[r0:r1, c0:c1]
            noise_vals.append(float(sub_img[sub_mask].std(ddof=0)))

    return np.array(noise_vals, dtype=np.float32)


def crop_center_pair(img: np.ndarray, mask: np.ndarray, block: int):
    rows, cols = img.shape
    target_rows = (rows // block) * block
    target_cols = (cols // block) * block
    if target_rows == 0 or target_cols == 0:
        return (
            np.empty((0, 0), dtype=img.dtype),
            np.empty((0, 0), dtype=mask.dtype),
        )
    start_r = (rows - target_rows) // 2
    start_c = (cols - target_cols) // 2
    end_r = start_r + target_rows
    end_c = start_c + target_cols
    return img[start_r:end_r, start_c:end_c], mask[start_r:end_r, start_c:end_c]


def compute_gni(noise_vals: np.ndarray, bins) -> float:
    finite_vals = noise_vals[np.isfinite(noise_vals)]
    if finite_vals.size == 0:
        return float("nan")
    hist, edges = np.histogram(finite_vals, bins=bins)
    if not np.any(hist):
        return float("nan")
    idx = int(hist.argmax())
    return float(0.5 * (edges[idx] + edges[idx + 1]))



def parse_time_any(value: Optional[str]):
    if not value:
        return None
    value = str(value)
    if ":" in value:
        parts = value.split(":")
        if len(parts) < 3:
            return None
        try:
            hh = int(parts[0]); mm = int(parts[1]); ss = int(float(parts[2]))
        except ValueError:
            return None
        return hh, mm, ss
    value = value.split(".")[0]
    if len(value) < 6:
        return None
    try:
        hh = int(value[0:2]); mm = int(value[2:4]); ss = int(value[4:6])
    except ValueError:
        return None
    return hh, mm, ss


def hms_to_datetime(hms):
    if hms is None:
        return None
    h, m, s = hms
    return datetime(2000, 1, 1, h, m, s)


def get_suv_factor_from_dicom(ds: pydicom.Dataset):
    bw = getattr(ds, "PatientWeight", None)
    if bw is None:
        raise RuntimeError("Falta PatientWeight (0010,1030)")
    try:
        bw_g = float(bw) * 1000.0
    except (TypeError, ValueError):
        raise RuntimeError("PatientWeight inválido") from None

    seq = getattr(ds, "RadiopharmaceuticalInformationSequence", None)
    if not seq:
        raise RuntimeError("Falta RadiopharmaceuticalInformationSequence (0054,0016)")
    r0 = seq[0]

    inj_time = parse_time_any(getattr(r0, "RadiopharmaceuticalStartTime", None))
    half_life = getattr(r0, "RadionuclideHalfLife", None)
    total_dose = getattr(r0, "RadionuclideTotalDose", None)

    if half_life is None or total_dose is None:
        raise RuntimeError("Faltan RadionuclideHalfLife o RadionuclideTotalDose")

    try:
        half_life = float(half_life)
        total_dose = float(total_dose)
    except (TypeError, ValueError):
        raise RuntimeError("Valores inválidos en Radionuclide info") from None

    acq_dt = hms_to_datetime(parse_time_any(getattr(ds, "AcquisitionTime", None)))
    if acq_dt is None:
        acq_dt = hms_to_datetime(parse_time_any(getattr(ds, "SeriesTime", None)))
    if acq_dt is None:
        raise RuntimeError("Falta AcquisitionTime/SeriesTime")

    inj_dt = hms_to_datetime(inj_time)
    if inj_dt is None:
        raise RuntimeError("Falta RadiopharmaceuticalStartTime")

    delta_t = (acq_dt - inj_dt).total_seconds()
    lam = math.log(2.0) / half_life
    Ainj_start = total_dose * math.exp(-lam * delta_t)

    k_suv = bw_g / Ainj_start
    return k_suv, {
        "PatientWeight_kg": float(bw),
        "Ainj_Bq": total_dose,
        "HalfLife_s": half_life,
        "Delta_t_s": float(delta_t),
        "Ainj_START_Bq": Ainj_start,
        "AcqTime": acq_dt.time().isoformat(),
        "InjTime": inj_dt.time().isoformat(),
    }
