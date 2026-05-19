"""pytest conftest: src/ klasörünü sys.path'e ekler ki 'simulator' top-level import edilebilsin.

pip install -e . yapıldığında bu dosya gerekmez; ama lokal pytest çalıştırırken
editable install olmadan da testler geçsin diye burada.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
