"""
Script: Backfill model metadata con campos faltantes
======================================================
Agrega 'model_type', 'n_features', 'trained_at' (fecha archivo) a los
metadata.json de los 19 modelos existentes que no tienen esos campos.

Ejecutar una vez para que el dashboard pueda mostrar la info correctamente:
    python scripts/backfill_model_metadata.py
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import MODELS_SAVED_DIR

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def backfill_metadata():
    models_dir = Path(MODELS_SAVED_DIR)
    updated = 0
    skipped = 0

    for model_dir in sorted(models_dir.glob('*')):
        if not model_dir.is_dir():
            continue

        meta_path = model_dir / 'metadata.json'
        if not meta_path.exists():
            logger.warning(f"No metadata.json in {model_dir.name}, skipping")
            skipped += 1
            continue

        with open(meta_path) as f:
            meta = json.load(f)

        changed = False

        # Detect model type from files present
        if 'model_type' not in meta:
            if (model_dir / 'model.keras').exists():
                meta['model_type'] = 'lstm_transformer'
            elif (model_dir / 'model.json').exists() or (model_dir / 'model.pkl').exists():
                meta['model_type'] = 'xgboost'
            else:
                meta['model_type'] = 'unknown'
            changed = True

        # n_features from features list
        if 'n_features' not in meta and 'features' in meta:
            meta['n_features'] = len(meta['features'])
            changed = True

        # trained_at from file modification time (best approximation for existing models)
        if 'trained_at' not in meta:
            mtime = model_dir.stat().st_mtime
            meta['trained_at'] = datetime.fromtimestamp(mtime).isoformat()
            changed = True

        # accuracy stays None — can only be added on retrain, not backfilled without re-evaluating
        if 'accuracy' not in meta:
            meta['accuracy'] = None
            changed = True

        if changed:
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            logger.info(f"✅ Updated {model_dir.name} → type={meta['model_type']}, "
                        f"n_features={meta.get('n_features')}, "
                        f"trained_at={meta['trained_at'][:10]}")
            updated += 1
        else:
            skipped += 1

    print(f"\n{'='*50}")
    print(f"Updated: {updated} models")
    print(f"Skipped: {skipped} (already complete or no metadata)")
    print(f"{'='*50}")
    print("\nNota: 'accuracy' solo se puede actualizar reentrenando el modelo.")
    print("Usa: python main.py train --ticker SPY --interval 1d")


if __name__ == '__main__':
    backfill_metadata()
