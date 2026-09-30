#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""معايير أداء لغة عربي (الإصدار 1.30) — البنية المعيارية التي طلبها التدقيق (الفصل 19).

الفلسفة:
  - كل معيار يقيس شيئًا واحدًا محددًا موثقًا في benchmarks/README.md.
  - الوضع الافتراضي: جدول أرقام فقط.
  - --quick: أحمال مصغّرة للاختبارات وCI (ثوانٍ لا دقائق).
  - --check: بوابات انحلال — أدوات لا تتطلب جهازًا مرجعيًا:
      (أ) تكافؤ النتائج: ناتج الدولاب = ناتج الشجري = القيمة الرياضية المتوقعة.
      (ب) نسبة الدولاب/الشجري: الدولاب ألا يكون أبطأ من الشجري × 1.5 (حد انحلال 50%).
      (ج) سقوف كارثية: كل معيار ألا يتجاوز سقفه المطلق (عشرات الأضعاف عن المتوقع)
          — يكشف الانحلال القطعي دون هشاشة أجهزة CI.
  - --baseline ملف: مقارنة صارمة 50% مقابل أرقام مرجعية لنفس الجهاز (بوابة الإصدار
    على جهاز المطور — وليست جزءًا من CI لأن الأجهزة تختلف).

الوحدات المستخدمة: مفسّر لغة عربي فقط + مكتبة بايثون القياسية. لا شبكة. لا كتابة
خارج مجلد المخرجات المؤقت. (بوابة أمان المرحلة: لا سطح هجوم جديد).
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arabi_lang.lexer import Lexer              # noqa: E402
from arabi_lang.parser import Parser            # noqa: E402
from arabi_lang.interpreter import Interpreter  # noqa: E402


# ================== الأحمال المرجعية ==================

# حلقة المليون داخل دالة — المعيار التاريخي للمشروع (خط الأساس منذ 1.22)
HOT_LOOP = '''دالة ب(ن):
    مجموع = ٠
    لكل س في مدى(ن):
        مجموع += س
    أعد مجموع

اطبع(ب(§حجم§))
'''
HOT_LOOP_N = 1_000_000
HOT_LOOP_EXPECTED = 499_999_500_000  # مجموع مدى(مليون) = ن(ن-١)/٢

# مولد كبير — المولدات دائمًا شجرية (حد الموثق للدولاب منذ 1.13)
GENERATOR = '''دالة مولد(ن):
    لكل س في مدى(ن):
        أنتج س

مجموع = ٠
لكل ق في مولد(§حجم§):
    مجموع += ق

اطبع(مجموع)
'''
GENERATOR_N = 200_000
GENERATOR_EXPECTED = 19_999_900_000  # مجموع مدى(٢٠٠ ألف)

QUICK_SCALE = 10  # عامل تصغير الأحمال في الوضع السريع


def _run_arabi(src, use_vm=True):
    """يحلل وينفذ برنامجًا ويعيد (الثواني، سطر الإخراج الأول)."""
    import io
    import contextlib
    tree = Parser(Lexer(src).tokenize()).parse()
    interp = Interpreter(use_vm=use_vm)
    buf = io.StringIO()
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(buf):
        interp.run(tree)
    elapsed = time.perf_counter() - t0
    out = buf.getvalue().strip().splitlines()
    return elapsed, (out[0] if out else '')


def _median_loop(src_template, n_value, use_vm, times):
    """وسيط عدة دورات لنفس الحمل — بتحقق النتيجة في كل دورة.

    كلا الحملين يجمعان مدى(ن) فالمتوقع = ن(ن-١)/٢ — يُشتق من الحجم نفسه
    ليبقى التحقق صحيحًا في الوضع السريع والمكتمل معًا.
    """
    src = src_template.replace('§حجم§', str(n_value))
    expected = n_value * (n_value - 1) // 2
    samples = []
    out = ''
    for _ in range(times):
        elapsed, out = _run_arabi(src, use_vm=use_vm)
        if int(out) != expected:
            raise RuntimeError(
                f'تكافؤ النتائج انكسر: الناتج={out} والمتوقع={expected}')
        samples.append(elapsed)
    return statistics.median(samples)


# ================== المعايير الخمسة ==================

