#!/usr/bin/env python3
"""Interface web sans dépendances externes pour piloter Extract + Transform."""

from __future__ import annotations

import html
import os
import subprocess
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
EXTRACT_SCRIPT = BASE_DIR / "1-extract" / "woocommerce_to_wizi.py"
TRANSFORM_SCRIPT = BASE_DIR / "2-transform" / "add_notes_filters.py"
LOAD_INPUT_DIR = BASE_DIR / "3-load" / "input"
UPLOAD_DIR = WEB_DIR / "uploads"


def run_command(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, cwd=str(BASE_DIR), capture_output=True, text=True)
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return result.returncode, output.strip()


def render_page(error: str = "", success: bool = False, outputs: tuple[str, str] | None = None, logs: list[tuple[str, list[str], int, str]] | None = None) -> str:
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

    return f"""<!doctype html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Migration WooCommerce → WiziShop</title>
  <link rel=\"stylesheet\" href=\"/styles.css\" />
</head>
<body>
  <main class=\"container\">
    <header>
      <h1>Interface ETL WooCommerce → WiziShop</h1>
      <p>Utilisez cette interface pour exécuter <strong>Extract + Transform</strong> sans CLI.</p>
    </header>

    <section class=\"card\">
      <h2>Lancer la conversion</h2>
      <form method=\"post\" action=\"/run\" enctype=\"multipart/form-data\">
        <label for=\"woocommerce_csv\">CSV WooCommerce</label>
        <input id=\"woocommerce_csv\" name=\"woocommerce_csv\" type=\"file\" accept=\".csv\" required />
        <button type=\"submit\">Lancer le pipeline</button>
      </form>
      <p class=\"hint\">L'étape Load API reste manuelle (script privé).</p>
    </section>

    {error_html}
    {success_html}
    {logs_section}
  </main>
</body>
</html>"""


class ETLHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._send_html(render_page())
            return

        if self.path == "/styles.css":
            css_path = WEB_DIR / "static" / "styles.css"
            if not css_path.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "styles.css introuvable")
                return
            content = css_path.read_text(encoding="utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Page introuvable")

    def do_POST(self):
        if self.path != "/run":
            self.send_error(HTTPStatus.NOT_FOUND, "Page introuvable")
            return

        content_type = self.headers.get("Content-Type", "")
        boundary_key = "boundary="
        if "multipart/form-data" not in content_type or boundary_key not in content_type:
            self._send_html(render_page(error="Format d'upload invalide."), status=HTTPStatus.BAD_REQUEST)
            return

        boundary = content_type.split(boundary_key, maxsplit=1)[1].encode("utf-8")
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)

        file_bytes, filename = self._extract_file_from_multipart(data, boundary, b"woocommerce_csv")
        if not file_bytes:
            self._send_html(render_page(error="Veuillez sélectionner un CSV WooCommerce avant de lancer."), status=HTTPStatus.BAD_REQUEST)
            return

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        LOAD_INPUT_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        upload_name = f"woocommerce_source_{timestamp}_{Path(filename).name or 'upload.csv'}"
        upload_path = UPLOAD_DIR / upload_name
        upload_path.write_bytes(file_bytes)

        extract_name = f"woocommerce_converted_ui_{timestamp}.csv"
        extract_output = LOAD_INPUT_DIR / extract_name

        logs = []

        cmd_extract = ["python3", str(EXTRACT_SCRIPT), str(upload_path), "--output", extract_name]
        extract_code, extract_log = run_command(cmd_extract)
        logs.append(("Étape 1 - Extract", cmd_extract, extract_code, extract_log))

        if extract_code != 0:
            self._send_html(render_page(error="L'étape Extract a échoué.", logs=logs), status=HTTPStatus.BAD_REQUEST)
            return

        transform_output = LOAD_INPUT_DIR / "woocommerce_converted_with_filters.csv"
        cmd_transform = [
            "python3", str(TRANSFORM_SCRIPT), "--input", str(extract_output), "--output", str(transform_output)
        ]
        transform_code, transform_log = run_command(cmd_transform)
        logs.append(("Étape 2 - Transform", cmd_transform, transform_code, transform_log))

        if transform_code != 0:
            self._send_html(render_page(error="L'étape Transform a échoué.", logs=logs), status=HTTPStatus.BAD_REQUEST)
            return

        self._send_html(
            render_page(
                success=True,
                outputs=(str(extract_output.relative_to(BASE_DIR)), str(transform_output.relative_to(BASE_DIR))),
                logs=logs,
            )
        )

    def _extract_file_from_multipart(self, body: bytes, boundary: bytes, field_name: bytes) -> tuple[bytes, str]:
        marker = b"name=\"" + field_name + b"\""
        for part in body.split(b"--" + boundary):
            if marker not in part:
                continue
            if b"filename=\"" not in part:
                continue
            header, _, payload = part.partition(b"\r\n\r\n")
            if not payload:
                continue
            payload = payload.rstrip(b"\r\n")
            filename = "upload.csv"
            filename_marker = b"filename=\""
            if filename_marker in header:
                filename_start = header.index(filename_marker) + len(filename_marker)
                filename_end = header.find(b"\"", filename_start)
                filename = header[filename_start:filename_end].decode("utf-8", errors="ignore")
            return payload, filename
        return b"", ""

    def _send_html(self, content: str, status: HTTPStatus = HTTPStatus.OK):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    host = os.getenv("ETL_UI_HOST", "0.0.0.0")
    port = int(os.getenv("ETL_UI_PORT", "5000"))
    server = ThreadingHTTPServer((host, port), ETLHandler)
    print(f"✅ Interface disponible sur http://{host}:{port}")
    print("   Ctrl+C pour arrêter")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
