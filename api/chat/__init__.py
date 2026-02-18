import json
import os
from typing import Any

import azure.functions as func
from openai import AzureOpenAI


REQUIRED_ENV_VARS = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"]


def _json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _get_claim(claims: list[dict[str, str]], key: str) -> str | None:
    for claim in claims:
        if claim.get("typ") == key:
            return claim.get("val")
    return None


def _extract_identity(req: func.HttpRequest) -> tuple[str | None, str | None]:
    raw = req.headers.get("x-ms-client-principal")
    if not raw:
        return None, None

    try:
        import base64

        decoded = base64.b64decode(raw).decode("utf-8")
        principal = json.loads(decoded)
    except Exception:
        return None, None

    claims = principal.get("claims", [])
    tenant_id = _get_claim(claims, "tid")
    user_upn = (
        _get_claim(claims, "preferred_username")
        or _get_claim(claims, "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn")
        or principal.get("userDetails")
    )
    return tenant_id, (user_upn.lower() if user_upn else None)


def _validate_env() -> str | None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        return f"Missing required environment variables: {', '.join(missing)}"
    return None


def _build_messages(history: list[dict[str, str]], prompt: str) -> list[dict[str, str]]:
    messages = [item for item in history if item.get("role") in {"user", "assistant", "system"}]
    messages.append({"role": "user", "content": prompt})
    return messages


def _chat_with_openai(model: str, messages: list[dict[str, str]]) -> str:
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version="2025-03-01-preview",
    )

    if model == "gpt-5-chat":
        response = client.responses.create(model=model, input=messages)
        return response.output_text or ""

    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content or ""


def main(req: func.HttpRequest) -> func.HttpResponse:
    env_error = _validate_env()
    if env_error:
        return _json_response({"error": env_error}, 500)

    tenant_id, user_upn = _extract_identity(req)

    allowed_tenant_id = (os.getenv("ALLOWED_TENANT_ID") or "").strip().lower()
    allowed_users = {
        user.strip().lower()
        for user in (os.getenv("ALLOWED_USERS") or "").split(",")
        if user.strip()
    }

    if allowed_tenant_id and (tenant_id or "").lower() != allowed_tenant_id:
        return _json_response({"error": "Access denied: wrong tenant."}, 403)

    if allowed_users and (user_upn not in allowed_users):
        return _json_response({"error": "Access denied: user not allowed."}, 403)

    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body."}, 400)

    prompt = (body.get("prompt") or "").strip()
    model = (body.get("model") or "gpt-35-turbo").strip()
    history = body.get("conversationHistory") or []

    if not prompt:
        return _json_response({"error": "Prompt is required."}, 400)

    if model not in {"gpt-35-turbo", "gpt-5-chat"}:
        return _json_response({"error": "Unsupported model."}, 400)

    try:
        messages = _build_messages(history, prompt)
        reply = _chat_with_openai(model, messages)
    except Exception as ex:
        return _json_response({"error": f"OpenAI call failed: {str(ex)}"}, 500)

    updated_history = [
        *history,
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": reply},
    ]

    return _json_response({"reply": reply, "conversationHistory": updated_history})
