"""Verify regenerated scientific results against the exact audited run02 snapshot."""
from pathlib import Path
import argparse, csv, hashlib, json

PROJECT_ROOT=Path(__file__).resolve().parents[2]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=PROJECT_ROOT/'data/public_cin')
    args=parser.parse_args();root=args.data_dir.expanduser().resolve()
    expected=json.loads((PROJECT_ROOT/'provenance/public_cin/run02/descriptive-results.json').read_text(encoding='utf-8'))
    actual=json.loads((root/'descriptive-results.json').read_text(encoding='utf-8'))
    if set(expected)!=set(actual):raise AssertionError('Top-level result keys changed')
    scientific_keys=[k for k in expected if k!='provenance']
    for key in scientific_keys:
        if actual[key]!=expected[key]:raise AssertionError('Scientific result differs: '+key)
    for key in ['source_sha256','soft_metadata_sha256','plan_sha256','common_rows','positive_in_all_18_libraries']:
        if actual['provenance'][key]!=expected['provenance'][key]:raise AssertionError('Provenance differs: '+key)
    projection=json.loads((PROJECT_ROOT/'fixtures/public_cin/annotation-projection-provenance.json').read_text())
    if actual['provenance']['annotation_sha256']!=projection['projection_sha256']:raise AssertionError('Fixture hash provenance mismatch')
    if actual['provenance']['annotation_source_gzip_sha256']!=expected['provenance']['annotation_sha256']:raise AssertionError('Source annotation provenance mismatch')
    tsv=root/'all-gene-descriptive-effects.tsv'
    digest=hashlib.sha256(tsv.read_bytes()).hexdigest()
    if digest!='364d2840e4db304d13c5ff0626130dbc556757ad3d26a3e03178a9422bd849ca':raise AssertionError('Effect TSV differs')
    groups={name:set() for name in ['CIN','X','2L']}
    with tsv.open(encoding='utf-8',newline='') as handle:
        for row in csv.DictReader(handle,delimiter='\t'):
            if row['normalization']=='chromosome_common_reference' and row['primary_detection']=='True' and row['chromosome'] in ['2R','3L','3R','4']:
                groups[row['contrast']].add(row['FlyBase_gene'])
    background=sorted(set.intersection(*groups.values()))
    frozen=(PROJECT_ROOT/'fixtures/public_cin/primary_background_gene_ids.txt').read_text(encoding='utf-8').splitlines()
    if background!=frozen or len(background)!=5599:raise AssertionError('Frozen primary gene subset differs')
    print(json.dumps({'scientific_keys_identical':scientific_keys,'panel_mapping_identical':True,'effects_tsv_sha256':digest,
        'common_rows':actual['provenance']['common_rows'],'common_positive_reference':actual['provenance']['positive_in_all_18_libraries'],
        'primary_threeway_detection':actual['shared_detection_counts']['1.0'],'identical_primary_background_genes':len(background),'status':'verified'},indent=2))

if __name__=='__main__':main()
