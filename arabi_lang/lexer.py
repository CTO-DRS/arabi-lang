# -*- coding: utf-8 -*-
"""المحلل اللفظي (Lexer) — يحوّل نص البرنامج إلى سلسلة رموز.

يدعم:
- الأرقام العربية الشرقية (٠-٩) والغربية (0-9)
- الفاصلة العربية (،) والغربية (,)
- كلمات مفتاحية مركبة من كلمتين: «وإلا إذا» و«ولا شيء»
- كتل بمسافات بادئة مثل بايثون (INDENT / DEDENT)
- النصوص المنسقة: ق"مرحبا {الاسم}" — البادئة ق (قالب)
- السلاسل الخام: خ"..." — البادئة خ (خام) بلا معالجة رموز الهروب
- النصوص متعددة الأسطر: ثلاث علامات اقتباس مزدوجة أو مفردة
- كلمات الإصدار 1.5: تعداد، خاصية، عالمي، تحقق، احذف
- كلمات الإصدار 1.7: أنتج (المولدات) وعلامة @ (المزخرفات)
- كلمات الإصدار 1.9: طابق (مطابقة الأنماط) وغير ذلك
- كلمات الإصدار 1.24: كـ (فلتر/ربط باستثناء)، والمعامل ٪ (U+066A) و٪=
  والفاصلة العشرية ٫ وفاصل الآلاف ٬ داخل الأرقام، وسياسة محو التشكيل
  (يُقبل ولا يميز) وقبول الكشيدة في المعرفات مع إرشاد ذكي عند إخفائها
  كلمة مفتاحية (المواصفة docs/مواصفة-اللغة.md)
"""

import re
import unicodedata

from .tokens import T, Token, strip_tashkeel
from .errors import LexerError

# تحويل الأرقام العربية الشرقية والفارسية إلى الغربية
AR2EN = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹',
                      '01234567890123456789')

DIGIT_CHARS = set('0123456789٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹')

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
    'كـ': T.AS,
    'اخيرا': T.FINALLY,
    'ارفع': T.RAISE,
    'استورد': T.IMPORT,
    'تجاهل': T.PASS,
    'صنف': T.CLASS,
    'هذا': T.THIS,
    'الأصل': T.SUPER,
    'بدل': T.SWITCH,
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
    # كلمات الإصدار 1.9
    'طابق': T.MATCH,
}

# كلمات مفتاحية مركبة — تتسامح مع التشكيل في كلمتيها (قرار المواصفة ق٢:
# التشكيل يُقبل ولا يميز)، ولاحقة النفي تستثني التشكيل كذلك
_TK = '[\u064B-\u0655\u0670]*'               # صفر أو أكثر من علامات التشكيل
_NOT_WORD = '(?![\\w\u064B-\u0655\u0670])'    # نهاية الكلمة بحرفياها وتشكيلها
ELIF_HINT = re.compile('[ \\t]+إ' + _TK + 'ذ' + _TK + 'ا' + _TK + _NOT_WORD)
NONE_HINT = re.compile('[ \\t]+ش' + _TK + 'ي' + _TK + 'ء' + _TK + _NOT_WORD)
OTHERWISE_HINT = re.compile('[ \\t]+ذ' + _TK + 'ل' + _TK + 'ك' + _TK + _NOT_WORD)

# جدول محو التشكيل — يطبق على الكلمات (المعرفات والكلمات المفتاحية) فقط
# عند قراءتها، فلا وجود لمعرفين يختلفان بتشكيل ولا كلمة مفتاحية تتعطل
# بتشكيلها الطبيعي. السلاسل والتعليقات لا تُمس (محتوى نصي مشروع)
_ANY_TASHKEEL = re.compile('[\u064B-\u0655\u0670]')

# الكشيدة: جزء مشروع من المعرف — استعمالها راسخ في المجموعة (الرابط
# هـ، والكلمة المفتاحية كـ). الممنوع تضليلًا: معرف تكتبه بكشيدة فيصير
# بعد حذفها كلمة مفتاحية — يعترض اللفظي برسالة إرشادية (قرار المواصفة ق٣)
TATWEEL = '\u0640'

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
    '%=': T.PERCENT_ASSIGN,
    '٪=': T.PERCENT_ASSIGN,
    '=>': T.ARROW,
    '->': T.RARROW,           # نوع الإرجاع ASCII (نظام الأنواع 1.26)
}

