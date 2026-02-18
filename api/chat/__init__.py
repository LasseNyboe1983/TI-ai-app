import json
import os
import base64
from typing import Any

import azure.functions as func
from openai import AzureOpenAI


REQUIRED_ENV_VARS = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"]

MODEL_REGISTRY = {
    "gpt-35-turbo": {
        "kind": "chat_completions",
        "endpoint_env": "AZURE_OPENAI_ENDPOINT",
        "key_env": "AZURE_OPENAI_KEY",
        "api_version": "2025-03-01-preview",
    },
    "gpt-5-chat": {
        "kind": "responses_text",
        "endpoint_env": "AZURE_OPENAI_ENDPOINT",
        "key_env": "AZURE_OPENAI_KEY",
        "api_version": "2025-03-01-preview",
    },
    "model-router": {
        "kind": "chat_completions",
        "endpoint_env": "MODEL_ROUTER_ENDPOINT",
        "key_env": "MODEL_ROUTER_KEY",
        "fallback_endpoint_env": "AZURE_OPENAI_ENDPOINT",
        "fallback_key_env": "AZURE_OPENAI_KEY",
        "api_version": "2025-01-01-preview",
        "api_version_env": "MODEL_ROUTER_API_VERSION",
    },
    "FLUX.1-Kontext-pro": {
        "kind": "responses_mixed",
        "endpoint_env": "FLUX_ENDPOINT",
        "key_env": "FLUX_KEY",
        "fallback_endpoint_env": "AZURE_OPENAI_ENDPOINT",
        "fallback_key_env": "AZURE_OPENAI_KEY",
        "api_version": "2025-01-01-preview",
        "api_version_env": "FLUX_API_VERSION",
    },
}


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


def _resolve_model_client(model: str) -> tuple[AzureOpenAI, dict[str, str]]:
    config = MODEL_REGISTRY[model]

    endpoint = os.getenv(config["endpoint_env"]) or os.getenv(config.get("fallback_endpoint_env", ""))
    key = os.getenv(config["key_env"]) or os.getenv(config.get("fallback_key_env", ""))
    api_version = os.getenv(config.get("api_version_env", "")) or config["api_version"]

    client = AzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )
    return client, config


def _extract_image_from_response(response: Any) -> str | None:
    output = getattr(response, "output", None) or []
    for block in output:
        contents = getattr(block, "content", None) or []
        for item in contents:
            item_type = getattr(item, "type", "")
            image_url = getattr(item, "image_url", None) or getattr(item, "url", None)
            b64 = getattr(item, "b64_json", None) or getattr(item, "base64", None)
            if image_url:
                return image_url
            if b64:
                return f"data:image/png;base64,{b64}"
            if item_type in {"output_image", "image"} and image_url:
                return image_url
    return None


def _chat_with_openai(model: str, messages: list[dict[str, str]]) -> dict[str, str]:
    client, config = _resolve_model_client(model)
    kind = config["kind"]

    if kind == "chat_completions":
        response = client.chat.completions.create(model=model, messages=messages)
        text = response.choices[0].message.content or ""
        return {"type": "text", "text": text}

    response = client.responses.create(model=model, input=messages)
    text = getattr(response, "output_text", "") or ""
    if text:
        return {"type": "text", "text": text}

    image_url = _extract_image_from_response(response)
    if image_url:
        return {"type": "image", "imageUrl": image_url}

    return {"type": "text", "text": "Model returned no displayable output."}


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

    if model not in MODEL_REGISTRY:
        return _json_response({"error": "Unsupported model."}, 400)

    try:
        messages = _build_messages(history, prompt)
        model_result = _chat_with_openai(model, messages)
    except Exception as ex:
        return _json_response({"error": f"OpenAI call failed: {str(ex)}"}, 500)

    reply_type = model_result.get("type", "text")
    reply_text = model_result.get("text", "")
    image_url = model_result.get("imageUrl")

    assistant_history_content = reply_text or ("[image generated]" if image_url else "")

    updated_history = [
        *history,
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": assistant_history_content},
    ]

    return _json_response(
        {
            "reply": reply_text,
            "replyType": reply_type,
            "imageUrl": image_url,
            "conversationHistory": updated_history,
        }
    )
