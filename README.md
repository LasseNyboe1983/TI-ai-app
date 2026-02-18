# TI AI Chat Hub (Clean-Room Rebuild)

Minimal Azure Static Web Apps setup with:
- Static frontend (`frontend/`)
- Python API (`api/`) for Azure OpenAI calls
- SWA authentication gate in `staticwebapp.config.json`

## 1) Required environment variables (SWA)
Set these in Azure Static Web App Configuration:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_KEY`
- `ALLOWED_TENANT_ID` (example: your Entra tenant GUID)
- `ALLOWED_USERS` (comma-separated UPN list, example: `user014@undervis.nu`)

Optional (if `model-router` uses a separate endpoint/key/version):

- `MODEL_ROUTER_ENDPOINT`
- `MODEL_ROUTER_KEY`
- `MODEL_ROUTER_API_VERSION` (default: `2025-01-01-preview`)

Optional (if `FLUX.1-Kontext-pro` uses a separate endpoint/key/version):

- `FLUX_ENDPOINT`
- `FLUX_KEY`
- `FLUX_API_VERSION` (default: `2025-03-01-preview`)

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
