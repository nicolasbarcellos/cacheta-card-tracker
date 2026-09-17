"""A re-detecção tem de obedecer aos `--set`, e a ordem é o que garante isso.

O `--redetectar` existe para comparar MODELO com MODELO no mesmo vídeo. Este
modelo é preso à escala (medido: ampliar o recorte 4× fez ele não detectar
nada em 28 de 31 casos), então comparar um modelo treinado a 1280 com outro
treinado a 1600 só faz sentido rodando cada um na SUA resolução — e quem diz a
resolução é `--set detect_imgsz=...`.

Até 2026-09-17 os overrides eram aplicados DEPOIS da re-detecção: o vídeo
inteiro era lido na resolução antiga e o override só valia para o pipeline. O
sintoma é o pior que um instrumento pode ter — número plausível, medição
errada, sem aviso nenhum. É a mesma família dos defeitos que o CLAUDE.md já
registra em "o atraso máximo era do INSTRUMENTO".
"""

import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carrega_modulo_replay():
    """O `scripts/` não é pacote; o teste carrega o arquivo pelo caminho."""
    spec = importlib.util.spec_from_file_location(
        "replay_cli", RAIZ / "scripts" / "replay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gravacao_minima(tmp_path: Path) -> Path:
    grav = tmp_path / "20260101-000000"
    grav.mkdir()
    linhas = [{"t": "frame", "i": i, "ts": i / 30, "v": i, "dets": []}
              for i in range(3)]
    (grav / "sessao.jsonl").write_text(
        "\n".join(json.dumps(x) for x in linhas), encoding="utf-8")
    (grav / "meta.json").write_text(json.dumps({"config": {}}),
                                    encoding="utf-8")
    return grav


def test_set_detect_imgsz_vale_na_REDETECCAO_nao_so_depois(tmp_path, capsys):
    mod = carrega_modulo_replay()
    from app.config import config

    original = config.detect_imgsz
    visto = {}

    def redetecta_falso(gravacao, registros, modelo, passo):
        # o que a re-detecção enxergaria ao construir o CardDetector
        visto["imgsz"] = config.detect_imgsz
        destino = gravacao / "sessao-falso.jsonl"
        destino.write_text("\n".join(json.dumps(r) for r in registros),
                           encoding="utf-8")
        return destino

    mod.redetecta = redetecta_falso
    grav = gravacao_minima(tmp_path)
    argv = sys.argv
    sys.argv = ["replay.py", str(grav), "--redetectar", "modelo_novo.pt",
                "--set", "detect_imgsz=1600"]
    try:
        mod.main()
    finally:
        sys.argv = argv
        config.detect_imgsz = original

    assert visto["imgsz"] == 1600, (
        "a re-deteccao rodou a "
        f"{visto['imgsz']} px enquanto o --set pedia 1600: o video foi lido na "
        "resolucao errada e a comparacao entre modelos nao vale")
