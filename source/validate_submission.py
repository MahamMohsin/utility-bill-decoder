"""Fail-closed preflight and packaging; never uploads or submits."""
import argparse
import ast
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from csv_generator import read_csv, HEADERS
from model_client import configuration, ALLOWED_GOOGLE_MODELS, ROOT
from schemas import Bill

MAX_ZIP_BYTES = 15_000_000  # Conservative decimal MB.
SOURCE_FILES = {
    'main.py','schemas.py','model_client.py','image_utils.py','extractor.py',
    'question_answering.py','csv_generator.py','validate_submission.py',
    'requirements.txt','README.md','.env.example','reference_kesc_0008.json',
    'test_pipeline.py','app.py',
}
REQUIRED_SOURCE = SOURCE_FILES - {'app.py'}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def validate_outputs(root):
    result = {}
    for level,count,keys in [('level1',10,['bill_id']),
                             ('level2',120,['bill_id','question_id','question'])]:
        target = root/'output'/f'{level}.csv'
        require(target.exists(), f'Missing {target}')
        # Output header must have exact raw spelling and no BOM.
        with target.open('r',encoding='utf-8',newline='') as stream:
            require(stream.readline().rstrip('\r\n') == ','.join(HEADERS[level]),
                    f'{level}: header must be exactly '+','.join(HEADERS[level]))
        actual = read_csv(target,level,count)
        template = read_csv(root/'test'/'csv'/f'{level}.csv',level,count)
        require([[r[k] for k in keys] for r in actual] ==
                [[r[k] for k in keys] for r in template],
                f'{level}: identifiers, questions or row order changed')
        for i,row in enumerate(actual,1):
            field = 'json' if level == 'level1' else 'answer'
            require(bool(row[field].strip()),f'{level} row {i}: empty {field}')
            if level == 'level1':
                require('\n' not in row[field] and '\r' not in row[field],
                        f'Level 1 row {i}: JSON must be one line')
                Bill.model_validate_json(row[field])
        result[level] = actual
    bill_ids = [r['bill_id'] for r in result['level1']]
    require(len(set(bill_ids)) == 10 and all(bill_ids),'Level 1 IDs must be unique and nonempty')
    require(set(r['bill_id'] for r in result['level2']) == set(bill_ids),
            'Level 2 must cover the same 10 bills')
    for bill_id in bill_ids:
        questions = [r for r in result['level2'] if r['bill_id'] == bill_id]
        require(len(questions)==12 and len({r['question_id'] for r in questions})==12
                and all(r['question_id'] and r['question'].strip() for r in questions),
                f'{bill_id}: require 12 unique, nonempty questions')

def secret_values(root):
    # Read only for comparison; never report secret contents.
    values = []
    for filename in ('.env','api key.txt'):
        path = root/filename
        if path.is_file():
            for line in path.read_text(encoding='utf-8').splitlines():
                if '=' in line:
                    name,value = line.split('=',1)
                    if not any(word in name.upper() for word in ('KEY','TOKEN','SECRET')):
                        continue
                else:
                    value = line
                value = value.strip().strip('\"\'')
                if len(value) >= 16 and value != 'your-api-key-here':
                    values.append(value.encode())
    return values

def validate_sources(root):
    source = root/'source'
    require(source.is_dir(),'Missing source folder')
    selected = []
    for path in source.rglob('*'):
        if '__pycache__' in path.parts:
            continue  # Runtime bytecode is excluded, never packaged.
        require(not path.is_symlink(),f'Symlinks prohibited in source: {path.name}')
        if path.is_dir():
            require(False,f'Unexpected directory in source: {path.name}')
        relative = path.relative_to(source).as_posix()
        require(relative in SOURCE_FILES,f'Unexpected source file: {relative}')
        selected.append(path)
    require(REQUIRED_SOURCE <= {p.name for p in selected},'Required source files missing')
    readme = (source/'README.md').read_text(encoding='utf-8')
    for phrase in ('Python 3.12','pip install','main.py train','main.py batch',
                   'AI usage','Codex Desktop','Google Gemini API','validate_submission.py'):
        require(phrase in readme,f'README missing required documentation: {phrase}')
    for line in (source/'requirements.txt').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            require(bool(re.fullmatch(r'[\w.-]+==[\w.+-]+',line.strip())),
                    'Dependencies must be exactly pinned')
    model,key = configuration()
    example = (source/'.env.example').read_text()
    require(f'MODEL_NAME={model}' in example,
            '.env.example MODEL_NAME must match the configured inference model')
    require(model in readme,'README must disclose the configured model')
    require('API_KEY=your-api-key-here' in example,'Missing placeholder API_KEY')
    # All inference network calls must remain in the reviewed model gateway.
    for path in selected:
        if path.suffix != '.py':
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'),filename=path.name)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                imports.extend(x.name for x in node.names)
            elif isinstance(node,ast.ImportFrom):
                imports.append(node.module or '')
        forbidden = ('requests','httpx','openai','anthropic','google','urllib','socket')
        if path.name != 'model_client.py':
            require(not any(x.startswith(forbidden) for x in imports),
                    f'{path.name}: network imports must use model_client.py gateway')
    gateway = (source/'model_client.py').read_text()
    require("model not in ALLOWED_GOOGLE_MODELS" in gateway,'Missing runtime model guard')
    require(ALLOWED_GOOGLE_MODELS == ('gemini-3.1-flash-lite','gemini-3.5-flash-lite'),
            'Model allowlist changed')
    return selected

