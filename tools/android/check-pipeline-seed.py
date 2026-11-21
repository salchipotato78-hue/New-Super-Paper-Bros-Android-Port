#!/usr/bin/env python3
"""Checks that runtime/assets/pipeline/initial_pipeline_cache.db matches the current pipeline config.

Rows whose config_version differs from GXPipelineConfigVersion (aurora/lib/gx/pipeline.hpp) are
ignored at boot, so a stale seed silently makes every shader compile on first use.
Exit code 1 when any row is stale, so this can run in CI or before a release build.
"""
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "wiicompiled/aurora-main/lib/gx/pipeline.hpp"
SEED = ROOT / "wiicompiled/runtime/assets/pipeline/initial_pipeline_cache.db"


CLEAR_HEADER = ROOT / "wiicompiled/aurora-main/lib/gfx/clear.hpp"
TYPE_CLEAR = 0
TYPE_GX = 1


def read_version(path, name):
    match = re.search(rf"{name}\s*=\s*(\d+)", path.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"No se encontró {name} en {path}")
    return int(match.group(1))


def current_versions():
    # Each shader type has its own config version; a row is current only against its own type's version.
    return {
        TYPE_GX: read_version(HEADER, "GXPipelineConfigVersion"),
        TYPE_CLEAR: read_version(CLEAR_HEADER, "ClearPipelineConfigVersion"),
    }


def main() -> int:
    versions = current_versions()
    conn = sqlite3.connect(SEED)
    rows = conn.execute(
        "SELECT type, config_version, COUNT(*) FROM pipeline_cache GROUP BY type, config_version ORDER BY type, config_version"
    ).fetchall()
    total = sum(count for _, _, count in rows)
    stale = sum(count for t, v, count in rows if versions.get(t) != v)
    print(f"Versiones actuales: GX {versions[TYPE_GX]}, Clear {versions[TYPE_CLEAR]}. "
          f"Filas en la semilla: {total}. Obsoletas: {stale}.")
    for t, v, count in rows:
        name = {TYPE_GX: "GX", TYPE_CLEAR: "Clear"}.get(t, f"tipo {t}")
        current = versions.get(t) == v
        print(f"  {name} config_version {v}: {count} filas{'' if current else '  <- obsoleta'}")
    if stale:
        print("La semilla está obsoleta: los shaders nuevos se compilarán en el teléfono hasta que se regenere "
              "(ver android/README.md, sección de semilla).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
