"""Reproduce descriptive moments from the public eLife16620 Figure7 workbook.

This is source-data arithmetic, not a drug-rescue or patient simulation.
Only the Python standard library is required. Download the source at
https://cdn.elifesciences.org/articles/16620/elife-16620-fig7-data1-v1.xlsx
and pass its path with --source. There are no inferential tests or paired
contrasts because raw cell counts and explicit line-pair IDs are absent.
"""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from statistics import mean, stdev
from zipfile import ZipFile
import json
import math
import xml.etree.ElementTree as ET

SOURCE_SHA256='62e710b61a15a697f64f57fece56de4f7ea4698422fc0790ff8ce9b841e4742d'
SOURCE_URL='https://cdn.elifesciences.org/articles/16620/elife-16620-fig7-data1-v1.xlsx'
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
GROUPS=[('C','Wild-type'),('D','FL-Bub1b'),('E','Bub1b\u0394I'),('F','Bub1b\u0394N'),('G','Bub1bN')]

def analyse(source):
    raw=Path(source).read_bytes()
    if sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Source workbook checksum mismatch')
    with ZipFile(source) as archive:
        book=ET.fromstring(archive.read('xl/workbook.xml'))
        sheets=book.findall('m:sheets/m:sheet',NS)
        if len(sheets)!=1 or sheets[0].get('name')!='Figure_7_source_data':
            raise ValueError('Unexpected source worksheet')
        strings=[''.join(s.itertext()) for s in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        root=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        cells={}
        for node in root.findall('m:sheetData/m:row/m:c',NS):
            value=node.find('m:v',NS)
            if value is not None:
                cells[node.get('r')]=strings[int(value.text)] if node.get('t')=='s' else float(value.text)
    for address,label in [('B4','Misalignments (%) \u2013 Vehicle'),('B16','Misalignments (%) \u2013 10 nM AZD')]:
        if cells.get(address)!=label:raise ValueError('Source condition header mismatch')
    groups=[]
    for column,label in GROUPS:
        if cells.get(column+'4')!=label or cells.get(column+'16')!=label:
            raise ValueError('Source genotype header mismatch')
        conditions={}
        for name,first,avg_row,sd_row in [('vehicle',5,11,12),('AZD_10nM',17,23,24)]:
            values=[cells[column+str(i)] for i in range(first,first+6)]
            if any(not isinstance(v,float) or not math.isfinite(v) or not 0<=v<=100 for v in values):
                raise ValueError('Invalid percentage, including valid zero boundary')
            average,sd=mean(values),stdev(values)
            for computed,row in [(average,avg_row),(sd,sd_row)]:
                if not math.isclose(computed,cells[column+str(row)],rel_tol=1e-12,abs_tol=1e-12):
                    raise ValueError('Computed moment differs from source cached summary')
            conditions[name]={'source_cells':[column+str(i) for i in range(first,first+6)],
                'line_record_percentages':values,'n_line_records':6,'mean_percent':average,'sample_SD_percentage_points':sd}
        groups.append({'source_label':label,'conditions':conditions,
            'AZD_minus_vehicle_difference_of_group_means_percentage_points':conditions['AZD_10nM']['mean_percent']-conditions['vehicle']['mean_percent']})
    return {'schema':'mva-public-aurora-descriptive-reanalysis/v1','source_url':SOURCE_URL,'source_sha256':SOURCE_SHA256,
        'primary_article':'https://doi.org/10.7554/eLife.16620','source_figure':'Figure7B, source data1',
        'groups':groups,'all_cached_means_and_sample_SDs_reproduced':True,
        'scope':'Measured public alignment percentages after an imposed challenge; not basal completed divisions, BUB1B-patient rescue, survival or clinical response.',
        'limits':['Caption reports six lines and at least25cells perline; raw cell counts and explicit line-pair IDs are not supplied.',
            'No reconstructed cell denominators, paired contrasts, new P values or confidence intervals.',
            'AZD raises the mean misalignment in every listed expression group. FL/DeltaI protection versus WT under AZD is a different comparison.',
            'These are WT/transgenic-expression MEFs, not the BubR1-hypomorphic mice of the2013 survival abstract.',
            'The cells are observed under an imposed mitotic hold; completed faithful daughter output is unmeasured.'],
        'drug_efficacy_rank_created':False,'child_response_simulated':False}

def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=analyse(args.source)
    encoded=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
    if args.output:args.output.write_text(encoded,encoding='utf-8',newline='\n')
    else:print(encoded,end='')

if __name__=='__main__':main()
