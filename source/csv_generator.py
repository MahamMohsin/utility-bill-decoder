import csv
from pathlib import Path

HEADERS = {'level1':['bill_id','json'], 'level2':['bill_id','question_id','question','answer']}

def read_csv(path, level, expected_count=None):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != HEADERS[level]:
            raise ValueError(f'{path}: expected exact columns {HEADERS[level]}')
        rows = list(reader)
    if expected_count is not None and len(rows) != expected_count:
        raise ValueError(f'{path}: expected {expected_count} rows, found {len(rows)}')
    if any(None in row or any(x is None for x in row.values()) for row in rows):
        raise ValueError(f'{path}: malformed CSV row')
    return rows

def write_csv(path, level, rows):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=HEADERS[level])
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
