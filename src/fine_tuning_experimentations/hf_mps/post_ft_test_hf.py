from pathlib import Path
from fine_tuning_experimentations.config.comparator_schema import ComparatorConfig
from fine_tuning_experimentations.hf_mps.comparator import build_predictor, resolve_device
from fine_tuning_experimentations.data_processing.validate_spider import load_canonical_jsonl
from fine_tuning_experimentations.evaluation.comparison import select_examples, build_comparison_table

cfg = ComparatorConfig()
cfg.generation.max_new_tokens = 64
 
device = resolve_device()
print('device:', device)
 
predictor = build_predictor(cfg, device)
records = load_canonical_jsonl(Path(cfg.data.valid_path))
print('total valid records:', len(records))

selected = select_examples(records, 'random', 2, 42)
rows = build_comparison_table(selected, predictor, Path(cfg.data.database_root))
for row in rows:
    print('---')
    for key, value in row.items():
        print(f'{key}: {value}')