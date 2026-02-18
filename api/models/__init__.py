import json

import azure.functions as func


MODELS = [
    {"id": "gpt-35-turbo", "label": "gpt-35-turbo", "type": "text"},
    {"id": "gpt-5-chat", "label": "gpt-5-chat", "type": "text"},
    {"id": "model-router", "label": "model-router", "type": "text"},
    {"id": "FLUX.1-Kontext-pro", "label": "FLUX.1-Kontext-pro", "type": "image"},
]


def main(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"models": MODELS}),
        status_code=200,
        mimetype="application/json",
    )
