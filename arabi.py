#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""عربي — لغة برمجة عربية بالكامل.

الاستخدام:
    python arabi.py ملف.عربي        تشغيل ملف برمجي
    python arabi.py                 فتح المفسر التفاعلي (REPL)
    python arabi.py -c "كود"        تنفيذ كود مباشر
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
    """المفسر التفاعلي — ينفذ الأسطر فورًا ويحفظ المتغيرات بينها."""
    print(BANNER)
    interpreter = Interpreter()
    buffer = []
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


def show_help():
    print("""عربي — لغة برمجة عربية بالكامل

الاستخدام:
    python arabi.py ملف.عربي        تشغيل ملف برمجي
    python arabi.py                 فتح المفسر التفاعلي (REPL)
    python arabi.py -c "كود"        تنفيذ كود مباشر
    python arabi.py --نسخة | -v     عرض الإصدار
    python arabi.py --مساعدة | -h   عرض هذه المساعدة

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
    elif first in ('-c', '--كود'):
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
