"""`python -m simulator` entry point."""
from __future__ import annotations

import sys

from loguru import logger

from simulator.engine import run


def main() -> int:
    """Simulator engine'i başlatır ve exit kodunu döner.

    Engine başarılı ile çalışırsa 0, config hatasında 2 döner.
    Beklenmeyen hatalar loglanır.

    Returns:
        0 başarılı exit, 2 ise config hatası (FileNotFoundError veya ValueError).

    Raises:
        Hiçbir istisna dışarı çıkmaz; tüm hatalar loglanarak exit kodu dönülür.
    """
    try:
        run()
        return 0
    except FileNotFoundError as e:
        logger.error("Config dosyası bulunamadı: {}", e)
        return 2
    except ValueError as e:
        logger.error("Config geçersiz: {}", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
