"""Exercise browser state and pipeline integration without network calls."""
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest
from schemas import Extraction
from web_app import decoding_error, extract_upload

ROOT = Path(__file__).resolve().parents[1]


def sample():
    import json
    data = json.loads((ROOT / 'source/reference_kesc_0008.json').read_text())
    return Extraction.model_validate({'bill': data, 'evidence': {'history': [], 'details': [], 'uncertainties': []}})


class BrowserTests(unittest.TestCase):
    def test_missing_key_has_actionable_safe_message(self):
        message = decoding_error(ValueError('Set API_KEY in the project root .env'))
        self.assertIn('restart', message)
        self.assertIn('your-api-key-here', message)
        self.assertNotIn('secret-provider-body', decoding_error(RuntimeError('secret-provider-body')))

    def test_empty_and_populated_chat(self):
        # First table rendering imports pandas/Arrow; allow cold Windows startup.
        app = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=15).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.chat_input[0].disabled)
        self.assertTrue(app.button[0].disabled)
        # The empty uploader resets prior state only when its identity changes.
        app.session_state['result'] = sample()
        app.session_state['client'] = object()
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.chat_input[0].disabled)
        self.assertEqual(len(app.metric), 3)
        with patch('web_app.answer_questions', return_value={'user': 'Grounded answer'}):
            app.chat_input[0].set_value('Explain my charges').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['messages'][-1]['content'], 'Grounded answer')
        with patch('web_app.answer_questions', side_effect=RuntimeError('secret-provider-body')):
            app.chat_input[0].set_value('Try again').run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertNotIn('secret-provider-body', app.error[0].value)

    def test_temporary_upload_is_removed(self):
        data = io.BytesIO()
        Image.new('RGB', (20, 20), 'white').save(data, format='PNG')
        captured = []
        def fake_extract(client, path, cache):
            self.assertTrue(path.exists())
            captured.append(path)
            return 'result'
        with patch('web_app.extract', side_effect=fake_extract):
            self.assertEqual(extract_upload(data.getvalue(), object()), 'result')
        self.assertFalse(captured[0].exists())


if __name__ == '__main__':
    unittest.main()
