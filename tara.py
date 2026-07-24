"""
Lógica de tara (baseline) para DataFrames do DataViewer.

Protocolos:
- agua_anterior: última amostra \"Água DI\" anterior no mesmo experimento
- amostra_anterior: amostra_id - 1 (compatível com notebook H2O)
- media_agua: média de todas as Água DI do mesmo experimento
- manual: média das amostras marcadas pelo usuário (por experimento)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


PROTOCOLOS = {
    "agua_anterior": "Última Água DI anterior (recomendado)",
    "amostra_anterior": "Amostra anterior (id − 1)",
    "media_agua": "Média de todas as Água DI do experimento",
    "manual": "Seleção manual de amostras de tara",
}

META_COLS = {
    "data", "identificador", "mensurando", "amostra_id",
    "valor_referencia", "info_amostra", "Timestamps", "Timestamp",
}


def _amostra_sort_key(valor):
    try:
        return (0, int(valor))
    except (TypeError, ValueError):
        return (1, str(valor))


def _eh_agua_di(info, filtro: str = "água di") -> bool:
    if info is None or (isinstance(info, float) and np.isnan(info)):
        return False
    return filtro.casefold() in str(info).casefold()


def colunas_feature(df: pd.DataFrame) -> list[str]:
    """Colunas numéricas de medição (exclui metadados e rel_* existentes)."""
    cols = []
    for c in df.columns:
        if c in META_COLS or str(c).startswith("rel_"):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


def remover_colunas_rel(df: pd.DataFrame) -> pd.DataFrame:
    drop = [c for c in df.columns if str(c).startswith("rel_")]
    return df.drop(columns=drop, errors="ignore")


def listar_amostras_unicas(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (identificador, amostra_id) com info e ref."""
    cols = [c for c in ("identificador", "amostra_id", "info_amostra", "valor_referencia", "data") if c in df.columns]
    if "identificador" not in cols or "amostra_id" not in cols:
        return pd.DataFrame()
    out = (
        df[cols]
        .drop_duplicates(subset=["identificador", "amostra_id"])
        .copy()
    )
    out["_ord"] = out["amostra_id"].map(lambda x: _amostra_sort_key(x))
    out = out.sort_values(["identificador", "_ord"]).drop(columns="_ord")
    return out.reset_index(drop=True)


def _medias_por_amostra(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    group_cols = [c for c in ("identificador", "amostra_id") if c in df.columns]
    if not group_cols:
        return pd.DataFrame()
    return (
        df.groupby(group_cols, dropna=False)[feature_cols]
        .mean(numeric_only=True)
        .reset_index()
    )


def aplicar_tara(
    df: pd.DataFrame,
    protocolo: str,
    filtro_agua: str = "água di",
    amostras_manuais: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """
    Retorna cópia do df sem rel_* antigas + novas colunas rel_<feature>.

    amostras_manuais: lista de (identificador, amostra_id) para protocolo manual.
    """
    if df is None or df.empty:
        return df

    if protocolo not in PROTOCOLOS:
        raise ValueError(f"Protocolo desconhecido: {protocolo}")

    base = remover_colunas_rel(df.copy())
    features = colunas_feature(base)
    if not features:
        raise ValueError("Nenhuma coluna numérica de feature para aplicar tara.")

    if "identificador" not in base.columns or "amostra_id" not in base.columns:
        raise ValueError("DataFrame precisa de colunas identificador e amostra_id.")

    medias = _medias_por_amostra(base, features)
    for col in features:
        base[f"rel_{col}"] = np.nan

    # Índice rápido: (identificador, amostra_id) -> série de médias
    media_map = {
        (str(r["identificador"]), str(r["amostra_id"])): r
        for _, r in medias.iterrows()
    }

    # Metadados únicos por amostra (info, ref)
    meta = listar_amostras_unicas(base)

    for ident, grupo_meta in meta.groupby("identificador", sort=False):
        grupo_meta = grupo_meta.copy()
        grupo_meta["_ord"] = grupo_meta["amostra_id"].map(_amostra_sort_key)
        grupo_meta = grupo_meta.sort_values("_ord")

        ids_ordenados = [str(x) for x in grupo_meta["amostra_id"].tolist()]
        info_por_id = {
            str(r["amostra_id"]): r.get("info_amostra")
            for _, r in grupo_meta.iterrows()
        }

        # Baseline por amostra-alvo: dict amostra_id -> key da tara ou None
        tara_de = {}

        if protocolo == "media_agua":
            aguas = [
                aid for aid in ids_ordenados
                if _eh_agua_di(info_por_id.get(aid), filtro_agua)
            ]
            if not aguas:
                continue
            # média das médias das águas
            stack = [media_map[(str(ident), aid)][features] for aid in aguas if (str(ident), aid) in media_map]
            if not stack:
                continue
            baseline_global = pd.concat(stack, axis=1).mean(axis=1)
            for aid in ids_ordenados:
                mask = (base["identificador"].astype(str) == str(ident)) & (
                    base["amostra_id"].astype(str) == aid
                )
                if _eh_agua_di(info_por_id.get(aid), filtro_agua):
                    for col in features:
                        base.loc[mask, f"rel_{col}"] = 0.0
                else:
                    for col in features:
                        base.loc[mask, f"rel_{col}"] = base.loc[mask, col] - baseline_global[col]
            continue

        if protocolo == "manual":
            manuais = {
                (str(i), str(a))
                for i, a in (amostras_manuais or [])
                if str(i) == str(ident)
            }
            if not manuais:
                continue
            stack = [
                media_map[k][features]
                for k in manuais
                if k in media_map
            ]
            if not stack:
                continue
            baseline_global = pd.concat(stack, axis=1).mean(axis=1)
            manuais_ids = {a for _, a in manuais}
            for aid in ids_ordenados:
                mask = (base["identificador"].astype(str) == str(ident)) & (
                    base["amostra_id"].astype(str) == aid
                )
                if aid in manuais_ids:
                    for col in features:
                        base.loc[mask, f"rel_{col}"] = 0.0
                else:
                    for col in features:
                        base.loc[mask, f"rel_{col}"] = base.loc[mask, col] - baseline_global[col]
            continue

        # agua_anterior ou amostra_anterior — tara por amostra
        for idx, aid in enumerate(ids_ordenados):
            tara_id = None
            if protocolo == "amostra_anterior":
                if idx > 0:
                    tara_id = ids_ordenados[idx - 1]
            else:  # agua_anterior
                for prev in reversed(ids_ordenados[:idx]):
                    if _eh_agua_di(info_por_id.get(prev), filtro_agua):
                        tara_id = prev
                        break

            tara_de[aid] = tara_id

        for aid, tara_id in tara_de.items():
            mask = (base["identificador"].astype(str) == str(ident)) & (
                base["amostra_id"].astype(str) == aid
            )
            if tara_id is None:
                # sem tara: se é água DI, zera; senão deixa NaN
                if _eh_agua_di(info_por_id.get(aid), filtro_agua):
                    for col in features:
                        base.loc[mask, f"rel_{col}"] = 0.0
                continue

            key = (str(ident), str(tara_id))
            if key not in media_map:
                continue
            baseline = media_map[key]
            for col in features:
                base.loc[mask, f"rel_{col}"] = base.loc[mask, col] - baseline[col]

    return base
