"""Insomnia başlatıcı.

    python main.py          pencereyle açılır
    python main.py --tray   yalnız tepsi simgesiyle açılır (Windows açılışında böyle başlar)
"""

import sys


def main() -> int:
    from insomnia import single_instance

    if not single_instance.acquire():
        return 0  # çalışan kopyaya penceresini göstermesi söylendi

    from insomnia.app import App

    App(start_hidden="--tray" in sys.argv[1:]).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
