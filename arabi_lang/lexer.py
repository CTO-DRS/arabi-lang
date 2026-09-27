# -*- coding: utf-8 -*-
"""المحلل اللفظي (Lexer) — يحوّل نص البرنامج إلى سلسلة رموز.

يدعم:
- الأرقام العربية الشرقية (٠-٩) والغربية (0-9)
- الفاصلة العربية (،) والغربية (,)
- كلمات مفتاحية مركبة من كلمتين: «وإلا إذا» و«ولا شيء»
- كتل بمسافات بادئة مثل بايثون (INDENT / DEDENT)
- النصوص المنسقة: ق"مرحبا {الاسم}" — البادئة ق (قالب)
- النصوص متعددة الأسطر: ثلاث علامات اقتباس مزدوجة أو مفردة
- كلمات الإصدار 1.5: تعداد، خاصية، عالمي، تحقق، احذف
- كلمات الإصدار 1.7: أنتج (المولدات) وعلامة @ (المزخرفات)
"""

import re

from .tokens import T, Token
from .errors import LexerError

# تحويل الأرقام العربية إلى الغربية
AR2EN = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')

DIGIT_CHARS = set('0123456789٠١٢٣٤٥٦٧٨٩')

KEYWORDS = {
    'دالة': T.DEF,
    'أعد': T.RETURN,
    'لو': T.IF,
    'وإلا': T.ELSE,
    'طالما': T.WHILE,
    'لكل': T.FOR,
    'في': T.IN,
    'كسر': T.BREAK,
    'استمر': T.CONTINUE,
    'صح': T.TRUE,
    'خطأ': T.FALSE,
    'و': T.AND,
    'أو': T.OR,
    'ليس': T.NOT,
    'جرب': T.TRY,
    'باستثناء': T.EXCEPT,
    'اخيرا': T.FINALLY,
    'ارفع': T.RAISE,
    'استورد': T.IMPORT,
    'تجاهل': T.PASS,
    'صنف': T.CLASS,
    'هذا': T.THIS,
    'الأصل': T.SUPER,
    'بدّل': T.SWITCH,
    'حالة': T.CASE,
    'افتراض': T.DEFAULT,
    # كلمات الإصدار 1.5
    'تعداد': T.ENUM,
    'خاصية': T.PROPERTY,
    'عالمي': T.GLOBAL,
    'تحقق': T.ASSERT,
    'احذف': T.DELETE,
    # كلمات الإصدار 1.7
    'أنتج': T.YIELD,
    # كلمات الإصدار 1.8
    'واجهة': T.INTERFACE,
}

# كلمات مفتاحية مركبة
ELIF_HINT = re.compile(r'[ \t]+إذا(?!\w)')     # وإلا إذا
NONE_HINT = re.compile(r'[ \t]+شيء(?!\w)')     # ولا شيء

IDENT_RE = re.compile(r'[\w\u064B-\u0655\u0670]+')          # يسمح بالتشكيل داخل الاسم
IDENT_START_RE = re.compile(r'[^\W\d]')

TWO_CHAR_OPS = {
    '**': T.POWER,
    '==': T.EQ,
    '!=': T.NEQ,
    '<=': T.LTE,
    '>=': T.GTE,
    '+=': T.PLUS_ASSIGN,
    '-=': T.MINUS_ASSIGN,
    '*=': T.STAR_ASSIGN,
    '/=': T.SLASH_ASSIGN,
    '=>': T.ARROW,
}

ONE_CHAR_OPS = {
    '+': T.PLUS, '-': T.MINUS, '*': T.STAR, '/': T.SLASH, '%': T.PERCENT,
    '=': T.ASSIGN, '<': T.LT, '>': T.GT,
    '(': T.LPAREN, ')': T.RPAREN,
    '[': T.LBRACKET, ']': T.RBRACKET,
    '{': T.LBRACE, '}': T.RBRACE,
    ',': T.COMMA, ':': T.COLON, '.': T.DOT,
    '@': T.AT,
}

OPEN_BRACKETS = {'(': ')', '[': ']', '{': '}'}
CLOSE_BRACKETS = {')': '(', ']': '[', '}': '{'}

ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '0': '\0', 'a': '\a', 'b': '\b', 'f': '\f'}


