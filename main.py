import os
import tempfile
import requests
from flask import Flask, request, jsonify, render_template_string

from invoice2data import extract_data
from invoice2data.extract.loader import read_templates

app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<title>Fattura - OCR.space + invoice2data</title>
<h2>Carica fattura (PDF, JPG, PNG)</h2>
<form method="post" action="/upload" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">Invia</button>
</form>
<p>Oppure usa POST /upload con un client (es. Postman).</p>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "Nessun file nella richiesta (field name: file)."}), 400

    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error": "File non valido."}), 400

    api_key = os.getenv("OCR_SPACE_API_KEY")
    if not api_key:
        return jsonify({"error": "Manca la Secret OCR_SPACE_API_KEY su Replit."}), 500

    files = {"file": (f.filename, f.stream, f.mimetype or "application/octet-stream")}
    data = {
        "language": "ita",
        "OCREngine": 2,
        "isTable": True,
        "scale": True,
        "isCreateSearchablePdf": True,
    }
    resp = requests.post(
        "https://api.ocr.space/parse/image",
        files=files,
        data=data,
        headers={"apikey": api_key},
        timeout=180,
    )
    try:
        ocr = resp.json()
    except Exception:
        return jsonify({"error": "Risposta OCR non valida.", "raw": resp.text[:1000]}), 502

    if ocr.get("IsErroredOnProcessing"):
        return jsonify({
            "error": "Errore in OCR.space",
            "details": ocr.get("ErrorMessage") or ocr.get("ErrorDetails"),
        }), 502

    parsed_results = ocr.get("ParsedResults") or []
    pdf_url = parsed_results[0].get("SearchablePDFURL") if parsed_results else None

    templates = []
    try:
        templates += read_templates()
    except Exception:
        pass
    try:
        templates += read_templates("templates")
    except Exception:
        pass

    result = None
    if pdf_url:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
        pdf_bin = requests.get(pdf_url, timeout=180)
        with open(pdf_path, "wb") as out:
            out.write(pdf_bin.content)

        try:
            result = extract_data(pdf_path, templates=templates, input_module="pdfminer")
        finally:
            try:
                os.remove(pdf_path)
            except Exception:
                pass

    if not result:
        raw_text = parsed_results[0].get("ParsedText", "") if parsed_results else ""
        return jsonify({"invoice": None, "raw_text": raw_text})

    return jsonify({"invoice": result})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
