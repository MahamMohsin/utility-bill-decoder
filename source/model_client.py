"""Only application inference gateway. No model fallback or paid service setup."""
import json
import os
from pathlib import Path
import socket
import time
import urllib.error
import urllib.request
from dotenv import load_dotenv

ALLOWED_GOOGLE_MODELS = ('gemini-3.1-flash-lite', 'gemini-3.5-flash-lite')
ROOT = Path(__file__).resolve().parents[1]

def configuration():
    load_dotenv(ROOT / '.env', override=False)
    provider = os.getenv('MODEL_PROVIDER', 'google')
    model = os.getenv('MODEL_NAME') or os.getenv('GEMINI_MODEL') or 'gemini-3.1-flash-lite'
    key = os.getenv('API_KEY') or os.getenv('GEMINI_API_KEY')
    if provider != 'google' or model not in ALLOWED_GOOGLE_MODELS:
        raise ValueError('This implementation permits only the two officially allowed Google models')
    if not key or key == 'your-api-key-here':
        raise ValueError('Set API_KEY in the project root .env')
    return model, key

class Client:
    def __init__(self):
        self.model, self._key = configuration()
        self.last_call = 0.0

    def generate(self, prompt, images=(), schema=None):
        parts = [{'text': prompt}] + list(images)
        config = {'temperature': 0, 'maxOutputTokens': 16000,
                  'responseMimeType': 'application/json'}
        if schema is not None:
            config['responseJsonSchema'] = schema
        payload = json.dumps({'contents':[{'role':'user','parts':parts}],
                              'generationConfig':config}).encode()
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent'
        for attempt in range(5):
            time.sleep(max(0, 4.2 - (time.monotonic()-self.last_call)))
            self.last_call = time.monotonic()
            request = urllib.request.Request(url, payload, {
                'Content-Type':'application/json', 'x-goog-api-key':self._key})
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    result = json.load(response)
                candidates = result.get('candidates', [])
                if not candidates or candidates[0].get('finishReason') != 'STOP':
                    raise RuntimeError('Model response blocked or incomplete; no result saved')
                body = ''.join(p.get('text','') for p in candidates[0]['content']['parts'])
                return json.loads(body)
            except urllib.error.HTTPError as error:
                code = error.code
                # Never echo request headers, URL credentials, or provider response bodies.
                if code not in (429,500,502,503,504) or attempt == 4:
                    raise RuntimeError(f'Gemini HTTP {code}; configured model {self.model}. No fallback used.') from None
                time.sleep(min(60, 5 * 2**attempt))
            except (urllib.error.URLError, socket.timeout, TimeoutError):
                if attempt == 4:
                    raise RuntimeError('Gemini network request failed after retries') from None
                time.sleep(5 * 2**attempt)
        raise RuntimeError('API retries exhausted')
