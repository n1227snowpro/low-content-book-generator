#!/usr/bin/env python3
"""
Low-Content Book Generator — Web UI + API backend
Run locally:  python3 app.py
Cloud:        gunicorn app:app
"""

import io
import os
import hmac
import hashlib
from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

PAGE_SIZES = {
    "8.25x11":  (8.25, 11.0),
    "8.5x11":   (8.5,  11.0),
    "6x9":      (6.0,   9.0),
    "5.5x8.5":  (5.5,   8.5),
}

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


def build_pdf(file_stream, num_pages, page_size, output_name):
    img_raw = Image.open(file_stream)
    img = img_raw.convert("RGB")

    if page_size in PAGE_SIZES:
        w_in, _ = PAGE_SIZES[page_size]
        dpi_x = img.width / w_in
    else:
        dpi = img_raw.info.get("dpi", (300, 300))
        dpi_x = dpi[0] if isinstance(dpi, tuple) else dpi
        if not dpi_x or dpi_x < 1:
            dpi_x = 300

    pages = [img.copy() for _ in range(num_pages - 1)]
    pdf_buffer = io.BytesIO()
    img.save(pdf_buffer, format="PDF", save_all=True, append_images=pages, resolution=dpi_x)
    pdf_buffer.seek(0)
    return pdf_buffer


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    """Web UI endpoint — returns PDF as download."""
    if "image" not in request.files:
        return jsonify({"error": "No image file uploaded."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        return jsonify({"error": "Only JPG and PNG files are supported."}), 400

    try:
        num_pages = int(request.form.get("pages", 100))
        if num_pages < 1 or num_pages > 1000:
            return jsonify({"error": "Pages must be between 1 and 1000."}), 400
    except ValueError:
        return jsonify({"error": "Invalid page count."}), 400

    output_name = request.form.get("output_name", "").strip()
    if not output_name:
        base = os.path.splitext(file.filename)[0]
        output_name = f"{base}_{num_pages}pages"
    if not output_name.endswith(".pdf"):
        output_name += ".pdf"

    page_size = request.form.get("page_size", "original")

    try:
        pdf_buffer = build_pdf(file.stream, num_pages, page_size, output_name)
        return send_file(pdf_buffer, mimetype="application/pdf",
                         as_attachment=True, download_name=output_name)
    except Exception as e:
        return jsonify({"error": f"Failed to generate PDF: {str(e)}"}), 500


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """
    REST API endpoint.

    Accepts multipart/form-data:
      - image       (file)    JPG or PNG
      - pages       (int)     default 100
      - page_size   (string)  8.25x11 | 8.5x11 | 6x9 | 5.5x8.5 | original
      - output_name (string)  optional filename

    Optional header:
      X-API-Key: <WEBHOOK_SECRET env var>

    Returns: PDF binary (application/pdf)
    """
    # Optional API key auth
    if WEBHOOK_SECRET:
        key = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(key, WEBHOOK_SECRET):
            return jsonify({"error": "Unauthorized"}), 401

    if "image" not in request.files:
        return jsonify({"error": "No image file uploaded."}), 400

    file = request.files["image"]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        return jsonify({"error": "Only JPG and PNG files are supported."}), 400

    try:
        num_pages = int(request.form.get("pages", 100))
        if num_pages < 1 or num_pages > 1000:
            return jsonify({"error": "Pages must be between 1 and 1000."}), 400
    except ValueError:
        return jsonify({"error": "Invalid page count."}), 400

    page_size = request.form.get("page_size", "8.25x11")
    output_name = request.form.get("output_name", "").strip()
    if not output_name:
        base = os.path.splitext(file.filename)[0]
        output_name = f"{base}_{num_pages}pages"
    if not output_name.endswith(".pdf"):
        output_name += ".pdf"

    try:
        pdf_buffer = build_pdf(file.stream, num_pages, page_size, output_name)
        return send_file(pdf_buffer, mimetype="application/pdf",
                         as_attachment=True, download_name=output_name)
    except Exception as e:
        return jsonify({"error": f"Failed to generate PDF: {str(e)}"}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9000))
    app.run(debug=True, port=port)
