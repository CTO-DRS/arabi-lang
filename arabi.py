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
    python arabi.py --لغة           تشغيل خادم اللغة (LSP) للمحررات
    python arabi.py --نسخة          عرض الإصدار
"""

import io
import sys
import os
import contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arabi_lang import __version__
from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser
from arabi_lang.interpreter import Interpreter
from arabi_lang.errors import ArabiError
from arabi_lang import tools
from arabi_lang import lsp as lsp_module

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
    """يطبع الخطأ بشكل واضح مع سطر الكود المعني."""
    print(str(error), file=sys.stderr)
    if lines and error.line and 1 <= error.line <= len(lines):
        source_line = lines[error.line - 1].rstrip()
        width = len(str(error.line))
        print(f'  {error.line} | {source_line}', file=sys.stderr)
        print('  ' + ' ' * width + ' | ^', file=sys.stderr)


def check_file(path):
    """يفحص صياغة الملف دون تنفيذه — يفيد في الأدوات والتحرير الآلي."""
    try:
        with open(path, encoding='utf-8') as f:
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
    """يقرأ مصدر ملف مع رسائل خطأ عربية موحدة."""
    try:
        with open(path, encoding='utf-8') as f:
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
        print('  للتثبيت: python arabi.py --ثبت مسار_أو_رابط')
        return
    print(f'المكتبات المثبتة ({len(packages)}):')
    for pkg in packages:
        print(f'  - {pkg[:-len(".عربي")]}')


def run_file(path):
    try:
        with open(path, encoding='utf-8') as f:
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
        tokens = Lexer(source).tokenize()
        tree = Parser(tokens).parse()
        # مجلد الملف هو أساس البحث عن الوحدات المستوردة
        script_dir = os.path.dirname(os.path.abspath(path))
        Interpreter(script_dir=script_dir).run(tree)
    except ArabiError as error:
        print_error(error, lines)
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
    print("""عربي — لغة برمجة عربية بالكامل

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
    python arabi.py --نسخة | -v     عرض الإصدار
    python arabi.py --مساعدة | -h   عرض هذه المساعدة

الوحدات المدمجة: رياضيات، وقت، ملفات، جيسون، عشوائية، نظام، تنظيم، شبكة، تحويل، اختبارات، خادم، قاعدة، ترميز، جداول، خيوط، تواريخ، إحصاء
الأمثلة موجودة في مجلد examples/""")
    sys.exit(0)


def main():
    args = sys.argv[1:]
    if not args:
        repl()
        return
    first = args[0]
    if first in ('--نسخة', '-v', '--version'):
        print(f'عربي — الإصدار {__version__}')
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
    elif first in ('--لغة', '--lsp'):
        # خادم اللغة: يتواصل عبر القنوات القياسية بلا أي مخرجات أخرى
        lsp_module.main()
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
    else:
        run_file(first)


if __name__ == '__main__':
    main()
