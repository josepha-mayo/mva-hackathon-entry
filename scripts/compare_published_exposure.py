"""Run the public aggregate exposure sensitivity without network access."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from mva_hackathon.published_exposure import analyze

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', type=Path, default=ROOT / 'configs/published-exposure-inputs.json')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
raw = args.input.read_bytes()
result = analyze(json.loads(raw))
result['input_sha256'] = sha256(raw).hexdigest()
encoded = json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + '\n'
if args.output:
    args.output.write_text(encoded, encoding='utf-8', newline='\n')
    print(json.dumps({'output': str(args.output), 'input_sha256': result['input_sha256'], 'clinical_advancement_granted': False}))
else:
    print(encoded, end='')
