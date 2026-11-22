"""Export reproducible, public-domain factual summaries for the static corporate site.

Run from the repository root: python scripts/build_site_data.py
This derives all numeric values from the same local, cited Table 5 CSV that drives Streamlit.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import condition_means, cross_validate, nested_cross_validate, naive_v0, optimize_recipe, DOI, engineering_casebook

ROOT = Path(__file__).resolve().parents[1]
means = condition_means().sort_values(['temperature_C', 'flow_sccm', 'pulse_ms', 'purge_s']).copy()
metrics, _ = cross_validate()
nested, _ = nested_cross_validate()
v0 = naive_v0(10)
v1 = optimize_recipe(10, objective='time')['best']

rows = []
for _, row in means.iterrows():
    rows.append({
        'temperature_C': int(row.temperature_C),
        'flow_sccm': int(row.flow_sccm),
        'pulse_ms': int(row.pulse_ms),
        'purge_s': int(row.purge_s),
        'gpc_mean_A': round(float(row.gpc_mean_A), 5),
        'gpc_sd_A': round(float(row.gpc_sd_A), 5),
        'replications': int(row.replications),
    })

payload = {
    'title': 'ALD-OPTIX — ALD Process Decision Support',
    'source': 'Pan & Lei, Materials 2025, 18(9), 1918, Tables 4–5',
    'doi': DOI,
    'data_description': '32 measured GPC values; 16 factorial conditions, 2 replicates per condition',
    'scope': 'Al2O3 thermal ALD, TMA/H2O, one published experiment',
    'experiment_count': 32,
    'recipe_count': 16,
    'baseline_MAE_A': round(float(metrics['baseline_MAE_A']), 6),
    'initial_complex_MAE_A': round(float(metrics['initial_complex_MAE_A']), 6),
    'nested_MAE_A': round(float(nested['MAE_A_per_cycle']), 6),
    'nested_selection': nested['model_choices'],
    'comparison_10nm': {
        'baseline_gpc_A': round(float(v0['gpc_mean_A']), 5),
        'baseline_cycles': int(v0['cycles']),
        'baseline_min': round(float(v0['sequence_time_s'])/60, 5),
        'best_gpc_A': round(float(v1['gpc_mean_A']), 5),
        'best_cycles': int(v1['cycles']),
        'best_min': round(float(v1['sequence_time_s'])/60, 5),
        'model_sequence_reduction_pct': round(100*(float(v0['sequence_time_s'])-float(v1['sequence_time_s']))/float(v0['sequence_time_s']), 4),
    },
    'recipes': rows,
    'engineering_cases': engineering_casebook(),
    'warning': 'Educational pre-screening; time excludes tool overhead; not a production claim.',
}
out = ROOT/'site'/'data.json'
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print('Exported', out, 'with', len(rows), 'measured settings')
