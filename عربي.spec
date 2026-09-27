# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# مواصفة بناء الملف التنفيذي المستقل للغة «عربي» — PyInstaller
#
# البناء:  python3 -m PyInstaller عربي.spec --noconfirm --clean
# الناتج:  dist/عربي — ملف واحد قابل للتنفيذ يحمل المفسّر كاملًا
#          (كل وحدات arabi_lang والوحدات القياسية السبعة عشر)
# ولا يحتاج المستخدم إلى بايثون مثبت على جهازه إطلاقًا.
# ============================================================

a = Analysis(
    ['arabi.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # واجهات رسومية ولعب لا تستخدمها اللغة — تقليل الحجم
        'tkinter',
        'turtle',
        'turtledemo',
        'pydoc_data',
        'xmlrpc',
        'test',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# وضع الملف الواحد: كل شيء داخل تنفيذي واحد
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='عربي',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
