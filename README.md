# Apigee LLM Gateway & Security Guardrails

Enterprise AI Gateway solution built on Google Cloud Apigee, Cloud Run, Google GenAI (Gemini), and Google Cloud Model Armor.

---

## Architecture Diagram

```mermaid
graph TD
    Client["Client Application"] -->|1. POST /v1/llms-gw-api/gemini<br/>apikey, prompt, model| Apigee

    subgraph Apigee["Apigee API Proxy (llms-gw-api)"]
        direction TB
        VA["VA-VerifyApiKey<br/>(Extracts API Product attributes)"]
        SA["SA-SpikeArrest & Q-DynamicQuota"]
        FC["FC-SanitizePrompt<br/>(PromptSanitization Shared Flow)"]
        DC["DC-LlmUsedTokens<br/>(DataCapture -> dc_llm_used_tokens)"]

        VA --> SA --> FC
    end

    subgraph CloudRun["Cloud Run Service (apigee-integration)"]
        direction TB
        SanitizeEndpoint["POST /sanitizePrompt<br/>(Validates Prompt Safety)"]
        GeminiEndpoint["POST /gemini<br/>(Calls GenAI SDK & Counts Tokens)"]
    end

    subgraph GCP["Google Cloud AI Services"]
        ModelArmor["Google Cloud Model Armor<br/>(llm-shield-template, us-central1)"]
        GeminiAPI["Google GenAI<br/>(Gemini 2.5 / Flash Models)"]
    end

    FC -->|2. ServiceCallout<br/>POST /sanitizePrompt| SanitizeEndpoint
    SanitizeEndpoint -->|3. REST API: sanitizeUserPrompt| ModelArmor
    ModelArmor -->|4. Verdict: NO_MATCH_FOUND / MATCH_FOUND| SanitizeEndpoint
    SanitizeEndpoint -->|5. Sanitization result| FC

    Apigee -->|6. Target Forward<br/>POST /gemini| GeminiEndpoint
    GeminiEndpoint -->|7. SDK generate_content| GeminiAPI
    GeminiAPI -->|8. Generated text + token metadata| GeminiEndpoint
    GeminiEndpoint -->|9. JSON: prompt, response, tokens_count| Apigee

    Apigee --> DC
    DC -->|10. Final Response HTTP 200| Client
```

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client App
    participant Apigee as Apigee (llms-gw-api)
    participant Run as Cloud Run (apigee-integration)
    participant MA as Model Armor
    participant Gemini as Google GenAI (Gemini)

    Client->>Apigee: POST /v1/llms-gw-api/gemini (apikey, model, prompt)
    Note over Apigee: VA-VerifyApiKey (reads ModelArmorTemplatePath)<br/>SA-SpikeArrest & Q-DynamicQuota

    opt ModelArmorTemplatePath is configured on API Product
        Apigee->>Run: POST /sanitizePrompt (prompt, model_armor_template_url)
        Run->>MA: POST /templates/...:sanitizeUserPrompt (Bearer Token)
        MA-->>Run: sanitizationResult (matchState)

        alt Violation Detected (MATCH_FOUND)
            Run-->>Apigee: {"verdict": "MATCH_FOUND", "message": "..."}
            Apigee-->>Client: 400 Bad Request (RF-RaiseFault)
        else Safety Check Passed (NO_MATCH_FOUND)
            Run-->>Apigee: {"verdict": "NO_MATCH_FOUND"}
        end
    end

    Apigee->>Run: POST /gemini (prompt, model, X-Max-Output-Tokens, X-Api-Key)
    Run->>Gemini: client.models.generate_content(...)
    Gemini-->>Run: response text + total_token_count
    Run-->>Apigee: 200 OK {"prompt": "...", "response": "...", "tokens_count": N}

    Note over Apigee: DC-LlmUsedTokens records tokens_count into dc_llm_used_tokens
    Apigee-->>Client: 200 OK (prompt, response, tokens_count)
```

---

## Repository Structure

```
.
├── README.md                              # Root repository documentation & architecture
├── .gitignore                             # Git ignore rules
├── llms-gw-api_rev20_2026_10_07/          # Apigee API Proxy bundle (/v1/llms-gw-api)
│   └── apiproxy/                          # Policies, proxies, and target endpoints
├── PromptSanitization_rev4_2026_10_07/    # Apigee Shared Flow bundle
│   └── sharedflowbundle/                  # Service Callout & Raise Fault policies
├── model-armor/                           # Model Armor security template configurations
│   └── llm-shield-template-importable.json # Importable template configuration
└── integration/                           # Cloud Run backend microservice
    ├── main.py                            # Flask application (/gemini, /sanitizePrompt)
    ├── pyproject.toml                     # Python dependencies (uv)
    ├── uv.lock                            # Dependency lockfile
    └── README.md                          # Backend service documentation
```

---

## Request Flow Overview

1. **Client Request:** Client calls the Apigee proxy endpoint (`POST /v1/llms-gw-api/gemini`) with an API key, target model, and prompt.
2. **Authentication & Rate Limiting:**
   - `VA-VerifyApiKey` validates credentials and extracts API Product attributes (`ModelArmorTemplatePath`, `max_output_tokens`).
   - `SA-SpikeArrest` and `Q-DynamicQuota` enforce traffic management policies.
3. **Prompt Sanitization:**
   - If `ModelArmorTemplatePath` is configured, Apigee invokes `FC-SanitizePrompt` (Shared Flow).
   - The shared flow issues a `ServiceCallout` to the Cloud Run `/sanitizePrompt` endpoint.
   - Cloud Run invokes Google Cloud Model Armor (`:sanitizeUserPrompt`) to inspect for prompt injection, jailbreaks, malicious URLs, and safety violations.
   - If a violation is detected (`MATCH_FOUND`), a `400 Bad Request` fault is raised and execution stops.
4. **LLM Generation:**
   - When the prompt passes safety checks, Apigee forwards the request to Cloud Run (`POST /gemini`).
   - Cloud Run uses the `google-genai` SDK to generate content with the Gemini model.
5. **Analytics & Data Capture:**
   - The response includes the generated text and `tokens_count`.
   - `DC-LlmUsedTokens` captures the consumed token count into the Apigee Data Collector (`dc_llm_used_tokens`).
   - Apigee returns the final response (HTTP 200) to the client.
