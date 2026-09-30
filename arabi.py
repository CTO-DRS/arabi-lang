#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""عربي — لغة برمجة عربية بالكامل.

الاستخدام:
    python arabi.py ملف.عربي        تشغيل ملف برمجي
    python arabi.py                 فتح المفسر التفاعلي (REPL)
    python arabi.py -c "كود"        تنفيذ كود مباشر
    python arabi.py --تحقق ملف      فحص الصياغة دون تنفيذ
    python arabi.py --نسق ملفات     تنسيق الملفات وإصلاح الإزاحة
    python arabi.py --افحص ملفات    فحص الملفات بحثًا عن المشكلات
    python arabi.py --وثق ملف [ناتج] توليد توثيق Markdown
    python arabi.py --ثبت مسار|رابط  تثبيت مكتبة في مجلد مكتبات/
    python arabi.py --حزم           عرض المكتبات المثبتة
    python arabi.py حزمة تثبيت ...   مدير الحزم: تثبيت/إزالة/قائمة/بحث/تحديث
    python arabi.py --لغة           تشغيل خادم اللغة (LSP) للمحررات
    python arabi.py --عامل م:منفذ --مفتاح سر   عامل موزع مصادق بالمفتاح
    python arabi.py --نسخة          عرض الإصدار

    أو بعد التثبيت عبر pip (الإصدار 1.16+):
    arabi ملف.عربي                  الأمر المثبت مع الحزمة
    python -m arabi ...             الوحدة نفسها بلا أمر
"""

import io
import json
import multiprocessing
import sys
import os
import contextlib


def is_frozen():
    """هل يعمل المفسّر كملف تنفيذي مستقل (مبني بـ PyInstaller)؟

    PyInstaller يضبط الخاصية sys.frozen عند تشغيل النسخة المجمّعة —
    عندها لا نحتاج لإضافة مجلد المصدر إلى مسار البحث لأن كل الوحدات
    مضمّنة داخل الملف التنفيذي نفسه.
    """
    return getattr(sys, 'frozen', False)


if not is_frozen():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabi_lang import __version__
from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser
from arabi_lang.interpreter import Interpreter
from arabi_lang.errors import ArabiError
from arabi_lang import tools
from arabi_lang import bytecode
from arabi_lang import lsp as lsp_module


def version_text():
    """سطر الإصدار — يصف النسخة التنفيذية المستقلة عند تجمّدها."""
    base = f'عربي — الإصدار {__version__}'
    return base + (' — تنفيذي مستقل' if is_frozen() else '')


def prog_name():
    """اسم البرنامج في رسائل الاستخدام — يتكيف مع النسخة التنفيذية."""
    return './عربي' if is_frozen() else 'python arabi.py'


BANNER = rf"""
  ____              _____
 / __ \            |_   _|                _
