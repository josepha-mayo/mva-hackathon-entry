"""Verify the private review bundle without extracting or executing its contents."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def verify(path):
    expected_zip = 'dfe554cabde43b35832ae15a2047f83e6c3a15af34acdf2b3d54209c6a827436'
    expected_candidate = '91eee59817e75b18761436e2f417e647d5a129e1ca82969e4698b4e2c2edaf03'
    expected_source = '66e18c920cf8e8c4c212b5cdb06a4464cb977cee042ae6fe1620b91209b337e5'
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if digest(Path(path).read_bytes()) != expected_zip:
        raise ValueError('Archive identity mismatch; do not use this bundle')
    prefix = 'MVA_age_resolved_turnover_review/'
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive members')
        manifest = json.loads(bundle.read(prefix + 'MANIFEST.json'))
        entries = manifest['files']
        if len(entries) != 9:
            raise ValueError('Unexpected manifest entry count')
        expected_names = {prefix + 'MANIFEST.json'}
        for item in entries:
            rel = PurePosixPath(item['path'])
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Unsafe manifest path')
            name = prefix + item['path']
            expected_names.add(name)
            data = bundle.read(name)
            if len(data) != item['bytes'] or digest(data) != item['sha256']:
                raise ValueError('Manifest mismatch: ' + item['path'])
        if set(names) != expected_names:
            raise ValueError('Unmanifested archive member')
        source = bundle.read(prefix + 'source/report.native-turnover-review.md')
        candidate = bundle.read(prefix + 'report.age-resolved-turnover-candidate.md')
        addition = bundle.read(prefix + 'amendment.txt')
        anchor = b'Match cell-cycle state, and quantify kinetochore-localized '
        if digest(source) != expected_source or digest(candidate) != expected_candidate:
            raise ValueError('Report identity mismatch')
        if source.count(anchor) != 1 or source.replace(anchor, addition + anchor, 1) != candidate:
            raise ValueError('Candidate is not the exact additive amendment')
    return {'manifest_entries_verified': 9, 'exact_additive_reconstruction': True,
            'candidate_sha256': expected_candidate, 'release_authorized': False,
            'clinical_efficacy_established': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.bundle), indent=2))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + '\n')
