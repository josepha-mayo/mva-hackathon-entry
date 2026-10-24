"""Plot frozen descriptive results; no treatment model or inferential fit."""
from pathlib import Path
import argparse, csv, hashlib, json, os, sys
PROJECT_ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir',type=Path,default=PROJECT_ROOT/'data/public_cin',
                    help='Regenerated TSV and SVG directory; defaults to ignored data/public_cin under this project.')
args=parser.parse_args()
DATA_DIR=args.data_dir.expanduser().resolve()
RESULT_PATH=PROJECT_ROOT/'provenance/public_cin/run02/descriptive-results.json'
EFFECTS_PATH=DATA_DIR/'all-gene-descriptive-effects.tsv'
PORTABLE_DIAGNOSTIC_SHA='2f5666273968745d4bc7a0ee610b4d4391a0376ec42ddff1591385bf63c46a8a'
ORIGINAL_DIAGNOSTIC_SHA='9b7863b5649577412061e5d30fab32b4889863a332846c2c5440e151b3574f6a'
ORIGINAL_PLOT_SCRIPT_SHA='94820ffb61ee2953ac86f392bf4b8dd1e8d2c225ab2fbb27e77e99784fb350e3'
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
RESULT_SHA='316a80379df02d227385eeaa5aa8e96ddebf77040e24182196d9d495cc69c263'
TSV_SHA='364d2840e4db304d13c5ff0626130dbc556757ad3d26a3e03178a9422bd849ca'
METHOD='chromosome_common_reference'
SUBSET='identical_threeway_detected_off_X_and_2L'
ARMS={'2R','3L','3R','4'}
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(RESULT_PATH)==RESULT_SHA
assert sha(EFFECTS_PATH)==TSV_SHA
result=json.loads((RESULT_PATH).read_text(encoding='utf-8'))
diagnostic_path=PROJECT_ROOT/'results/public_cin/posthoc-pool-sensitivity.json'
assert sha(diagnostic_path)==PORTABLE_DIAGNOSTIC_SHA
diagnostic=json.loads(diagnostic_path.read_text(encoding='utf-8'))
assert diagnostic['genes']==5599 and diagnostic['input_sha256']==TSV_SHA
records={k:{} for k in ['CIN','X','2L']}
with (EFFECTS_PATH).open(encoding='utf-8',newline='') as handle:
    for row in csv.DictReader(handle,delimiter='\t'):
        if row['normalization']==METHOD: records[row['contrast']][row['FlyBase_gene']]=row
genes=sorted(set.intersection(*(set(x) for x in records.values())))
genes=[g for g in genes if all(records[c][g]['primary_detection']=='True' and records[c][g]['chromosome'] in ARMS for c in records)]
assert len(genes)==5599
assert genes==(PROJECT_ROOT/'fixtures/public_cin/primary_background_gene_ids.txt').read_text(encoding='utf-8').splitlines()
x=np.array([float(records['CIN'][g]['median_log2_difference']) for g in genes])
ys={name:np.array([float(records[name][g]['median_log2_difference']) for g in genes]) for name in ['X','2L']}
stats={name:next(r for r in result['comparisons'] if r['comparison']=='CIN_vs_'+name and r['method']==METHOD and r['subset']==SUBSET and r['cpm_threshold']==1.) for name in ['X','2L']}
assert all(v['genes']==len(genes) for v in stats.values())
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none'})
fig,axes=plt.subplots(1,2,figsize=(10,6.8),sharex=True,sharey=True)
all_values=np.concatenate([x,*ys.values()])
limit=float(np.ceil(np.max(np.abs(all_values))*2)/2+.1)
for ax,name,title in zip(axes,['X','2L'],['X trisomy\nversus matched control','2L-arm trisomy\nversus matched control']):
    density=ax.hexbin(x,ys[name],gridsize=55,extent=(-limit,limit,-limit,limit),mincnt=1,bins='log',cmap='viridis',linewidths=0)
    ax.axhline(0,color='#999999',linewidth=.6,linestyle='--',zorder=0)
    ax.axvline(0,color='#999999',linewidth=.6,linestyle='--',zorder=0)
    ax.set(xlim=(-limit,limit),ylim=(-limit,limit),title=title,xlabel='Complex CIN: median log₂ difference\nin normalized counts')
    ax.text(.04,.97,'Descriptive Spearman ρ = '+format(stats[name]['spearman_descriptive_rho'],'.3f')+'\nSame 5,599 genes',transform=ax.transAxes,va='top',ha='left',bbox={'facecolor':'white','alpha':.9,'edgecolor':'none'})
    fig.colorbar(density,ax=ax,fraction=.046,pad=.04,label='Genes per hexagon (log scale)')
axes[0].set_ylabel('Trisomy: median log₂ difference\nin normalized counts')
fig.suptitle('Public fly-brain expression: full-cohort descriptive comparison',fontsize=14.5,fontweight='bold',y=.98)
fig.text(.065,.215,'Three matched collection-day pools per condition, each containing three larval fly brains.\nEach arm normalized separately; common-positive reference. Same detected genes outside X and 2L.',fontsize=10.3,va='top')
fig.text(.065,.125,'A separate post hoc check omitting collection-day pairs can reverse either correlation sign.\nCohort, age/temperature, cell composition and deposited-row selection limit transfer.\nThese are relative-expression summaries, not DESeq2 reproduction, drug response or patient benefit.',fontsize=10.3,va='top',color='#444444')
fig.subplots_adjust(left=.13,right=.88,top=.84,bottom=.34,wspace=.35)
out=DATA_DIR/'figures';out.mkdir(exist_ok=True)
paths=[]
for ext in ['svg']:
    path=out/('cin-trisomy-relative-expression.'+ext)
    fig.savefig(path,dpi=180,facecolor='white')
    with path.open('r+b') as handle: handle.flush();os.fsync(handle.fileno())
    paths.append({'path':path.relative_to(DATA_DIR).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size})
plt.close(fig)
manifest={'script_sha256':sha(Path(__file__)),'source_results_sha256':RESULT_SHA,'source_effects_sha256':TSV_SHA,'posthoc_diagnostic_sha256':sha(diagnostic_path),'original_posthoc_diagnostic_sha256':ORIGINAL_DIAGNOSTIC_SHA,'original_plot_script_sha256':ORIGINAL_PLOT_SCRIPT_SHA,'logical_data_directory':'data/public_cin','path_note':'Only project-relative logical paths are serialized; --data-dir is not embedded.','matplotlib':matplotlib.__version__,'numpy':np.__version__,'same_gene_universe':len(genes),'comparison_statistics':stats,'files':paths}
with (out/'figure-manifest.json').open('w',encoding='utf-8',newline='\n') as handle:
    json.dump(manifest,handle,indent=2,allow_nan=False);handle.write('\n');handle.flush();os.fsync(handle.fileno())
print(json.dumps(manifest,indent=2))
