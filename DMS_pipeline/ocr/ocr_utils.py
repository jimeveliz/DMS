import re
import json
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def corregir_scan_range(scan_range: str) -> str:
    """Corrige el formato del rango de escaneo. Elimina un 1,/,I extra al inicio si existe."""
    if "-" not in scan_range:
        return scan_range
    ini, fin = scan_range.split("-")
    if ini.startswith(("1", "/", "I")):
        ini = ini[1:]
    if fin.startswith(("1", "/", "I")):
        fin = fin[1:]
    return f"{ini}-{fin}"


def extraer_tabla_dosimetrica(lines, paciente=None):
    """Extrae la tabla dosimétrica de las líneas OCR y
      la devuelve como un DataFrame. Empieza a buscar
      la tabla a partir de la línea que contiene "Series" y "Type".
    """
    series_rows = []
    start_table = False
    for line in lines:
        if "Series" in line and "Type" in line:
            start_table = True
            continue
        if not start_table:
            continue

        if re.match(r"^\d+\s", line):
            parts = line.split()
            if len(parts) < 3:
                series_rows.append({
                    "Serie": parts[0],
                    "Type": parts[1],
                    "ScanRange": "-",
                    "CTDIvol": "-",
                    "DLP": "-",
                    "Phantom": "-"
                })
            else:
                if "-" in parts[2]:
                    scan_range = corregir_scan_range(parts[2])
                    offset = 0
                elif len(parts) >= 4 and "-" in parts[2] + parts[3]:
                    scan_range = corregir_scan_range(parts[2] + "-" + parts[3])
                    offset = 1
                else:
                    scan_range = "-"
                    offset = 0

                if len(parts) < 5 + offset:
                    if paciente:
                        logger.warning("Se omitira la fila para el paciente: %s", paciente)
                    continue

                phantom_idx = 5 + offset
                if len(parts) > phantom_idx + 1:
                    phantom = parts[phantom_idx] + " " + parts[phantom_idx + 1]
                elif len(parts) > phantom_idx:
                    phantom = parts[phantom_idx]
                else:
                    phantom = "-"

                dlp_token = parts[4 + offset]
                if dlp_token.isdigit() and (4 + offset + 1) < len(parts) and parts[4 + offset + 1].isdigit():
                    dlp = dlp_token + "." + parts[4 + offset + 1]
                else:
                    dlp = dlp_token

                series_rows.append({
                    "Serie": parts[0],
                    "Type": parts[1],
                    "ScanRange": scan_range,
                    "CTDIvol": parts[3 + offset],
                    "DLP": dlp,
                    "Phantom": phantom
                })
    return pd.DataFrame(series_rows)


def extraer_encabezado_desde_lineas(lines):
    """Extrae el encabezado de las líneas OCR y
      lo devuelve como un diccionario. Busca las claves:
      'Patient Name', 'Exam no', 'Accession Number', 'Patient ID', 
      'Exam Description', 'Total Exam DLP'."""

    encabezado = {
        "Patient Name": None,
        "Exam no": None,
        "Accession Number": None,
        "Patient ID": None,
        "Exam Description": None,
        "Total Exam DLP": None
    }
    for line in lines:
        line_clean = line.strip().lower()
        if line_clean.startswith("patient name"):
            match = re.search(r"patient name[:\-]?\s*(.+)", line, re.IGNORECASE)
            if match:
                encabezado["Patient Name"] = match.group(1).strip()
        elif line_clean.startswith("exam no"):
            match = re.search(r"exam no[:\-]?\s*(.+)", line, re.IGNORECASE)
            if match:
                encabezado["Exam no"] = match.group(1).strip()
        elif line_clean.startswith("accession number"):
            match = re.search(r"accession number[:\-]?\s*(.+)", line, re.IGNORECASE)
            if match:
                encabezado["Accession Number"] = match.group(1).strip()
        elif line_clean.startswith("patient id"):
            match = re.search(r"patient id[:\-]?\s*(.+)", line, re.IGNORECASE)
            if match:
                encabezado["Patient ID"] = match.group(1).strip()
        elif line_clean.startswith("exam description"):
            match = re.search(r"exam description[:\-]?\s*(.+)", line, re.IGNORECASE)
            if match:
                encabezado["Exam Description"] = match.group(1).strip()
        elif line_clean.startswith("total exam dlp"):
            match = re.search(r"total exam dlp[:\-]?\s*(.+)", line, re.IGNORECASE)
            if match:
                encabezado["Total Exam DLP"] = match.group(1).strip()
    return encabezado


def guardar_json_completo(encabezado, series, nombre_archivo, dicom_header=None):
    data = {
        "encabezado": encabezado,
        "series": series
    }
    if dicom_header is not None:
        data["dicom_header"] = dicom_header
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

