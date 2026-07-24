"""
Variáveis derivadas: operações básicas entre colunas numéricas do DataFrame.
"""

from __future__ import annotations

import re
import pandas as pd

OPERACOES = {
    "+": "Soma (A + B)",
    "-": "Diferença (A − B)",
    "*": "Produto (A × B)",
    "/": "Razão (A ÷ B)",
}

_NOME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validar_nome(nome: str) -> str | None:
    """Retorna mensagem de erro ou None se o nome for válido."""
    nome = (nome or "").strip()
    if not nome:
        return "Informe um nome para a variável."
    if not _NOME_OK.match(nome):
        return "Use apenas letras, números e _ (não começar com número)."
    return None


def colunas_numericas(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def aplicar_variaveis(df: pd.DataFrame, definicoes: list[dict]) -> pd.DataFrame:
    """
    Aplica definições [{nome, a, op, b}, ...] sobre uma cópia do DataFrame.

    Remove antes colunas cujos nomes estão na lista (reaplica do zero).
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    nomes = [d["nome"] for d in definicoes if d.get("nome")]
    out = out.drop(columns=[n for n in nomes if n in out.columns], errors="ignore")

    for d in definicoes:
        nome = d.get("nome")
        a = d.get("a")
        op = d.get("op")
        b = d.get("b")
        if not nome or a not in out.columns or b not in out.columns:
            continue
        if op == "+":
            out[nome] = out[a] + out[b]
        elif op == "-":
            out[nome] = out[a] - out[b]
        elif op == "*":
            out[nome] = out[a] * out[b]
        elif op == "/":
            out[nome] = out[a] / out[b]
        else:
            continue
    return out


def expressao(a: str, op: str, b: str) -> str:
    return f"{a} {op} {b}"