ONE_CHAR_OPS = {
    '+': T.PLUS, '-': T.MINUS, '*': T.STAR, '/': T.SLASH, '%': T.PERCENT,
    '٪': T.PERCENT,          # باقي القسمة بالعلامة العربية (U+066A)
    '=': T.ASSIGN, '<': T.LT, '>': T.GT,
    '(': T.LPAREN, ')': T.RPAREN,
    '[': T.LBRACKET, ']': T.RBRACKET,
    '{': T.LBRACE, '}': T.RBRACE,
    ',': T.COMMA, ':': T.COLON, '.': T.DOT,
    '@': T.AT,
    '→': T.RARROW,           # نوع الإرجاع (U+2192 — نظام الأنواع 1.26)
}

OPEN_BRACKETS = {'(': ')', '[': ']', '{': '}'}
CLOSE_BRACKETS = {')': '(', ']': '[', '}': '{'}

ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '0': '\0', 'a': '\a', 'b': '\b', 'f': '\f'}

# محارف تُعامل فراغًا إضافة إلى المسافة والتبويب — أشهرها مسافة
# اللصق غير الفاصلة (NBSP) من Word والمتصفحات، وهذه كانت تسقط
# البرنامج برسالة غامضة في أهم سيناريو للمبتدئ (الإصدار 1.23)
EXTRA_SPACE = set('\u00A0\u000B\u000C')

# أسماء عربية للمحارف الخفية الشائعة — تظهر في رسائل «رمز غير معروف»
# مهربة (U+XXXX) بدل طباعتها كمصفة لا تُرى (الإصدار 1.23)
_HIDDEN_NAMES = {
    0x200B: 'مسافة عريضة صفرية', 0x200C: 'رابط غير فاصل',
    0x200D: 'رابط فاصل', 0x200E: 'علامة اتجاه يسار-يمين',
    0x200F: 'علامة اتجاه يمين-يسار', 0x202A: 'علامة تضمين اتجاه',
    0x202B: 'علامة تضمين اتجاه يمين-يسار', 0x202C: 'قافض اتجاه',
    0x202D: 'علامة تجاوز اتجاه', 0x202E: 'علامة تجاوز اتجاه يمين-يسار',
    0x00A0: 'مسافة غير فاصلة', 0x00AD: 'شرطة اختيارية',
    0xFEFF: 'علامة ترتيب البايتات (BOM)', 0x0000: 'محرف معدوم',
    0x0640: 'كشيدة',
    0x066B: 'الفاصلة العشرية العربية (جاءت خارج عدد؟)',
    0x066C: 'فاصل الآلاف العربي (جاء خارج عدد؟)',
}


def describe_char(ch):
    """وصف آمن لمحرف في رسالة خطأ: الخفية تُهرب بترميزها واسمها
    العربي إن عرفناه، والظاهرة تُعرض كما هي — فلا يعود BOM أو
    علامة اتجاه تظهر كمسافة أو مقتبسين فارغين."""
    code = ord(ch)
    label = _HIDDEN_NAMES.get(code)
    if label is None and (unicodedata.category(ch) in ('Cc', 'Cf')
                          or (ch.isspace() and ch != ' ')):
        label = 'محرف خفي'
    if label:
        return f'U+{code:04X} ({label})'
    return f"'{ch}'"


