"""Single-user Streamlit interface for the shared bill pipeline."""
import hashlib
import io
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError

from extractor import extract
from model_client import Client, ROOT
from question_answering import answer_questions


def amount(value):
    return 'Not printed' if value is None else f'Rs {value:,.2f}'


def decoding_error(error):
    """Expose known configuration fixes without echoing provider bodies or secrets."""
    if isinstance(error, ValueError):
        if str(error) == 'Set API_KEY in the project root .env':
            return ('Your Gemini API key is missing. Open .env in the project folder, '
                    'replace your-api-key-here with your key, save, and restart the app '
                    '(Ctrl+C in PowerShell, then run the Streamlit command again).')
        if str(error) == 'This implementation permits only the two officially allowed Google models':
            return ('Check .env: MODEL_PROVIDER must be google and MODEL_NAME must be '
                    'gemini-3.1-flash-lite or gemini-3.5-flash-lite. Restart after editing.')
    return 'Unable to decode this bill. Check your local API configuration and connection, then try again.'


def read_upload(data):
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return ImageOps.exif_transpose(image).convert('RGB')


def extract_upload(data, client):
    # A stable neutral filename enables caching without keeping the uploaded image.
    with tempfile.TemporaryDirectory(prefix='bill-decoder-') as directory:
        path = Path(directory) / 'bill.png'
        read_upload(data).save(path)
        return extract(client, path, ROOT / 'cache')


