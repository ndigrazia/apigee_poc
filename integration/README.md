# Apigee Integration Backend Service

A lightweight Flask microservice deployed on Google Cloud Run that integrates with Google GenAI (Gemini) and Google Cloud Model Armor. It handles LLM request processing, token consumption counting, and prompt safety sanitization.

---

## Tech Stack & Dependencies

- **Runtime:** Python `>= 3.14`
- **Package Manager:** [`uv`](https://github.com/astral-sh/uv)
- **Framework:** Flask 3.1.x, Gunicorn 26.x
- **Google Cloud SDKs:** `google-genai`, `google-auth`
- **HTTP Client:** `requests`

---

## Configuration & Environment Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `PORT` | Integer | `8080` | Port for the HTTP server to listen on. |
| `GOOGLE_APPLICATION_CREDENTIALS` | String | *(Optional)* | Path to service account key file when running outside GCP. On Cloud Run, Application Default Credentials (ADC) are used automatically. |

---

## API Endpoints

### 1. `POST /gemini`

Generates content using the Google GenAI SDK and returns the generated text along with total token count metadata.

#### Required Headers
| Header | Type | Description |
| :--- | :--- | :--- |
| `X-Api-Key` | String | Gemini API key required for `genai.Client(api_key=...)`. |
| `X-Max-Output-Tokens` | Integer | Maximum tokens allowed for generation. |

#### Request Body
```json
{
  "prompt": "Explain API gateways in 3 bullet points",
  "model": "gemini-2.5-flash"
}
```

#### Response (HTTP 200)
```json
{
  "prompt": "Explain API gateways in 3 bullet points",
  "response": "1. Traffic Management...\n2. Security...\n3. Monitoring...",
  "tokens_count": 84
}
```

#### Error Responses
- **`400 Bad Request`:** Missing JSON body or missing required fields (`prompt`, `model`, `X-Max-Output-Tokens`).
- **`401 Unauthorized`:** Missing `X-Api-Key` header.
- **`500 Internal Server Error`:** Exception during Gemini API invocation.

---

### 2. `POST /sanitizePrompt`

Sends user prompt text to Google Cloud Model Armor to check for prompt injection, jailbreaks, malicious URLs, sensitive data leakage, and Responsible AI (RAI) safety violations.

#### Authentication
Uses Google Application Default Credentials (`google.auth.default()`) to generate a Bearer token automatically when calling the Model Armor REST API.

#### Request Body
```json
{
  "prompt": "Hello world",
  "model_armor_template_url": "https://modelarmor.us-central1.rep.googleapis.com/v1/projects/tma-gemini-enterprise/locations/us-central1/templates/llm-shield-template:sanitizeUserPrompt"
}
```

> **Note:** The `model_armor_template_url` field also accepts Google Cloud resource paths (e.g. `projects/<project>/locations/<location>/templates/<template_id>`).

#### Response (Prompt Passed - HTTP 200)
```json
{
  "verdict": "NO_MATCH_FOUND",
  "message": "Prompt passed sanity check."
}
```

#### Response (Violation Detected - HTTP 200)
```json
{
  "verdict": "MATCH_FOUND",
  "message": "Prompt failed sanity check due to the following filters: pi_and_jailbreak, rai:dangerous"
}
```

#### Response (Error - HTTP 400 / 500)
```json
{
  "verdict": "ERROR",
  "message": "Error interacting with ModelArmor : <error details>"
}
```

---

## Local Development

### 1. Install Dependencies
```bash
# Sync virtual environment using uv
uv sync
```

### 2. Run the Service

**Development Server:**
```bash
uv run python main.py
```

**Production Server (Gunicorn):**
```bash
uv run gunicorn --bind 0.0.0.0:8080 main:app
```

---

## Testing

### Test `/gemini`
```bash
curl -i -X POST "http://localhost:8080/gemini" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_GEMINI_API_KEY" \
  -H "X-Max-Output-Tokens: 1024" \
  -d '{
    "prompt": "Hello Gemini",
    "model": "gemini-2.5-flash"
  }'
```

### Test `/sanitizePrompt`
```bash
curl -i -X POST "http://localhost:8080/sanitizePrompt" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello world",
    "model_armor_template_url": "https://modelarmor.us-central1.rep.googleapis.com/v1/projects/tma-gemini-enterprise/locations/us-central1/templates/llm-shield-template:sanitizeUserPrompt"
  }'
```

---

## Deployment (Cloud Run)

Deploy the service directly to Google Cloud Run from this directory:

```bash
gcloud run deploy apigee-integration \
  --source . \
  --project tma-gemini-enterprise \
  --region us-central1 \
  --service-account 154372397551-compute@developer.gserviceaccount.com \
  --port 8080 \
  --allow-unauthenticated
```

