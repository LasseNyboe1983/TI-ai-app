import json
import os
from typing import Any

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


def main(req: func.HttpRequest) -> func.HttpResponse:
    endpoint = _get_required_env("AZURE_OPENAI_ENDPOINT")
    api_key = _get_required_env("AZURE_OPENAI_KEY")

    deployment = (
        _get_required_env("READ_DOC_EMBEDDING_DEPLOYMENT")
        or _get_required_env("EMBEDDINGS_DEPLOYMENT")
    )

    if not endpoint or not api_key:
        return _json_response(
            {"error": "Missing required environment variables: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY"},
            500,
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

    api_version = (os.getenv("EMBEDDINGS_API_VERSION") or "2024-02-01").strip()

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