def validate_demo(root, reviewed):
    folder = root/'demo'
    if not folder.exists():
        return []
    files = list(folder.iterdir())
    require(len(files)==1 and files[0].name in ('demo.mp4','demo.mov','demo.webm'),
            'Demo folder must contain one supported demo video')
    video = files[0]
    require(video.is_file() and not video.is_symlink(),'Invalid demo file')
    require(500_000 <= video.stat().st_size <= MAX_ZIP_BYTES,'Demo must be at least 500 KB and fit the ZIP')
    probe = shutil.which('ffprobe')
    require(probe is not None,'ffprobe required to verify demo duration and video stream')
    result = subprocess.run([probe,'-v','error','-show_format','-show_streams',
                             '-of','json',str(video)],capture_output=True,text=True,check=True)
    data = json.loads(result.stdout)
    require(0 < float(data['format']['duration']) <= 180,'Demo must be no longer than 3 minutes')
    require(any(s['codec_type']=='video' for s in data['streams']),'Demo contains no video stream')
    require(reviewed,'Watch the demo, confirm it is a readable real working-app recording, '
                     'then pass --demo-reviewed. This cannot be established from metadata.')
    return files

def prepare(root, demo_reviewed=False):
    validate_outputs(root)
    files = validate_sources(root)
    files += [root/'output'/'level1.csv',root/'output'/'level2.csv']
    files += validate_demo(root,demo_reviewed)
    secrets = secret_values(root)
    contents = {}
    for path in files:
        data = path.read_bytes()
        require(not any(secret in data for secret in secrets),f'Secret detected in {path.name}')
        require(not re.search(rb'AIza[0-9A-Za-z_-]{30,}|sk-[0-9A-Za-z_-]{20,}',data),
                f'API key pattern detected in {path.name}')
        contents[path.relative_to(root).as_posix()] = data
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(contents.items()):
            archive.writestr(name,data)
    payload = buffer.getvalue()
    require(len(payload) <= MAX_ZIP_BYTES,f'ZIP exceeds 15 MB ({len(payload)} bytes)')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        require(archive.testzip() is None,'ZIP integrity check failed')
        require(set(archive.namelist()) == set(contents),'ZIP contents mismatch')
        require(all(archive.read(name)==data for name,data in contents.items()),'ZIP byte verification failed')
    return payload

def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--package',type=Path,help='Write validated ZIP (no upload)')
    parser.add_argument('--replace',action='store_true',help='Replace an existing generated ZIP after validation')
    parser.add_argument('--demo-reviewed',action='store_true')
    args = parser.parse_args()
    try:
        payload = prepare(args.root.resolve(),args.demo_reviewed)
        if args.package:
            destination = args.package.resolve()
            require(destination.suffix.lower()=='.zip','Package destination must be a ZIP file')
            require(not destination.exists() or (args.replace and destination.is_file()),
                    'Package already exists; choose a new filename or pass --replace')
            temporary=destination.with_suffix('.zip.tmp')
            temporary.write_bytes(payload)
            temporary.replace(destination)
        print(f'PASS: outputs, templates, schema, source, secrets, model, documentation, demo, ZIP ({len(payload)} bytes)')
    except Exception as error:
        parser.exit(1,f'FAIL: {error}\nNo ZIP created.\n')

if __name__ == '__main__':
    cli()
