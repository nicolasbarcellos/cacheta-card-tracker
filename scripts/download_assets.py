"""Baixa os PNGs das 52 cartas do deckofcardsapi.com (imagens estáticas).

Lá o rank 10 usa código "0" (ex.: 0S.png); salvamos com nosso código (10S.png).
"""
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cards import RANKS, SUITS  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "assets" / "cards"
OUT.mkdir(parents=True, exist_ok=True)

opener = urllib.request.build_opener()
opener.addheaders = [("User-Agent", "Mozilla/5.0")]
urllib.request.install_opener(opener)

for rank in RANKS:
    for suit in SUITS:
        remote = ("0" if rank == "10" else rank) + suit
        dest = OUT / f"{rank}{suit}.png"
        if dest.exists():
            continue
        url = f"https://deckofcardsapi.com/static/img/{remote}.png"
        print(f"baixando {url} -> {dest.name}")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                urllib.request.urlretrieve(url, dest)
                break
            except urllib.error.HTTPError as e:
                if attempt < max_retries - 1:
                    print(f"  erro {e.code}, tentando novamente...")
                    time.sleep(2 ** attempt)
                else:
                    raise

count = len(list(OUT.glob("*.png")))
print(f"{count} cartas em {OUT}")
assert count == 52, f"esperava 52 PNGs, tem {count}"
