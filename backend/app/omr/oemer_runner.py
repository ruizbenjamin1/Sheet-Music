"""Corre oemer con nuestras correcciones aplicadas en memoria (sin tocar site-packages).

Uso (lo arma `OemerEngine`): python -m app.omr.oemer_runner <imagen> -o <carpeta>
Acepta las mismas opciones que el comando `oemer`.

Corrección de E1-18 (oemer 0.1.8): `Measure.has_key()` hace `all(...)` sobre una lista
que puede estar vacía (compás con menos símbolos que pentagramas). `all([])` da True,
así que oemer cree que hay armadura y después `get_key()` hace `sfns_cands[0]` con una
lista vacía: IndexError y se cae la lectura entera. La versión corregida exige que haya
tantos símbolos como pentagramas antes de decir que hay armadura.

Si el parche no se puede aplicar (por ejemplo, cambió oemer), se sigue sin él y se deja
una línea con PATCH_FAILED_MARK en stderr, que `OemerEngine` pasa al log.
"""

from __future__ import annotations

import sys
from types import ModuleType

PATCH_FAILED_MARK = "PARCHE_OEMER_NO_APLICADO"


def make_has_key(bs: ModuleType):
    """Devuelve el `has_key` corregido, que usa `get_total_track_nums` y `Sfn` de `bs`."""

    def has_key(self) -> bool:
        n = bs.get_total_track_nums()
        start = n if self.at_beginning else 0
        syms = self.symbols[start:start + n]
        return len(syms) == n and all(isinstance(s, bs.Sfn) for s in syms)

    has_key.__oemer_patch__ = True
    return has_key


def apply_patch(bs: ModuleType) -> None:
    """Reemplaza `bs.Measure.has_key`. Lanza AttributeError si oemer ya no tiene lo esperado."""
    for name in ("Measure", "get_total_track_nums", "Sfn"):
        if not hasattr(bs, name):
            raise AttributeError(f"oemer.build_system ya no tiene {name}")
    if not callable(getattr(bs.Measure, "has_key", None)):
        raise AttributeError("oemer.build_system.Measure ya no tiene has_key")
    bs.Measure.has_key = make_has_key(bs)


def try_apply_patch() -> bool:
    try:
        import oemer.build_system as bs

        apply_patch(bs)
        return True
    except Exception as exc:  # seguir sin el parche antes que no leer nada
        print(f"{PATCH_FAILED_MARK}: {exc!r}", file=sys.stderr, flush=True)
        return False


def main() -> None:
    try_apply_patch()
    from oemer.ete import main as oemer_main

    oemer_main()  # lee sys.argv[1:] igual que el comando `oemer`


if __name__ == "__main__":
    main()
