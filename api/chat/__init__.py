import json
import logging
import os
import azure.functions as func
from ..shared.openai_client import get_client

ALLOWED_TENANT_ID = "a157a1e5-2a04-45f5-9ca8-bd60db6bafd4"

def main(req: func.HttpRequest) -> func.HttpResponse:
  try:
    # Validate tenant ID from Azure Static Web Apps auth headers
    principal_header = req.headers.get('x-ms-client-principal')
    if principal_header:
      import base64
      principal_data = json.loads(base64.b64decode(principal_header).decode('utf-8'))
      user_tenant_id = principal_data.get('tid')
      user_id = principal_data.get('userId', '')
      
      # Block personal Microsoft account domains
      personal_domains = ['hotmail.com', 'gmail.com', 'outlook.com', 'live.com', 'yahoo.com']
      is_personal = any(domain in user_id.lower() for domain in personal_domains)
      
      # Block personal Microsoft account tenant
      personal_tenant = '9188040d-6c67-4c5b-b112-36a304b66dad'
      
      if is_personal or user_tenant_id == personal_tenant:
        logging.warning(f"Personal account blocked: {user_id}, tenant: {user_tenant_id}")
        return func.HttpResponse(
          json.dumps({"error": "Personal Microsoft accounts are not permitted."}),
          mimetype="application/json",
          status_code=403
        )
      
      # Require tenant ID to be present
      if not user_tenant_id:
        logging.warning(f"No tenant ID for user: {user_id}")
        return func.HttpResponse(
          json.dumps({"error": "Access denied. Tenant verification required."}),
          mimetype="application/json",
          status_code=403
        )
      
      # Verify tenant matches
      if user_tenant_id.lower() != ALLOWED_TENANT_ID.lower():
        logging.warning(f"Access denied for tenant: {user_tenant_id}")
        return func.HttpResponse(
          json.dumps({"error": "Access denied. Only users from the authorized organization can access this service."}),
          mimetype="application/json",
          status_code=403
        )
    
    body = req.get_json()
    prompt = body.get("prompt")
    model = body.get("model")
    history = body.get("history", [])
    
    if not prompt or not model:
      return func.HttpResponse("Invalid request", status_code=400)

    client = get_client()
    
    # Use conversation history for context
    if model.startswith("gpt-35"):
      # For chat completions, use full message history
      messages = history if history else [{"role": "user", "content": prompt}]
      completion = client.chat.completions.create(
          model=model,
          messages=messages,
          max_tokens=512,
      )
      answer = completion.choices[0].message.content
    else:
      # For responses API, use input array with history
      input_messages = history if history else [{"role": "user", "content": prompt}]
      response = client.responses.create(
          model=model,
          input=input_messages,
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
        json.dumps({"error": "Service unavailable. Please try again later."}),
        mimetype="application/json",
        status_code=500,
    )
