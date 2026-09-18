"""A thread do vídeo morta NÃO pode travar o app.

Medido em 2026-09-18: a câmera foi aberta por outro processo, a thread de
escrita do vídeo caiu, a fila (30) encheu e o `frame()` ficou preso para
sempre — o laço de visão parou, o `mao.avi` ficou com 0 byte e nem o `Ctrl+C`
encerrava, porque o `close()` espera na MESMA fila.

Bloquear quando o disco não acompanha continua sendo a escolha do projeto (é o
que faz disco lento aparecer no FPS em vez de dessincronizar o vídeo do JSONL
em silêncio). O que não pode é bloquear por thread MORTA.

O trabalho roda numa THREAD com `join(timeout)` de propósito: o defeito que se
guarda aqui é uma TRAVA, e um teste que trava sob mutação não prova nada — ele
tem de FALHAR. É a armadilha que este repositório já registrou ao consertar a
âncora do atraso.
"""
import threading
import time

from app.recorder import SessionRecorder


def _mata_a_thread(rec):
    rec._fila.put(None)                  # o sentinela encerra o laço dela
    for _ in range(300):
        if not rec._thread.is_alive():
            return
        time.sleep(0.01)
    raise AssertionError("a thread do vídeo não encerrou")


def _termina_em(segundos, alvo):
    """True se `alvo` terminou dentro do prazo — sem pendurar a suíte."""
    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    t.join(timeout=segundos)
    return not t.is_alive()


def test_thread_do_video_MORTA_nao_trava_o_laco(tmp_path):
    rec = SessionRecorder(base_dir=str(tmp_path), nome="teste")
    _mata_a_thread(rec)

    def enche():
        for _ in range(60):              # o dobro do tamanho da fila
            rec.frame([], imagem=[[1]])

    assert _termina_em(10.0, enche), "o frame() ficou preso na fila cheia"
    assert rec._gravar_video is False, "devia ter desistido do vídeo"
    assert _termina_em(10.0, rec.close)


def test_close_com_a_thread_morta_nao_fica_preso(tmp_path):
    rec = SessionRecorder(base_dir=str(tmp_path), nome="teste")
    _mata_a_thread(rec)
    while True:                          # enche a fila com a thread morta
        try:
            rec._fila.put_nowait([[1]])
        except Exception:
            break
    assert _termina_em(20.0, rec.close), "o close() ficou preso na fila cheia"
