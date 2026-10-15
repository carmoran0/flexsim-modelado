#!/usr/bin/env python3
"""Genera flexsim-modelado.skill (zip) para subirlo en claude.ai: Ajustes > Capacidades > Skills.

Uso: python tools/empaquetar.py   ->  dist/flexsim-modelado.skill
Comprueba antes que la description del SKILL.md no pasa de 1024 caracteres.
"""
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / "skills" / "flexsim-modelado"


def main():
    md = SKILL / "SKILL.md"
    if not md.exists():
        sys.exit("falta skills/flexsim-modelado/SKILL.md")
    desc = next((l for l in md.read_text(encoding="utf-8").splitlines() if l.startswith("description:")), "")
    largo = len(desc.split(":", 1)[1].strip().strip('"'))
    if largo > 1024:
        sys.exit(f"description de {largo} caracteres (máximo 1024)")
    destino = RAIZ / "dist" / "flexsim-modelado.skill"
    destino.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                z.write(f, Path("flexsim-modelado", f.relative_to(SKILL)).as_posix())
    print(f"{destino.relative_to(RAIZ)}: {destino.stat().st_size} bytes, description {largo} caracteres")


if __name__ == "__main__":
    main()
