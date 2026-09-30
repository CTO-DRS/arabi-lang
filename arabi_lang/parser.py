# -*- coding: utf-8 -*-
"""المحلل النحوي (Parser) — يحوّل رموز المحلل اللفظي إلى شجرة صياغة AST.

محلل تنازلي تعاودي (Recursive Descent) بأولويات:
  أو < و < ليس < مقارنة < +/- < */٪ < سالب < ** < استدعاء/فهرسة/خاصية
"""

from .tokens import T, strip_tashkeel
from .nodes import (
    Program, ExprStmt, Assign, AugAssign, If, While, For, FuncDef, Return,
    TypeSpec,
    Break, Continue, Pass, Try, Raise, Import, ClassDef, InterfaceDef,
    Lambda, Switch, EnumDef, PropertyDef, Global, Assert, Delete, Yield,
    Match, PLiteral, PCapture, POr, PList, PDict,
    Num, Str, FString, Bool, Null, Name, ListLit, DictLit, ListComp, DictComp,
    BinOp, UnaryOp, Call, Index, Slice, MethodCall, Attribute, This, Super,
    Ternary, SpreadArg, Await,
)
from .errors import ParseError

CMP_OPS = {
    T.EQ: '==', T.NEQ: '!=', T.LT: '<', T.GT: '>',
    T.LTE: '<=', T.GTE: '>=', T.IN: 'في',
}

AUG_OPS = {
    T.PLUS_ASSIGN: '+', T.MINUS_ASSIGN: '-',
    T.STAR_ASSIGN: '*', T.SLASH_ASSIGN: '/',
    T.PERCENT_ASSIGN: '%',   # %= و ٪= (المرحلة 2 — ق١)
}

TOKEN_DESC = {
    T.NEWLINE: 'نهاية السطر',
    T.INDENT: 'مسافة بادئة',
    T.DEDENT: 'نهاية الكتلة',
    T.EOF: 'نهاية الملف',
    T.ARROW: "'=>'",
    T.RARROW: "'→'",
}

STMT_KEYWORDS = {
    T.DEF: 'دالة', T.RETURN: 'أعد', T.IF: 'لو', T.ELIF: 'وإلا إذا',
    T.ELSE: 'وإلا', T.WHILE: 'طالما', T.FOR: 'لكل', T.IN: 'في',
    T.BREAK: 'كسر', T.CONTINUE: 'استمر', T.TRUE: 'صح', T.FALSE: 'خطأ',
    T.NONE: 'ولا شيء', T.AND: 'و', T.OR: 'أو', T.NOT: 'ليس',
    T.TRY: 'جرب', T.EXCEPT: 'باستثناء', T.FINALLY: 'اخيرا',
    T.RAISE: 'ارفع', T.IMPORT: 'استورد', T.PASS: 'تجاهل',
    T.CLASS: 'صنف', T.THIS: 'هذا', T.SUPER: 'الأصل',
    T.SWITCH: 'بدل', T.CASE: 'حالة', T.DEFAULT: 'افتراض',
    T.ENUM: 'تعداد', T.PROPERTY: 'خاصية', T.GLOBAL: 'عالمي',
    T.ASSERT: 'تحقق', T.DELETE: 'احذف',
    T.YIELD: 'أنتج', T.INTERFACE: 'واجهة',
    T.MATCH: 'طابق', T.OTHERWISE: 'غير ذلك',
}

# كلمات مفتاحية يُسمح بظهورها كأسماء خصائص/طرق بعد النقطة
# (مثل ق["م"].احذف("مفتاح")) لعدم كسر طرق الأنواع المدمجة
KEYWORD_AS_NAME = {T.ENUM, T.PROPERTY, T.GLOBAL, T.ASSERT, T.DELETE}

# "انتظر" كلمة سياقية (الإصدار 1.15): تُعد تعبير انتظار إذا جاء بعدها
# رمز يمكن أن يبدأ تعبيرًا، وإلا تُعامل كاسم عادي — فلا تُكسر طرق مثل
# خيط.انتظر() وخادم.انتظر() ولا أي معرف يحمل الاسم نفسه.
_AWAIT_START = frozenset({
    T.INT, T.FLOAT, T.STRING, T.FSTRING, T.TRUE, T.FALSE, T.NONE,
    T.THIS, T.SUPER, T.IF, T.IDENT, T.DEF, T.LPAREN, T.LBRACKET,
    T.LBRACE, T.MINUS, T.NOT,
})


def tok_desc(tok):
    if tok.type in TOKEN_DESC:
        return TOKEN_DESC[tok.type]
    if tok.type is T.STRING:
        return f'نص "{tok.value}"'
    if tok.type is T.FSTRING:
        return f'نص منسق ق"{tok.value}"'
    if tok.type is T.IDENT:
        return f"الاسم '{tok.value}'"
    if tok.type in STMT_KEYWORDS:
        return f"'{tok.value}'"
    return f"'{tok.value}'"