| |  | | __ _ _ __   | |  _ __  ___  __ _| | _____
| |  | |/ _` | '__|  | | | '_ \/ __|/ _` | |/ / _ \
| |__| | (_| | |    _| |_| | | \__ \ (_| |   <  __/
 \____/ \__,_|_|   |_____|_| |_|___/\__,_|_|\_\___|

  لغة عربي — لغة برمجة عربية بالكامل (الإصدار {__version__})
  اكتب كودك بالعربية… وللخروج اكتب: خروج
"""


def run_code(source, script_dir=None):
    """ينفذ كودًا ويعيد المخرجات المطبوعة — للاختبارات والاستدعاء البرمجي."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        tokens = Lexer(source).tokenize()
        tree = Parser(tokens).parse()
        Interpreter(script_dir=script_dir).run(tree)
    return out.getvalue()


def print_error(error, lines=None):
    """يطبع الخطأ بشكل واضح مع سطر الكود المعني وعلامة تشير تحت
    العمود المذنب إن توفر (1.23)."""
    print(str(error), file=sys.stderr)
    if lines and error.line and 1 <= error.line <= len(lines):
        source_line = lines[error.line - 1].rstrip()
        width = len(str(error.line))
        pad = ' ' * (error.col - 1) if error.col else ''
        print(f'  {error.line} | {source_line}', file=sys.stderr)
        print('  ' + ' ' * width + f' | {pad}^', file=sys.stderr)


def check_file(path):
    """يفحص صياغة الملف دون تنفيذه — يفيد في الأدوات والتحرير الآلي."""
    try:
        with open(path, encoding='utf-8-sig') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"خطأ: الملف '{path}' غير موجود", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError:
        print('خطأ: الملف يجب أن يكون بترميز UTF-8', file=sys.stderr)
        sys.exit(1)
    try:
        tokens = Lexer(source).tokenize()
        tree = Parser(tokens).parse()
    except ArabiError as error:
        print_error(error, source.splitlines())
        sys.exit(1)
    print(f'✓ الصياغة سليمة — {len(tree.statements)} جملة على المستوى الأعلى')


def _read_source(path):
    """يقرأ مصدر ملف مع رسائل خطأ عربية موحدة — بترميز utf-8-sig
    فيزول علامة ترتيب البايتات (BOM) من محررات ويندوز (1.23)."""
    try:
        with open(path, encoding='utf-8-sig') as f:
            return f.read()
    except FileNotFoundError:
        print(f"خطأ: الملف '{path}' غير موجود", file=sys.stderr)
    except UnicodeDecodeError:
        print('خطأ: الملف يجب أن يكون بترميز UTF-8', file=sys.stderr)
    except IsADirectoryError:
        print(f"خطأ: '{path}' مجلد وليس ملفًا", file=sys.stderr)
    sys.exit(1)


# ================== أدوات النظام البيئي (الإصدار 1.6) ==================

def format_files(paths):
    """ينسق الملفات الممررة في مكانها ويطبع ملخصًا لكل ملف."""
    failed = False
    for path in paths:
        source = _read_source(path)
        try:
            formatted, changed = tools.format_source(source)
        except ArabiError as error:
            print_error(error, source.splitlines())
            failed = True
            continue
        if changed:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(formatted)
        print(f'✓ {path} — نُسّق ({changed} سطرًا معدلًا)'
              if changed else f'✓ {path} — منسق أصلًا (لا تغييرات)')
    if failed:
        sys.exit(1)


def lint_files(paths):
    """يفحص الملفات ويطبع النتائج — يخرج بكود ١ عند وجود أخطاء مؤكدة."""
    failed = False
    for path in paths:
        source = _read_source(path)
        try:
            issues = tools.lint_source(source)
        except ArabiError as error:
            print_error(error, source.splitlines())
            failed = True
            continue
        if not issues:
            print(f'✓ {path}: لا مشكلات')
            continue
        print(f'{path}:')
        for line, kind, msg in issues:
            mark = '✗' if kind == 'خطأ' else '⚠'
            print(f'  {mark} سطر {line}: {msg}')
            if kind == 'خطأ':
                failed = True
        errors = sum(1 for _, k, _ in issues if k == 'خطأ')
        warnings = len(issues) - errors
        print(f'  ── {errors} خطأ، {warnings} تحذير')
    if failed:
        sys.exit(1)


def document_file(path, output=None):
    """يولد توثيق Markdown للملف — يطبع أو يكتب في ملف ناتج."""
    source = _read_source(path)
    try:
        docs = tools.generate_docs(path, source)
    except ArabiError as error:
        print_error(error, source.splitlines())
        sys.exit(1)
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(docs)
        print(f'✓ وُلّد التوثيق في {output}')
    else:
        print(docs, end='')


def install_package(source):
    """يثبت مكتبة .عربي من مسار محلي أو رابط في مجلد مكتبات/."""
    try:
        name, dest = tools.install_package(source)
    except ArabiError as error:
        print(f'✗ {error}', file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        # روابط غير آسكية وأخطاء تحويل مشابهة — رسالة عربية لا أثر خام
        print(f"✗ مصدر المكتبة غير صالح: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"✗ فشل تحميل المكتبة: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f'✓ ثُبتت المكتبة \'{name}\' في {dest}')
    print(f"  لاستخدامها: استورد {name}")


def list_packages():
    """يعرض المكتبات المثبتة في مجلد مكتبات/ الحالي."""
    packages = tools.list_packages()
    if not packages:
        print('لا توجد مكتبات مثبتة في مجلد مكتبات/')
        print(f"  للتثبيت: {prog_name()} --ثبت مسار_أو_رابط")
        return
    print(f'المكتبات المثبتة ({len(packages)}):')
    for pkg in packages:
        print(f'  - {pkg[:-len(".عربي")]}')


# ================== سجل الحزم (الإصدار 1.12) ==================

def _parse_index_flag(args):
    """يستخرج العلم --الفهرس (مصدر بديل لسجل الحزم) من المعاملات."""
    for i, arg in enumerate(args):
        if arg in ('--الفهرس', '--index'):
            if i + 1 >= len(args):
                print("خطأ: العلم '--الفهرس' يحتاج مسارًا أو رابطًا بعده",
                      file=sys.stderr)
                sys.exit(1)
            return args[i + 1]
    return None


def _parse_flag_value(args, names, error_message):
    """يستخرج قيمة علم من المعاملات ويحذفهما — أو لا شيء إن غاب."""
    for i, arg in enumerate(args):
        if arg in names:
            if i + 1 >= len(args):
                print(f'خطأ: {arg} يحتاج قيمة بعده — {error_message}',
                      file=sys.stderr)
                sys.exit(1)
            return args[i + 1], [a for j, a in enumerate(args)
                                 if j not in (i, i + 1)]
    return None, args


def package_cli(args):
    """مدير الحزم: إنشاء|تثبيت|إزالة|قائمة|بحث|تحديث|مزامنة|ترقيات|فحص|خادم|نشر"""
    from arabi_lang import packages
    index_source = _parse_index_flag(args)
    # إزالة العلم وقيمته من المعاملات
    cleaned = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ('--الفهرس', '--index'):
            skip = True
            continue
        cleaned.append(a)
    args = cleaned

    if not args:
        print(f'استخدام: {prog_name()} حزمة <أمر> [معاملات]')
        print('الأوامر: إنشاء [اسم] — تثبيت [اسم|مسار|رابط] — إزالة اسم — قائمة — '
              'بحث [كلمة] — تحديث [اسم]')
        print('        مزامنة — ترقيات — فحص            بيئة المشروع (1.28)')
        print('        خادم [مجلد] --منفذ N --عنوان H --مفتاح سر [--بلا_واجهة]  '
              'سجل مجتمعي (1.20، واجهة متصفح 1.22)')
        print('        نشر مسار --الفهرس رابط [--نسخة X] [--مفتاح سر]  '
              'نشر إلى السجل (1.20)')
        print("مصدر الفهرس: --الفهرس مسار|رابط أو متغير البيئة "
              f"{packages.INDEX_ENV}")
        sys.exit(1)

    cmd = args[0]
    rest = args[1:]
    try:
        if cmd in ('إنشاء', '--إنشاء', 'init'):
            # إنشاء هيكل مشروع جديد (1.28): بيان + مدخل نموذجي
            version, rest = _parse_flag_value(
                rest, ('--نسخة', '--version'), 'نسخة مثل 0.1.0')
            desc, rest = _parse_flag_value(
                rest, ('--وصف', '--desc'), 'نص وصف الحزمة')
            created = packages.create_project(
                os.getcwd(), name=rest[0] if rest else None,
                version=version or '0.1.0', description=desc or '')
            for path in created:
                print(f'✓ أنشئ: {os.path.relpath(path)}')
            print(f'الخطوة التالية: {prog_name()} حزمة تثبيت اسم_الحزمة '
                  '— تُسجّل التبعيات في البيان')
        elif cmd in ('تثبيت', '--تثبيت', 'install'):
            target = rest[0] if rest else None
            _package_install(packages, target, index_source)
        elif cmd in ('إزالة', '--إزالة', 'remove'):
            if not rest:
                print("خطأ: 'حزمة إزالة' يحتاج اسم الحزمة بعده",
                      file=sys.stderr)
                sys.exit(1)
            print(packages.remove(rest[0]))
            if packages.unrecord_dependency(os.getcwd(), rest[0]):
                print(f'→ حُذفت التبعية {rest[0]} من '
                      f'{packages.MANIFEST_NAME}')
        elif cmd in ('قائمة', '--قائمة', 'list'):
            _package_list(packages)
        elif cmd in ('بحث', '--بحث', 'search'):
            _package_search(packages, rest[0] if rest else '', index_source)
        elif cmd in ('تحديث', '--تحديث', 'update'):
            target = rest[0] if rest else None
            _package_update(packages, target, index_source)
        elif cmd in ('مزامنة', '--مزامنة', 'sync'):
            _package_sync(packages, index_source)
        elif cmd in ('ترقيات', '--ترقيات', 'outdated'):
            _package_outdated(packages, index_source)
        elif cmd in ('فحص', '--فحص', 'verify'):
            _package_verify(packages)
        elif cmd in ('خادم', '--خادم', 'server'):
            # سجل مجتمعي محلي (1.20): يخدم الفهرس والتنزيل والنشر
            # وواجهة متصفح عربية (1.22) يعطلها علم --بلا_واجهة
            from arabi_lang import registry
            port_raw, rest = _parse_flag_value(
                rest, ('--منفذ', '--port'), 'رقم منفذ مثل 8000')
            host, rest = _parse_flag_value(
                rest, ('--عنوان', '--host'), 'عنوان مثل 127.0.0.1')
            key, rest = _parse_flag_value(
                rest, ('--مفتاح', '--key'), 'نص سر غير فارغ')
            no_web = False
            for flag in ('--بلا_واجهة', '--بلا-واجهة', '--no-web'):
                while flag in rest:
                    rest.remove(flag)
                    no_web = True
            # المجلد بعد نزع الأعلام — فيصح الترتيب بأي تسلسل
            # والافتراضي «سجل-الحزم» في دليل العمل (كان يشير لثابت محذوف
            # فينهار الأمر الموثق بلا مجلد — تقرير التدقيق م11-2)
            store = rest[0] if rest else registry.default_store_dir()
            try:
                port = int(port_raw) if port_raw else 0
            except ValueError:
                print(f"خطأ: المنفذ '{port_raw}' يجب أن يكون رقمًا مثل 8000",
                      file=sys.stderr)
                sys.exit(1)
            if port_raw and not 0 <= port <= 65535:
                print(f'خطأ: المنفذ {port} خارج المدى (٠-٦٥٥٣٥)',
                      file=sys.stderr)
                sys.exit(1)
            sys.exit(registry.run_server_cli(
                store, host=host or '127.0.0.1', port=port,
                auth_key=key, no_web=no_web))
        elif cmd in ('نشر', '--نشر', 'publish'):
            # نشر حزمة إلى سجل مجتمعي (1.20)
            if not rest:
                print("خطأ: 'حزمة نشر' يحتاج مسار الحزمة بعده (مجلد "
                      'ببيان أو ملف .عربي)', file=sys.stderr)
                sys.exit(1)
            if not index_source:
                print("خطأ: النشر يحتاج عنوان السجل: --الفهرس "
                      'http://مضيف:منفذ', file=sys.stderr)
                sys.exit(1)
            key, rest = _parse_flag_value(
                rest, ('--مفتاح', '--key'), 'نص سر غير فارغ')
            version, rest = _parse_flag_value(
                rest, ('--نسخة', '--version'), 'نسخة مثل 1.0.0')
            print(packages.publish(rest[0], index_source,
                                   auth_key=key, version=version))
        else:
            print(f"خطأ: أمر حزمة غير معروف: '{cmd}' — الأوامر: "
                  'إنشاء، تثبيت، إزالة، قائمة، بحث، تحديث، مزامنة، '
                  'ترقيات، فحص، خادم، نشر',
                  file=sys.stderr)
            sys.exit(1)
    except packages.ArabiError as error:
        print(f'✗ {error}', file=sys.stderr)
        sys.exit(1)


def _package_install(packages, target, index_source):
    """تثبيت حزمة بالاسم/المصدر، أو تبعيات المشروع إن لم يُحدد هدف."""
    if target is None:
        # تثبيت تبعيات مشروع له بيان محلي حزمة.json
        manifest_path = os.path.join(os.getcwd(), packages.MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            print('حدّد حزمة للتثبيت، أو شغّل الأمر داخل مشروع يحمل '
                  f'{packages.MANIFEST_NAME} لتثبيت تبعياته', file=sys.stderr)
            sys.exit(1)
        with open(manifest_path, encoding='utf-8') as f:
            deps = json.load(f).get('التبعيات', {})
        if not deps:
            print('المشروع بلا تبعيات — لا شيء للتثبيت')
            return
        for name, constraint in deps.items():
            _print_install(packages.install_dep(
                name, constraint, os.getcwd(), index_source, []))
    else:
        messages = packages.install(target, os.getcwd(), index_source)
        _print_install(messages)
        _record_installed(packages, target)


def _record_installed(packages, target):
    """يسجل التثبيت بالاسم من السجل في بيان المشروع (1.28 — ق١٧/ق١٨).

    القيد: الصريح من صيغة 'اسم>=قيد'، أو القيد الموجود سلفًا، أو
    '^النسخة المثبتة' — وبيان غائب ينشأ أدنى. مصادر المسار/الرابط
    لا تُسجّل (غير قابلة لإعادة الإنتاج من البيان).
    """
    if not isinstance(target, str):
        return
    if ('/' in target or '\\' in target
            or target.startswith(('http://', 'https://', 'file://'))
            or os.path.exists(target)):
        return                            # مصدر مباشر — لا تسجيل
    name, parsed = packages.split_request(target)
    if not packages.NAME_RE.match(name):
        return                            # فشل التثبيت يبرّر نفسه في الأعلى
    installed = packages.list_installed(os.getcwd())
    if name not in installed or not installed[name]['نسخة']:
        return
    constraint = parsed
    if constraint is None:
        existing = None
        if os.path.isfile(os.path.join(os.getcwd(),
                                       packages.MANIFEST_NAME)):
            try:
                existing = packages.read_project_manifest(
                    os.getcwd()).get('التبعيات', {}).get(name)
            except packages.ArabiError:
                existing = None
        constraint = existing or ('^' + installed[name]['نسخة'])
    changed, used = packages.record_dependency(os.getcwd(), name,
                                               constraint)
    if changed:
        print(f'→ سُجّلت التبعية {name} {used} في '
              f'{packages.MANIFEST_NAME}')


def _print_install(messages):
    """يطبع رسائل التثبيت مع ملخص القفل."""
    from arabi_lang import packages
    for text, kind in messages:
        print(('✓ ' if kind == 'ثُبتت' else '• ') + text)
    if any(kind == 'ثُبتت' for _, kind in messages):
        print(f'→ سُجّلت النسخ المثبتة في {packages.LOCK_NAME}')


def _package_list(packages):
    """عرض الحزم المثبتة مع نسخها وتبعياتها."""
    installed = packages.list_installed(os.getcwd())
    if not installed:
        print('لا حزم مثبتة في مجلد حزم/')
        print(f"  للتثبيت: {prog_name()} حزمة تثبيت اسم_الحزمة")
        return
    print(f'الحزم المثبتة ({len(installed)}):')
    for name, info in installed.items():
        version = info['نسخة'] or '؟'
        deps = '، '.join(info['تبعيات']) or 'بلا تبعيات'
        print(f'  - {name} v{version} — {deps}')


def _package_search(packages, term, index_source):
    """بحث في فهرس السجل بالاسم أو الوصف."""
    results = packages.search(term, index_source)
    if not results:
        print(f'لا نتائج للبحث عن "{term}"')
        return
    print(f'نتائج البحث ({len(results)}):')
    for name, info in results:
        desc = info.get('الوصف') or ''
        print(f"  - {name} v{info.get('النسخة', '؟')} — {desc}")


def _package_update(packages, target, index_source):
    """تحديث حزمة أو كل الحزم إلى أحدث نسخة في السجل.

    بعد النجاح: قيد التبعية في بيان المشروع يصحّح فقط حين تخالف
    النسخة الجديدة القيد المسجل (ق١٧) — ولا يدسّ عند بيان فاسد.
    """
    messages = packages.update(target, os.getcwd(), index_source)
    if not messages:
        print('لا حزم مثبتة لتحديثها')
        return
    _print_install(messages)
    manifest_path = os.path.join(os.getcwd(), packages.MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        return
    try:
        data = packages.read_project_manifest(os.getcwd())
        deps = data.get('التبعيات') or {}
        installed = packages.list_installed(os.getcwd())
        changed = False
        for dep, constraint in list(deps.items()):
            version = installed.get(dep, {}).get('نسخة')
            if version and not packages.satisfies(version, constraint):
                deps[dep] = '^' + version
                print(f'→ حُدّث قيد {dep} في البيان إلى {deps[dep]}')
                changed = True
        if changed:
            packages.write_project_manifest(os.getcwd(), data)
    except packages.ArabiError as exc:
        print(f'تنبيه: تعذر تحديث قيود البيان: '
              f'{getattr(exc, "message", None) or exc}', file=sys.stderr)


def _package_sync(packages, index_source):
    """مزامنة بيئة المشروع مع بيان حزمة.json (1.28)."""
    try:
        messages = packages.sync(os.getcwd(), index_source)
    except packages.ArabiError as error:
        print(f'✗ {getattr(error, "message", None) or error}',
              file=sys.stderr)
        sys.exit(1)
    for text, kind in messages:
        icon = {'ثُبتت': '✓', 'استُبدلت': '✓', 'مطابقة': '•',
                'زيادة': '•', 'تعذر': '✗'}.get(kind, '•')
        print(icon + ' ' + text)
    if not messages:
        print('البيئة موزونة مع البيان — لا تبعيات ولا حزم زيادة')
        return
    if any(kind == 'ثُبتت' for _, kind in messages):
        print(f'→ سُجّلت النسخ المثبتة في {packages.LOCK_NAME}')
    if any(kind == 'تعذر' for _, kind in messages):
        print('✗ المزامنة انتهت بأعطال — بقية البيئة موزونة',
              file=sys.stderr)
        sys.exit(1)


def _package_outdated(packages, index_source):
    """عرض الحزم التي لها نسخة أحدث في السجل (1.28) — معلوماتي."""
    rows = packages.outdated(os.getcwd(), index_source)
    if not rows:
        print('كل الحزم المثبتة على أحدث نسخة في السجل')
        return
    print(f'حزم لها نسخة أحدث في السجل ({len(rows)}):')
    for name, current, latest, desc in rows:
        note = f' — {desc}' if desc else ''
        print(f'  - {name} v{current} ← v{latest}{note}')
    print(f'  للتحديث: {prog_name()} حزمة تحديث')


def _package_verify(packages):
    """فحص سلامة بيئة المشروع — رمز خروج 1 عند الانحراف (ق٢٠)."""
    issues = packages.verify(os.getcwd())
    if not issues:
        print('✓ البيئة سليمة: القفل والبيان ومجلد الحزم متطابقة')
        return
    print(f'انحراف في بيئة المشروع ({len(issues)}):')
    for issue in issues:
        print(f'  - {issue}')
    sys.exit(1)


def run_file(path, use_bytecode=True, use_vm=True):
    try:
        with open(path, encoding='utf-8-sig') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"خطأ: الملف '{path}' غير موجود", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError:
        print('خطأ: الملف يجب أن يكون بترميز UTF-8', file=sys.stderr)
        sys.exit(1)
    except IsADirectoryError:
        print(f"خطأ: '{path}' مجلد وليس ملفًا", file=sys.stderr)
        sys.exit(1)

    lines = source.splitlines()
    try:
        # الكود الوسيط: الذاكرة الصالحة توفّر التحليل اللفظي والنحوي
        if use_bytecode:
            from arabi_lang.bytecode import read_program
            tree, _from_cache = read_program(path, source)
        else:
            tokens = Lexer(source).tokenize()
            tree = Parser(tokens).parse()
        # مجلد الملف هو أساس البحث عن الوحدات المستوردة
        script_dir = os.path.dirname(os.path.abspath(path))
        Interpreter(script_dir=script_dir,
                    use_bytecode=use_bytecode, use_vm=use_vm).run(tree)
    except ArabiError as error:
        print_error(error, lines)
        sys.exit(1)
    except RecursionError:
        # التعاود العميق وقت التشغيل خارج جرب — رسالة عربية وخروج
        # منظم بدل أثر بايثون خام (1.23)
        print('خطأ تشغيلي: تعاود عميق جدًا — تحقق من شرط التوقف في '
              'دالتك أو زد الحد بثبات', file=sys.stderr)
        sys.exit(1)


def compile_files(paths):
    """يترجم الملفات إلى كود وسيط دون تنفيذ — يطبع مسار كل ذاكرة."""
    failed = False
    for path in paths:
        source = _read_source(path)
        try:
            cpath = bytecode.compile_file(path)
            size = os.path.getsize(cpath)
            print(f'✓ {path} → {cpath} ({size} بايت)')
        except ArabiError as error:
            print_error(error, source.splitlines())
            failed = True
    if failed:
        sys.exit(1)


def _bracket_state(code):
    """يفحص توازن الأقواس والنصوص — لتحديد الحاجة لسطر إضافي في REPL."""
    depth = 0
    i = 0
    n = len(code)
    quote = None
    while i < n:
        c = code[i]
        if quote is not None:
            if c == '\\':
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in '"\'':
            quote = c
        elif c == '#':
            while i < n and code[i] != '\n':
                i += 1
            continue
        elif c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        i += 1
    return depth, quote


def _needs_more_input(code):
    stripped = code.rstrip()
    if not stripped:
        return False
    if stripped.endswith(':') or stripped.endswith('\\'):
        return True
    depth, quote = _bracket_state(stripped)
    return depth > 0 or quote is not None


def repl():
    """المفسر التفاعلي — ينفذ الأسطر فورًا ويحفظ المتغيرات بينها.

    يدعم سجل الأوامر والإكمال التلقائي (عند توفر readline).
    """
    print(BANNER)
    interpreter = Interpreter()
    history_file = _setup_readline(interpreter)
    buffer = []
    try:
        while True:
            try:
                prompt = '>>> ' if not buffer else '... '
                line = input(prompt)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print('\n(أُلغيت الجملة الحالية)')
                buffer = []
                continue

            if not buffer and line.strip() in ('خروج', 'exit', 'quit', 'سلام'):
                print('إلى اللقاء!')
                break

            buffer.append(line)
            code = '\n'.join(buffer)

            if _needs_more_input(code):
                continue
            buffer = []

            if not code.strip():
                continue

            try:
                tokens = Lexer(code).tokenize()
                tree = Parser(tokens).parse()
                result = interpreter.run(tree)
                if result is not None:
                    from arabi_lang.runtime import display
                    print(display(result))
            except ArabiError as error:
                print(str(error))
            except RecursionError:
                # التعاود العميق لا يقتل الجلسة — رسالة ثم استمرار (1.23)
                print('خطأ تشغيلي: تعاود عميق جدًا — تحقق من شرط التوقف '
                      'في دالتك')
    finally:
        if history_file:
            try:
                import readline
                readline.write_history_file(history_file)
            except (ImportError, OSError):
                pass


def _setup_readline(interpreter):
    """يفعّل سجل الأوامر والإكمال التلقائي — يعيد مسار ملف السجل."""
    try:
        import readline
    except ImportError:
        return None

    history_file = os.path.expanduser('~/.arabi_history')
    try:
        readline.read_history_file(history_file)
    except (OSError, IOError):
        pass

    from arabi_lang.lexer import KEYWORDS

    def complete(text, state):
        names = sorted(set(KEYWORDS)
                       | set(interpreter.globals.vars.keys()))
        matches = [n for n in names if n.startswith(text)]
        return matches[state] if state < len(matches) else None

    readline.set_completer(complete)
    readline.set_completer_delims(' \t\n,()[]{}:;=+-*/%<>!')
    if 'libedit' in (readline.__doc__ or ''):
        readline.parse_and_bind('bind ^I rl_complete')
    else:
        readline.parse_and_bind('tab: complete')
    return history_file


def show_help():
    # في النسخة التنفيذية المستقلة يكون البرنامج نفسه هو أمر التشغيل
    prog = prog_name()
    print(f"""عربي — لغة برمجة عربية بالكامل

الاستخدام:
    {prog} ملف.عربي        تشغيل ملف برمجي
    {prog}                 فتح المفسر التفاعلي (REPL)
    {prog} -c "كود"        تنفيذ كود مباشر
    {prog} --تحقق ملف      فحص الصياغة دون تنفيذ
    {prog} --نسق ملفات     تنسيق الملفات وإصلاح الإزاحة
    {prog} --افحص ملفات    فحص الملفات بحثًا عن المشكلات
    {prog} --وثق ملف [ناتج] توليد توثيق Markdown
    {prog} --ثبت مسار|رابط  تثبيت مكتبة في مجلد مكتبات/
    {prog} --حزم           عرض المكتبات المثبتة
    {prog} حزمة إنشاء [اسم]             إنشاء مشروع جديد ببيان ومدخل نموذجي
    {prog} حزمة تثبيت [اسم|مسار|رابط]
                                    تثبيت حزمة أو تبعيات المشروع (سجل الحزم) —
                                    التثبيت بالاسم يُسجّل التبعية في حزمة.json
    {prog} حزمة قائمة       عرض الحزم المثبتة في حزم/
    {prog} حزمة إزالة اسم   إزالة حزمة مثبتة (ومحوها من البيان)
    {prog} حزمة بحث [كلمة]  البحث في فهرس السجل
    {prog} حزمة تحديث [اسم] تحديث إلى أحدث نسخة في السجل
    {prog} حزمة مزامنة      موازنة بيئة المشروع مع بيان حزمة.json
    {prog} حزمة ترقيات      عرض الحزم التي لها نسخة أحدث في السجل
    {prog} حزمة فحص         فحص سلامة البيئة (رمز خروج 1 عند الانحراف)
    {prog} --بايت ملفات    ترجمة الملفات إلى كود وسيط (.بيت) دون تنفيذ
    {prog} --لا-بايت ملف   تشغيل معطّلًا الكود الوسيط (تجاهل الذاكرة)
    {prog} --لا-دولاب ملف  تشغيل معطّلًا الدولاب الافتراضي (ممسح شجري)
    {prog} --عامل م:منفذ [--مفتاح سر]  تشغيل عامل موزع يخدم موزعًا على الشبكة (1.18) ويوقع التحدي بالمفتاح المشترك (1.19)
    {prog} --نسخة | -v     عرض الإصدار
    {prog} --مساعدة | -h   عرض هذه المساعدة

ملاحظة: إن كان لديك الملف التنفيذي المستقل «عربي» (الإصدار 1.14+) فاستبدل
«python arabi.py» باسم الملف التنفيذي نفسه — يعمل بلا حاجة لبايثون:
    ./عربي ملف.عربي                تشغيل ملف برمجي
    ./عربي                         فتح المفسر التفاعلي (REPL)

ملاحظة: بعد تثبيت اللغة عبر pip (الإصدار 1.16+) استخدم الأمر arabi أو
python -m arabi بدل python arabi.py — كل الأدوات تعمل كما هي.

الوحدات المدمجة (٢٠): رياضيات، وقت، ملفات، جيسون، عشوائية، نظام، تنظيم، شبكة، تحويل، قاعدة، ترميز، جداول، خيوط، عمليات، موزعة، تشفير، تواريخ، إحصاء، اختبارات، خادم
الأمثلة موجودة في مجلد examples/""")
    sys.exit(0)


def main():
    # دعم وحدة 'عمليات' في التنفيذي المجمد (PyInstaller): يجب أن يكون
    # أول ما يُستدعى حتى تُعالج حزم إقلاع العمليات الابنة فورًا وتخرج —
    # في التشغيل العادي من المصدر لا أثر له إطلاقًا.
    multiprocessing.freeze_support()
    args = sys.argv[1:]
    if not args:
        repl()
        return
    first = args[0]
    if first in ('--نسخة', '-v', '--version'):
        print(version_text())
    elif first in ('--مساعدة', '-h', '--help'):
        show_help()
    elif first in ('--تحقق', '--check'):
        if len(args) < 2:
            print("خطأ: الخيار '--تحقق' يحتاج مسار ملف بعده", file=sys.stderr)
            sys.exit(1)
        check_file(args[1])
    elif first in ('--نسق', '--format'):
        if len(args) < 2:
            print("خطأ: الخيار '--نسق' يحتاج مسار ملف واحد على الأقل بعده",
                  file=sys.stderr)
            sys.exit(1)
        format_files(args[1:])
    elif first in ('--افحص', '--lint'):
        if len(args) < 2:
            print("خطأ: الخيار '--افحص' يحتاج مسار ملف واحد على الأقل بعده",
                  file=sys.stderr)
            sys.exit(1)
        lint_files(args[1:])
    elif first in ('--وثق', '--docs'):
        if len(args) < 2:
            print("خطأ: الخيار '--وثق' يحتاج مسار ملف بعده", file=sys.stderr)
            sys.exit(1)
        document_file(args[1], args[2] if len(args) > 2 else None)
    elif first in ('--ثبت', '--install'):
        if len(args) < 2:
            print("خطأ: الخيار '--ثبت' يحتاج مسار ملف أو رابطًا بعده",
                  file=sys.stderr)
            sys.exit(1)
        install_package(args[1])
    elif first in ('--حزم', '--packages'):
        list_packages()
    elif first in ('حزمة', 'packages-manage'):
        package_cli(args[1:])
    elif first in ('--لغة', '--lsp'):
        # خادم اللغة: يتواصل عبر القنوات القياسية بلا أي مخرجات أخرى
        lsp_module.main()
    elif first in ('--عامل', '--worker'):
        # عامل موزع: يربط بالموزع ويخدم مهامه حتى إغلاقه (الإصدار 1.18)
        # --مفتاح سر (1.19): يوقع تحدي المصادقة بالمفتاح المشترك
        if len(args) < 2:
            print("خطأ: الخيار '--عامل' يحتاج عنوانًا بعده بالشكل "
                  'المضيف:المنفذ — مثال: 192.168.1.10:7700',
                  file=sys.stderr)
            sys.exit(1)
        key = None
        if len(args) >= 4 and args[2] in ('--مفتاح', '--key'):
            key = args[3]
        elif len(args) > 2:
            print("خطأ: معاملات زائدة بعد العنوان — استخدم: "
                  "'--عامل المضيف:المنفذ --مفتاح السر'",
                  file=sys.stderr)
            sys.exit(1)
        from arabi_lang.distributed import run_worker_cli
        if key is not None:
            print(f'عامل عربي متصل بالموزع {args[1]} بالمفتاح السري '
                  '— في انتظار المهام…', flush=True)
        else:
            print(f'عامل عربي متصل بالموزع {args[1]} — في انتظار المهام…',
                  flush=True)
        sys.exit(run_worker_cli(args[1], key=key))
    elif first in ('--بايت', '--bytecode'):
        if len(args) < 2:
            print("خطأ: الخيار '--بايت' يحتاج مسار ملف واحد على الأقل بعده",
                  file=sys.stderr)
            sys.exit(1)
        compile_files(args[1:])
    elif first in ('--لا-بايت', '--no-bytecode'):
        if len(args) < 2:
            print("خطأ: الخيار '--لا-بايت' يحتاج مسار ملف بعده",
                  file=sys.stderr)
            sys.exit(1)
        run_file(args[1], use_bytecode=False)
    elif first in ('--لا-دولاب', '--no-vm'):
        if len(args) < 2:
            print("خطأ: الخيار '--لا-دولاب' يحتاج مسار ملف بعده",
                  file=sys.stderr)
            sys.exit(1)
        run_file(args[1], use_vm=False)
    elif first in ('-c', '--كود', '--تنفيذ'):
        if len(args) < 2:
            print("خطأ: الخيار '-c' يحتاج كودًا بعده", file=sys.stderr)
            sys.exit(1)
        try:
            tokens = Lexer(args[1]).tokenize()
            tree = Parser(tokens).parse()
            Interpreter().run(tree)
        except ArabiError as error:
            print(str(error), file=sys.stderr)
            sys.exit(1)
        except RecursionError:
            print('خطأ تشغيلي: تعاود عميق جدًا — تحقق من شرط التوقف في '
                  'دالتك', file=sys.stderr)
            sys.exit(1)
    else:
        run_file(first)


if __name__ == '__main__':
    main()
