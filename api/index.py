#!/usr/bin/env python3
"""Vercel entrypoint (WSGI) for the ETL web interface, without external web framework."""

from __future__ import annotations

import cgi
import html
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parents[1]
TMP_DIR = Path("/tmp/etl-ui")
UPLOAD_DIR = TMP_DIR / "uploads"
OUTPUT_DIR = TMP_DIR / "output"

EXTRACT_SCRIPT = BASE_DIR / "1-extract" / "woocommerce_to_wizi.py"
TRANSFORM_SCRIPT = BASE_DIR / "2-transform" / "add_notes_filters.py"
FILTERS_CSV = BASE_DIR / "3-load" / "input" / "filtres_wizishop.csv"
SOURCE_CSV = BASE_DIR / "export_webtoffe_woocommerce.csv"


def run_command(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, cwd=str(BASE_DIR), capture_output=True, text=True)
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return result.returncode, output.strip()


def render_page(error: str = "", success: bool = False, outputs: tuple[str, str] | None = None, logs: list[tuple[str, list[str], int, str]] | None = None) -> bytes:
    logs = logs or []
    logs_html = ""
    for step_name, command, code, output in logs:
        cmd = html.escape(" ".join(command))
        log_output = html.escape(output or "(aucune sortie)")
        logs_html += f"""
        <article class=\"log-block\">
          <h3>{html.escape(step_name)}</h3>
          <p><strong>Commande :</strong> <code>{cmd}</code></p>
          <p><strong>Code de retour :</strong> {code}</p>
          <pre>{log_output}</pre>
        </article>
        """

    success_html = ""
    if success and outputs:
        success_html = f"""
        <section class=\"card success\">
          <h3>Pipeline terminé ✅</h3>
          <ul>
            <li>CSV converti : <code>{html.escape(outputs[0])}</code></li>
            <li>CSV enrichi : <code>{html.escape(outputs[1])}</code></li>
          </ul>
          <p class=\"hint\">Sur Vercel, ces fichiers sont temporaires (stockage éphémère).</p>
        </section>
        """

    error_html = ""
    if error:
        error_html = f"""
        <section class=\"card error\">
          <h3>Erreur</h3>
          <p>{html.escape(error)}</p>
        </section>
        """

    logs_section = f"""
    <section class=\"card\">
      <h2>Logs d'exécution</h2>
      {logs_html}
    </section>
    """ if logs else ""

    page = f"""<!doctype html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Migration WooCommerce → WiziShop (Vercel)</title>
  <style>
  :root {{ --bg:#0f172a; --card:#111827; --border:#334155; --text:#e2e8f0; --muted:#94a3b8; --primary:#22c55e; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:linear-gradient(180deg,var(--bg),#020617); color:var(--text); }}
  .container {{ max-width:920px; margin:0 auto; padding:2rem 1rem 3rem; }}
  .card {{ background:rgba(17,24,39,.95); border:1px solid var(--border); border-radius:14px; padding:1rem; margin-top:1rem; }}
  label {{ display:block; margin-bottom:.4rem; font-weight:600; }}
  input[type=file] {{ display:block; margin-bottom:.8rem; width:100%; }}
  button {{ border:0; background:var(--primary); color:#052e16; font-weight:700; padding:.65rem 1rem; border-radius:10px; cursor:pointer; }}
  .hint {{ color:var(--muted); font-size:.92rem; }}
  .error {{ border-color:#7f1d1d; }} .success {{ border-color:#14532d; }}
  code {{ background:#1e293b; color:#cbd5e1; padding:.1rem .35rem; border-radius:6px; }}
  .log-block {{ border-top:1px solid var(--border); margin-top:.6rem; padding-top:.6rem; }}
  pre {{ white-space:pre-wrap; word-break:break-word; background:#020617; border:1px solid #1e293b; border-radius:10px; padding:.6rem; max-height:280px; overflow:auto; }}
  </style>
</head>
<body>
  <main class=\"container\">
    <header>
      <h1>Interface ETL WooCommerce → WiziShop (Vercel)</h1>
      <p>Upload un CSV WooCommerce puis lance <strong>Extract + Transform</strong>.</p>
    </header>

    <section class=\"card\">
      <h2>Lancer la conversion</h2>
      <form method=\"post\" enctype=\"multipart/form-data\">
        <label for=\"woocommerce_csv\">CSV WooCommerce</label>
        <input id=\"woocommerce_csv\" name=\"woocommerce_csv\" type=\"file\" accept=\".csv\" required />
        <button type=\"submit\">Lancer le pipeline</button>
      </form>
      <p class=\"hint\">⚠️ Les fonctions Vercel ont un timeout: pour des gros CSV, préférez exécuter localement.</p>
    </section>

    {error_html}
    {success_html}
    {logs_section}
  </main>
</body>
</html>"""
    return page.encode("utf-8")


