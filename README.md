# TI AI Chat Hub (Clean-Room Rebuild)

Minimal Azure Static Web Apps setup with:
- Static frontend (`frontend/`)
- Python API (`api/`) for Azure OpenAI calls
- SWA authentication gate in `staticwebapp.config.json`
- In-chat document attach (`PDF`, `DOCX`, `TXT`, `MD`) for context-aware chat

## 1) Required environment variables (SWA)
Set these in Azure Static Web App Configuration:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_KEY`
- `ALLOWED_TENANT_ID` (example: your Entra tenant GUID)
- `ALLOWED_USERS` (comma-separated UPN list, example: `user014@undervis.nu`)

Required for **Read Doc** model (embeddings indexing):

- `READ_DOC_EMBEDDING_DEPLOYMENT` (your Azure OpenAI embedding deployment name, e.g. `text-embedding-3-large-...`)

Optional for **Read Doc**:

- `READ_DOC_CHAT_MODEL` (chat model to answer with after selecting doc chunks; default: `gpt-35-turbo`)
- `READ_DOC_EMBEDDING_ENDPOINT` (if embeddings are in a different Azure OpenAI resource than chat; can be the resource endpoint like `https://<resource>.cognitiveservices.azure.com/` or even a full `/openai/deployments/.../embeddings?api-version=...` URL)
- `READ_DOC_EMBEDDING_KEY` (key for `READ_DOC_EMBEDDING_ENDPOINT`)
- `READ_DOC_EMBEDDINGS_API_VERSION` (default: `2024-02-01`; if you supply a full embeddings URL with `?api-version=...`, it will be used automatically)
- `EMBEDDINGS_API_VERSION` (default: `2024-02-01`)

Required for **Image-To-Text** (OCR + chat):

- `IMAGE_TO_TEXT_OCR_ENDPOINT` (Azure AI Vision endpoint, e.g. `https://<resource>.cognitiveservices.azure.com/`)
- `IMAGE_TO_TEXT_OCR_KEY`

Optional for **Image-To-Text**:

- `IMAGE_TO_TEXT_OCR_API_VERSION` (default: `2023-02-01-preview`)
- `IMAGE_TO_TEXT_CHAT_MODEL` (default: `gpt-35-turbo`)
- `IMAGE_TO_TEXT_CHAT_API_VERSION` (default: `2025-03-01-preview`)

Optional (if `model-router` uses a separate endpoint/key/version):

- `MODEL_ROUTER_ENDPOINT`
- `MODEL_ROUTER_KEY`
- `MODEL_ROUTER_API_VERSION` (default: `2025-01-01-preview`)

Optional (if `FLUX.1-Kontext-pro` uses a separate endpoint/key/version):

- `FLUX_ENDPOINT` (resource endpoint like `https://<resource>.openai.azure.com/` or full `.../openai/v1/`)
- `FLUX_KEY`
- `FLUX_API_VERSION` (default: `2025-04-01-preview`)

## 2) Authentication provider
In Static Web App Authentication:
- Add Microsoft Entra ID provider
- Use single-tenant app registration

## 3) Deploy mapping
When creating/reconfiguring SWA from this repo:
- App location: `frontend`
- API location: `api`
- Output location: *(blank)*

## 3.1) GitHub Actions secret
Add this repository secret before first deploy:

- `AZURE_STATIC_WEB_APPS_API_TOKEN` (from Azure Static Web App -> Manage deployment token)

## 4) First validation sequence
1. Open site in private window.
2. Confirm redirect to Entra sign-in.
3. Sign in with allowed user.
4. Verify chat page loads and can send a prompt.
5. Sign in with disallowed user and verify `/api/chat` returns `403`.

## 6) Document chat (current behavior)
- Use **Attach document** in chat actions and select `PDF`, `DOCX`, `TXT`, or `MD`.
- Maximum file size is `10 MB`.
- Document data is held only in current chat page state.
- Document context is cleared when **Clear chat** or **Sign out** is used.

## 5) Maintenance mode
Maintenance mode is currently **disabled** in this repo.

To put the app offline again, you can reintroduce a global route lock in `frontend/staticwebapp.config.json`, swap `frontend/index.html` to a maintenance page, and have API functions return `503`.
