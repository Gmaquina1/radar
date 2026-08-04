#!/usr/bin/env python3
"""Corrige texto com acentos corrompidos antes de publicar o Radar.

O Google My Maps atualmente entrega parte do KML com bytes UTF-8 que foram
interpretados como CP932. O resultado inclui textos como ``Mﾃ｡quinas`` e
``LEILﾃグ``. A correção só é aceita quando reduz sinais objetivos de
codificação quebrada, preservando nomes próprios e textos que já estão certos.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


_TOKEN_RE = re.compile(r"\S+")
_HALFWIDTH_RE = re.compile(r"[\uff61-\uff9f]")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")

# Alguns bytes do KML já chegaram substituídos por U+FFFD. Nesses casos a
# conversão original não é reversível, então restauramos apenas expressões de
# português inequívocas observadas nos campos do mapa.
_LOSSY_MAP_REPLACEMENTS = {
    "DESCRIﾃ�ﾃグ": "DESCRIÇÃO",
    "LOCALIZAﾃ�ﾃグ": "LOCALIZAÇÃO",
    "OBSERVAﾃ�ﾃグ": "OBSERVAÇÃO",
    "EMBARCAﾃ�ﾃ髭S": "EMBARCAÇÕES",
    "SOLUﾃ�ﾃ髭S": "SOLUÇÕES",
    "LOCAﾃ�ﾃ髭S": "LOCAÇÕES",
    "SERVIﾃ�OS": "SERVIÇOS",
    "CAﾃ�AMBAS": "CAÇAMBAS",
    "Aﾃ�O": "AÇÃO",
    "ﾂ�": "•",
}


def _mojibake_score(value: str) -> int:
    """Pontua apenas indícios fortes de texto com codificação quebrada."""
    return (
        6 * len(_HALFWIDTH_RE.findall(value))
        + 8 * value.count("�")
        + 2 * value.count("Ã")
        + 2 * value.count("Â")
        + len(_CJK_RE.findall(value))
    )


def _decode_if_better(value: str, encoding: str) -> str:
    try:
        candidate = value.encode(encoding).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return candidate if _mojibake_score(candidate) < _mojibake_score(value) else value


def _repair_token(match: re.Match[str]) -> str:
    token = match.group(0)
    if not (_HALFWIDTH_RE.search(token) or "Ã" in token or "Â" in token):
        return token
    current = token
    for _ in range(2):
        candidates = [
            current,
            _decode_if_better(current, "cp932"),
            _decode_if_better(current, "cp1252"),
            _decode_if_better(current, "latin-1"),
        ]
        best = min(candidates, key=_mojibake_score)
        if best == current:
            break
        current = best
    return current


def corrigir_texto(value: str | None) -> str:
    """Restaura acentos corrompidos sem reescrever o conteúdo capturado."""
    if not value:
        return "" if value is None else value
    corrected = str(value)
    for broken, replacement in _LOSSY_MAP_REPLACEMENTS.items():
        corrected = corrected.replace(broken, replacement)
    corrected = re.sub(r"(?<=\d)m�(?=(?:\W|$))", "m³", corrected)
    corrected = _TOKEN_RE.sub(_repair_token, corrected)
    return unicodedata.normalize("NFC", corrected)


def corrigir_dados(value: Any) -> Any:
    """Aplica a correção recursivamente a estruturas vindas de CSV/JSON."""
    if isinstance(value, str):
        return corrigir_texto(value)
    if isinstance(value, list):
        return [corrigir_dados(item) for item in value]
    if isinstance(value, tuple):
        return tuple(corrigir_dados(item) for item in value)
    if isinstance(value, dict):
        return {
            corrigir_texto(key) if isinstance(key, str) else key: corrigir_dados(item)
            for key, item in value.items()
        }
    return value


def tem_codificacao_corrompida(value: str | None) -> bool:
    """Indica se ainda há marcadores típicos do erro do mapa."""
    if not value:
        return False
    return bool(_HALFWIDTH_RE.search(str(value)) or "�" in str(value))
