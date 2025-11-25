from fastapi import FastAPI, Request
from seed_mongo import db  # db:cliente de mongo.
from typing import List, Dict, Any, Optional, Set
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path
import re
from datetime import datetime
import html as html_lib
import logging

def _make_serializable(doc: dict) -> dict:
    """Convierte ObjectId a str y deja el resto igual para JSON."""
    if not doc:
        return doc
    d = dict(doc)
    _id = d.get("_id")
    if _id is not None:
        d["_id"] = str(_id)
    return d

app = FastAPI(title="API")

# [config]
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
LOGGER = logging.getLogger("index")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)

# Endpoints conocidos a detectar en HTML
KNOWN_ENDPOINTS: Dict[str, str] = {
    "/ct": "ct",
    "/ocr": "ocr",
    "/pet": "pet",
}

# Busca titulo y descripcion en HTML
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_DESC_RE = re.compile(
    r"<meta[^>]+name=[\"']description[\"'][^>]*content=[\"'](.*?)[\"']",
    re.IGNORECASE | re.DOTALL,
)


def _is_hidden_or_ignored(name: str) -> bool:
    return name.startswith(".") or name.startswith("_")


def extract_title(file_path: Path) -> Optional[str]:
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            chunk = f.read(4096)  # ~4KB
        m = TITLE_RE.search(chunk)
        if not m:
            return None
        # Normalizar espacios y entidades HTML
        title = html_lib.unescape(" ".join(m.group(1).split()))
        return title if title else None
    except Exception as e:
        LOGGER.warning("No se pudo extraer <title> de %s: %s", file_path, e)
        return None


def extract_description(file_path: Path) -> Optional[str]:
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            chunk = f.read(8192)
        m = META_DESC_RE.search(chunk)
        if not m:
            return None
        desc = html_lib.unescape(" ".join(m.group(1).split()))
        return desc if desc else None
    except Exception as e:
        LOGGER.debug("No se pudo extraer meta description de %s: %s", file_path, e)
        return None


def detect_endpoints(file_path: Path) -> List[str]:
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        LOGGER.warning("No se pudo leer %s para detectar endpoints: %s", file_path, e)
        return []

    found: Set[str] = set()
    for pattern, key in KNOWN_ENDPOINTS.items():
        if pattern in content or pattern.replace("/", "\\/") in content:
            found.add(key)
    return sorted(found)