def _name_from_path(path, tok):
    """يستخرج اسم الربط من مسار ملف: 'مكتبة/هندسة.عربي' → 'هندسة'."""
    base = path.replace('\\', '/').rstrip('/').split('/')[-1]
    if base.endswith('.عربي'):
        base = base[:-len('.عربي')]
    if not base:
        raise ParseError(
            f"لا يمكن استنتاج اسم الوحدة من المسار '{path}'", tok.line, tok.col)
    return base


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0
        # كومة تتبع المولدات: صحيح إذا جسم الدالة الحالي يحوي 'أنتج'
        self._yield_scopes = []

    # ---------- أدوات ----------

    def cur(self):
        return self.toks[self.i]

    def advance(self):
        tok = self.toks[self.i]
        if self.i < len(self.toks) - 1:
            self.i += 1
        return tok

    def peek(self, k=0):
        j = min(self.i + k, len(self.toks) - 1)
        return self.toks[j]

    def check(self, type_):
        return self.cur().type is type_

    def match(self, type_):
        if self.check(type_):
            return self.advance()
        return None

    def expect(self, type_, message):
        if self.check(type_):
            return self.advance()
        self.error(message)

    def error(self, message):
        tok = self.cur()
        raise ParseError(f'{message} — لكن وجدت {tok_desc(tok)}',
                         tok.line, tok.col)

    def skip_newlines(self):
        while self.check(T.NEWLINE):
            self.advance()

    # ---------- نقطة الدخول ----------

    def parse(self):
        # حارس التعاود (1.23): التعشيش العميق جدًا (~ألفا قوس متداخل)
        # كان يفجّر RecursionError بايثونية خامًا تصل الطرفية إنجليزية
        # — الآن تُحوّل لخطأ نحوي عربي واضح في موضعها
        try:
            return self._parse()
        except RecursionError:
            tok = self.cur()
            raise ParseError(
                'التعشيش عميق جدًا — بسّط التعبير أو قسّمه على أسطر '
                'ومتغيرات أصغر', tok.line, tok.col)

    def _parse(self):
        statements = []
        self.skip_newlines()
        while not self.check(T.EOF):
            statements.append(self.statement())
            self.skip_newlines()
        return Program(statements, 1)   # كل العقد تحمل سطرها — وحتى الجذر

    # ---------- الجمل ----------

    def statement(self):
        stmt = self._statement()
        t = self.cur().type
        if t in (T.NEWLINE, T.EOF, T.DEDENT):
            return stmt
        # الجمل التي تنتهي بكتلة (لو/طالما/لكل/دالة/جرب/صنف/بدّل/طابق) تستهلك DEDENT
        # داخل block()، لذا الجملة التالية تبدأ مباشرة
        if isinstance(stmt, (If, While, For, FuncDef, Try, ClassDef,
                             Switch, PropertyDef, EnumDef, InterfaceDef,
                             Match)):
            return stmt
        self.error('متوقع نهاية السطر بعد الجملة')

    def _statement(self):
        t = self.cur().type
        if t is T.AT:
            return self.decorated_def()
        if t is T.DEF:
            return self.func_def()
        if t is T.IF:
            return self.if_stmt()
        if t is T.WHILE:
            return self.while_stmt()
        if t is T.FOR:
            return self.for_stmt()
        if t is T.RETURN:
            return self.return_stmt()
        if t is T.BREAK:
            tok = self.advance()
            return Break(tok.line)
        if t is T.CONTINUE:
            tok = self.advance()
            return Continue(tok.line)
        if t is T.PASS:
            tok = self.advance()
            return Pass(tok.line)
        if t is T.TRY:
            return self.try_stmt()
        if t is T.RAISE:
            return self.raise_stmt()
        if t is T.IMPORT:
            return self.import_stmt()
        if t is T.CLASS:
            return self.class_def()
        if t is T.INTERFACE:
            return self.interface_def()
        if t is T.SWITCH:
            return self.switch_stmt()
        if t is T.MATCH:
            return self.match_stmt()
        if t is T.ENUM:
            return self.enum_stmt()
        if t is T.PROPERTY:
            return self.property_def()
        if t is T.GLOBAL:
            return self.global_stmt()
        if t is T.ASSERT:
            return self.assert_stmt()
        if t is T.DELETE:
            return self.delete_stmt()
        if t is T.YIELD:
            return self.yield_stmt()
        # «من وحدة استورد ...» — 'من' كلمة سياقية في بداية الجملة
        if (t is T.IDENT and self.cur().value == 'من'
                and self.peek(1).type in (T.IDENT, T.STRING)):
            return self.import_stmt()
        # «غير متزامنة دالة ...» — كلمتان سياقيتان في بداية الجملة (1.15)
        if (t is T.IDENT and self.cur().value == 'غير'
                and self.peek(1).type is T.IDENT
                and self.peek(1).value in ('متزامنة', 'متزامن')
                and self.peek(2).type is T.DEF):
            return self.func_def()
        return self.expr_stmt()

    def block(self):
        self.expect(T.COLON, "متوقع ':' في نهاية السطر")
        if self.check(T.ASSIGN):
            self.error("متوقع ':' — هل تقصد '==' للمقارنة؟")
        self.expect(T.NEWLINE, "متوقع سطرًا جديدًا بعد ':'")
        if not self.check(T.INDENT):
            self.error("متوقع كتلة بمسافة بادئة بعد ':'")
        self.advance()
        statements = []
        while True:
            if self.check(T.EOF):
                self.error("كتلة غير مغلقة — انتهى الملف قبل نهاية الكتلة")
            if self.check(T.DEDENT):
                self.advance()
                break
            statements.append(self.statement())
            self.skip_newlines()
        return statements

    def func_def(self):
        """تعريف دالة: دالة اسم(...) — أو 'غير متزامنة دالة اسم(...)' (1.15).

        يُستدعى من موضعين: الرمز الحالي 'دالة'، أو بداية الجملة 'غير'
        (الكلمتان السياقيتان غير + متزامنة/متزامن قبل 'دالة').
        """
        tok = self.cur()
        # "دالة غير متزامنة" — كلمتان سياقيتان بعد 'دالة' (الإصدار 1.15):
        # الدالة تعمل في خيط مستقل عند استدعائها ويعيد استدعاؤها مهمة.
        is_async = False
        if (self.check(T.IDENT) and self.cur().value == 'غير'
                and self.peek(1).type is T.IDENT
                and self.peek(1).value in ('متزامنة', 'متزامن')
                and self.peek(2).type is T.DEF):
            self.advance()                         # غير
            self.advance()                         # متزامنة
            is_async = True
        self.expect(T.DEF, "متوقع كلمة 'دالة'")
        name = self.expect_ident("متوقع اسم الدالة بعد 'دالة'"
                                 + (" (بعد 'غير متزامنة')" if is_async else ''))
        params, rest, anns = self.parse_params()
        ret = None
        if self.match(T.RARROW):               # نوع الإرجاع (1.26)
            ret = self.parse_type()
        self._yield_scopes.append(False)
        try:
            body = self.block()
        finally:
            is_generator = self._yield_scopes.pop()
        if is_async and is_generator:
            raise ParseError(
                f"الدالة '{name}' لا يمكن أن تكون غير متزامنة ومولدة معًا "
                "— لا تدمج 'أنتج' مع 'غير متزامنة'", tok.line, tok.col)
        if is_generator and ret is not None:
            raise ParseError(
                f"المولد '{name}' لا يقبل نوع إرجاع بعد '→' — "
                "الاستدعاء يعيد مولدًا وقيمه تُنتج بـ'أنتج' "
                'داخل الجسم (نظام الأنواع 1.26)', tok.line, tok.col)
        return FuncDef(name, params, body, tok.line,
                       is_generator=is_generator, rest=rest,
                       is_async=is_async, anns=anns, ret=ret)

    def decorated_def(self):
        """مزخرفات فوق الدالة:
        @اسم
        @اسم(وسيط)
        دالة ..."""
        tok = self.advance()                       # @
        decorators = [self.expression()]
        self.skip_newlines()
        while self.check(T.AT):
            self.advance()
            decorators.append(self.expression())
            self.skip_newlines()
        # يقبل 'دالة' و'غير متزامنة دالة' على السواء (المواصفة ق٩):
        # المفسر يطبق المزخرف على قيمة الدالة غير المتزامنة كما هي
        is_async_head = (self.check(T.IDENT)
                         and self.cur().value == 'غير'
                         and self.peek(1).type is T.IDENT
                         and self.peek(1).value in ('متزامنة', 'متزامن')
                         and self.peek(2).type is T.DEF)
        if not (self.check(T.DEF) or is_async_head):
            self.error("المزخرف @ يجب أن يسبق تعريف دالة 'دالة' أو "
                       "'غير متزامنة دالة' مباشرة")
        func = self.func_def()
        func.decorators = decorators
        func.line = tok.line
        return func

    def yield_stmt(self):
        """أنتج [تعبير] — يُنتج قيمة من المولد."""
        tok = self.advance()                       # أنتج
        if self.cur().type in (T.NEWLINE, T.EOF, T.DEDENT):
            if self._yield_scopes:
                self._yield_scopes[-1] = True
            return Yield(None, tok.line)
        if self._yield_scopes:
            self._yield_scopes[-1] = True
        return Yield(self.expression(), tok.line)

    def parse_params(self):
        """يقرأ المعاملات مع التوصيف والافتراضيات والمتغير:
        (أ، ب: عدد = ٥، ...البقية)

        يعيد (قائمة المعاملات، اسم المعامل المتغير أو None،
        التوصيفات {الاسم: TypeSpec}) — نظام الأنواع 1.26.
        """
        self.expect(T.LPAREN, "متوقع '(' لفتح قائمة المعاملات")
        params = []
        rest = None
        anns = {}
        if not self.check(T.RPAREN):
            if self.check(T.ELLIPSIS):             # البدء مباشرة بـ ...الاسم
                self.advance()
                rest = self.expect_ident(
                    "متوقع اسم المعامل المتغير بعد '...'")
                if self.match(T.COLON):            # توصيف المتغير (1.26)
                    anns[rest] = self.parse_type()
                if self.match(T.COMMA) and not self.check(T.RPAREN):
                    self.error("المعامل المتغير '...' يجب أن يكون الأخير")
            else:
                self._append_param(params, anns)
                while self.match(T.COMMA):
                    if self.check(T.RPAREN):           # فاصلة أخيرة مسموحة
                        break
                    if self.check(T.ELLIPSIS):
                        if rest is not None:
                            self.error('تكرار المعامل المتغير — يُسمح بـ ... مرة واحدة')
                        self.advance()
                        rest = self.expect_ident(
                            "متوقع اسم المعامل المتغير بعد '...'")
                        if self.match(T.COLON):    # توصيف المتغير (1.26)
                            anns[rest] = self.parse_type()
                        if self.match(T.COMMA) and not self.check(T.RPAREN):
                            self.error(
                                "المعامل المتغير '...' يجب أن يكون الأخير")
                        continue
                    self._append_param(params, anns)
        self.expect(T.RPAREN, "متوقع ')' لإغلاق قائمة المعاملات")
        if rest is not None and any(p[0] == rest for p in params):
            self.error(
                f"اسم المعامل المتغير '{rest}' مكرر مع معامل عادي")
        return params, rest, anns

    def parse_param(self):
        """معامل واحد: اسم [: نوع] [= قيمة افتراضية] (1.26)"""
        name = self.expect_ident('متوقع اسم معامل')
        spec = None
        if self.match(T.COLON):                    # توصيف النوع (1.26)
            spec = self.parse_type()
        default = None
        if self.match(T.ASSIGN):
            default = self.expression()
        return (name, default, spec)

    def _append_param(self, params, anns):
        """يقرأ معاملًا ويضيفه لقائمة المعاملات وتوصيفه لقاموس التوصيفات."""
        p = self.parse_param()
        params.append(p)
        if p[2] is not None:
            anns[p[0]] = p[2]

    def parse_type(self, inside_generic=False):
        """نوع في موضع توصيف (نظام الأنواع 1.26):

        نوع      ← 'ولا شيء' | 'دالة' | اسم ('[' نوع (':' نوع)? ']')?
        التعمية لقائمة/قاموس فقط وبمستوى واحد — والباقي خطأ نحوي إرشادي.
        """
        tok = self.cur()
        if self.match(T.NONE):
            return TypeSpec('ولا شيء', tok.line)
        if self.match(T.DEF):                      # 'دالة' سياقيًا (ق١٣)
            return TypeSpec('دالة', tok.line)
        name = self.expect_ident(
            'متوقع نوعًا (عائلة مدمجة أو صنفًا)')
        stripped = strip_tashkeel(name)
        element = key = value = None
        if self.check(T.LBRACKET):
            if stripped not in ('قائمة', 'قاموس'):
                self.error(
                    f"التعمية على '{name}' غير مدعومة — فقط 'قائمة' "
                    "و'قاموس' تقبلان أقواس التعمية")
            if inside_generic:
                self.error(
                    f"التعمية المتداخلة غير مدعومة — لا يوضع نوع معيّم "
                    f"داخل '{name}[...]'")
            self.advance()
            if stripped == 'قائمة':
                element = self.parse_type(inside_generic=True)
            else:
                key = self.parse_type(inside_generic=True)
                self.expect(
                    T.COLON,
                    "متوقع ':' بين نوع المفتاح ونوع القيمة في قاموس[...]")
                value = self.parse_type(inside_generic=True)
            self.expect(T.RBRACKET, "متوقع ']' لإغلاق التعمية")
        return TypeSpec(name, tok.line,
                        element=element, key=key, value=value)

    def if_stmt(self):
        tok = self.advance()                       # لو
        test = self.expression()
        body = self.block()
        elifs = []
        orelse = None
        while self.check(T.ELIF):
            self.advance()
            c = self.expression()
            b = self.block()
            elifs.append((c, b))
        if self.check(T.ELSE):
            self.advance()
            orelse = self.block()
        return If(test, body, elifs, orelse, tok.line)

    def while_stmt(self):
        tok = self.advance()                       # طالما
        test = self.expression()
        body = self.block()
        return While(test, body, tok.line)

    def for_stmt(self):
        tok = self.advance()                       # لكل
        targets = [self.expect_ident("متوقع اسم متغير الحلقة بعد 'لكل'")]
        while self.match(T.COMMA):
            targets.append(self.expect_ident('متوقع اسم متغير'))
        self.expect(T.IN, "متوقع الكلمة المفتاحية 'في' في حلقة 'لكل'")
        iterable = self.expression()
        body = self.block()
        return For(targets, iterable, body, tok.line)

    def return_stmt(self):
        tok = self.advance()                       # أعد
        if self.cur().type in (T.NEWLINE, T.EOF, T.DEDENT):
            return Return(None, tok.line)
        return Return(self.expression(), tok.line)

    def try_stmt(self):
        """جرب مع كتل باستثناء متعددة — التقاط بالصنف (المواصفة ق٦):

        جرب: ... باستثناء صنف_أ كـ هـ: ... باستثناء كـ هـ: ... اخيرا: ...
        الصيغ التاريخية (باستثناء: وباستثناء هـ:) متوافقة كاملة.
        """
        tok = self.advance()                       # جرب
        body = self.block()
        clauses = []
        finally_body = None
        while self.check(T.EXCEPT):
            self.advance()
            filter_expr = None
            binding = None
            if self.check(T.AS):
                self.advance()                     # كـ — عام مع ربط اختياري
                if self.check(T.IDENT):
                    binding = self.advance().value
            elif self.check(T.IDENT):
                if self.peek(1).type is T.AS:
                    filter_expr = self._class_filter()
                    self.advance()                 # كـ — فلتر مع ربط اختياري
                    if self.check(T.IDENT):
                        binding = self.advance().value
                else:
                    # الصيغة التاريخية: باستثناء هـ: — ربط عام
                    binding = self.advance().value
            clauses.append((filter_expr, binding, self.block()))
        if self.check(T.FINALLY):
            self.advance()
            finally_body = self.block()
        if not clauses and finally_body is None:
            self.error("'جرب' يتطلب 'باستثناء' أو 'اخيرا' بعده")
        return Try(body, clauses, finally_body, tok.line)

    def _class_filter(self):
        """مسار صنف الفلتر بعد 'باستثناء': اسم أو اسم.اسم... —
        يُقيَّم وقت الالتقاط ويجب أن يعطي صنفًا (المواصفة ق٦)."""
        tok = self.advance()
        e = Name(tok.value, tok.line)
        while self.check(T.DOT):
            self.advance()
            name_tok = self.cur()
            if (name_tok.type is not T.IDENT
                    and name_tok.type not in KEYWORD_AS_NAME):
                self.error("متوقع اسمًا بعد '.' في فلتر 'باستثناء'")
            self.advance()
            e = Attribute(e, name_tok.value, tok.line)
        return e

    def raise_stmt(self):
        tok = self.advance()                       # ارفع
        if self.cur().type in (T.NEWLINE, T.EOF, T.DEDENT):
            self.error("متوقع رسالة الخطأ بعد 'ارفع'")
        return Raise(self.expression(), tok.line)

    def import_stmt(self):
        """صيغ الاستيراد الثلاث:
        استورد وحدة
        استورد "مسار/ملف.عربي"
        من وحدة استورد اسم، اسم
        """
        # صيغة «من ... استورد ...» — 'من' كلمة سياقية
        if self.check(T.IDENT) and self.cur().value == 'من':
            tok = self.advance()                   # من
            if self.check(T.STRING):
                module = None
                path = self.advance().value
                bound = _name_from_path(path, tok)
            else:
                module = self.expect_ident("متوقع اسم الوحدة بعد 'من'")
                path = None
                bound = module
            self.expect(T.IMPORT, "متوقع الكلمة 'استورد' في صيغة 'من ... استورد ...'")
            names = [self.expect_ident('متوقع اسمًا للاستيراد بعد استورد')]
            while self.match(T.COMMA):
                if self.check(T.NEWLINE) or self.check(T.EOF):
                    break
                names.append(self.expect_ident('متوقع اسمًا للاستيراد'))
            return Import(module, path, names, bound, tok.line)

        tok = self.advance()                       # استورد
        if self.check(T.STRING):
            path = self.advance().value
            return Import(None, path, None, _name_from_path(path, tok), tok.line)
        name = self.expect_ident("متوقع اسم الوحدة بعد 'استورد'")
        return Import(name, None, None, name, tok.line)

    def class_def(self):
        tok = self.advance()                       # صنف
        name = self.expect_ident("متوقع اسم الصنف بعد 'صنف'")
        superclass = None
        # الوراثة: صنف ابن من أصل — 'من' كلمة سياقية، والوراثة المتعددة بفواصل
        if self.check(T.IDENT) and self.cur().value == 'من':
            self.advance()
            superclass = self.expect_ident("متوقع اسم الصنف الأصل بعد 'من'")
            if self.match(T.COMMA):
                superclass = [superclass]
                superclass.append(self.expect_ident('متوقع اسم صنف الأصل الثاني'))
                while self.match(T.COMMA):
                    superclass.append(self.expect_ident('متوقع اسم صنف أصل'))
        body = self.block()
        return ClassDef(name, superclass, body, tok.line)

    def interface_def(self):
        """واجهة الاسم [من أصل] — عقد مجرد تلتزم به الأصناف.

        طرق بلا جسم = مجردة (يجب تنفيذها)، بجسم = تنفيذ افتراضي يورث.
        """
        tok = self.advance()                       # واجهة
        name = self.expect_ident("متوقع اسم الواجهة بعد 'واجهة'")
        superclass = None
        if self.check(T.IDENT) and self.cur().value == 'من':
            self.advance()
            superclass = self.expect_ident(
                "متوقع اسم الواجهة الأصل بعد 'من'")
            if self.match(T.COMMA):
                superclass = [superclass]
                superclass.append(
                    self.expect_ident('متوقع اسم واجهة الأصل الثاني'))
                while self.match(T.COMMA):
                    superclass.append(
                        self.expect_ident('متوقع اسم واجهة أصل'))
        body, abstract = self._interface_block(name)
        return InterfaceDef(name, superclass, body, abstract, tok.line)

    def _interface_block(self, name):
        """كتلة الواجهة: طرق (بجسم أو بلا جسم) وثوابت وتجاهل فقط."""
        self.expect(T.COLON, "متوقع ':' في نهاية السطر")
        if self.check(T.ASSIGN):
            self.error("متوقع ':' — هل تقصد '==' للمقارنة؟")
        self.expect(T.NEWLINE, "متوقع سطرًا جديدًا بعد ':'")
        if not self.check(T.INDENT):
            self.error("متوقع كتلة بمسافة بادئة بعد ':'")
        self.advance()
        body = []
        abstract = []
        while True:
            if self.check(T.EOF):
                self.error("كتلة غير مغلقة — انتهى الملف قبل نهاية الكتلة")
            if self.check(T.DEDENT):
                self.advance()
                break
            if self.check(T.DEF):
                fn = self._interface_method()
                if fn.body is None:
                    abstract.append(fn.name)
                body.append(fn)
            elif self.check(T.PASS):
                p = self.advance()
                body.append(Pass(p.line))
            else:
                stmt = self.expr_stmt()            # ثابت: الاسم = قيمة
                body.append(stmt)
            self.skip_newlines()
        if not body:
            self.error(
                f"الواجهة '{name}' فارغة — أضف طريقة مجردة أو "
                'تنفيذًا افتراضيًا أو ثابتًا')
        return body, abstract

    def _interface_method(self):
        """طريقة داخل واجهة: بجسم (تنفيذ افتراضي) أو بلا جسم (مجردة)."""
        tok = self.advance()                       # دالة
        name = self.expect_ident("متوقع اسم الطريقة بعد 'دالة'")
        params, rest, anns = self.parse_params()
        ret = None
        if self.match(T.RARROW):                   # توثيق النوع في الواجهة (1.26)
            ret = self.parse_type()
        if self.check(T.NEWLINE) or self.check(T.EOF) or self.check(T.DEDENT):
            if self.check(T.NEWLINE):              # نهاية سطر الطريقة المجردة
                self.advance()
            return FuncDef(name, params, None, tok.line, rest=rest,
                           anns=anns, ret=ret)
        body = self.block()
        return FuncDef(name, params, body, tok.line, rest=rest,
                       anns=anns, ret=ret)

    def switch_stmt(self):
        """بدّل التعبير — كتل حالة على أسطر تالية بنفس مستوى 'بدل':

        بدّل يوم
        حالة "السبت":
            ...
        افتراض:
            ...
        """
        tok = self.advance()                       # بدّل
        subject = self.expression()
        self.expect(T.NEWLINE,
                    "متوقع سطرًا جديدًا بعد تعبير 'بدل'")
        cases = []
        default_body = None
        while self.check(T.CASE):
            self.advance()
            value = self.expression()
            body = self.block()
            cases.append((value, body))
        if self.check(T.DEFAULT):
            self.advance()
            default_body = self.block()
        if not cases and default_body is None:
            self.error("'بدل' يحتاج 'حالة' واحدة على الأقل أو 'افتراض'")
        return Switch(subject, cases, default_body, tok.line)

    # ---------- مطابقة الأنماط (الإصدار 1.9) ----------

    def match_stmt(self):
        """طابق تعبير — كتل حالة بنفس مستوى 'طابق' وربما فرع غير ذلك:

        طابق قيمة
        حالة ١ أو ٢:
            ...
        حالة [أ، ...الباقي] إن أ > ٠:
            ...
        غير ذلك:
            ...
        """
        tok = self.advance()                       # طابق
        subject = self.expression()
        self.expect(T.NEWLINE,
                    "متوقع سطرًا جديدًا بعد تعبير 'طابق'")
        cases = []
        default_body = None
        while self.check(T.CASE):
            self.advance()
            pattern = self._parse_pattern()
            guard = None
            # الحارس: حالة نمط إن شرط — 'إن' كلمة سياقية بعد النمط
            if self.check(T.IDENT) and self.cur().value == 'إن':
                self.advance()
                guard = self.expression()
            body = self.block()
            cases.append((pattern, guard, body))
        if self.check(T.OTHERWISE):
            self.advance()
            default_body = self.block()
        if not cases and default_body is None:
            self.error("'طابق' يحتاج 'حالة' واحدة على الأقل أو 'غير ذلك'")
        return Match(subject, cases, default_body, tok.line)

    def _parse_pattern(self):
        """نمط كامل: نمط مغلق أو بدائل بأو."""
        first = self._parse_closed_pattern()
        if not self.check(T.OR):
            return first
        pats = [first]
        while self.match(T.OR):
            pats.append(self._parse_closed_pattern())
        return POr(pats, first.line)

    def _parse_closed_pattern(self):
        """نمط مغلق: حرفية، التقاط، رمز بديل، مسار قيمة، قائمة، أو قاموس."""
        tok = self.cur()
        t = tok.type
        if t in (T.INT, T.FLOAT):
            self.advance()
            return PLiteral(Num(tok.value, tok.line), tok.line)
        if t is T.STRING:
            self.advance()
            return PLiteral(Str(tok.value, tok.line), tok.line)
        if t in (T.TRUE, T.FALSE):
            self.advance()
            return PLiteral(Bool(t is T.TRUE, tok.line), tok.line)
        if t is T.NONE:
            self.advance()
            return PLiteral(Null(tok.line), tok.line)
        if t is T.MINUS and self.peek(1).type in (T.INT, T.FLOAT):
            self.advance()
            num = self.advance()
            return PLiteral(UnaryOp('-', Num(num.value, num.line), tok.line),
                            tok.line)
        if t is T.LBRACKET:
            return self._list_pattern()
        if t is T.LBRACE:
            return self._dict_pattern()
        if t is T.IDENT:
            self.advance()
            if tok.value == '_':
                return PCapture(None, tok.line)     # الرمز البديل
            if self.check(T.DOT):
                # نمط قيمة: مسار خصائص مثل تعداد.عضو — يُقارن بالمساواة
                obj = Name(tok.value, tok.line)
                while self.check(T.DOT):
                    self.advance()
                    name_tok = self.cur()
                    if (name_tok.type is not T.IDENT
                            and name_tok.type not in KEYWORD_AS_NAME):
                        self.error("متوقع اسمًا بعد '.' في نمط القيمة")
                    self.advance()
                    obj = Attribute(obj, name_tok.value, tok.line)
                return PLiteral(obj, tok.line)
            return PCapture(tok.value, tok.line)
        self.error('نمط غير صالح — المتوقع حرفية أو اسم أو قائمة أو قاموس')

    def _list_pattern(self):
        """نمط قائمة: [أ، ب] أو [أ، ...الباقي] — '...' يجمع ما تبقى."""
        tok = self.advance()                       # [
        items = []
        rest = None
        if not self.check(T.RBRACKET):
            while True:
                if self.check(T.ELLIPSIS):
                    self.advance()
                    if self.check(T.IDENT):
                        rest = self.advance().value
                    else:
                        rest = False               # ... بلا اسم — تجاهل البقية
                    if not self.check(T.RBRACKET):
                        self.error("'...' يجب أن يكون آخر عنصر في نمط القائمة")
                    break
                items.append(self._parse_pattern())
                if self.match(T.COMMA):
                    if self.check(T.RBRACKET):     # فاصلة أخيرة مسموحة
                        break
                    continue
                break
        self.expect(T.RBRACKET, "متوقع ']' لإغلاق نمط القائمة")
        return PList(items, rest, tok.line)

    def _dict_pattern(self):
        """نمط قاموس: {الاسم: ن، العمر: ع} — مفاتيحه نصية افتراضيًا."""
        tok = self.advance()                       # {
        keys = []
        patterns = []
        if not self.check(T.RBRACE):
            while True:
                key_node, _ = self._dict_key()
                keys.append(key_node)
                self.expect(T.COLON, "متوقع ':' بين مفتاح النمط وقيمته")
                patterns.append(self._parse_pattern())
                if self.match(T.COMMA):
                    if self.check(T.RBRACE):       # فاصلة أخيرة مسموحة
                        break
                    continue
                break
        self.expect(T.RBRACE, "متوقع '}' لإغلاق نمط القاموس")
        return PDict(keys, patterns, tok.line)

    def enum_stmt(self):
        """تعداد الاسم: عضو، عضو = قيمة — كل عضو في سطر مستقل.

        الأعضاء بدون قيمة تأخذ رقمًا تلقائيًا يبدأ من ١ ويزيد.
        """
        tok = self.advance()                       # تعداد
        name = self.expect_ident("متوقع اسم التعداد بعد 'تعداد'")
        body = self.block()
        members = []
        for stmt in body:
            if isinstance(stmt, ExprStmt) and isinstance(stmt.expr, Name):
                members.append((stmt.expr.name, None, stmt.line))
            elif (isinstance(stmt, Assign) and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], Name)):
                members.append((stmt.targets[0].name, stmt.value, stmt.line))
            else:
                self.error("داخل 'تعداد' تُعرّف أسماء فقط: عضو أو عضو = قيمة")
        if not members:
            self.error(f"التعداد '{name}' فارغ — أضف عضوًا واحدًا على الأقل")
        return EnumDef(name, members, tok.line)

    def property_def(self):
        """خاصية محسوبة داخل صنف: خاصية الاسم: ... جسم ..."""
        tok = self.advance()                       # خاصية
        name = self.expect_ident("متوقع اسم الخاصية بعد 'خاصية'")
        body = self.block()
        return PropertyDef(name, body, tok.line)

    def global_stmt(self):
        """عالمي اسم، اسم — تعيينات هذه الأسماء تذهب للنطاق العام."""
        tok = self.advance()                       # عالمي
        names = [self.expect_ident("متوقع اسمًا بعد 'عالمي'")]
        while self.match(T.COMMA):
            names.append(self.expect_ident('متوقع اسمًا'))
        return Global(names, tok.line)

    def assert_stmt(self):
        """تحقق شرط، "رسالة" — يرفع خطأ إذا كان الشرط خطأ."""
        tok = self.advance()                       # تحقق
        test = self.expression()
        message = None
        if self.match(T.COMMA):
            message = self.expression()
        return Assert(test, message, tok.line)

    def delete_stmt(self):
        """احذف اسم أو عنصر قائمة/قاموس أو خاصية كائن."""
        tok = self.advance()                       # احذف
        target = self.expression()
        if not isinstance(target, (Name, Index, Attribute)):
            self.error("بعد 'احذف' متوقع اسمًا أو فهرسة [م] أو خاصية كائن")
        return Delete(target, tok.line)

    def expr_stmt(self):
        tok = self.cur()
        first = self.expression()
        exprs = [first]
        while self.check(T.COMMA):
            self.advance()
            exprs.append(self.expression())

        if self.check(T.ASSIGN):
            self.advance()
            for e in exprs:
                if not isinstance(e, (Name, Index, Attribute)):
                    self.error('الجهة اليسرى من الإسناد يجب أن تكون اسمًا أو عنصرًا مفهرسًا أو خاصية')
            values = [self.expression()]
            while self.check(T.COMMA):
                self.advance()
                values.append(self.expression())
            if len(exprs) == 1 and len(values) == 1:
                value = values[0]
            elif len(exprs) == len(values):
                value = ListLit(values, tok.line)
            elif len(exprs) > 1 and len(values) == 1:
                value = values[0]                  # تفكيك وقت التشغيل
            else:
                self.error('عدد القيم لا يطابق عدد المتغيرات في الإسناد')
            if self.check(T.ASSIGN):
                # الإسناد المتسلسل أ = ب = ٣ كان يسقط برسالة «متوقع نهاية
                # السطر» المضللة — رسالة دقيقة الآن (المواصفة ق١٠)
                self.error('الإسناد المتسلسل غير مدعوم (أ = ب = ٣) — '
                           'أسند كل متغير في جملة مستقلة')
            return Assign(exprs, value, tok.line)

        if self.cur().type in AUG_OPS:
            if len(exprs) != 1 or not isinstance(exprs[0], (Name, Index, Attribute)):
                self.error('الإسناد المركب يحتاج متغيرًا واحدًا على اليمين')
            op = AUG_OPS[self.advance().type]
            value = self.expression()
            return AugAssign(exprs[0], op, value, tok.line)

        if len(exprs) == 1:
            return ExprStmt(first, tok.line)
        self.error('تعبير غير صالح')

    # ---------- التعبيرات ----------

    def expression(self):
        return self.or_expr()

    def or_expr(self):
        e = self.and_expr()
        while self.check(T.OR):
            tok = self.advance()
            e = BinOp('أو', e, self.and_expr(), tok.line)
        return e

    def and_expr(self):
        e = self.not_expr()
        while self.check(T.AND):
            tok = self.advance()
            e = BinOp('و', e, self.not_expr(), tok.line)
        return e

    def not_expr(self):
        if self.check(T.NOT):
            tok = self.advance()
            return UnaryOp('ليس', self.not_expr(), tok.line)
        return self.comparison()

    def comparison(self):
        e = self.additive()
        # «ليس في»: عامل مركب من كلمتين
        if self.check(T.NOT) and self.peek(1).type is T.IN:
            tok = self.advance()
            self.advance()
            right = self.additive()
            self._reject_chained()
            return BinOp('ليس في', e, right, tok.line)
        if self.cur().type in CMP_OPS:
            tok = self.advance()
            right = self.additive()
            self._reject_chained()
            return BinOp(CMP_OPS[tok.type], e, right, tok.line)
        return e

    def _reject_chained(self):
        """يرفض المقارنات المتسلسلة برسالة دقيقة (المواصفة ق١٠):
        كانت تسقط برسالة مضللة مثل «متوقع تعبيرًا» أو «متوقع ')'
        """
        if self.cur().type in CMP_OPS or (
                self.check(T.NOT) and self.peek(1).type is T.IN):
            self.error('المقارنات المتسلسلة غير مدعومة (مثل أ < ب < ج) '
                       '— ادمج الشرطين بكلمة «و»: أ < ب و ب < ج')

    def additive(self):
        e = self.multiplicative()
        while self.cur().type in (T.PLUS, T.MINUS):
            tok = self.advance()
            op = '+' if tok.type is T.PLUS else '-'
            e = BinOp(op, e, self.multiplicative(), tok.line)
        return e

    def multiplicative(self):
        e = self.unary()
        while self.cur().type in (T.STAR, T.SLASH, T.PERCENT):
            tok = self.advance()
            op = {T.STAR: '*', T.SLASH: '/', T.PERCENT: '%'}[tok.type]
            e = BinOp(op, e, self.unary(), tok.line)
        return e

    def unary(self):
        # "انتظر مهمة" — كلمة سياقية بأولوية أحادي التعبير (الإصدار 1.15):
        # ترتبط أضيق من العمليات الثنائية: انتظر م + ١ تعني (انتظر م) + ١
        if (self.check(T.IDENT) and self.cur().value == 'انتظر'
                and self.peek(1).type in _AWAIT_START):
            tok = self.advance()
            return Await(self.unary(), tok.line)
        if self.check(T.MINUS):
            tok = self.advance()
            return UnaryOp('-', self.unary(), tok.line)
        if self.check(T.PLUS):
            self.advance()
            return self.unary()
        return self.power()

    def power(self):
        e = self.postfix()
        if self.check(T.POWER):
            tok = self.advance()
            return BinOp('**', e, self.unary(), tok.line)   # تجميع يميني
        return e

    def postfix(self):
        e = self.primary()
        while True:
            if self.check(T.LPAREN):
                e = self.call(e)
            elif self.check(T.LBRACKET):
                e = self.index(e)
            elif self.check(T.DOT):
                e = self.attribute(e)
            else:
                break
        return e

    def call(self, func):
        tok = self.advance()                       # (
        args = self.parse_call_args()
        return Call(func, args, tok.line)

    def parse_call_args(self):
        """يقرأ معاملات الاستدعاء: موضعية أو بالاسم (اسم = قيمة)."""
        args = []
        if not self.check(T.RPAREN):
            args.append(self.parse_arg())
            while self.match(T.COMMA):
                if self.check(T.RPAREN):           # فاصلة أخيرة مسموحة
                    break
                args.append(self.parse_arg())
        self.expect(T.RPAREN, "متوقع ')' لإغلاق الاستدعاء")
        return args

    def parse_arg(self):
        """معامل استدعاء واحد: تعبير، اسم = تعبير، أو ...تعبير (تفكيك)."""
        if self.check(T.ELLIPSIS):
            tok = self.advance()
            return (None, SpreadArg(self.expression(), tok.line))
        if (self.check(T.IDENT) and self.peek(1).type is T.ASSIGN):
            name_tok = self.advance()
            self.advance()                         # =
            value = self.expression()
            return (name_tok.value, value)
        return (None, self.expression())

    def index(self, obj):
        tok = self.advance()                       # [
        start = None
        if not self.check(T.COLON):
            start = self.expression()
        if self.check(T.COLON):
            self.advance()
            stop = None
            if not self.check(T.COLON) and not self.check(T.RBRACKET):
                stop = self.expression()
            step = None
            if self.check(T.COLON):
                self.advance()
                if not self.check(T.RBRACKET):
                    step = self.expression()
            self.expect(T.RBRACKET, "متوقع ']' لإغلاق التقطيع")
            return Slice(obj, start, stop, step, tok.line)
        self.expect(T.RBRACKET, "متوقع ']' لإغلاق الفهرسة")
        return Index(obj, start, tok.line)

    def attribute(self, obj):
        tok = self.advance()                       # .
        name_tok = self.cur()
        if name_tok.type is not T.IDENT and name_tok.type not in KEYWORD_AS_NAME:
            self.error("متوقع اسم خاصية أو طريقة بعد '.'")
        self.advance()
        name = name_tok.value
        if self.check(T.LPAREN):
            self.advance()
            args = self.parse_call_args()
            return MethodCall(obj, name, args, tok.line)
        return Attribute(obj, name, tok.line)

    def primary(self):
        tok = self.cur()
        t = tok.type
        if t is T.INT or t is T.FLOAT:
            self.advance()
            return Num(tok.value, tok.line)
        if t is T.STRING:
            self.advance()
            return Str(tok.value, tok.line)
        if t is T.FSTRING:
            self.advance()
            return self._fstring_parts(tok)
        if t is T.TRUE:
            self.advance()
            return Bool(True, tok.line)
        if t is T.FALSE:
            self.advance()
            return Bool(False, tok.line)
        if t is T.NONE:
            self.advance()
            return Null(tok.line)
        if t is T.THIS:
            self.advance()
            return This(tok.line)
        if t is T.SUPER:
            self.advance()
            return Super(tok.line)
        if t is T.IF:
            return self.ternary_node()             # لو شرط: قيمة وإلا قيمة
        if t is T.IDENT:
            self.advance()
            return Name(tok.value, tok.line)
        if t is T.DEF and self.peek(1).type is T.LPAREN:
            return self.lambda_expr()
        if t is T.LPAREN:
            self.advance()
            e = self.expression()
            self.expect(T.RPAREN, "متوقع ')' لإغلاق التعبير")
            return e
        if t is T.LBRACKET:
            return self.list_literal()
        if t is T.LBRACE:
            return self.dict_literal()
        self.error('متوقع تعبيرًا')

    def ternary_node(self):
        """التعبير الثلاثي: لو شرط: قيمة1 وإلا قيمة2.

        يمكن أن يظهر في أي موضع تعبير: النتيجة = لو العمر >= ١٨: "بالغ" وإلا "طفل"
        """
        tok = self.advance()                       # لو
        test = self.or_expr()
        self.expect(T.COLON, "متوقع ':' بعد شرط التعبير الثلاثي 'لو'")
        if_true = self.or_expr()
        self.expect(T.ELSE, "متوقع 'وإلا' لإكمال التعبير الثلاثي: لو شرط: قيمة وإلا قيمة")
        if_false = self.expression()
        return Ternary(test, if_true, if_false, tok.line)

    def lambda_expr(self):
        """دالة سهمية: دالة(س، ص) => س + ص"""
        tok = self.advance()                       # دالة
        params, rest, anns = self.parse_params()
        if self.match(T.RARROW):
            self.error(
                "الدالة السهمية لا تقبل نوع إرجاع — التوصيف للمعاملات "
                'فقط، ونوع الإرجاع للدالة الكتلية (نظام الأنواع 1.26)')
        self.expect(T.ARROW, "متوقع '=>' بعد معاملات الدالة السهمية")
        if self.check(T.NEWLINE) or self.check(T.EOF):
            self.error('جسم الدالة السهمية يجب أن يكون تعبيرًا واحدًا على نفس السطر')
        body = self.expression()
        return Lambda(params, body, tok.line, rest=rest, anns=anns)

    def list_literal(self):
        tok = self.advance()                       # [
        if self.check(T.RBRACKET):
            self.advance()
            return ListLit([], tok.line)
        first = self._list_item()
        if self.check(T.FOR):                      # فهم قائمة: [... لكل س في ل]
            return self._list_comp(first, tok)
        items = [first]
        while self.match(T.COMMA):
            if self.check(T.RBRACKET):             # فاصلة أخيرة مسموحة
                break
            items.append(self._list_item())
        self.expect(T.RBRACKET, "متوقع ']' لإغلاق القائمة")
        return ListLit(items, tok.line)

    def _list_comp(self, first, tok):
        """يكمل تحليل فهم القائمة بعد أول عنصر + كلمة 'لكل'."""
        if isinstance(first, SpreadArg):
            self.error(
                "التوسيع '...' غير مسموح في عنصر الفهم — عنصر الفهم تعبير "
                'يحسب لكل تكرار، والتفكيك يتم بأهداف العبارة (لكل أ، ب في …)')
        clauses = [self._comp_clause()]
        while self.check(T.FOR):                   # عبارات لكل متتالية
            clauses.append(self._comp_clause())
        self.expect(T.RBRACKET, "متوقع ']' لإغلاق فهم القائمة")
        return ListComp(first, clauses, tok.line)

    def _comp_clause(self):
        """عبارة 'لكل أ، ب في متتالية إن شرط' — الشرط اختياري."""
        self.advance()                             # لكل
        targets = [self.expect_ident("متوقع اسم متغير بعد 'لكل' في الفهم")]
        while self.match(T.COMMA):
            targets.append(self.expect_ident('متوقع اسم متغير في التفكيك'))
        self.expect(T.IN, "متوقع الكلمة المفتاحية 'في' في فهم القائمة")
        iterable = self.expression()
        cond = None
        if self.check(T.IDENT) and self.cur().value == 'إن':
            self.advance()                         # إن كلمة سياقية مثل حرّاس طابق
            cond = self.expression()
        return (targets, iterable, cond)

    def _list_item(self):
        """عنصر قائمة: تعبير أو ...تعبير (تفكيك)."""
        if self.check(T.ELLIPSIS):
            tok = self.advance()
            return SpreadArg(self.expression(), tok.line)
        return self.expression()

    def dict_literal(self):
        tok = self.advance()                       # {
        if not self.check(T.RBRACE):
            first_key, bare_name = self._dict_key()
            self.expect(T.COLON, "متوقع ':' بين مفتاح القاموس وقيمته")
            first_val = self.expression()
            if self.check(T.FOR):                  # فهم قاموس: {م: ق لكل س في ل}
                return self._dict_comp(first_key, first_val, tok, bare_name)
            keys = [first_key]
            values = [first_val]
            while self.match(T.COMMA):
                if self.check(T.RBRACE):
                    break
                key_node, _ = self._dict_key()
                keys.append(key_node)
                self.expect(T.COLON, "متوقع ':' بين مفتاح القاموس وقيمته")
                values.append(self.expression())
            self.expect(T.RBRACE, "متوقع '}' لإغلاق القاموس")
            return DictLit(keys, values, tok.line)
        self.advance()
        return DictLit([], [], tok.line)

    def _dict_comp(self, first_key, first_val, tok, bare_name=None):
        """يكمل تحليل فهم القاموس بعد مفتاح:قيمة + كلمة 'لكل'.

        المفتاح المعرّف المجرّد (ن) يعامل كمتغير يُقيّم كل تكرار —
        ولتعريف مفتاح ثابت يُقتبس: {"ثابت": ق}.
        """
        if bare_name is not None:
            first_key = Name(bare_name, tok.line)
        clauses = [self._comp_clause()]
        while self.check(T.FOR):
            clauses.append(self._comp_clause())
        self.expect(T.RBRACE, "متوقع '}' لإغلاق فهم القاموس")
        return DictComp(first_key, first_val, clauses, tok.line)

    def _dict_key(self):
        """مفتاح القاموس: معرّف بلا اقتباس يعامل كنص — {الحالة: 200} ≡ {"الحالة": 200}.

        يعيد (العقدة، الاسم_المجرّد) — الاسم_المجرّد ليُستبدل بمتغير في فهم القاموس.
        المعرّف المجرّد يُقبل فقط إذا تلاه ':' مباشرة، وإلا فهو بداية
        تعبير محسوب كـ {س % 2: س}.
        """
        if self.check(T.IDENT) and self.peek(1).type is T.COLON:
            tok = self.advance()
            return Str(tok.value, tok.line), tok.value
        return self.expression(), None

    # ---------- أدوات ----------

    def expect_ident(self, message):
        tok = self.cur()
        if tok.type is not T.IDENT:
            self.error(message)
        self.advance()
        return tok.value

    # ---------- النص المنسق ----------

    def _fstring_parts(self, tok):
        """يقسم محتوى النص المنسق إلى أجزاء حرفية وتعبيرات.

        {تعبير} تُحلّل كتعبير كامل، و{{ و }} حرفيتان (قوس واحد).
        """
        text = tok.value
        parts = []          # ('str', نص) أو ('expr', عقدة)
        buf = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            if c == '{':
                if i + 1 < n and text[i + 1] == '{':
                    buf.append('{')
                    i += 2
                    continue
                if buf:
                    parts.append(('str', ''.join(buf)))
                    buf = []
                depth = 1
                j = i + 1
                while j < n and depth > 0:
                    if text[j] == '{':
                        depth += 1
                    elif text[j] == '}':
                        depth -= 1
                    j += 1
                if depth != 0:
                    raise ParseError(
                        "قوس '}' غير مغلق داخل النص المنسق", tok.line, tok.col)
                expr_src = text[i + 1:j - 1].strip()
                if not expr_src:
                    raise ParseError(
                        'تعبير فارغ داخل {} في النص المنسق', tok.line, tok.col)
                parts.append(('expr', self._sub_expression(expr_src, tok.line)))
                i = j
            elif c == '}':
                if i + 1 < n and text[i + 1] == '}':
                    buf.append('}')
                    i += 2
                    continue
                raise ParseError(
                    "قوس '}' بدون '{' مقابلة في النص المنسق — استخدم }} لطباعة قوس",
                    tok.line, tok.col)
            else:
                buf.append(c)
                i += 1
        if buf:
            parts.append(('str', ''.join(buf)))
        return FString(parts, tok.line)

    def _sub_expression(self, src, line):
        """يحلل نصًا صغيرًا كتعبير واحد (لتعبيرات النص المنسق)."""
        from .lexer import Lexer
        try:
            sub_toks = Lexer(src).tokenize()
        except Exception as exc:
            raise ParseError(
                f"تعبير غير صالح داخل النص المنسق '{src}': {exc}", line)
        # التعبيرات الفرعية سطر واحد — نتخلص من الرموز البنيوية
        sub_toks = [t for t in sub_toks
                    if t.type not in (T.NEWLINE, T.INDENT, T.DEDENT)]
        sub = Parser(sub_toks)
        try:
            node = sub.expression()
            sub.expect(T.EOF, f"تعبير غير مكتمل '{src}' داخل النص المنسق")
        except ParseError as exc:
            raise ParseError(
                f"تعبير غير صالح داخل النص المنسق '{src}' — {exc.message}", line)
        return node
