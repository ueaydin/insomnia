"""Insomnia.exe üretir.

    python build.py

Sürüm numarası insomnia/__init__.py içindeki __version__ değerinden okunur.
Çıktı: dist\\Insomnia.exe (tek dosya, taşınabilir) ve Inno Setup 6 kuruluysa
dist\\Insomnia-Setup-<sürüm>.exe (kurulum paketi; bkz. kurulum\\insomnia.iss).
Exe adında sürüm yoktur; böylece "Başlangıçta çalıştır" kaydı yeni sürümde de aynı dosyayı gösterir.
Ara dosyalar proje klasörüne değil geçici klasöre yazılır.
"""

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from insomnia import APP_NAME, __version__, icons  # noqa: E402

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable(u'040904B0', [
      StringStruct(u'CompanyName', u'ufukenginaydin'),
      StringStruct(u'FileDescription', u'Insomnia'),
      StringStruct(u'FileVersion', u'{version}'),
      StringStruct(u'InternalName', u'Insomnia'),
      StringStruct(u'LegalCopyright', u'ufukenginaydin'),
      StringStruct(u'OriginalFilename', u'Insomnia.exe'),
      StringStruct(u'ProductName', u'Insomnia'),
      StringStruct(u'ProductVersion', u'{version}')])]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def find_iscc() -> str | None:
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        path = os.path.join(base, "Programs" if base == os.environ.get("LOCALAPPDATA") else "", "Inno Setup 6", "ISCC.exe")
        if base and os.path.exists(path):
            return path
    return shutil.which("ISCC")


def installer() -> int:
    """Kurulum paketini üretir (Inno Setup 6 kuruluysa)."""
    import subprocess

    iscc = find_iscc()
    if not iscc:
        print("Not: Inno Setup 6 bulunamadı; kurulum paketi üretilmedi (yalnız taşınabilir exe var).")
        return 0
    done = subprocess.run([iscc, "/Q", f"/DSurum={__version__}", os.path.join(ROOT, "kurulum", "insomnia.iss")])
    target = os.path.join(ROOT, "dist", f"{APP_NAME}-Setup-{__version__}.exe")
    if done.returncode != 0 or not os.path.exists(target):
        print("HATA: kurulum paketi üretilemedi")
        return 1
    print(f"Tamam: {target} ({os.path.getsize(target) / 1e6:.1f} MB)")
    return 0


def main() -> int:
    import PyInstaller.__main__

    work = tempfile.mkdtemp(prefix="insomnia-build-")
    try:
        icon_path = os.path.join(work, "icon.ico")
        icons.app_icon(256).save(icon_path, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])

        parts = (__version__.split(".") + ["0", "0", "0"])[:4]
        version_path = os.path.join(work, "version_info.txt")
        with open(version_path, "w", encoding="utf-8") as f:
            f.write(VERSION_INFO.format(nums=", ".join(parts), version=__version__))

        local_dist = os.path.join(work, "dist")
        PyInstaller.__main__.run(
            [
                os.path.join(ROOT, "main.py"),
                f"--name={APP_NAME}",
                "--onefile",
                "--noconsole",
                "--clean",
                "--noconfirm",
                f"--icon={icon_path}",
                f"--version-file={version_path}",
                f"--add-data={os.path.join(ROOT, 'insomnia', 'ui')};insomnia/ui",
                "--hidden-import=pystray._win32",
                "--exclude-module=tkinter",
                f"--distpath={local_dist}",
                f"--workpath={os.path.join(work, 'build')}",
                f"--specpath={work}",
            ]
        )
        built = os.path.join(local_dist, f"{APP_NAME}.exe")
        if not os.path.exists(built):
            print("HATA: exe üretilemedi")
            return 1
        os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
        target = os.path.join(ROOT, "dist", f"{APP_NAME}.exe")
        shutil.copy2(built, target)
        shutil.copy2(icon_path, os.path.join(ROOT, "dist", f"{APP_NAME}.ico"))
        print(f"\nTamam: {target} (sürüm {__version__}, {os.path.getsize(target) / 1e6:.1f} MB)")
        return installer()
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