def parse_upload(environ: dict) -> tuple[bytes, str]:
    if environ.get("REQUEST_METHOD") != "POST":
        return b"", ""

    form = cgi.FieldStorage(
        fp=environ["wsgi.input"],
        environ=environ,
        keep_blank_values=True,
    )
    fileitem = form["woocommerce_csv"] if "woocommerce_csv" in form else None
    if fileitem is None or not getattr(fileitem, "file", None):
        return b"", ""

    file_bytes = fileitem.file.read()
    filename = getattr(fileitem, "filename", "upload.csv") or "upload.csv"
    return file_bytes, filename


def app(environ: dict, start_response) -> Iterable[bytes]:
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")

    if path != "/":
        body = b"Not Found"
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    if method == "GET":
        body = render_page()
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    if method != "POST":
        body = b"Method Not Allowed"
        start_response("405 Method Not Allowed", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    content_type = (environ.get("CONTENT_TYPE") or "").lower()
    content_length = environ.get("CONTENT_LENGTH") or "0"
    if "multipart/form-data" not in content_type or content_length in ("", "0"):
        body = render_page(error="Veuillez sélectionner un CSV WooCommerce avant de lancer.")
        start_response("400 Bad Request", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    file_bytes, filename = parse_upload(environ)
    if not file_bytes:
        body = render_page(error="Veuillez sélectionner un CSV WooCommerce avant de lancer.")
        start_response("400 Bad Request", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    if not FILTERS_CSV.exists():
        body = render_page(error="Fichier manquant: 3-load/input/filtres_wizishop.csv. Ajoutez-le au projet pour utiliser Transform.")
        start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]
    if not SOURCE_CSV.exists():
        body = render_page(error="Fichier manquant: export_webtoffe_woocommerce.csv à la racine du projet.")
        start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    upload_name = f"woocommerce_source_{timestamp}_{Path(filename).name}"
    upload_path = UPLOAD_DIR / upload_name
    upload_path.write_bytes(file_bytes)

    extract_output = OUTPUT_DIR / f"woocommerce_converted_ui_{timestamp}.csv"
    transform_output = OUTPUT_DIR / "woocommerce_converted_with_filters.csv"

    logs = []
    cmd_extract = ["python3", str(EXTRACT_SCRIPT), str(upload_path), "--output", str(extract_output)]
    extract_code, extract_log = run_command(cmd_extract)
    logs.append(("Étape 1 - Extract", cmd_extract, extract_code, extract_log))

    if extract_code != 0:
        body = render_page(error="L'étape Extract a échoué.", logs=logs)
        start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    cmd_transform = [
        "python3", str(TRANSFORM_SCRIPT), "--input", str(extract_output), "--output", str(transform_output),
        "--filters", str(FILTERS_CSV), "--source", str(SOURCE_CSV)
    ]
    transform_code, transform_log = run_command(cmd_transform)
    logs.append(("Étape 2 - Transform", cmd_transform, transform_code, transform_log))

    if transform_code != 0:
        body = render_page(error="L'étape Transform a échoué.", logs=logs)
        start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    body = render_page(success=True, outputs=(str(extract_output), str(transform_output)), logs=logs)
    start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
    return [body]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    server = make_server("0.0.0.0", 5000, app)
    print("✅ Interface disponible sur http://0.0.0.0:5000")
    server.serve_forever()
