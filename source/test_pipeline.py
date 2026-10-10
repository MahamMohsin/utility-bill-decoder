import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace
import zipfile
from pydantic import ValidationError
from csv_generator import read_csv,write_csv
from model_client import configuration
from question_answering import calculate,history_count,validate_answer_years,direct_history_answer
from schemas import Bill,Extraction,History
import main
from validate_submission import validate_outputs,prepare,SOURCE_FILES

REFERENCE = json.loads((Path(__file__).parent/'reference_kesc_0008.json').read_text())

class Tests(unittest.TestCase):
    def test_compact_history_year_is_grounded(self):
        history=History.model_validate({'month':'Sep25','units':75,'bill_amount':816,'payment':850})
        self.assertEqual(history.month,'2025-09')
        validate_answer_years('September 2025 had 75 units.',{'history':[history.model_dump()]})

    def test_history_merges_payment_table_and_usage_chart(self):
        extraction=Extraction.model_validate({'bill':REFERENCE,'evidence':{
            'history':[{'month':'Apr25','units':None,'bill_amount':500,'payment':500},
                       {'month':'2025-04','units':141,'bill_amount':None,'payment':None}],
            'details':[],'uncertainties':[]}})
        self.assertEqual(len(extraction.evidence.history),1)
        self.assertEqual(extraction.evidence.history[0].units,141)
        self.assertEqual(extraction.evidence.history[0].bill_amount,500)

    def test_monthly_average_is_computed_from_printed_history(self):
        extraction=Extraction.model_validate({'bill':REFERENCE,'evidence':{
            'history':[{'month':f'2025-{i:02d}','units':i,'bill_amount':None,'payment':None}
                       for i in range(1,13)],'details':[],'uncertainties':[]}})
        answer=direct_history_answer('What are my average monthly units consumed?',extraction)
        self.assertIn('6.50 units per month',answer)
    def test_official_schema_rejects_invalid_values(self):
        Bill.model_validate(REFERENCE)
        for field,value in [('units_consumed','151'),('units_consumed',True),
                            ('current_bill',float('nan')),('due_date','2026-02-30'),
                            ('account_number','secret')]:
            sample = {**REFERENCE,field:value}
            with self.subTest(field=field,value=value),self.assertRaises(ValidationError):
                Bill.model_validate(sample)
        missing = copy.deepcopy(REFERENCE)
        del missing['arrears']
        with self.assertRaises(ValidationError):
            Bill.model_validate(missing)

    def test_arithmetic_is_safe_and_exact(self):
        self.assertEqual(calculate('tax / bill * 100',{'tax':569.62,'bill':3430.24}),'16.61')
        self.assertEqual(calculate('after - before',{'after':3716,'before':3430}),'286.00')
        for expression in ("__import__('os').system('echo fail')",'a.x','a / 0','9999 + a'):
            with self.subTest(expression=expression),self.assertRaises((ValueError,ArithmeticError)):
                calculate(expression,{'a':1})

    def test_history_count_and_unsupported_year(self):
        extraction = Extraction.model_validate({'bill':REFERENCE,'evidence':{'history':[
            {'month':'2025-07','units':239,'bill_amount':None,'payment':None},
            {'month':'2025-08','units':203,'bill_amount':None,'payment':None},
            {'month':'2026-04','units':151,'bill_amount':None,'payment':None}],
            'details':[],'uncertainties':[]}})
        answer = history_count('How many months in my history went above 200 units?',extraction)
        self.assertIn('2 of the 2 printed previous months',answer)
        self.assertIn('2025-07',answer)
        with self.assertRaises(ValueError):
            validate_answer_years('July 2007',extraction.model_dump())
        validate_answer_years('The estimated cost is PKR 2020.',extraction.model_dump())
        for answer in ('Level 1 gives 3716.','See bill_current_bill.','The JSON shows the total.'):
            with self.subTest(answer=answer),self.assertRaises(ValueError):
                validate_answer_years(answer,extraction.model_dump())

    def test_late_payment_tiers_preserve_printed_totals(self):
        extraction=Extraction.model_validate({'bill':REFERENCE,'evidence':{
            'history':[],'details':[],'uncertainties':[], 'late_payment_tiers':[
                {'period':'22-24 April 2026','payable_amount':3574,
                 'surcharge_amount':143.03,'surcharge_percent':5},
                {'period':'After 24 April 2026','payable_amount':3716,
                 'surcharge_amount':286.06,'surcharge_percent':10}]}})
        self.assertEqual(len(extraction.evidence.late_payment_tiers),2)
        self.assertEqual(extraction.evidence.late_payment_tiers[0].payable_amount,3574)
        self.assertEqual(extraction.bill.payable_after_due_date,3716)

    def test_model_guard(self):
        with patch.dict('os.environ',{'MODEL_PROVIDER':'google','MODEL_NAME':'gemini-pro','API_KEY':'test'}):
            with self.assertRaises(ValueError):
                configuration()

    def fixture(self,root):
        source = root/'source'
        source.mkdir()
        for name in SOURCE_FILES:
            origin = Path(__file__).parent/name
            if origin.exists():
                (source/name).write_bytes(origin.read_bytes())
        one = [{'bill_id':f'B{i}','json':json.dumps(REFERENCE)} for i in range(10)]
        two = [{'bill_id':f'B{i}','question_id':f'Q{j}',
                'question':'Question, with "quotes"?','answer':'Printed information is unavailable.'}
               for i in range(10) for j in range(1,13)]
        for folder in ('test/csv','output'):
            write_csv(root/folder/'level1.csv','level1',one)
            write_csv(root/folder/'level2.csv','level2',two)
        return one,two

    def test_valid_package_and_corrupt_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one,two = self.fixture(root)
            with patch('validate_submission.configuration',return_value=('gemini-3.5-flash-lite','test')):
                payload = prepare(root)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertIn('output/level1.csv',archive.namelist())
                self.assertFalse(any('.env' == Path(n).name for n in archive.namelist()))
                self.assertEqual(archive.testzip(),None)
            self.assertEqual(read_csv(root/'output/level2.csv','level2')[0]['question'],two[0]['question'])
            two[0]['question'] = 'changed'
            write_csv(root/'output/level2.csv','level2',two)
            with self.assertRaises(ValueError):
                validate_outputs(root)

    def test_batch_end_to_end_preserves_120_questions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.fixture(root)
            bills=root/'test/bills'
            bills.mkdir()
            for i in range(10):
                (bills/f'B{i}.png').write_bytes(b'image fixture; extraction mocked')
            extraction=Extraction.model_validate({'bill':REFERENCE,'evidence':{
                'history':[],'details':[],'uncertainties':[]}})
            def answers(client,result,questions,cache,refresh):
                return {q['question_id']:'Grounded fixture answer, with punctuation.' for q in questions}
            args=Namespace(command='batch',bills=bills,templates=root/'test/csv',
                           output=root/'output',refresh=False)
            with patch('main.Client'),patch('main.extract',return_value=extraction),\
                 patch('main.answer_questions',side_effect=answers),patch('main.ROOT',root):
                main.run(args)
            validate_outputs(root)
            self.assertEqual(len(read_csv(root/'output/level2.csv','level2')),120)

    def test_secrets_and_wrong_header_block_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.fixture(root)
            (root/'source/.env').write_text('API_KEY=secret')
            with self.assertRaises(ValueError),patch('validate_submission.configuration',return_value=('gemini-3.5-flash-lite','test')):
                prepare(root)
            (root/'source/.env').unlink()
            path=root/'output/level1.csv'
            path.write_text(path.read_text().replace('bill_id,json','bill_id,JSON',1))
            with self.assertRaises(ValueError):
                validate_outputs(root)

if __name__ == '__main__':
    unittest.main()
