"""A exposição que a câmera USOU fica na gravação, não só a que foi pedida.

Faltou em 2026-09-25: a mesma luz deu, na MESMA agitação, nitidez 3.274 numa
gravação e 2.485 na outra, e o `meta.json` só dizia `cam_exposicao = None`
("automática") nas duas. Sondado na MX Brio no mesmo dia: a câmera informa o
valor real (−6 com a mesa iluminada, −4 com a lente coberta).
"""
import json

from app.leitura import exposicoes
from app.recorder import SessionRecorder
from tests.test_fps_e_camera import Cv2Falso, _camera, _espera


def _registros(rec: SessionRecorder):
    rec.close()
    with (rec.dir / "sessao.jsonl").open(encoding="utf-8") as f:
        return [json.loads(ln) for ln in f]


def test_a_camera_informa_a_exposicao_ATUAL_nao_a_pedida(monkeypatch):
    """Guarda contra ler uma vez na abertura: a automática muda com a cena."""
    cv2_falso = Cv2Falso()
    cam = _camera(monkeypatch, cv2_falso, fps=60)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None)
        cap = cv2_falso.abertas[0]
        cap.props["exp"] = -6
        assert _espera(lambda: cam.exposicao_lida == -6)
        cap.props["exp"] = -4          # a lente foi coberta
        assert _espera(lambda: cam.exposicao_lida == -4), \
            "a exposição tem de ser relida enquanto a câmera roda"
    finally:
        cam.stop()


def test_a_gravacao_registra_a_exposicao_so_quando_ela_MUDA(tmp_path):
    rec = SessionRecorder(base_dir=tmp_path, gravar_video=False, nome="s")
    for i, valor in enumerate([None, -6, -6, -6, -4, -4, -6]):
        rec.frame([])
        rec.exposicao(i, valor)
    cam = [r for r in _registros(rec) if r["t"] == "camera"]
    assert [(r["i"], r["exposicao"]) for r in cam] == [(1, -6), (4, -4), (6, -6)]


def test_a_fracao_de_cada_exposicao_sai_dos_registros():
    registros = (
        [{"t": "frame", "i": 0}]                          # antes de saber: fora
        + [{"t": "camera", "i": 1, "exposicao": -6}]
        + [{"t": "frame", "i": i} for i in range(1, 4)]   # 3 frames a -6
        + [{"t": "camera", "i": 4, "exposicao": -5}]
        + [{"t": "frame", "i": 4}]                        # 1 frame a -5
    )
    assert exposicoes(registros) == {-6: 0.75, -5: 0.25}


def test_gravacao_ANTIGA_nao_tem_exposicao_e_isso_nao_vira_zero():
    assert exposicoes([{"t": "frame", "i": 0}, {"t": "mao", "i": 0}]) == {}
