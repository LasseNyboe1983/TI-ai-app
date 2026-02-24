import base64
import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import azure.functions as func
from openai import AzureOpenAI, OpenAI


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_OCR_CHARS = 12000
MAX_VISION_OCR_CHARS = 24000


def _json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _decode_payload(raw_b64: str) -> bytes:
    payload = (raw_b64 or "").strip()
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload, validate=True)


def _guess_image_mime(file_name: str) -> str:
    lower = (file_name or "").strip().lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return "image/png"


def _normalize_openai_v1_base_url(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.endswith("/openai/v1"):
        return raw + "/"
    if raw.endswith("/openai/v1/"):
        return raw
    return raw + "/openai/v1/"


def _extract_read_text(read_result: dict[str, Any]) -> str:
    content = read_result.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    blocks = read_result.get("blocks")
    if not isinstance(blocks, list):
        return ""

    lines: list[str] = []
    for block in blocks:
        for line in (block or {}).get("lines") or []:
            text = (line or {}).get("text")
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())

    return "\n".join(lines).strip()


def _ocr_with_azure_ai_vision(image_bytes: bytes) -> str:
    endpoint = _env("IMAGE_TO_TEXT_OCR_ENDPOINT")
    key = _env("IMAGE_TO_TEXT_OCR_KEY")

    if not endpoint or not key:
        raise RuntimeError("Missing OCR settings.")

    api_version = _env("IMAGE_TO_TEXT_OCR_API_VERSION") or "2023-02-01-preview"

    lowered_endpoint = endpoint.lower()
    if "/openai/" in lowered_endpoint or lowered_endpoint.endswith(".openai.azure.com"):
        raise RuntimeError(
            "IMAGE_TO_TEXT_OCR_ENDPOINT appears to be an Azure OpenAI endpoint. "
            "If you want OCR via Azure OpenAI vision, set IMAGE_TO_TEXT_VISION_DEPLOYMENT (and optionally IMAGE_TO_TEXT_VISION_BASE_URL/KEY) "
            "and remove IMAGE_TO_TEXT_OCR_ENDPOINT/KEY."
        )

    base = endpoint.rstrip("/")
    url = f"{base}/computervision/imageanalysis:analyze?{urlencode({'api-version': api_version, 'features': 'read'})}"

    req = Request(
        url,
        method="POST",
        data=image_bytes,
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/octet-stream",
        },
    )

    with urlopen(req, timeout=30) as res:
        raw = res.read().decode("utf-8")

    payload = json.loads(raw) if raw else {}
    read_result = payload.get("readResult")
    if not isinstance(read_result, dict):
        raise RuntimeError("OCR service did not return readResult.")

    return _extract_read_text(read_result)


def _ocr_with_azure_openai_vision(image_bytes: bytes, file_name: str) -> str:
    deployment = _env("IMAGE_TO_TEXT_VISION_DEPLOYMENT")
    if not deployment:
        raise RuntimeError("Missing OCR settings.")

    base_url = (
        _env("IMAGE_TO_TEXT_VISION_BASE_URL")
        or _env("AZURE_OPENAI_V1_BASE_URL")
        or _env("AZURE_OPENAI_ENDPOINT")
    )
    key = _env("IMAGE_TO_TEXT_VISION_KEY") or _env("AZURE_OPENAI_KEY")

    if not base_url or not key:
        raise RuntimeError(
            "Missing OCR settings: IMAGE_TO_TEXT_VISION_BASE_URL (or AZURE_OPENAI_V1_BASE_URL/AZURE_OPENAI_ENDPOINT) and IMAGE_TO_TEXT_VISION_KEY (or AZURE_OPENAI_KEY)."
        )

    normalized_base_url = _normalize_openai_v1_base_url(base_url)
    client = OpenAI(base_url=normalized_base_url, api_key=key)

    mime = _guess_image_mime(file_name)
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    instruction = (
        "Extract all text from the image exactly as written. "
        "Preserve line breaks when possible. "
        "If there is no text, return an empty string."
    )

    completion = client.chat.completions.create(
        model=deployment,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        temperature=0,
    )

    text = (completion.choices[0].message.content or "").strip()
    return text[:MAX_VISION_OCR_CHARS]