def scan_static(static_dir: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not static_dir.exists():
        LOGGER.warning("El directorio static no existe: %s", static_dir)
        return items

    for root, dirs, files in os.walk(static_dir):
        # Filtrar directorios ignorados
        dirs[:] = [d for d in dirs if not _is_hidden_or_ignored(d)]
        for fname in files:
            if _is_hidden_or_ignored(fname):
                continue
            if not fname.lower().endswith(".html"):
                continue
            fpath = Path(root) / fname
            try:
                rel_path = fpath.relative_to(static_dir)
            except Exception:
                rel_path = Path(fname)

            ruta_rel = rel_path.as_posix()
            url = f"/static/{ruta_rel}"


            title = extract_title(fpath) or rel_path.stem
            desc = extract_description(fpath)

            items.append(
                {
                    "titulo": title,
                    "url": url,
                    "descripcion": desc,
                }
            )

    # Orden: por título ascendente y luego por URL
    items.sort(key=lambda x: (x.get("titulo", "").lower(), x.get("url", "")))
    return items

@app.get("/ping") #verifica la conexion con mongoDB"""
async def ping():
    # Verifica conexión con MongoDB ejecutando un comando ligero
    await db.command("ping")
    return {"status": "ok"}


@app.get("/ct") #enrutadores para obtener datos de la coleccion ct
async def obtener_pacientes():
    # Lee documentos de la colección y pasa por la función de serialización
    docs = await db["series_ct"].find().to_list(length=3000)
    pacientes = [_make_serializable(d) for d in docs]
    return {"pacientes": pacientes}

@app.get("/ocr")
async def obtener_pacientes():
    #Lee algunos documentos de la colección (ajusta el nombre si es necesario)
    docs = await db["dose_report"].find().to_list(length=1000)
    pacientes = [_make_serializable(d) for d in docs]
    return {"pacientes": pacientes}


@app.get("/pet")
async def obtener_pacientes():
    #Lee algunos documentos de la colección (ajusta el nombre si es necesario)
    docs = await db["series_pet1"].find().to_list(length=1000)
    pacientes = [_make_serializable(d) for d in docs]
    return {"pacientes": pacientes}


from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# [endpoint JSON]
@app.get("/_apps.json")
def apps_json():
    items = scan_static(STATIC_DIR)
    return JSONResponse(content={"items": items})


# [endpoint HTML]
@app.get("/")
def index():
    items = scan_static(STATIC_DIR)
    total = len(items)
    # Construir filas HTML
    def _esc(s: Optional[str]) -> str:
        return html_lib.escape(s or "")

    rows = []
    for it in items:
        
        row = f"""
        <tr class=\"row\" data-search=\"{_esc((it.get('titulo','')+' '+it.get('url','')))}\">
            <td>{_esc(it.get('titulo'))}</td>
            <td><a href=\"{_esc(it.get('url'))}\" target=\"_blank\">{_esc(it.get('url'))}</a></td>
            <td>{_esc(it.get('descripcion') or '')}</td>
        </tr>
        """
        rows.append(row)

    rows_html = "\n".join(rows)

    empty_msg = "" if total else "<p>No se encontraron archivos .html en /static.</p>"

    html = f"""
    <!DOCTYPE html>
    <html lang=\"es\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Índice de visualizaciones</title>
        <style>
            body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 20px; color: #1f2937; }}
            h1 {{ margin: 0 0 10px; font-size: 22px; }}
            .toolbar {{ display: flex; align-items: center; gap: 10px; margin: 10px 0 16px; }}
            #search {{ padding: 8px 10px; width: 360px; max-width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 8px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }}
            th {{ background: #f8fafc; position: sticky; top: 0; z-index: 1; }}
            tr:hover {{ background: #f9fafb; }}
            .muted {{ color: #6b7280; }}
            .count {{ font-size: 13px; color: #6b7280; }}
            .copy-btn {{ padding: 4px 8px; border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 6px; cursor: pointer; }}
            .copy-btn:hover {{ background: #eef2ff; }}
            .table-wrap {{ overflow: auto; max-height: 75vh; border: 1px solid #e5e7eb; border-radius: 6px; }}
            .footer {{ margin-top: 10px; }}
        </style>
    </head>
    <body>
        <h1>Índice de visualizaciones</h1>
        <div class=\"toolbar\">
            <input id=\"search\" type=\"text\" placeholder=\"Buscar por título, URL o endpoint...\" oninput=\"filter()\" />
            <span class=\"count\"><span id=\"shown\">{total}</span> de <span id=\"total\">{total}</span> páginas</span>
            <a class=\"muted\" href=\"/_apps.json\" target=\"_blank\">Ver JSON</a>
        </div>
        {empty_msg}
        <div class=\"table-wrap\">
        <table>
            <thead>
                <tr>
                    <th>Título</th>
                    <th>URL</th>
                    <th>Descripción</th>
                </tr>
            </thead>
            <tbody id=\"tbody\">
                {rows_html}
            </tbody>
        </table>
        </div>

        <script>
        function norm(s) {{ return (s || '').toLowerCase(); }}

        function filter() {{
            var q = norm(document.getElementById('search').value);
            var rows = document.querySelectorAll('#tbody tr');
            var shown = 0;
            rows.forEach(function(row) {{
                var haystack = row.getAttribute('data-search') || '';
                var ok = !q || norm(haystack).indexOf(q) !== -1;
                row.style.display = ok ? '' : 'none';
                if (ok) shown++;
            }});
            document.getElementById('shown').textContent = shown;
        }}

        document.addEventListener('click', function(e) {{
            var btn = e.target.closest('.copy-btn');
            if (!btn) return;
            var relative = btn.getAttribute('data-url') || '';
            var absolute = window.location.origin + relative;
            navigator.clipboard.writeText(absolute).then(function() {{
                btn.textContent = 'Copiado!';
                setTimeout(function() {{ btn.textContent = 'Copiar URL'; }}, 1200);
            }}).catch(function() {{
                btn.textContent = 'Error';
                setTimeout(function() {{ btn.textContent = 'Copiar URL'; }}, 1200);
            }});
        }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
