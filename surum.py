"""PyInstaller için Windows sürüm bilgisi dosyası (surum.txt) üretir.

Kullanım: python surum.py v1.0.2
Ürün adı ve sürüm her derlemede aynı biçimde yazılır; imzalama bu alanlara bakar.
"""
import re
import sys

URUN = 'Marlen Gate'
DOSYA = 'Marlengate.exe'

eslesme = re.match(r'v?(\d+)\.(\d+)\.(\d+)', sys.argv[1] if len(sys.argv) > 1 else '')
a, b, c = (int(x) for x in eslesme.groups()) if eslesme else (0, 0, 0)
surum = f'{a}.{b}.{c}'

open('surum.txt', 'w', encoding='utf-8').write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({a}, {b}, {c}, 0), prodvers=({a}, {b}, {c}, 0), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041F04B0', [
      StringStruct('CompanyName', 'Marlen'),
      StringStruct('FileDescription', '{URUN}'),
      StringStruct('FileVersion', '{surum}'),
      StringStruct('InternalName', 'Marlengate'),
      StringStruct('LegalCopyright', 'MIT License, (c) 2026 Marlen'),
      StringStruct('OriginalFilename', '{DOSYA}'),
      StringStruct('ProductName', '{URUN}'),
      StringStruct('ProductVersion', '{surum}')])]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])
  ]
)
""")
