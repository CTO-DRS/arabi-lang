# -*- coding: utf-8 -*-
"""تعريف الرموز (Tokens) المستخدمة في لغة عربي."""

from enum import Enum, auto


class T(Enum):
    # ---- حرفية ----
    INT = auto()       # عدد صحيح
    FLOAT = auto()     # عدد عشري
    STRING = auto()    # نص
    IDENT = auto()     # معرف (اسم متغير/دالة)

    # ---- كلمات مفتاحية ----
    DEF = auto()       # دالة
    RETURN = auto()    # أعد
    IF = auto()        # لو
    ELIF = auto()      # وإلا إذا
    ELSE = auto()      # وإلا
    WHILE = auto()     # طالما
    FOR = auto()       # لكل
    IN = auto()        # في
    BREAK = auto()     # كسر
    CONTINUE = auto()  # استمر
    TRUE = auto()      # صح
    FALSE = auto()     # خطأ
    NONE = auto()      # ولا شيء
    AND = auto()       # و
    OR = auto()        # أو
    NOT = auto()       # ليس
    TRY = auto()       # جرب
    EXCEPT = auto()    # باستثناء
    AS = auto()        # كـ (تعليم فلتر باستثناء أو ربطه)
    FINALLY = auto()   # اخيرا
    RAISE = auto()     # ارفع
    IMPORT = auto()    # استورد
    PASS = auto()      # تجاهل
    CLASS = auto()     # صنف
    THIS = auto()      # هذا
    SUPER = auto()     # الأصل
    ARROW = auto()     # => (الدوال السهمية)
    RARROW = auto()    # → أو -> (نوع الإرجاع — نظام الأنواع 1.26)
    SWITCH = auto()    # بدّل
    CASE = auto()      # حالة
    DEFAULT = auto()   # افتراض
    FSTRING = auto()   # ق"نص منسق {تعبير}"

    # ---- كلمات الإصدار 1.5 ----
    ENUM = auto()      # تعداد
    PROPERTY = auto()  # خاصية (محسوبة)
    GLOBAL = auto()    # عالمي
    ASSERT = auto()    # تحقق
    DELETE = auto()    # احذف

    # ---- كلمات الإصدار 1.7 ----
    YIELD = auto()     # أنتج (المولدات)

    # ---- كلمات الإصدار 1.8 ----
    INTERFACE = auto()  # واجهة (عقد مجرد تلتزم به الأصناف)

    # ---- كلمات الإصدار 1.9 ----
    MATCH = auto()      # طابق (مطابقة الأنماط)
    OTHERWISE = auto()  # غير ذلك (الفرع الافتراضي في المطابقة)

    # ---- معاملات ----
    PLUS = auto()          # +
    MINUS = auto()         # -
    STAR = auto()          # *
    SLASH = auto()         # /
    PERCENT = auto()       # % أو ٪ (U+066A)
    POWER = auto()         # **
    ASSIGN = auto()        # =
    PLUS_ASSIGN = auto()   # +=
    MINUS_ASSIGN = auto()  # -=
    STAR_ASSIGN = auto()   # *=
    SLASH_ASSIGN = auto()  # /=
    PERCENT_ASSIGN = auto()  # %= أو ٪=
    EQ = auto()            # ==
    NEQ = auto()           # !=
    LT = auto()            # <
    GT = auto()            # >
    LTE = auto()           # <=
    GTE = auto()           # >=
    LPAREN = auto()        # (
    RPAREN = auto()        # )
    LBRACKET = auto()      # [
    RBRACKET = auto()      # ]
    LBRACE = auto()        # {
    RBRACE = auto()        # }
    COMMA = auto()         # , أو ،
    COLON = auto()         # :
    DOT = auto()           # .
    ELLIPSIS = auto()      # ... (معامل متغير أو تفكيك)
    AT = auto()            # @

    # ---- بنيوية ----
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()


# محو التشكيل — المصدر الواحد الذي تلتزم به كل الطبقات (المواصفة ق٢):
# المعرفات والكلمات المفتاحية والجداول المسجلة كلها على الشكل المجرّد
STRIP_TASHKEEL = str.maketrans('', '', ''.join(chr(c) for c in
                             range(0x064B, 0x0656)) + '\u0670')


def strip_tashkeel(name):
    """يمحو التشكيل من اسم — محايد للأسماء المجرّدة أصلاً."""
    return name.translate(STRIP_TASHKEEL)


class Token:
    """رمز واحد من مخرجات المحلل اللفظي.

    line رقم السطر (يبدأ من ١) وcol موقع المحرف الأول في السطر
    (يبدأ من ١، ومحسوب بالمحارف لا الأعمدة البصرية) — العمود
    يخدم رسائل الخطأ الدقيقة وعلامة التشير تحت الرمز المذنب.
    """

    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, type_, value, line, col=0):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self):
        return (f'Token({self.type.name}, {self.value!r}, '
                f'line={self.line}, col={self.col})')
