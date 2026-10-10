"""Rebuild analysis from bundled raw data; no network download is performed."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic-models',action='store_true',help='Explicitly reproduce models on unverified date intervals; operational use remains prohibited')
    args=parser.parse_args()
    commands=[['analysis/prepare_dataset.py'],['analysis/clean_validate_data.py'],['analysis/explore_performance.py']]
    if args.diagnostic_models:
        commands.append(['analysis/train_compare_models.py','--diagnostic'])
    commands.extend([['analysis/cluster_routes.py'],['analysis/scenario_simulator.py'],
                     ['analysis/rank_recommendations.py'],['deployment/build_companion.py']])
    for command in commands:
        print('Running '+' '.join(command),flush=True)
        subprocess.run([sys.executable,*command],cwd=ROOT,check=True)
    print('Reproduction complete. All operational scenario results remain hypothetical.')


if __name__=='__main__':
    main()
