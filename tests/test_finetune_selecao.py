"""Quem entra no treino: o marcador NAO_TREINAR e a revisão apagada.

A seleção de dataset é opt-OUT — `finetune_local.main` varre TODAS as pastas de
`datasets/real/` e só pula as que estiverem no `--holdout`. Dado auditado mas
MEDIDO como nocivo (os `-classe` e os `-dificeis2`) entrava por omissão, e o
único aviso era a memória de quem digitava a linha de comando. O marcador põe a
decisão junto do dado; estes testes são o que garante que ele não vire enfeite.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "training"))
import finetune_local as fl  # noqa: E402


def _dataset(tmp_path, nome, frames=("a", "b"), revisados=None):
    """Pasta no formato images/ + labels/ + review/ que o collect() espera."""
    pasta = tmp_path / nome
    revisados = frames if revisados is None else revisados
    for sub in ("images", "labels", "review"):
        (pasta / sub).mkdir(parents=True)
    for f in frames:
        (pasta / "images" / f"{f}.jpg").write_bytes(b"")
        (pasta / "labels" / f"{f}.txt").write_text("0 0.5 0.5 0.1 0.2\n")
        if f in revisados:
            (pasta / "review" / f"{f}.jpg").write_bytes(b"")
    return pasta


def test_pasta_sem_marcador_treina(tmp_path):
    pasta = _dataset(tmp_path, "partida")
    assert fl.motivo_para_nao_treinar(pasta) is None
    assert len(fl.collect(pasta, needs_review=True)) == 2


def test_marcador_tira_a_pasta_e_devolve_o_motivo(tmp_path):
    pasta = _dataset(tmp_path, "partida-classe")
    (pasta / fl.MARCADOR).write_text(
        "REPROVADO em 2026-08-26: custou 0,9 ponto de perda de detecção.\n"
        "Ver CLAUDE.md.\n", encoding="utf-8")
    motivo = fl.motivo_para_nao_treinar(pasta)
    assert motivo is not None
    assert motivo.startswith("REPROVADO em 2026-08-26")
    # o motivo é UMA linha: ele vai para o print da seleção, e um parágrafo
    # inteiro ali esconde as outras pastas
    assert "\n" not in motivo


def test_marcador_VAZIO_ainda_tira_a_pasta_do_treino(tmp_path):
    """O marcador é a decisão; o texto é só para quem for ler depois.

    Guarda contra a implementação ingênua (`return texto.strip() or None`), que
    devolveria None num marcador vazio e treinaria a pasta em silêncio — que é
    exatamente o modo de falha que o marcador existe para eliminar.
    """
    pasta = _dataset(tmp_path, "partida-dificeis2")
    (pasta / fl.MARCADOR).write_text("   \n\n", encoding="utf-8")
    assert fl.motivo_para_nao_treinar(pasta)


def test_o_marcador_nao_mexe_em_quem_o_collect_ja_rejeitava(tmp_path):
    """As duas regras são independentes: review/ rejeita o RÓTULO, o marcador
    rejeita a PASTA."""
    pasta = _dataset(tmp_path, "partida", frames=("a", "b", "c"),
                     revisados=("a", "c"))
    assert fl.motivo_para_nao_treinar(pasta) is None
    nomes = {img.stem for img, _ in fl.collect(pasta, needs_review=True)}
    assert nomes == {"a", "c"}
