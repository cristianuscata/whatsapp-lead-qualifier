"""Pruebas reproducibles de las tools MCP — SIN modelo ni red.

Verifican directamente la lógica de datos (caso feliz, caso límite sin
evidencia, y entrada inválida). Se ejecutan offline y de forma determinista:

    python tests/test_tools.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_server import buscar_metas, buscar_recordatorios


def test_caso_feliz_meta_existente():
    r = buscar_metas("PTE")
    assert r["ok"] is True
    assert r["cantidad_registros"] == 1
    assert r["meta"]["clave"] == "PTE"
    assert 0 <= r["meta"]["avance_pct"] <= 100
    print("OK  caso feliz  -> PTE:", r["meta"]["avance_pct"], "% de avance")


def test_caso_limite_meta_inexistente():
    r = buscar_metas("frances")
    assert r["ok"] is True
    assert r["cantidad_registros"] == 0  # no inventa: sin evidencia
    print("OK  caso limite -> meta inexistente devuelve cantidad_registros = 0")


def test_recordatorios_por_estado():
    r = buscar_recordatorios("pendiente")
    assert r["ok"] is True
    assert all(x["estado"] == "pendiente" for x in r["recordatorios"])
    print("OK  recordatorios pendientes:", r["cantidad_registros"])


def test_entrada_invalida():
    r = buscar_recordatorios("xyz")
    assert r["ok"] is False
    assert "invalido" in r["error"].lower() or "inválido" in r["error"].lower()
    print("OK  entrada invalida -> error claro, sin romper la app")


if __name__ == "__main__":
    test_caso_feliz_meta_existente()
    test_caso_limite_meta_inexistente()
    test_recordatorios_por_estado()
    test_entrada_invalida()
    print("\nTODAS LAS PRUEBAS DE TOOLS PASARON")
