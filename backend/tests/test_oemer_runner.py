"""Pruebas del parche de oemer (E1-18) con un módulo falso: no importan oemer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.omr import oemer_runner


class Sfn:
    pass


class Clef:
    pass


def _fake_bs(tracks: int = 2):
    class Measure:
        def __init__(self, symbols, at_beginning=False):
            self.symbols = symbols
            self.at_beginning = at_beginning

        def has_key(self):  # como el original de oemer 0.1.8
            n = tracks
            start = n if self.at_beginning else 0
            return all(isinstance(s, Sfn) for s in self.symbols[start:start + n])

    return SimpleNamespace(Measure=Measure, Sfn=Sfn, get_total_track_nums=lambda: tracks)


def test_el_original_falla_con_lista_vacia():
    bs = _fake_bs()
    assert bs.Measure([]).has_key() is True  # el bug: all([]) da True


def test_parche_con_lista_vacia_da_false():
    bs = _fake_bs()
    oemer_runner.apply_patch(bs)
    assert getattr(bs.Measure.has_key, "__oemer_patch__", False)
    assert bs.Measure([]).has_key() is False
    # Al principio del sistema los primeros símbolos son claves: solo claves, sin armadura.
    assert bs.Measure([Clef(), Clef()], at_beginning=True).has_key() is False
    # Menos símbolos que pentagramas tampoco es armadura.
    assert bs.Measure([Sfn()]).has_key() is False


def test_parche_sigue_detectando_armaduras():
    bs = _fake_bs()
    oemer_runner.apply_patch(bs)
    assert bs.Measure([Sfn(), Sfn()]).has_key() is True
    assert bs.Measure([Clef(), Clef(), Sfn(), Sfn(), Clef()], at_beginning=True).has_key() is True
    assert bs.Measure([Sfn(), Clef()]).has_key() is False


def test_si_oemer_cambio_no_aplica_el_parche():
    bs = SimpleNamespace(Sfn=Sfn, get_total_track_nums=lambda: 2)  # sin Measure
    with pytest.raises(AttributeError):
        oemer_runner.apply_patch(bs)


def test_try_apply_patch_avisa_y_sigue(monkeypatch, capsys):
    def boom(bs):
        raise AttributeError("cambió oemer")

    monkeypatch.setattr(oemer_runner, "apply_patch", boom)
    import sys

    monkeypatch.setitem(sys.modules, "oemer", SimpleNamespace(__path__=[]))
    monkeypatch.setitem(sys.modules, "oemer.build_system", SimpleNamespace())
    assert oemer_runner.try_apply_patch() is False
    assert oemer_runner.PATCH_FAILED_MARK in capsys.readouterr().err