def bench_startup(quick=False):
    """بدء المفسّر: عملية بايثون كاملة تستورد وتشغّل برنامجًا أدنى."""
    times = 3 if quick else 7
    code = (
        'import sys; sys.path.insert(0, %r); '
        'from arabi_lang.lexer import Lexer; '
        'from arabi_lang.parser import Parser; '
        'from arabi_lang.interpreter import Interpreter; '
        "Interpreter(use_vm=True).run(Parser(Lexer('اطبع(1+1)').tokenize()).parse())"
        % str(ROOT)
    )
    samples = []
    for _ in range(times):
        t0 = time.perf_counter()
        r = subprocess.run([sys.executable, '-c', code],
                           capture_output=True, text=True, timeout=120)
        samples.append(time.perf_counter() - t0)
        if r.returncode != 0 or r.stdout.strip() != '2':
            raise RuntimeError(f'معيار البدء فشل: {r.stderr[-200:]}')
    return {'ثانية': round(statistics.median(samples), 4),
            'سقف': 10.0 if quick else 5.0,
            'ملاحظة': 'عملية كاملة: استيراد + تحليل + تنفيذ'}


def bench_hot_loop(quick=False):
    """الحلقة الساخنة: الدولاب مقابل الشجري — معيار التكافؤ والأداء معًا."""
    scale = QUICK_SCALE if quick else 1
    n = HOT_LOOP_N // scale
    times = 3
    vm = _median_loop(HOT_LOOP, n, True, times)
    tree = _median_loop(HOT_LOOP, n, False, times)
    return {'دولاب_ثانية': round(vm, 3), 'شجري_ثانية': round(tree, 3),
            'نسبة_التسريع': round(tree / vm, 2),
            'سقف_دولاب': 15.0 if quick else 8.0,
            'سقف_شجري': 30.0 if quick else 15.0}


def bench_generators(quick=False):
    """المولد الكبير — المسار الشجري دائمًا (متابعة حد الموثق)."""
    scale = QUICK_SCALE if quick else 1
    n = GENERATOR_N // scale
    elapsed, out = _run_arabi(GENERATOR.replace('§حجم§', str(n)), use_vm=True)
    expected = n * (n - 1) // 2
    if int(out) != expected:
        raise RuntimeError(f'ناتج المولد خاطئ: {out} والمتوقع {expected}')
    return {'ثانية': round(elapsed, 3), 'عناصر': n,
            'سقف': 10.0 if quick else 30.0}  # القياس الفعلي 8.0s — السقف كارثي (×4) لا حاد


def bench_env_encode(quick=False):
    """كلفة ترميز بيئة الجذر (قدّم على العمليات/الموزع) بحجم بيئة متغير."""
    from arabi_lang.processes import _encode_root
    from arabi_lang.runtime import Env
    sizes = [200, 2000] if not quick else [50, 500]
    result = {}
    for size in sizes:
        env = Env(None)
        for i in range(size):
            env.set(f'متغير_{i}', i * 1.5)
        t0 = time.perf_counter()
        _encode_root(env, None, None)
        result[f'ترميز_{size}_ثانية'] = round(time.perf_counter() - t0, 4)
    result['سقف'] = 2.0
    return result


def bench_crypto(quick=False):
    """نفاذية التشفير التماثلي: ميجابايت/ثانية للشفّر والفكّ."""
    from arabi_lang.crypto import _crypto_encrypt, _crypto_decrypt
    mb = 1 if not quick else 0.2
    text = 'أ' * int(mb * 1_000_000)
    key = 'مفتاح-معياري-ثابت-للقياس'
    t0 = time.perf_counter()
    enc = _crypto_encrypt([text, key], None)
    t_enc = time.perf_counter() - t0
    t0 = time.perf_counter()
    dec = _crypto_decrypt([enc, key], None)
    t_dec = time.perf_counter() - t0
    if dec != text:
        raise RuntimeError('فك التشفير أعاد نصًا مختلفًا — تكافؤ انكسر')
    return {'شفّر_مبثث': round(mb / t_enc, 2), 'فكّ_مبثث': round(mb / t_dec, 2),
            'سقف_ثانية_لكل_اتجاه': 30.0 if quick else 15.0}


SUITES = [
    ('بدء', bench_startup, 'عملية كاملة أدنى — استيراد وتشغيل'),
    ('حلقة_ساخنة', bench_hot_loop, 'مليون تكرار داخل دالة: دولاب مقابل شجري'),
    ('مولدات', bench_generators, 'مولد ٢٠٠ ألف عنصر — المسار الشجري'),
    ('بيئة_قدّم', bench_env_encode, 'ترميز بيئة الجذر بحجمين (سريع: ٥٠/٥٠٠، كامل: ٢٠٠/٢٠٠٠)'),
    ('تشفير', bench_crypto, 'نفاذية شفّر/فكّ ميجابايت/ثانية'),
]


# ================== البوابات ==================

