"""POST HOC conditional pool-pair omission diagnostic; not a preregistered analysis.

Reads the exact run02 effect export. Full-data normalization, references, detection,
annotation and the 5599-gene background stay fixed. No factors are re-estimated.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import itertools
import json
import numpy as np

from compare_public_cin_counts import ranks

PROJECT_ROOT=Path(__file__).resolve().parents[2]
INPUT_SHA='364d2840e4db304d13c5ff0626130dbc556757ad3d26a3e03178a9422bd849ca'
ORIGINAL_REVIEWER_SCRIPT_SHA='e556a248d31490fd1b65db7aa771e7c90f44dab5e3ab6e2bef2d1daf3fd26d98'
SCIENTIFIC_KEYS=['genes','within_contrast_pairwise_rank_correlations','leave_one_pool_pair_out_correlations']

def rho(a,b):
    # The primary script's average-tie ranks are zero-based; adding one does not
    # affect their Pearson correlation. This matches the reviewer's rankdata use.
    return float(np.corrcoef(ranks(a),ranks(b))[0,1])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=PROJECT_ROOT/'data/public_cin')
    parser.add_argument('--verify',action='store_true',help='Compare with the shipped post hoc diagnostic result.')
    args=parser.parse_args();data_dir=args.data_dir.expanduser().resolve()
    source=data_dir/'all-gene-descriptive-effects.tsv'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=INPUT_SHA:raise RuntimeError('Expected the exact audited run02 effect export; checksum differs')
    by={name:{} for name in ['CIN','X','2L']}
    with source.open(encoding='utf-8',newline='') as handle:
        for row in csv.DictReader(handle,delimiter='\t'):
            if row['normalization']!='chromosome_common_reference':continue
            records=by[row['contrast']];gene=row['FlyBase_gene']
            if gene in records:raise RuntimeError('Duplicate contrast/gene effect row')
            records[gene]=row
    eligible=[{g for g,r in records.items() if r['primary_detection']=='True' and r['chromosome'] in ['2R','3L','3R','4']} for records in by.values()]
    genes=sorted(set.intersection(*eligible))
    frozen_path=PROJECT_ROOT/'fixtures/public_cin/primary_background_gene_ids.txt'
    frozen=frozen_path.read_text(encoding='utf-8').splitlines()
    if genes!=frozen or len(genes)!=5599:raise RuntimeError('Primary full-data background differs')
    arrays={name:np.array([[float(rows[g]['pool_'+day]) for day in ['4','5','6']] for g in genes]) for name,rows in by.items()}
    if not all(np.isfinite(a).all() for a in arrays.values()):raise RuntimeError('Non-finite pool effects')
    within={name:{f'{a+4}-{b+4}':rho(x[:,a],x[:,b]) for a,b in itertools.combinations(range(3),2)} for name,x in arrays.items()}
    omitted={}
    for name in ['X','2L']:
        values=[]
        for a,b in itertools.product(range(3),repeat=2):
            left=np.median(np.delete(arrays['CIN'],a,axis=1),axis=1)
            right=np.median(np.delete(arrays[name],b,axis=1),axis=1)
            values.append({'drop_CIN_pair':str(a+4),'drop_other_pair':str(b+4),'rho':rho(left,right)})
        omitted[name]={'min':min(v['rho'] for v in values),'max':max(v['rho'] for v in values),'values':values}
    result={
        'utc':datetime.now(timezone.utc).isoformat(),
        'type':'POST HOC conditional reviewer diagnostic; not preregistered',
        'input':'data/public_cin/all-gene-descriptive-effects.tsv',
        'input_path_note':'Logical project-relative input; a supplied --data-dir path is deliberately not serialized.',
        'input_sha256':digest,
        'script':'analysis/public_cin/posthoc_pool_sensitivity.py',
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'original_reviewer_script_sha256':ORIGINAL_REVIEWER_SCRIPT_SHA,
        'frozen_gene_ids_sha256':hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        'genes':len(genes),
        'held_fixed':{
            'normalization':'Run02 chromosome_common_reference factors estimated from all six libraries per contrast, within nuclear arm.',
            'reference':'8916 common genes positive in all 18 full-data libraries; chromosome-specific subsets remain fixed.',
            'detection':'Full-data >=1 CPM in >=3/6 libraries for each of all three contrasts; no re-filtering after omission.',
            'universe':'Same 5599 genes assigned to 2R,3L,3R,4 in every calculation.',
            'other':'Annotation, pseudocount 0.5 and the exported pool_4/pool_5/pool_6 effects are unchanged.',
        },
        'omission':'Independently omit one matched control/case collection-day pair from CIN and from the other contrast; enumerate all 3x3 combinations.',
        'retained_summary':'Median of two remaining paired log2 effects, numerically their arithmetic mean.',
        'within_contrast_pairwise_rank_correlations':within,
        'leave_one_pool_pair_out_correlations':omitted,
        'limitations':'Only three biological pools per condition. Full-data factors and feature selection are held fixed, so this is not a refitted pipeline or independent validation. The overlapping omission summaries are not new experiments, confidence intervals, P values or preregistered results. Sign changes preclude treating computational sign stability as robust biological direction. No drug, functional-rescue or patient-efficacy inference.',
    }
    if args.verify:
        reference=json.loads((PROJECT_ROOT/'results/public_cin/posthoc-pool-sensitivity.json').read_text(encoding='utf-8'))
        for key in SCIENTIFIC_KEYS:
            if result[key]!=reference[key]:raise AssertionError('Post hoc scientific result differs: '+key)
    output=data_dir/'posthoc-pool-sensitivity.json'
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'type':result['type'],'genes':len(genes),'within_CIN':within['CIN'],
        'conditional_omission_ranges':{n:{k:v for k,v in r.items() if k in ['min','max']} for n,r in omitted.items()},
        'verified_against_shipped_result':bool(args.verify)},indent=2))

if __name__=='__main__':main()
