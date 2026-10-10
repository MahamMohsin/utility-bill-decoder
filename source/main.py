import argparse
import json
import logging
from pathlib import Path
from csv_generator import read_csv, write_csv
from extractor import extract, atomic_json
from model_client import Client, ROOT
from question_answering import answer_questions

def images(folder):
    result = {}
    for path in Path(folder).rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.png','.jpg','.jpeg'):
            if path.stem in result:
                raise ValueError(f'Duplicate bill image ID: {path.stem}')
            result[path.stem] = path
    if not result:
        raise ValueError(f'No bill images found in {folder}')
    return result

def run(args):
    client = Client()
    if args.command == 'verify-api':
        result = client.generate('Return JSON {"ok":true}.')
        if result.get('ok') is not True:
            raise ValueError('Unexpected API verification response')
        print(f'API verification passed: {client.model}')
        return
    cache = ROOT / 'cache'
    if args.command == 'ask':
        path = Path(args.bill)
        result = extract(client,path,cache,args.refresh)
        answers = answer_questions(client,result,[{'question_id':'user',
                                  'question':args.question}],cache,args.refresh)
        print(answers['user'])
        return
    found = images(args.bills)
    if args.command == 'train':
        failures = []
        for bill_id,path in sorted(found.items()):
            logging.info('Extracting %s',bill_id)
            try:
                result = extract(client,path,cache,args.refresh)
                atomic_json(ROOT/'output'/'training'/f'{bill_id}.json',result.model_dump())
                if bill_id == 'KESC_0008':
                    reference = json.loads((Path(__file__).parent/'reference_kesc_0008.json').read_text())
                    actual = result.bill.model_dump()
                    differences = {key:{'expected':value,'actual':actual[key]}
                                   for key,value in reference.items() if actual[key] != value}
                    atomic_json(ROOT/'output'/'training'/'regression.json',differences)
                    logging.info('KESC_0008 reference mismatches: %s',len(differences))
                    samples = [{'question_id':'sample_tax','question':'How much of my bill is taxes?'},
                               {'question_id':'sample_history','question':'How many months in my history went above 200 units?'}]
                    answers = answer_questions(client,result,samples,cache,args.refresh)
                    atomic_json(ROOT/'output'/'training'/'sample_answers.json',answers)
                logging.info('Completed %s',bill_id)
            except Exception as error:
                logging.error('%s failed: %s',bill_id,type(error).__name__)
                failures.append(bill_id)
        if failures:
            raise RuntimeError('Training failed for: '+', '.join(failures))
        return
    level1 = read_csv(Path(args.templates)/'level1.csv','level1',10)
    level2 = read_csv(Path(args.templates)/'level2.csv','level2',120)
    ids = [r['bill_id'] for r in level1]
    if len(set(ids)) != 10 or set(r['bill_id'] for r in level2) != set(ids):
        raise ValueError('Invalid template bill IDs')
    missing = set(ids)-set(found)
    if missing:
        raise ValueError('Missing bill images: '+', '.join(sorted(missing)))
    for bill_id in ids:
        questions = [r for r in level2 if r['bill_id'] == bill_id]
        if len(questions) != 12 or len({r['question_id'] for r in questions}) != 12:
            raise ValueError(f'{bill_id}: expected 12 unique questions')
    # Cache checkpoints persist; publish official CSVs only after all bills succeed.
    for bill_id in ids:
        logging.info('Processing %s',bill_id)
        result = extract(client,found[bill_id],cache,args.refresh)
        questions = [r for r in level2 if r['bill_id'] == bill_id]
        answers = answer_questions(client,result,questions,cache,args.refresh)
        next(r for r in level1 if r['bill_id']==bill_id)['json'] = result.bill.model_dump_json()
        for row in questions:
            row['answer'] = answers[row['question_id']]
        logging.info('Completed %s',bill_id)
    write_csv(Path(args.output)/'level1.csv','level1',level1)
    write_csv(Path(args.output)/'level2.csv','level2',level2)
    print('Generated both CSV outputs. Run validate_submission.py before packaging.')

def cli():
    parser = argparse.ArgumentParser(description='WTQ Utility Bill Decoder')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('verify-api')
    ask = sub.add_parser('ask')
    ask.add_argument('--bill',type=Path,required=True)
    ask.add_argument('--question',required=True)
    ask.add_argument('--bills',type=Path,default=ROOT/'train'/'bills')
    ask.add_argument('--refresh',action='store_true')
    training = sub.add_parser('train')
    training.add_argument('--bills',type=Path,default=ROOT/'train'/'bills')
    training.add_argument('--refresh',action='store_true')
    batch = sub.add_parser('batch')
    batch.add_argument('--bills',type=Path,default=ROOT/'test'/'bills')
    batch.add_argument('--templates',type=Path,default=ROOT/'test'/'csv')
    batch.add_argument('--output',type=Path,default=ROOT/'output')
    batch.add_argument('--refresh',action='store_true')
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:
        run(parser.parse_args())
    except (ValueError,RuntimeError,FileNotFoundError) as error:
        parser.exit(1,f'ERROR: {error}\n')
    except Exception as error:
        parser.exit(1,f'ERROR: {type(error).__name__}; no submission created\n')

if __name__ == '__main__':
    cli()
