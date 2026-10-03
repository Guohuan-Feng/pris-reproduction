from pathlib import Path
import hashlib
import json
import random

root = Path(__file__).parent
path = root / 'controls' / 'plan.json'
path.parent.mkdir(exist_ok=True)
if path.exists():
    raise RuntimeError('Precommitted plan exists; do not change its random draw.')
rng = random.Random(20261002)
choices = [{'model': model, 'target': target}
           for model in ['extra_trees', 'hist_gradient_boosting']
           for target in ['raw', 'log1p']]
items = []
for index, routing in enumerate(['chemistry', 'kmeans3', 'chemistry', 'kmeans3', 'chemistry'], 1):
    keys = ['cu_o', 'fe_anion', 'other'] if routing == 'chemistry' else ['cluster0', 'cluster1', 'cluster2']
    spec = {'input': rng.choice(['composition', 'composition_repaired']),
            'routing': routing, 'global': rng.choice(choices).copy(),
            'experts': {key: rng.choice(choices).copy() for key in keys}}
    items.append({'id': f'C{index:02d}', 'specification': spec})
plan = {'seed': 20261002, 'attempts': 5, 'prefix_rule': 'Run first N where N equals total Agent attempted pipelines, including invalid/duplicate attempts.',
        'protocol_sha256': hashlib.sha256((root / 'PROTOCOL.md').read_bytes()).hexdigest(),
        'matched_scope': 'Common menu and attempted-pipeline count. Actual model fits, compute time and search priors differ.',
        'candidates': items}
path.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'saved': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))