def main():
    st.set_option('client.toolbarMode', 'viewer')
    st.set_page_config(page_title='Bill Decoder | Know your bill', page_icon='⚡', layout='wide')
    st.markdown((Path(__file__).with_name('web_style.css')).read_text(), unsafe_allow_html=True)
    st.markdown('''<div class="brandbar"><div><span class="brandmark">BD</span> BILL DECODER</div>
    <span class="edition">WOMEN TECH QUEST / 2026</span></div>
    <div class="hero"><div><h1>YOUR BILL. <span>DECODED.</span></h1>
    <p>Upload. Understand. Ask. <span class="provider-tags">KE / LESCO / IESCO</span></p></div>
    <div class="hero-stamp" aria-hidden="true">ϟ</div></div>''', unsafe_allow_html=True)

    for key, default in [('upload_id', None), ('result', None), ('messages', []), ('client', None)]:
        if key not in st.session_state:
            st.session_state[key] = default

    left, right = st.columns([0.9, 1.25], gap='large')
    with left:
        st.subheader('01 / Your bill')
        with st.container(border=True):
            uploaded = st.file_uploader('Drop a bill image here', type=['png', 'jpg', 'jpeg'],
                                        help='PNG or JPG, up to 20 MB. Choose a clear, complete bill.')
            data = uploaded.getvalue() if uploaded is not None else None
            upload_id = hashlib.sha256(data).hexdigest() if data is not None else None
            if upload_id != st.session_state.upload_id:
                st.session_state.update(upload_id=upload_id, result=None, messages=[])
            valid = False
            if data is not None:
                if len(data) > 20 * 1024 * 1024:
                    st.error('This image is too large. Please choose a file under 20 MB.')
                else:
                    try:
                        preview = read_upload(data)
                        with st.expander('View uploaded bill', expanded=False):
                            st.image(preview, caption='Your uploaded bill', width='stretch')
                        valid = True
                    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                        st.error('We could not open this image. Choose a valid PNG or JPG.')
            else:
                st.caption('Choose a clear, complete photo of your bill.')
            st.caption('Extraction sends this image to Google Gemini. Your API key stays on this computer.')
            if st.button('Decode my bill ↗', type='primary', disabled=not valid, width='stretch'):
                st.session_state.update(result=None, messages=[])
                try:
                    with st.spinner('Reading the small print. This can take a few minutes…'):
                        st.session_state.client = st.session_state.client or Client()
                        st.session_state.result = extract_upload(data, st.session_state.client)
                    st.success('Bill decoded. Your breakdown is ready.')
                except Exception as error:
                    st.error(decoding_error(error))

    with right:
        st.subheader('02 / The big picture')
        result = st.session_state.result
        if result is None:
            st.markdown('''<div class="empty-results"><span class="eyebrow">CLARITY STARTS HERE</span>
            <h2>Know what you owe.</h2><p>Decode a bill to see payment, usage, and charges.</p>
            <div class="blank-metrics"><span>PAYABLE<br><b>—</b></span><span>UNITS<br><b>—</b></span><span>DUE DATE<br><b>—</b></span></div></div>''', unsafe_allow_html=True)
        else:
            bill = result.bill
            st.caption(f'{bill.provider or "Provider not printed"} / {bill.bill_month or "Month not printed"}')
            metrics = st.columns(3)
            metrics[0].metric('Pay by due date', amount(bill.payable_within_due_date))
            metrics[1].metric('Units consumed', 'Not printed' if bill.units_consumed is None else f'{bill.units_consumed:,.0f}')
            metrics[2].metric('Due date', bill.due_date or 'Not printed')
            if result.evidence.uncertainties:
                st.warning('Some details need a closer look: ' + ' '.join(result.evidence.uncertainties))
            overview, breakdown, history, raw = st.tabs(['OVERVIEW', 'CHARGES & TAXES', 'HISTORY', 'JSON'])
            with overview:
                st.table([{'Detail': label, 'Value': value} for label, value in [
                    ('Current bill', amount(bill.current_bill)), ('Arrears', amount(bill.arrears)),
                    ('Pay after due date (highest printed tier)', amount(bill.payable_after_due_date)),
                    ('Tariff', bill.tariff or 'Not printed'), ('Reading date', bill.reading_date or 'Not printed')]])
                if result.evidence.late_payment_tiers:
                    st.caption('Printed late-payment tiers')
                    st.dataframe([tier.model_dump() for tier in result.evidence.late_payment_tiers], hide_index=True)
            with breakdown:
                rows = [{'Category': 'Charge', 'Type': item.type.replace('_', ' ').title(), 'Amount': amount(item.amount)} for item in bill.charges]
                rows += [{'Category': 'Tax', 'Type': item.type.replace('_', ' ').title(), 'Amount': amount(item.amount)} for item in bill.taxes]
                if rows:
                    st.table(rows)
                else:
                    st.info('No individual charges or taxes were readable on this bill.')
                st.caption(f'Total charges: {amount(bill.total_charges)} · Total taxes: {amount(bill.total_taxes)}')
            with history:
                if result.evidence.history:
                    st.dataframe([row.model_dump() for row in result.evidence.history], hide_index=True)
                else:
                    st.info('No readable usage history was printed on this bill.')
            with raw:
                st.json(bill.model_dump())
            st.download_button('Download bill details ↓', bill.model_dump_json(indent=2),
                               file_name='bill-details.json', mime='application/json')

    st.markdown('<div class="question-banner"><b>03 / ASK THE SMALL PRINT.</b><span>Your bill. Your questions. Clear answers.</span></div>', unsafe_allow_html=True)
    st.caption('Try: “What happens if I pay late?” or “Explain my charges.”')
    conversation = st.container(height=220 if st.session_state.messages else 'content', border=False)
    with conversation:
        for message in st.session_state.messages:
            with st.chat_message(message['role']):
                st.write(message['content'])
    with st.container():
        question = st.chat_input('Ask a question about your bill…', disabled=st.session_state.result is None)
    if question:
        st.session_state.messages.append({'role': 'user', 'content': question})
        with conversation:
            with st.chat_message('user'):
                st.write(question)
        try:
            with st.spinner('Checking the evidence and doing the maths…'):
                answer = answer_questions(st.session_state.client, st.session_state.result,
                                          [{'question_id': 'user', 'question': question}], ROOT / 'cache')['user']
            st.session_state.messages.append({'role': 'assistant', 'content': answer})
            with conversation:
                with st.chat_message('assistant'):
                    st.write(answer)
        except Exception:
            st.error('Could not answer right now. Check your connection and ask again.')
    st.markdown('<div class="footer">BILL DECODER <span>BUILT FOR CLARITY. / WOMEN TECH QUEST 2026</span></div>', unsafe_allow_html=True)