def _ocr_image(image_bytes: bytes, file_name: str) -> str:
    """Try OCR via Azure AI Vision first (if configured), otherwise via Azure OpenAI vision (if configured)."""

    endpoint = _env("IMAGE_TO_TEXT_OCR_ENDPOINT")
    key = _env("IMAGE_TO_TEXT_OCR_KEY")
    if endpoint and key:
        return _ocr_with_azure_ai_vision(image_bytes)

    # No Vision resource configured; try Azure OpenAI vision OCR.
    return _ocr_with_azure_openai_vision(image_bytes, file_name)


def _build_messages(history: list[dict[str, str]], prompt: str, ocr_text: str) -> list[dict[str, str]]:
    messages = [item for item in history if item.get("role") in {"user", "assistant", "system"}]

    safe_ocr = (ocr_text or "").strip()[:MAX_OCR_CHARS]
    if safe_ocr:
        messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "You are helping a user interpret an image that has been OCR'd into text. "
                    "Use the OCR text as the primary source. If the OCR text is insufficient, say so clearly.\n\n"
                    f"OCR text:\n{safe_ocr}"
                ),
            },
        )

    messages.append({"role": "user", "content": prompt})
    return messages


def main(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response(
        {"error": "Service temporarily unavailable: maintenance mode is active."},
        503,
    )

    openai_endpoint = _env("AZURE_OPENAI_ENDPOINT")
    openai_key = _env("AZURE_OPENAI_KEY")

    if not openai_endpoint or not openai_key:
        return _json_response(
            {"error": "Missing required environment variables: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY"},
            500,
        )

    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body."}, 400)

    prompt = (body.get("prompt") or "").strip()
    history = body.get("conversationHistory") or []
    file_name = (body.get("fileName") or "").strip()
    file_b64 = body.get("fileContentBase64") or ""

    if not prompt:
        return _json_response({"error": "Prompt is required."}, 400)

    if not file_name or not file_b64:
        return _json_response(
            {"error": "Image-To-Text requires a selected file (fileName + fileContentBase64)."},
            400,
        )

    try:
        image_bytes = _decode_payload(file_b64)
    except Exception:
        return _json_response({"error": "Invalid base64 file payload."}, 400)

    if len(image_bytes) > MAX_IMAGE_BYTES:
        max_mb = MAX_IMAGE_BYTES // (1024 * 1024)
        return _json_response({"error": f"File too large. Max size is {max_mb} MB."}, 413)

    try:
        ocr_text = _ocr_image(image_bytes, file_name)
    except Exception as ex:
        return _json_response({"error": f"OCR failed: {str(ex)}"}, 500)

    model = _env("IMAGE_TO_TEXT_CHAT_MODEL") or _env("READ_DOC_CHAT_MODEL") or "gpt-35-turbo"
    api_version = _env("IMAGE_TO_TEXT_CHAT_API_VERSION") or "2025-03-01-preview"

    client = AzureOpenAI(
        api_key=openai_key,
        azure_endpoint=openai_endpoint,
        api_version=api_version,
    )

    messages = _build_messages(history, prompt, ocr_text)

    try:
        response = client.chat.completions.create(model=model, messages=messages)
        reply = response.choices[0].message.content or ""
    except Exception as ex:
        return _json_response({"error": f"Chat call failed: {str(ex)}"}, 500)

    assistant_history_content = reply or "(No response)"

    updated_history = [
        *history,
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": assistant_history_content},
    ]

    return _json_response(
        {
            "reply": reply,
            "replyType": "text",
            "ocrTextPreview": (ocr_text or "")[:600],
            "conversationHistory": updated_history,
        }
    )
