import base64
import json
from io import BytesIO
from typing import Any

import azure.functions as func
from docx import Document
from pypdf import PdfReader


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200000
CHUNK_SIZE = 1400
CHUNK_OVERLAP = 200
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _extension(file_name: str) -> str:
    lower_name = (file_name or "").strip().lower()
    if "." not in lower_name:
        return ""
    return "." + lower_name.rsplit(".", 1)[1]


def _decode_payload(raw_b64: str) -> bytes:
    payload = (raw_b64 or "").strip()
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload, validate=True)


def _extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx_text(data: bytes) -> str:
    document = Document(BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_text(file_ext: str, data: bytes) -> str:
    if file_ext == ".pdf":
        return _extract_pdf_text(data)
    if file_ext == ".docx":
        return _extract_docx_text(data)
    if file_ext in {".txt", ".md"}:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="ignore")
    return ""


def _normalize_text(text: str) -> str:
    compact = "\n".join(line.rstrip() for line in text.splitlines())
    return compact.strip()


def _chunk_text(text: str) -> list[str]:
    value = text[:MAX_TEXT_CHARS]
    chunks: list[str] = []
    start = 0

    while start < len(value):
        end = min(start + CHUNK_SIZE, len(value))
        chunks.append(value[start:end].strip())
        if end >= len(value):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)

    return [chunk for chunk in chunks if chunk]


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body."}, 400)

    file_name = (body.get("fileName") or "").strip()
    file_content_b64 = body.get("fileContentBase64") or ""

    if not file_name:
        return _json_response({"error": "fileName is required."}, 400)
    if not file_content_b64:
        return _json_response({"error": "fileContentBase64 is required."}, 400)

    file_ext = _extension(file_name)
    if file_ext not in ALLOWED_EXTENSIONS:
        return _json_response(
            {"error": "Unsupported file type. Allowed: PDF, DOCX, TXT, MD."},
            400,
        )

    try:
        file_bytes = _decode_payload(file_content_b64)
    except Exception:
        return _json_response({"error": "Invalid base64 file payload."}, 400)

    if len(file_bytes) > MAX_FILE_BYTES:
        max_mb = MAX_FILE_BYTES // (1024 * 1024)
        return _json_response({"error": f"File too large. Max size is {max_mb} MB."}, 413)

    try:
        extracted = _extract_text(file_ext, file_bytes)
    except Exception as ex:
        return _json_response({"error": f"Failed to parse document: {str(ex)}"}, 400)

    normalized = _normalize_text(extracted)
    if not normalized:
        return _json_response({"error": "No readable text found in this document."}, 400)

    chunks = _chunk_text(normalized)

    return _json_response(
        {
            "fileName": file_name,
            "chunks": chunks,
            "chunkCount": len(chunks),
            "charCount": len(normalized),
            "maxFileBytes": MAX_FILE_BYTES,
            "maxFileMb": MAX_FILE_BYTES // (1024 * 1024),
        }
    )
