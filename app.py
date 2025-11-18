import os
import json
from flask import Flask, request, jsonify, send_from_directory, redirect, session
from openai import AzureOpenAI

app = Flask(__name__, static_folder='frontend', static_url_path='')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
ALLOWED_TENANT_ID = "a157a1e5-2a04-45f5-9ca8-bd60db6bafd4"
ALLOWED_USERS = [
    "user014@undervis.nu"
]

# OpenAI client
def get_openai_client():
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2025-03-01-preview",
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
    )

# Routes for frontend
@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/chat')
@app.route('/chat.html')
def chat():
    return send_from_directory('frontend', 'chat.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('frontend', path)

# API endpoint
@app.route('/api/chat', methods=['POST'])
def chat_api():
    # Get user info from App Service Easy Auth headers
    client_principal = request.headers.get('X-MS-CLIENT-PRINCIPAL')
    
    if not client_principal:
        return jsonify({"error": "Not authenticated"}), 401
    
    # Decode the principal
    import base64
    principal_data = json.loads(base64.b64decode(client_principal).decode('utf-8'))
    
    user_id = principal_data.get('userId', '').lower()
    user_tenant_id = principal_data.get('tid', '')
    
    # Validate tenant
    if user_tenant_id.lower() != ALLOWED_TENANT_ID.lower():
        return jsonify({"error": "Access denied. Wrong tenant."}), 403
    
    # Validate user is in allowed list
    if user_id not in ALLOWED_USERS:
        return jsonify({"error": "Access denied. Your account is not authorized."}), 403
    
    # Process the request
    data = request.get_json()
    prompt = data.get('prompt')
    model = data.get('model')
    history = data.get('history', [])
    
    if not prompt or not model:
        return jsonify({"error": "Invalid request"}), 400
    
    try:
        client = get_openai_client()
        
        if model.startswith("gpt-35"):
            messages = history if history else [{"role": "user", "content": prompt}]
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=512
            )
            answer = completion.choices[0].message.content
        else:
            input_messages = history if history else [{"role": "user", "content": prompt}]
            response = client.responses.create(
                model=model,
                input=input_messages,
                max_tokens=512
            )
            answer = response.output.content
        
        return jsonify({"answer": answer})
    
    except Exception as e:
        return jsonify({"error": "An error occurred processing your request"}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8000)
