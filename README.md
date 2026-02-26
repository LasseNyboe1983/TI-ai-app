# TI AI Chat Hub (Clean-Room Rebuild)

Minimal Azure Static Web Apps setup with:
- Static frontend (`frontend/`)
- Python API (`api/`) for Azure OpenAI calls
- SWA authentication gate in `staticwebapp.config.json`
- In-chat document attach (`PDF`, `DOCX`, `TXT`, `MD`) for context-aware chat

## 0) Current build state (Feb 24, 2026)

**Deployed UX (frontend):**
- Model picker is populated from `GET /api/models`.
- The action-button area is dynamic based on selected model type:
	- **Chat** models: shows **Attach document**
	- **Image-To-Text** models: shows **Attach image file**
	- **Picture** models: shows no action buttons
- When an **Image-To-Text** model is selected, **Send** posts to `POST /api/image-to-text` (not `/api/chat`) and includes the selected file as base64.

**Backend endpoints (Azure Functions):**
- `POST /api/chat` – normal chat (supports document context)
- `POST /api/document` – parses PDF/DOCX/TXT/MD into chunks
- `GET /api/models` – returns model list for the picker
- `POST /api/embeddings` – embeddings helper (currently not wired to the UI)
- `POST /api/image-to-text` – OCR + then chat (Image-To-Text flow)

**Models shown in the picker (current):**
- `gpt-35-turbo` (type `chat`)
- `gpt-5-chat` (type `chat`)
- `model-router` (type `chat`)
- `gpt-4.1` (type `image-to-text`) – internally still uses model id `read-doc` in the API payload
- `FLUX.1-Kontext-pro` (type `picture`)

**Image-To-Text implementation details:**
- `POST /api/image-to-text` performs OCR, then injects OCR text into a system message, then calls a chat model to answer.
- OCR provider is configurable:
	- Option A: Azure AI Vision (Computer Vision) OCR via `IMAGE_TO_TEXT_OCR_ENDPOINT/KEY`
	- Option B: Azure OpenAI vision OCR via `IMAGE_TO_TEXT_VISION_DEPLOYMENT` and `IMAGE_TO_TEXT_VISION_BASE_URL` (recommended when using Foundry deployments only)

**Known gaps / TODOs:**
- The embeddings-based document indexing feature exists (`/api/embeddings`) but is not currently exposed in the UI.
- The image picker allows selecting *any* file (per requirement), but non-image files may fail when sent to the vision OCR step.
- For clarity, consider renaming the Image-To-Text model id from `read-doc` to something like `image-to-text` (would require updating frontend/back-end checks).

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

Choose ONE OCR provider:

Option A) Azure AI Vision (Computer Vision) OCR:

- `IMAGE_TO_TEXT_OCR_ENDPOINT` (Azure AI Vision endpoint, e.g. `https://<vision-resource>.cognitiveservices.azure.com/`)
- `IMAGE_TO_TEXT_OCR_KEY`

Option B) Azure OpenAI vision OCR (no separate Vision resource):

- `IMAGE_TO_TEXT_VISION_DEPLOYMENT` (a vision-capable deployment, e.g. a GPT-4.1 / GPT-4o deployment)
- `IMAGE_TO_TEXT_VISION_BASE_URL` (e.g. `https://<resource>.openai.azure.com/openai/v1/`)
- `IMAGE_TO_TEXT_VISION_KEY` (defaults to `AZURE_OPENAI_KEY` if omitted)

Optional for **Image-To-Text**:

- `IMAGE_TO_TEXT_OCR_API_VERSION` (default: `2023-02-01-preview`, only for Option A)
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

The app is using normal authenticated routing in `frontend/staticwebapp.config.json`, the full app UI in `frontend/index.html`, and live API function handlers.

## 7) Collaboration workflow
- Changes made in this workspace are intended for the GitHub project.
- Default expectation: after completing requested changes, stage, commit, and push updates to `origin/main`.
- Default expectation: batch all requested edits into one consolidated change set whenever feasible, to minimize repeated Accept actions.
