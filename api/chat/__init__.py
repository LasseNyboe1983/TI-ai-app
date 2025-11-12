import json
import logging
import azure.functions as func
from ..shared.openai_client import get_client

def main(req: func.HttpRequest) -> func.HttpResponse:
  try:
    body = req.get_json()
    prompt = body.get("prompt")
    model = body.get("model")
    if not prompt or not model:
      return func.HttpResponse("Invalid request", status_code=400)

    client = get_client()
    if model.startswith("gpt-35"):
      completion = client.chat.completions.create(
          model=model,
          messages=[{"role": "user", "content": prompt}],
          max_tokens=512,
      )
      answer = completion.choices[0].message.content
    else:
      response = client.responses.create(
          model=model,
          input=[{"role": "user", "content": prompt}],
          max_output_tokens=512,
      )
      answer = response.output[0].content[0].text
    return func.HttpResponse(
        json.dumps({"answer": answer}),
        mimetype="application/json",
        status_code=200,
    )
  except Exception as exc:  # noqa: BLE001 - Azure Functions entry point
    logging.exception("Chat handler failed: %s", exc)
    return func.HttpResponse(
        json.dumps({"error": "Service unavailable", "detail": str(exc)}),
        mimetype="application/json",
        status_code=500,
    )
