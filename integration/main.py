import os
from flask import Flask, request, jsonify
from google import genai
from google.genai import types
import requests
import logging
import google.auth.transport.requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/gemini', methods=['POST'])
def gemini_request_handler():
    try:
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "Invalid JSON payload"}), 400

        prompt = request_data.get('prompt')
        model = request_data.get('model')
        max_output_tokens = request.headers.get('X-Max-Output-Tokens')
        api_key = request.headers.get('X-Api-Key')

        missing_params = []
        if not prompt: missing_params.append('prompt (JSON)')
        if not model: missing_params.append('model (JSON)')
        if not max_output_tokens: missing_params.append('X-Max-Output-Tokens (Header)')
        if not api_key: missing_params.append('X-Api-Key (Header)')

        if missing_params:
            if 'X-Api-Key (Header)' in missing_params:
                logger.error(f"API key header missing for Gemini. Ensure Apigee is injecting it correctly. Missing: {missing_params}")
                return jsonify({"error": "Authentication required: API key not provided by proxy."}), 401
            else:
                logger.error(f"Missing required parameters in Gemini request: {missing_params}")
                return jsonify({"error": f"Missing required parameters: {', '.join(missing_params)}"}), 400

        response = get_gemini_response(prompt, model, api_key, max_output_tokens)
        return response
    except Exception as e:
        logger.error(f"Error in Gemini request handler: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error processing Gemini request: {str(e)}"}), 500


def get_gemini_response(prompt, model, api_key, max_tokens):
    try:
        client = genai.Client(api_key=api_key)
        generation_config = types.GenerateContentConfig(
            temperature=0.5,
            top_p=0.95,
            top_k=64,
            max_output_tokens=int(max_tokens),
            response_mime_type="text/plain",
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=generation_config,
        )
        usage_metadata = response.usage_metadata
        tokens_count = usage_metadata.total_token_count if usage_metadata else None

        resp = {
            "prompt": prompt,
            "response": response.text,
            "tokens_count": tokens_count
        }
        return jsonify(resp)
    except Exception as e:
        logger.error(f"Error calling Gemini API in get_gemini_response: {e}", exc_info=True)
        return jsonify({"error": f"Error calling Gemini API: {str(e)}"}), 500


@app.route('/sanitizePrompt', methods=['POST'])
def prompt_sanitization_handler():
    try:
        request_data = request.get_json()
        prompt = request_data['prompt']
        model_armor_template_url = request_data['model_armor_template_url']

        id_token = get_id_token()
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {id_token}'
        }
        modelarmor_request_data = {'user_prompt_data': {'text': prompt}}
        modelarmor_response = requests.post(model_armor_template_url, headers=headers, json=modelarmor_request_data)
        modelarmor_response.raise_for_status()

        response_data = modelarmor_response.json()
        if response_data.get('sanitizationResult', {}).get('filterMatchState') == 'MATCH_FOUND':
            matching_filters = find_matching_filter_types(response_data)
            return {
                "verdict": "MATCH_FOUND",
                "message": f"Prompt failed sanity check due to the following filters: {', '.join(matching_filters)}"
            }
        else:
            return {"verdict": "NO_MATCH_FOUND", "message": "Prompt passed sanity check."}
    except Exception as e:
        return {"verdict": "ERROR", "message": f"Error interacting with ModelArmor : {e}"}


def find_matching_filter_types(response_data):
    matching_filters = []
    try:
        sanitization_result = response_data.get('sanitizationResult', {})
        filter_results = sanitization_result.get('filterResults', {})

        for category, filter_dict in filter_results.items():
            if not isinstance(filter_dict, dict):
                continue

            for filter_name, filter_data in filter_dict.items():
                if not isinstance(filter_data, dict):
                    continue

                if 'inspectResult' in filter_data:
                    filter_data = filter_data['inspectResult']

                if filter_data.get('matchState') == 'MATCH_FOUND':
                    # Check for nested Responsible AI (RAI) filters
                    rai_types = filter_data.get('raiFilterTypeResults')
                    if rai_types and isinstance(rai_types, dict):
                        for rai_name, rai_val in rai_types.items():
                            if isinstance(rai_val, dict) and rai_val.get('matchState') == 'MATCH_FOUND':
                                matching_filters.append(f"rai:{rai_name}")
                    else:
                        matching_filters.append(category)

        return sorted(list(set(matching_filters)))
    except Exception as e:
        logger.error(f"Error parsing Model Armor filter types: {e}", exc_info=True)
        return []
    

def get_id_token():
    creds, _ = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token


def main():
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


if __name__ == "__main__":
    main()

