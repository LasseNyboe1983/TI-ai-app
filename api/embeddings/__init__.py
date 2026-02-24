import json
import os
from typing import Any
from urllib.parse import parse_qs, urlparse

import azure.functions as func
from openai import AzureOpenAI


MAX_INPUTS = 128
MAX_TEXT_CHARS = 8000


def _json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _get_required_env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def _normalize_azure_openai_endpoint(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""

    parsed = urlparse(raw)
    path = (parsed.path or "").rstrip("/")

    if "/openai" in path:
        before_openai = path.split("/openai", 1)[0]
        raw = f"{parsed.scheme}://{parsed.netloc}{before_openai}"

    return raw.rstrip("/")


def _extract_deployment_from_url(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    path = parsed.path or ""
    marker = "/openai/deployments/"
    if marker not in path:
        return None

    tail = path.split(marker, 1)[1]
    deployment = tail.split("/", 1)[0].strip()
    return deployment or None


def _extract_api_version_from_url(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    query = parse_qs(parsed.query or "")
    versions = query.get("api-version") or query.get("api_version")
    if not versions:
        return None
    version = str(versions[0] or "").strip()
    return version or None


def main(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response(
        {"error": "Service temporarily unavailable: maintenance mode is active."},
        503,
    )

    raw_endpoint = (
        _get_required_env("READ_DOC_EMBEDDING_ENDPOINT")
        or _get_required_env("AZURE_OPENAI_ENDPOINT")
    )
    api_key = (
        _get_required_env("READ_DOC_EMBEDDING_KEY")
        or _get_required_env("AZURE_OPENAI_KEY")
    )

    if not raw_endpoint or not api_key:
        return _json_response(
            {
                "error": (
                    "Missing required environment variables: "
                    "READ_DOC_EMBEDDING_ENDPOINT (or AZURE_OPENAI_ENDPOINT), "
                    "READ_DOC_EMBEDDING_KEY (or AZURE_OPENAI_KEY)"
                )
            },
            500,
        )

    endpoint = _normalize_azure_openai_endpoint(raw_endpoint)

    deployment = (
        _get_required_env("READ_DOC_EMBEDDING_DEPLOYMENT")
        or _get_required_env("EMBEDDINGS_DEPLOYMENT")
        or _extract_deployment_from_url(raw_endpoint)
    )

    if not deployment:
        return _json_response(
            {
                "error": "Missing required environment variable: READ_DOC_EMBEDDING_DEPLOYMENT (or EMBEDDINGS_DEPLOYMENT)"
            },
            500,
        )

    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body."}, 400)

    inputs = body.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return _json_response({"error": "'inputs' must be a non-empty array of strings."}, 400)

    if len(inputs) > MAX_INPUTS:
        return _json_response(
            {"error": f"Too many inputs. Max is {MAX_INPUTS}."},
            413,
        )

    cleaned: list[str] = []
    for item in inputs:
        if not isinstance(item, str):
            return _json_response({"error": "All items in 'inputs' must be strings."}, 400)
        text = item.strip()
        if not text:
            cleaned.append("")
            continue
        cleaned.append(text[:MAX_TEXT_CHARS])

    api_version = (
        (os.getenv("READ_DOC_EMBEDDINGS_API_VERSION") or "").strip()
        or (os.getenv("EMBEDDINGS_API_VERSION") or "").strip()
        or _extract_api_version_from_url(raw_endpoint)
        or "2024-02-01"
    )

    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )

    try:
        response = client.embeddings.create(
            model=deployment,
            input=cleaned,
        )
    except Exception as ex:
        return _json_response({"error": f"Embeddings call failed: {str(ex)}"}, 500)

    vectors: list[list[float] | None] = [None] * len(cleaned)
    for item in getattr(response, "data", []) or []:
        index = getattr(item, "index", None)
        embedding = getattr(item, "embedding", None)
        if isinstance(index, int) and 0 <= index < len(vectors) and isinstance(embedding, list):
            vectors[index] = embedding

    if any(v is None for v in vectors):
        return _json_response(
            {"error": "Embeddings response was missing one or more vectors."},
            500,
        )

    dim = len(vectors[0]) if vectors and vectors[0] else 0

    usage = getattr(response, "usage", None)
    usage_payload = None
    if usage is not None:
        usage_payload = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    return _json_response(
        {
            "deployment": deployment,
            "apiVersion": api_version,
            "dimension": dim,
            "embeddings": vectors,
            "usage": usage_payload,
        }
    )
