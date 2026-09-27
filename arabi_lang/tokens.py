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
    FINALLY = auto()   # اخيرا
    RAISE = auto()     # ارفع
    IMPORT = auto()    # استورد
    PASS = auto()      # تجاهل
    CLASS = auto()     # صنف
    THIS = auto()      # هذا
    SUPER = auto()     # الأصل
    ARROW = auto()     # => (الدوال السهمية)
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
    PERCENT = auto()       # %
    POWER = auto()         # **
    ASSIGN = auto()        # =
    PLUS_ASSIGN = auto()   # +=
    MINUS_ASSIGN = auto()  # -=
    STAR_ASSIGN = auto()   # *=
    SLASH_ASSIGN = auto()  # /=
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


class Token:
    """رمز واحد من مخرجات المحلل اللفظي."""

    __slots__ = ('type', 'value', 'line')

    def __init__(self, type_, value, line):
        self.type = type_
        self.value = value
        self.line = line

    def __repr__(self):
        return f'Token({self.type.name}, {self.value!r}, line={self.line})'
