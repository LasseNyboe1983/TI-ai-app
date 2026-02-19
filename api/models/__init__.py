import json

import azure.functions as func


MODELS = [
    {"id": "gpt-35-turbo", "label": "gpt-35-turbo", "type": "chat"},
    {"id": "gpt-5-chat", "label": "gpt-5-chat", "type": "chat"},
    {"id": "model-router", "label": "model-router", "type": "chat"},
    {"id": "FLUX.1-Kontext-pro", "label": "FLUX.1-Kontext-pro", "type": "picture"},
]


def main(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": "Service temporarily unavailable: maintenance mode is active."}),
        status_code=503,
        mimetype="application/json",
    )

    return func.HttpResponse(
        json.dumps({"models": MODELS}),
        status_code=200,
        mimetype="application/json",
    )
