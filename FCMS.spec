# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — FCMS (FC Mining Stats) 단일 exe 빌드.

빌드:
    pyinstaller FCMS.spec

산출물:
    dist/FCMS.exe  (단일 파일, 콘솔 창 없음)

핵심 포함 사항:
    - customtkinter assets/themes (collect_all로 자동 누락 방지)
    - urllib3 (HTTP keep-alive pool)
    - certifi (urllib3 SSL 인증서 번들 — 다른 PC에서 HTTPS 실패 방지)
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(SPEC)))

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []


# ─────────────────────────────────────────────
# customtkinter — assets/themes 디렉터리 통째로 포함
# ─────────────────────────────────────────────
_d, _b, _h = collect_all('customtkinter')
datas += _d
binaries += _b
hiddenimports += _h

# ─────────────────────────────────────────────
# urllib3 — pure python이지만 안전하게 collect_all
# ─────────────────────────────────────────────
_d, _b, _h = collect_all('urllib3')
datas += _d
binaries += _b
hiddenimports += _h

# ─────────────────────────────────────────────
# certifi — SSL 인증서 번들 (HTTPS 실패 방지)
# ─────────────────────────────────────────────
datas += collect_data_files('certifi')
hiddenimports += ['certifi']

# ─────────────────────────────────────────────
# Pretendard 한글 폰트 — process-private 등록 후 CTkFont에서 사용
# icon.ico — 런타임에 iconbitmap()이 디스크에서 읽음 (spec의 icon= 옵션은
#            exe resource에 박는 것일 뿐 디스크 파일과는 별개)
# ─────────────────────────────────────────────
datas += [
    ('assets/Pretendard-Regular.ttf', 'assets'),
    ('assets/Pretendard-Bold.ttf', 'assets'),
    ('assets/icon.ico', 'assets'),
]

# ─────────────────────────────────────────────
# PIL — iconphoto가 ICO 안의 모든 사이즈를 멀티 PhotoImage로 등록할 때 사용
# (customtkinter가 PIL 의존이라 자동 포함되긴 하지만 명시)
# ─────────────────────────────────────────────
hiddenimports += ['PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.IcoImagePlugin']


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FCMS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
