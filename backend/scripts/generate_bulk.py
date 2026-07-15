"""Generate a large synthetic corpus to prove ingestion scales past 500 files.

Writes many JSON files into backend/data/bulk/ (simulating thousands of
extracted CAD/PDF documents), so we can ingest a directory, not one file.

Usage:  python -m scripts.generate_bulk 2500
"""
import json
import random
import sys
from pathlib import Path

from app import config

OUT_DIR = config.BASE_DIR / "data" / "bulk"

MATERIALS = ["GI", "SS304", "MS", "Aluminium"]
PAINTS = ["powder", "liquid", "solvent", "water-based"]
FILTER_TYPES = ["dry", "water-wash", "cartridge"]
TYPES = ["product", "bom", "quotation", "spec"]


def make_record(i: int) -> dict:
    length = random.choice([6, 8, 9, 10, 12, 14])
    width = random.choice([4, 5, 6, 7])
    fans = max(1, round(length * width / 20))
    return {
        "id": f"GEN-{i:05d}",
        "type": random.choice(TYPES),
        "title": f"Paint Booth GEN-{i:05d}",
        "category": "paint_booth",
        "length_m": length,
        "width_m": width,
        "height_m": random.choice([3.5, 4, 4.5]),
        "fans": fans,
        "filters": fans * 12,
        "filter_type": random.choice(FILTER_TYPES),
        "material": random.choice(MATERIALS),
        "paint_type": random.choice(PAINTS),
        "airflow_m3h": fans * 9000,
        "notes": f"Synthetic engineering record {i} for scale testing.",
    }


def main(total: int, per_file: int = 50) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in OUT_DIR.glob("*.json"):
        f.unlink()

    written = 0
    file_idx = 0
    while written < total:
        chunk = [make_record(written + j) for j in range(min(per_file, total - written))]
        (OUT_DIR / f"batch_{file_idx:04d}.json").write_text(
            json.dumps(chunk, ensure_ascii=False), encoding="utf-8"
        )
        written += len(chunk)
        file_idx += 1
    print(f"Wrote {written} records across {file_idx} files into {OUT_DIR}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
    main(n)