class Lexer:
    """يستقبل نص البرنامج المصدري وينتج قائمة من الرموز."""

    def __init__(self, source, lenient_indent=False):
        src = source.replace('\r\n', '\n').replace('\r', '\n')
        if not src.endswith('\n'):
            src += '\n'
        self.src = src
        self.pos = 0
        self.line = 1
        self.tokens = []
        self.indents = [0]
        self.brackets = []          # لتتبع الأقواس المفتوحة
        self.at_line_start = True
        # الوضع المتساهل: يقبل إزاحات غير متسقة (لأدوات الفحص والتنسيق)
        self.lenient_indent = lenient_indent

    # ---------- أدوات مساعدة ----------

    def error(self, message):
        raise LexerError(message, self.line)

    def add(self, type_, value):
        self.tokens.append(Token(type_, value, self.line))

    # ---------- التحليل ----------

    def tokenize(self):
        while self.pos < len(self.src):
            if self.at_line_start and not self.brackets:
                if self._handle_indentation():
                    continue          # سطر فارغ أو تعليق فقط — تخطاه
            ch = self.src[self.pos]

            if ch == '\n':
                if not self.brackets:
                    self._emit_newline()
                    self.at_line_start = True
                self.pos += 1
                self.line += 1
                continue

            if ch in ' \t':
                self.pos += 1
                continue

            if ch == '#':
                while self.pos < len(self.src) and self.src[self.pos] != '\n':
                    self.pos += 1
                continue

            if ch in DIGIT_CHARS:
                self._read_number()
                continue

            if ch in '"\'':
                self._read_string(ch)
                continue

            if ch == '،':             # الفاصلة العربية
                self.add(T.COMMA, '،')
                self.pos += 1
                continue

            if self.src.startswith('...', self.pos):
                self.add(T.ELLIPSIS, '...')
                self.pos += 3
                continue

            pair = self.src[self.pos:self.pos + 2]
            if pair in TWO_CHAR_OPS:
                self.add(TWO_CHAR_OPS[pair], pair)
                self.pos += 2
                continue

            if ch in ONE_CHAR_OPS:
                t = ONE_CHAR_OPS[ch]
                if ch in OPEN_BRACKETS:
                    self.brackets.append((ch, self.line))
                elif ch in CLOSE_BRACKETS:
                    if not self.brackets or self.brackets[-1][0] != CLOSE_BRACKETS[ch]:
                        self.error(f"قوس إغلاق '{ch}' غير متوافق مع قوس الفتح")
                    self.brackets.pop()
                self.add(t, ch)
                self.pos += 1
                continue

            if IDENT_START_RE.match(ch):
                self._read_word()
                continue

            self.error(f"رمز غير معروف: '{ch}'")

        # نهاية الملف
        if self.brackets:
            ch, ln = self.brackets[-1]
            raise LexerError(f"قوس '{ch}' بقي مفتوحًا حتى نهاية الملف", ln)
        if self.tokens and self.tokens[-1].type not in (T.NEWLINE, T.INDENT, T.DEDENT):
            self._emit_newline()
        while len(self.indents) > 1:
            self.indents.pop()
            self.add(T.DEDENT, 0)
        self.add(T.EOF, None)
        return self.tokens

    # ---------- المسافات البادئة ----------

    def _handle_indentation(self):
        """يعالج بداية السطر: INDENT/DEDENT أو تخطي سطر فارغ.

        يعيد True إذا كان السطر فارغًا أو تعليقًا فقط (تم تخطيه).
        """
        width = 0
        i = self.pos
        n = len(self.src)
        while i < n:
            c = self.src[i]
            if c == ' ':
                width += 1
                i += 1
            elif c == '\t':
                width += 4 - (width % 4)
                i += 1
            else:
                break

        # سطر فارغ أو تعليق فقط — لا يؤثر على المسافات البادئة
        if i >= n or self.src[i] == '\n' or self.src[i] == '#':
            while i < n and self.src[i] != '\n':
                i += 1
            self.pos = i + 1        # تخطى السطر Including '\n'
            self.line += 1
            return True

        self.pos = i
        current = self.indents[-1]
        if width > current:
            self.indents.append(width)
            self.add(T.INDENT, width)
        elif width < current:
            while self.indents[-1] > width:
                self.indents.pop()
                self.add(T.DEDENT, width)
            if self.indents[-1] != width:
                if self.lenient_indent:
                    # الوضع المتساهل: إزاحة بين مستويين — تعامل ككتلة أعمق
                    self.indents.append(width)
                    self.add(T.INDENT, width)
                else:
                    self.error('مسافة بادئة غير متسقة — تحقق من محاذاة الأسطر')
        self.at_line_start = False
        return False

    def _emit_newline(self):
        if self.tokens and self.tokens[-1].type not in (T.NEWLINE, T.INDENT, T.DEDENT):
            self.add(T.NEWLINE, '\\n')

    # ---------- الأرقام ----------

    def _read_number(self):
        start = self.pos
        n = len(self.src)
        while self.pos < n and self.src[self.pos] in DIGIT_CHARS:
            self.pos += 1
        is_float = False

        # جزء عشري
        if (self.pos < n and self.src[self.pos] == '.'
                and self.pos + 1 < n and self.src[self.pos + 1] in DIGIT_CHARS):
            is_float = True
            self.pos += 1
            while self.pos < n and self.src[self.pos] in DIGIT_CHARS:
                self.pos += 1

        # الأس العلمي
        if self.pos < n and self.src[self.pos] in 'eE':
            j = self.pos + 1
            if j < n and self.src[j] in '+-':
                j += 1
            if j < n and self.src[j] in DIGIT_CHARS:
                is_float = True
                self.pos = j
                while self.pos < n and self.src[self.pos] in DIGIT_CHARS:
                    self.pos += 1

        text = self.src[start:self.pos].translate(AR2EN)
        if is_float:
            self.add(T.FLOAT, float(text))
        else:
            self.add(T.INT, int(text))

    # ---------- النصوص ----------

    def _read_escape(self, buf):
        """يعالج تسلسل الهروب بعد الرمز \\ ويسجل ناتجه في buf.

        يستدعى والـ self.pos يشير إلى رمز الهروب (بعد \\).
        """
        if self.pos >= len(self.src):
            self.error('نص غير مغلق')
        e = self.src[self.pos]
        if e == 'u':
            hex_part = self.src[self.pos + 1:self.pos + 5]
            if len(hex_part) != 4:
                self.error("رمز '\\u' يحتاج 4 أرقام سداسية عشرية")
            try:
                buf.append(chr(int(hex_part, 16)))
            except ValueError:
                self.error(f"رمز سداسي عشري غير صالح: '{hex_part}'")
            self.pos += 4
        elif e in ESCAPES:
            buf.append(ESCAPES[e])
        elif e in '"\'':
            buf.append(e)
        else:
            buf.append('\\' + e)
        self.pos += 1

    def _read_string(self, quote):
        start_line = self.line
        self.pos += 1
        buf = []
        n = len(self.src)

        # نص متعدد الأسطر: """...""" أو '''...'''
        triple = self.src[self.pos:self.pos + 2] == quote * 2
        if triple:
            self.pos += 2
            closer = quote * 3
            while True:
                if self.pos >= n:
                    self.error('نص غير مغلق — أنسيت ثلاث علامات اقتباس')
                c = self.src[self.pos]
                if self.src[self.pos:self.pos + 3] == closer:
                    self.pos += 3
                    break
                if c == '\n':
                    self.line += 1          # سطر حقيقي داخل النص — يحتسب للأخطاء اللاحقة
                if c == '\\':
                    self.pos += 1
                    if self.pos >= n:
                        self.error('نص غير مغلق')
                    self._read_escape(buf)
                    continue
                buf.append(c)
                self.pos += 1
            # رمز النص الممتد يحمل سطر بدايته (أسلم لرسائل الأخطاء والتنسيق)
            self.tokens.append(Token(T.STRING, ''.join(buf), start_line))
            return

        while True:
            if self.pos >= n:
                self.error('نص غير مغلق — أنسيت علامة الاقتباس')
            c = self.src[self.pos]
            if c == quote:
                self.pos += 1
                break
            if c == '\n':
                self.error('نص غير مغلق — النصوص لا تمتد على عدة أسطر')
            if c == '\\':
                self.pos += 1
                if self.pos >= n:
                    self.error('نص غير مغلق')
                self._read_escape(buf)
                continue
            buf.append(c)
            self.pos += 1
        self.add(T.STRING, ''.join(buf))

    def _read_fstring(self, quote):
        """يقرأ نصًا منسقًا: ق"..." — البادئة ق اختصار لـ«قالب».

        يدعم أيضًا النصوص المنسقة متعددة الأسطر: ق + ثلاث علامات اقتباس
        يبقى محتوى {تعبير} خامًا لمحلله لاحقًا، مع إدراك الأقواس
        ليسمح بعلامات اقتباس داخل التعبير: ق"طول الاسم {طول("أحمد")}"
        """
        start_line = self.line

        # ---- نص منسق متعدد الأسطر: ق"""...""" ----
        if self.src[self.pos + 1:self.pos + 3] == quote * 2:
            self.pos += 3
            closer = quote * 3
            buf = []
            n = len(self.src)
            depth = 0
            while True:
                if self.pos >= n:
                    self.error('نص منسق متعدد الأسطر غير مغلق — أنسيت ثلاث علامات اقتباس')
                c = self.src[self.pos]
                if depth == 0 and self.src[self.pos:self.pos + 3] == closer:
                    self.pos += 3
                    break
                if c == '\n':
                    self.line += 1
                if c == '\\':
                    self.pos += 1
                    if self.pos >= n:
                        self.error('نص منسق غير مغلق')
                    self._read_escape(buf)
                    continue
                if c in '([{':
                    depth += 1
                elif c in ')]}':
                    depth = max(0, depth - 1)
                buf.append(c)
                self.pos += 1
            self.tokens.append(Token(T.FSTRING, ''.join(buf), start_line))
            return

        # ---- نص منسق سطري: ق"..." ----
        self.pos += 1                     # تخطَّ علامة الاقتباس الافتتاحية
        buf = []
        n = len(self.src)
        depth = 0
        while True:
            if self.pos >= n:
                self.error('نص منسق غير مغلق — أنسيت علامة الاقتباس')
            c = self.src[self.pos]
            if c == quote and depth == 0:
                self.pos += 1
                break
            if c == '\n' and depth == 0:
                self.error('نص منسق غير مغلق — النصوص لا تمتد على عدة أسطر')
            if c == '\n':
                self.line += 1              # سطر داخل تعبير متعدد الأسطر
            if c == '\\':
                self.pos += 1
                if self.pos >= n:
                    self.error('نص منسق غير مغلق')
                self._read_escape(buf)
                continue
            if c in '([{':
                depth += 1
            elif c in ')]}':
                depth = max(0, depth - 1)
            buf.append(c)
            self.pos += 1
        self.tokens.append(Token(T.FSTRING, ''.join(buf), start_line))

    # ---------- الكلمات والمعرفات ----------

    def _read_word(self):
        m = IDENT_RE.match(self.src, self.pos)
        word = m.group(0)
        end = m.end()

        # كلمات مفتاحية مركبة
        if word == 'وإلا':
            m2 = ELIF_HINT.match(self.src, end)
            if m2:
                self.add(T.ELIF, 'وإلا إذا')
                self.pos = m2.end()
                return
        if word == 'ولا':
            m2 = NONE_HINT.match(self.src, end)
            if m2:
                self.add(T.NONE, 'ولا شيء')
                self.pos = m2.end()
                return

        self.pos = end

        # بادئة النص المنسق: ق متبوعة مباشرة بعلامة اقتباس
        if word == 'ق' and self.pos < len(self.src) and self.src[self.pos] in '"\'':
            self._read_fstring(self.src[self.pos])
            return

        kw = KEYWORDS.get(word)
        if kw is not None:
            self.add(kw, word)
        else:
            self.add(T.IDENT, word)