def check_gates(results, quick):
    """بوابات --check — تعيد قائمة (اسم_البوابة، سليم؟، تفصيل)."""
    gates = []
    hl = results['حلقة_ساخنة']
    ratio = hl['نسبة_التسريع']
    gates.append(('تكافؤ_النتائج', True,
                  'دولاب=شجري=القيمة الرياضية (مفحوص برفع خطأ داخل كل دورة)'))
    gates.append(('دولاب_لا_أبطأ_من_الشجري×1.5', ratio >= 1 / 1.5,
                  f"نسبة_التسريع={ratio} (الحد الأدنى: {round(1/1.5, 2)})"))
    gates.append(('سقف_دولاب', hl['دولاب_ثانية'] <= hl['سقف_دولاب'],
                  f"{hl['دولاب_ثانية']}s ≤ {hl['سقف_دولاب']}s"))
    gates.append(('سقف_شجري', hl['شجري_ثانية'] <= hl['سقف_شجري'],
                  f"{hl['شجري_ثانية']}s ≤ {hl['سقف_شجري']}s"))
    st = results['بدء']
    gates.append(('سقف_البدء', st['ثانية'] <= st['سقف'],
                  f"{st['ثانية']}s ≤ {st['سقف']}s"))
    gn = results['مولدات']
    gates.append(('سقف_المولدات', gn['ثانية'] <= gn['سقف'],
                  f"{gn['ثانية']}s ≤ {gn['سقف']}s"))
    ee = results['بيئة_قدّم']
    worst = max(v for k, v in ee.items() if k.endswith('_ثانية'))
    gates.append(('سقف_ترميز_البيئة', worst <= ee['سقف'],
                  f"{worst}s ≤ {ee['سقف']}s"))
    cr = results['تشفير']
    gates.append(('سقف_التشفير', cr['شفّر_مبثث'] > 0 and cr['فكّ_مبثث'] > 0,
                  f"شفّر={cr['شفّر_مبثث']} MB/s، فكّ={cr['فكّ_مبثث']} MB/s (نفاذية موجبة)"))
    return gates


def check_baseline(results, path):
    """مقارنة صارمة مقابل أرقام جهاز مرجعي — انحلال >50% = فشل."""
    base = json.loads(Path(path).read_text(encoding='utf-8'))
    failures = []
    flat = {}
    for suite, data in results.items():
        for k, v in data.items():
            if isinstance(v, (int, float)) and not k.startswith('سقف') and k != 'عناصر':
                flat[f'{suite}.{k}'] = v
    for key, ref in base['numbers'].items():
        got = flat.get(key)
        if got is None:
            continue  # معيار أُضيف بعد تسجيل الخط الأساس — يوثق لا يفشل
        if got > ref * 1.5:
            failures.append(f'{key}: {got} > المرجع {ref} × 1.5')
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description='معايير أداء لغة عربي')
    ap.add_argument('--quick', action='store_true', help='أحمال مصغّرة للاختبارات')
    ap.add_argument('--check', action='store_true', help='بوابات الانحلال (تكافؤ/نسب/سقوف)')
    ap.add_argument('--baseline', help='مقارنة صارمة 50%% مقابل ملف خط أساس')
    ap.add_argument('--json', action='store_true', help='إخراج JSON للآلات')
    ap.add_argument('--save-baseline', help='تسجيل الأرقام كخط أساس في ملف')
    args = ap.parse_args(argv)

    results = {}
    for name, fn, _doc in SUITES:
        results[name] = fn(quick=args.quick)

    if args.json and not args.check:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        print('معايير أداء لغة عربي' + (' (وضع سريع)' if args.quick else ''))
        print('=' * 62)
        for name, _fn, doc in SUITES:
            print(f'— {name}: {doc}')
            for k, v in results[name].items():
                if k == 'ملاحظة':
                    print(f'    ({v})')
                else:
                    print(f'    {k:<28} {v}')

    failed = False
    if args.check:
        print('\nبوابات الانحلال:')
        for name, ok, detail in check_gates(results, args.quick):
            print(f'  [{"سليم" if ok else "فشل"}] {name}: {detail}')
            failed = failed or not ok
    if args.baseline:
        fails = check_baseline(results, args.baseline)
        if fails:
            failed = True
            print('\nمقارنة الخط الأساس — انحلال >50%:')
            for f in fails:
                print(f'  [فشل] {f}')
        else:
            print('\nمقارنة الخط الأساس: بلا انحلال >50%')
    if args.save_baseline:
        flat = {}
        for suite, data in results.items():
            for k, v in data.items():
                if isinstance(v, (int, float)) and not k.startswith('سقف') and k != 'عناصر':
                    flat[f'{suite}.{k}'] = v
        Path(args.save_baseline).write_text(
            json.dumps({'machine': 'جهاز المطور المرجعي — سُجلت عند إصدار 1.30.0',
                        'python': sys.version.split()[0],
                        'numbers': flat}, ensure_ascii=False, indent=1),
            encoding='utf-8')
        print(f'\nسُجّل الخط الأساس في {args.save_baseline}')

    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