class Lexer:
    """يستقبل نص البرنامج المصدري وينتج قائمة من الرموز."""

    def __init__(self, source, lenient_indent=False):
        # تطبيع Unicode مرة واحدة عند الدخول (الإصدار 1.23): المعرف
        # المفكك (NFD) والمركب (NFC) يحملان الاسم نفسه، والكلمة
        # المفتاحية المفككة تعود كلمة مفتاحية — فلا تعدد صامت للأسماء
        src = unicodedata.normalize('NFC', source)
        # علامة ترتيب البايتات من محررات ويندوز تُزال (والقراءة من
        # الملفات بـ utf-8-sig تتكفل بها أولًا — هذه حماية أخيرة)
        if src.startswith('\ufeff'):
            src = src[1:]
        src = src.replace('\r\n', '\n').replace('\r', '\n')
        if not src.endswith('\n'):
            src += '\n'
        self.src = src
        self.pos = 0
        self.line = 1
        self.tokens = []
        self.indents = [0]
        self.brackets = []          # لتتبع الأقواس المفتوحة
        self.at_line_start = True
        # موضع بداية الرمز الجاري إصداره — يحسب منه العمود (1.23)
        self._tok_start = 0
        # الوضع المتساهل: يقبل إزاحات غير متسقة (لأدوات الفحص والتنسيق)
        self.lenient_indent = lenient_indent

    # ---------- أدوات مساعدة ----------

    def _col_at(self, pos):
        """عمود الموضع في سطره (يبدأ من ١، بالمحارف)."""
        return pos - self.src.rfind('\n', 0, pos)

    def error(self, message, pos=None):
        raise LexerError(message, self.line,
                         self._col_at(self.pos if pos is None else pos))

    def add(self, type_, value):
        self.tokens.append(Token(type_, value, self.line,
                                 self._col_at(self._tok_start)))

    # ---------- التحليل ----------

    def tokenize(self):
        while self.pos < len(self.src):
            if self.at_line_start and not self.brackets:
                if self._handle_indentation():
                    continue          # سطر فارغ أو تعليق فقط — تخطاه
            self._tok_start = self.pos
            ch = self.src[self.pos]

            if ch == '\n':
                if not self.brackets:
                    self._emit_newline()
                    self.at_line_start = True
                self.pos += 1
                self.line += 1
                continue

            if ch in ' \t' or ch in EXTRA_SPACE:
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
                    self.brackets.append((ch, self.line, self._col_at(self.pos)))
                elif ch in CLOSE_BRACKETS:
                    if not self.brackets or self.brackets[-1][0] != CLOSE_BRACKETS[ch]:
                        if self.brackets:
                            open_ch, open_line, open_col = self.brackets[-1]
                            self.error(
                                f"قوس إغلاق '{ch}' غير متوافق — القوس المفتوح "
                                f"الأقرب هو '{open_ch}' من السطر {open_line}، "
                                f'العمود {open_col}')
                        self.error(
                            f"قوس إغلاق '{ch}' بلا قوس فتح مطابق")
                    self.brackets.pop()
                self.add(t, ch)
                self.pos += 1
                continue

            if IDENT_START_RE.match(ch):
                self._read_word()
                continue

            self.error(f'رمز غير معروف: {describe_char(ch)}')

        # نهاية الملف
        if self.brackets:
            ch, ln, col = self.brackets[-1]
            raise LexerError(
                f"قوس '{ch}' بقي مفتوحًا حتى نهاية الملف", ln, col)
        self._tok_start = self.pos
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
        # الأعداد الصحيحة مع فاصل الآلاف العربي ٬ بين الأرقام — يُمحى
        # من القيمة (المواصفة ق٥)، ويُقبل فقط إذا تلاه رقم
        while self.pos < n:
            c = self.src[self.pos]
            if c in DIGIT_CHARS:
                self.pos += 1
            elif (c == '\u066C' and self.pos + 1 < n
                    and self.src[self.pos + 1] in DIGIT_CHARS):
                self.pos += 1              # فاصل آلاف يُمحى من القيمة
            else:
                break
        is_float = False

        # جزء عشري: النقطة أو الفاصلة العشرية العربية ٫ (U+066B)
        if (self.pos < n and self.src[self.pos] in '.\u066B'
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

        text = (self.src[start:self.pos].translate(AR2EN)
                .replace('\u066C', '').replace('\u066B', '.'))
        if is_float:
            self.add(T.FLOAT, float(text))
        else:
            self.add(T.INT, int(text))

    # ---------- النصوص ----------

    def _read_escape(self, buf):
        """يعالج تسلسل الهروب بعد الرمز \\ ويسجل ناتجه في buf.

        يستدعى والـ self.pos يشير إلى رمز الهروب (بعد \\).
        الهروب الذي يستهلك سطرًا جديدًا (\\ متبوعة بنهاية سطر داخل
        سلسلة) يرفع عداد الأسطر — وإلا انحرفت أرقام كل الأسطر
        التالية بواحد (إصلاح 1.23).
        """
        if self.pos >= len(self.src):
            self.error('نص غير مغلق')
        e = self.src[self.pos]
        if e == '\n':
            self.line += 1
        elif e == 'u':
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
                    self.error('نص غير مغلق — نسيت ثلاث علامات اقتباس')
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
            # رمز النص الممتد يحمل سطر وعمود بدايته (أسلم لرسائل الأخطاء)
            self.tokens.append(Token(T.STRING, ''.join(buf), start_line,
                                     self._col_at(self._tok_start)))
            return

        while True:
            if self.pos >= n:
                self.error('نص غير مغلق — نسيت علامة الاقتباس')
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

    def _read_rawstring(self, quote):
        """يقرأ سلسلة خام: خ"..." — لا معالجة لرموز الهروب إطلاقًا.

        الشرطة المائلة المعكوسة حرف عادي، وهذا مفيد لأنماط التعبيرات
        النمطية والمسارات. يدعم أيضًا الشكل الممتد بثلاث علامات اقتباس.
        """
        start_line = self.line
        self.pos += 1                     # تخطَّ علامة الاقتباس الافتتاحية
        n = len(self.src)

        # ---- سلسلة خام متعددة الأسطر: خ"""...""" ----
        if self.src[self.pos:self.pos + 2] == quote * 2:
            self.pos += 2
            closer = quote * 3
            end = self.src.find(closer, self.pos)
            if end == -1:
                self.error('سلسلة خام غير مغلقة — نسيت ثلاث علامات اقتباس')
            text = self.src[self.pos:end]
            self.line += text.count('\n')
            self.pos = end + 3
            self.tokens.append(Token(T.STRING, text, start_line,
                                     self._col_at(self._tok_start)))
            return

        # ---- سلسلة خام سطرية: خ"..." ----
        buf = []
        while True:
            if self.pos >= n:
                self.error('سلسلة خام غير مغلقة — نسيت علامة الاقتباس')
            c = self.src[self.pos]
            if c == quote:
                self.pos += 1
                break
            if c == '\n':
                self.error('سلسلة خام غير مغلقة — النصوص لا تمتد على عدة أسطر')
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
                    self.error('نص منسق متعدد الأسطر غير مغلق — نسيت ثلاث علامات اقتباس')
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
            self.tokens.append(Token(T.FSTRING, ''.join(buf), start_line,
                                     self._col_at(self._tok_start)))
            return

        # ---- نص منسق سطري: ق"..." ----
        self.pos += 1                     # تخطَّ علامة الاقتباس الافتتاحية
        buf = []
        n = len(self.src)
        depth = 0
        in_expr_str = None                # اقتباس سلسلة داخل التعبير (1.23)
        while True:
            if self.pos >= n:
                self.error('نص منسق غير مغلق — نسيت علامة الاقتباس')
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
            if depth > 0:
                # الاقتباسات داخل التعبير تُتتبَّع فلا تُحسب أقواس
                # تظهر داخل نص داخلي خطأً (إصلاح 1.23)
                if in_expr_str is not None:
                    if c == in_expr_str:
                        in_expr_str = None
                elif c in '"\'':
                    in_expr_str = c
                elif c in '([{':
                    depth += 1
                elif c in ')]}':
                    depth = max(0, depth - 1)
            elif c in '([{':
                depth += 1
            buf.append(c)
            self.pos += 1
        self.tokens.append(Token(T.FSTRING, ''.join(buf), start_line,
                                 self._col_at(self._tok_start)))

    # ---------- الكلمات والمعرفات ----------

    def _read_word(self):
        m = IDENT_RE.match(self.src, self.pos)
        # محو التشكيل من الكلمة قبل أي شيء (المواصفة ق٢): المطابقة
        # والإصدار على الشكل المجرّد — والمواضع تبقى على المصدر الخام
        word = m.group(0)
        # المحو عند الحاجة فقط — الأغلبية الساحقة بلا تشكيل، وفحص
        # regex السريع أرخص من الترجمة العمياء لكل كلمة
        if _ANY_TASHKEEL.search(word):
            word = strip_tashkeel(word)
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
        if word == 'غير':
            m2 = OTHERWISE_HINT.match(self.src, end)
            if m2:
                self.add(T.OTHERWISE, 'غير ذلك')
                self.pos = m2.end()
                return

        self.pos = end

        # بادئة النص المنسق: ق متبوعة مباشرة بعلامة اقتباس
        if word == 'ق' and self.pos < len(self.src) and self.src[self.pos] in '"\'':
            self._read_fstring(self.src[self.pos])
            return

        # بادئة السلسلة الخام: خ متبوعة مباشرة بعلامة اقتباس
        if word == 'خ' and self.pos < len(self.src) and self.src[self.pos] in '"\'':
            self._read_rawstring(self.src[self.pos])
            return

        kw = KEYWORDS.get(word)
        if kw is not None:
            self.add(kw, word)
        else:
            # إرشاد ذكي (ق٣): كشيدة زائدة تخفي كلمة مفتاحية (لوـ → لو)
            # — والكشيدة نفسها جزء مشروع من المعرف (هـ الرابط)
            bare = word.replace(TATWEEL, '')
            if bare != word and bare in KEYWORDS:
                self.error(
                    f"'{word}' ليس معرفًا — بعد حذف الكشيدة تصير الكلمة "
                    f"المفتاحية '{bare}'. إن أردت الكلمة المفتاحية فاكتب "
                    f"'{bare}' بلا كشيدة، وإن أردت معرفًا فاختر اسمًا آخر")
            self.add(T.IDENT, word)
