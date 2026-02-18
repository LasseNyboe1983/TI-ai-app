import json
import os
import base64
from typing import Any

import azure.functions as func
from openai import AzureOpenAI


REQUIRED_ENV_VARS = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"]


def _tenant_from_issuer(issuer: str | None) -> str | None:
    if not issuer:
        return None

    marker = "login.microsoftonline.com/"
    if marker not in issuer:
        return None

    tail = issuer.split(marker, 1)[1]
    tenant = tail.split("/", 1)[0].strip().lower()
    return tenant or None


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


def _first_claim(claims: list[dict[str, str]], keys: list[str]) -> str | None:
    for key in keys:
        value = _get_claim(claims, key)
        if value:
            return value
    return None


def _extract_identity(req: func.HttpRequest) -> tuple[str | None, str | None, str | None]:
    raw = req.headers.get("x-ms-client-principal")
    if not raw:
        return None, None, None

    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        principal = json.loads(decoded)
    except Exception:
        return None, None, None

    claims = principal.get("claims", [])
    tenant_id = _first_claim(
        claims,
        [
            "tid",
            "http://schemas.microsoft.com/identity/claims/tenantid",
            "tenantid",
        ],
    )
    if not tenant_id:
        tenant_id = _tenant_from_issuer(_first_claim(claims, ["iss"]))
    user_upn = (
        _first_claim(
            claims,
            [
                "preferred_username",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
                "upn",
                "email",
                "name",
            ],
        )
        or principal.get("userDetails")
    )
    provider = principal.get("identityProvider")
    return tenant_id, (user_upn.lower() if user_upn else None), provider


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)

    try:
        decoded = base64.urlsafe_b64decode(payload + padding).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _extract_identity_from_aad_tokens(req: func.HttpRequest) -> tuple[str | None, str | None]:
    token = req.headers.get("x-ms-token-aad-id-token") or req.headers.get("x-ms-token-aad-access-token")
    if not token:
        return None, None

    payload = _decode_jwt_payload(token)
    if not payload:
        return None, None

    tenant_id = payload.get("tid")
    if not tenant_id:
        tenant_id = _tenant_from_issuer(str(payload.get("iss") or ""))
    user_upn = (
        payload.get("preferred_username")
        or payload.get("upn")
        or payload.get("email")
    )

    return (
        str(tenant_id).lower() if tenant_id else None,
        str(user_upn).lower() if user_upn else None,
    )


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

    if model in {"gpt-5-chat", "model-router"}:
        response = client.responses.create(model=model, input=messages)
        return response.output_text or ""

    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content or ""


def main(req: func.HttpRequest) -> func.HttpResponse:
    env_error = _validate_env()
    if env_error:
        return _json_response({"error": env_error}, 500)

    tenant_id, user_upn, provider = _extract_identity(req)
    if not tenant_id or not user_upn:
        token_tenant_id, token_user_upn = _extract_identity_from_aad_tokens(req)
        tenant_id = tenant_id or token_tenant_id
        user_upn = user_upn or token_user_upn

    allowed_tenant_id = (os.getenv("ALLOWED_TENANT_ID") or "").strip().lower()
    allowed_users = {
        user.strip().lower()
        for user in (os.getenv("ALLOWED_USERS") or "").split(",")
        if user.strip()
    }

    if provider and provider.lower() != "aad":
        return _json_response({"error": "Access denied: Microsoft Entra sign-in required."}, 403)

    if allowed_users and (user_upn not in allowed_users):
        return _json_response({"error": "Access denied: user not allowed."}, 403)

    if allowed_tenant_id:
        if tenant_id:
            if tenant_id.lower() != allowed_tenant_id:
                actual_tenant = tenant_id
                return _json_response(
                    {
                        "error": f"Access denied: wrong tenant. expected={allowed_tenant_id} actual={actual_tenant}",
                        "expectedTenant": allowed_tenant_id,
                        "actualTenant": actual_tenant,
                    },
                    403,
                )
        elif not allowed_users:
            return _json_response(
                {
                    "error": "Access denied: tenant claim missing and no ALLOWED_USERS fallback configured.",
                    "expectedTenant": allowed_tenant_id,
                    "actualTenant": "missing",
                },
                403,
            )

    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body."}, 400)

    prompt = (body.get("prompt") or "").strip()
    model = (body.get("model") or "gpt-35-turbo").strip()
    history = body.get("conversationHistory") or []

    if not prompt:
        return _json_response({"error": "Prompt is required."}, 400)

    if model not in {"gpt-35-turbo", "gpt-5-chat", "model-router"}:
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
