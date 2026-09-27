#!/usr/bin/env bash
# ============================================================
# بناء الملف التنفيذي المستقل للغة «عربي» — بلا حاجة لبايثون
# عند التشغيل على جهاز المستخدم النهائي.
#
# الاستخدام:
#   scripts/بناء_التنفيذي.sh
#
# المتطلبات: بايثون 3.8+ و PyInstaller
#   python3 -m pip install pyinstaller
# الناتج:    dist/عربي — ملف واحد قابل للتنفيذ يحمل المفسّر كاملًا
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/.."

echo "── التحقق من PyInstaller…"
if ! python3 -m PyInstaller --version 2>/dev/null; then
    echo "   PyInstaller غير مثبت — جارٍ التثبيت…"
    python3 -m pip install pyinstaller
fi

echo "── البناء (قد يستغرق دقيقة)…"
python3 -m PyInstaller عربي.spec --noconfirm --clean

echo "── فحص سريع للناتج…"
./dist/عربي --نسخة
./dist/عربي -c 'اطبع("التنفيذي المستقل يعمل ✓")'

echo ""
echo "✓ تم البناء: dist/عربي"
echo "  جرّبه: ./dist/عربي examples/01_مرحبا.عربي"
echo "  ملاحظة: انسخ الملف إلى أي جهاز بنفس نظام التشغيل — لا يحتاج بايثون"
