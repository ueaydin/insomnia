"""Insomnia başlatıcı.

    python main.py          pencereyle açılır
    python main.py --tray   yalnız tepsi simgesiyle açılır (Windows açılışında böyle başlar)

Çalışan kopyaya komut (program kapalıysa --baslat onu tepside açıp başlatır):

    python main.py --baslat 60                    60 dakikalık oturum (0 = süresiz)
    python main.py --baslat 60 --islem shutdown   bitince kapat (restart, hibernate)
    python main.py --durdur
    python main.py --ekran-kapat
"""

import sys


def main() -> int:
    from insomnia import remote, single_instance

    args = sys.argv[1:]
    command = remote.parse_args(args)
    if command is not None:
        if command["komut"] == "bad":
            return 2
        result = remote.send(command)
        if result is not None:
            return 0 if result.get("ok") else 1
        if command["komut"] != "start":
            return 1  # program kapalı: durdurulacak ya da ekranı kapatacak kopya yok

    if not single_instance.acquire():
        return 0  # çalışan kopyaya penceresini göstermesi söylendi

    from insomnia.app import App

    App(start_hidden="--tray" in args or command is not None, first_command=command).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
