"""Fetch only fixed public GEO processed files; fail closed on checksum drift."""
from pathlib import Path
import argparse, gzip, hashlib, json, urllib.parse, urllib.request

PROJECT_ROOT=Path(__file__).resolve().parents[2]
SOURCES=PROJECT_ROOT/'fixtures/public_cin/sources.json'
sha=lambda data:hashlib.sha256(data).hexdigest()

def check(path,expected):
    if path.exists():
        actual=sha(path.read_bytes())
        if actual!=expected:
            raise RuntimeError(f'Existing file checksum mismatch; left untouched: {path.name} (expected {expected}, found {actual})')
        return True
    return False

def publish(path,data,expected):
    if sha(data)!=expected:raise RuntimeError('Downloaded/decoded checksum mismatch: '+path.name)
    if check(path,expected):return
    try:
        with path.open('xb') as handle:handle.write(data)
    except FileExistsError:
        check(path,expected)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=PROJECT_ROOT/'data/public_cin')
    parser.add_argument('--verify-only',action='store_true',help='Verify existing inputs without network access.')
    args=parser.parse_args();root=args.data_dir.expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    sources=json.loads(SOURCES.read_text(encoding='utf-8'))['public_downloads']
    # Preflight every existing file before downloading or creating any input.
    for item in sources:
        check(root/item['name'],item['sha256'])
        if 'decoded_name' in item:check(root/item['decoded_name'],item['decoded_sha256'])
    receipt=[]
    for item in sources:
        dest=root/item['name'];exists=check(dest,item['sha256'])
        if exists:data=dest.read_bytes()
        else:
            if args.verify_only:raise FileNotFoundError('Missing public input: '+item['name'])
            url=urllib.parse.urlparse(item['url'])
            if url.scheme!='https' or url.hostname!='ftp.ncbi.nlm.nih.gov' or not url.path.startswith('/geo/series/'):
                raise RuntimeError('Only fixed HTTPS public GEO URLs are permitted')
            request=urllib.request.Request(item['url'],headers={'User-Agent':'Public-CIN-reproducibility-capsule/1.0'})
            with urllib.request.urlopen(request,timeout=60) as response:
                data=response.read(item['bytes']+1)
            if len(data)!=item['bytes'] or sha(data)!=item['sha256']:
                raise RuntimeError('Public source changed or download was incomplete; no file replaced: '+item['name'])
        decoded=None
        if 'decoded_name' in item:
            decoded=gzip.decompress(data)
            if len(decoded)!=item['decoded_bytes'] or sha(decoded)!=item['decoded_sha256']:
                raise RuntimeError('Decoded GEO metadata checksum mismatch: '+item['name'])
        publish(dest,data,item['sha256'])
        if decoded is not None:publish(root/item['decoded_name'],decoded,item['decoded_sha256'])
        receipt.append({'file':item['name'],'sha256':item['sha256'],'status':'verified_existing' if exists else 'downloaded_verified'})
    print(json.dumps({'public_inputs':receipt},indent=2))

if __name__=='__main__':main()
