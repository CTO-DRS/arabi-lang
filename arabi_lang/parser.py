# -*- coding: utf-8 -*-
"""المحلل النحوي (Parser) — يحوّل رموز المحلل اللفظي إلى شجرة صياغة AST.

محلل تنازلي تعاودي (Recursive Descent) بأولويات:
  أو < و < ليس < مقارنة < +/- < */٪ < سالب < ** < استدعاء/فهرسة/خاصية
"""

from .tokens import T
from .nodes import (
    Program, ExprStmt, Assign, AugAssign, If, While, For, FuncDef, Return,
    Break, Continue, Pass, Try, Raise, Import, ClassDef, Lambda, Switch,
    Num, Str, FString, Bool, Null, Name, ListLit, DictLit, BinOp, UnaryOp,
    Call, Index, Slice, MethodCall, Attribute, This, Super,
)
from .errors import ParseError

CMP_OPS = {
    T.EQ: '==', T.NEQ: '!=', T.LT: '<', T.GT: '>',
    T.LTE: '<=', T.GTE: '>=', T.IN: 'في',
}

AUG_OPS = {
    T.PLUS_ASSIGN: '+', T.MINUS_ASSIGN: '-',
    T.STAR_ASSIGN: '*', T.SLASH_ASSIGN: '/',
}

TOKEN_DESC = {
    T.NEWLINE: 'نهاية السطر',
    T.INDENT: 'مسافة بادئة',
    T.DEDENT: 'نهاية الكتلة',
    T.EOF: 'نهاية الملف',
    T.ARROW: "'=>'",
}

STMT_KEYWORDS = {
    T.DEF: 'دالة', T.RETURN: 'أعد', T.IF: 'لو', T.ELIF: 'وإلا إذا',
    T.ELSE: 'وإلا', T.WHILE: 'طالما', T.FOR: 'لكل', T.IN: 'في',
    T.BREAK: 'كسر', T.CONTINUE: 'استمر', T.TRUE: 'صح', T.FALSE: 'خطأ',
    T.NONE: 'ولا شيء', T.AND: 'و', T.OR: 'أو', T.NOT: 'ليس',
    T.TRY: 'جرب', T.EXCEPT: 'باستثناء', T.FINALLY: 'اخيرا',
    T.RAISE: 'ارفع', T.IMPORT: 'استورد', T.PASS: 'تجاهل',
    T.CLASS: 'صنف', T.THIS: 'هذا', T.SUPER: 'الأصل',
    T.SWITCH: 'بدّل', T.CASE: 'حالة', T.DEFAULT: 'افتراض',
}


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
            f"لا يمكن استنتاج اسم الوحدة من المسار '{path}'", tok.line)
    return base


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

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
        raise ParseError(f'{message} — لكن وجدت {tok_desc(self.cur())}', self.cur().line)

    def skip_newlines(self):
        while self.check(T.NEWLINE):
            self.advance()

    # ---------- نقطة الدخول ----------

    def parse(self):
        statements = []
        self.skip_newlines()
        while not self.check(T.EOF):
            statements.append(self.statement())
            self.skip_newlines()
        return Program(statements)

    # ---------- الجمل ----------

    def statement(self):
        stmt = self._statement()
        t = self.cur().type
        if t in (T.NEWLINE, T.EOF, T.DEDENT):
            return stmt
        # الجمل التي تنتهي بكتلة (لو/طالما/لكل/دالة/جرب/صنف/بدّل) تستهلك DEDENT
        # داخل block()، لذا الجملة التالية تبدأ مباشرة
        if isinstance(stmt, (If, While, For, FuncDef, Try, ClassDef, Switch)):
            return stmt
        self.error('متوقع نهاية السطر بعد الجملة')

    def _statement(self):
        t = self.cur().type
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
        if t is T.SWITCH:
            return self.switch_stmt()
        # «من وحدة استورد ...» — 'من' كلمة سياقية في بداية الجملة
        if (t is T.IDENT and self.cur().value == 'من'
                and self.peek(1).type in (T.IDENT, T.STRING)):
            return self.import_stmt()
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
        tok = self.advance()                       # دالة
        name = self.expect_ident("متوقع اسم الدالة بعد 'دالة'")
        params = self.parse_params()
        body = self.block()
        return FuncDef(name, params, body, tok.line)

    def parse_params(self):
        """يقرأ قائمة المعاملات مع الافتراضيات: (أ، ب = ٥)"""
        self.expect(T.LPAREN, "متوقع '(' لفتح قائمة المعاملات")
        params = []
        if not self.check(T.RPAREN):
            params.append(self.parse_param())
            while self.match(T.COMMA):
                if self.check(T.RPAREN):           # فاصلة أخيرة مسموحة
                    break
                params.append(self.parse_param())
        self.expect(T.RPAREN, "متوقع ')' لإغلاق قائمة المعاملات")
        return params

    def parse_param(self):
        """معامل واحد: اسم أو اسم = قيمة افتراضية"""
        name = self.expect_ident('متوقع اسم معامل')
        default = None
        if self.match(T.ASSIGN):
            default = self.expression()
        return (name, default)

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
        tok = self.advance()                       # جرب
        body = self.block()
        except_body = None
        finally_body = None
        if self.check(T.EXCEPT):
            self.advance()
            except_body = self.block()
        if self.check(T.FINALLY):
            self.advance()
            finally_body = self.block()
        if except_body is None and finally_body is None:
            self.error("'جرب' يتطلب 'باستثناء' أو 'اخيرا' بعده")
        return Try(body, except_body, finally_body, tok.line)

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
        # الوراثة: صنف ابن من أصل — 'من' كلمة سياقية
        if self.check(T.IDENT) and self.cur().value == 'من':
            self.advance()
            superclass = self.expect_ident("متوقع اسم الصنف الأصل بعد 'من'")
        body = self.block()
        return ClassDef(name, superclass, body, tok.line)

    def switch_stmt(self):
        """بدّل التعبير — كتل حالة على أسطر تالية بنفس مستوى 'بدّل':

        بدّل يوم
        حالة "السبت":
            ...
        افتراض:
            ...
        """
        tok = self.advance()                       # بدّل
        subject = self.expression()
        self.expect(T.NEWLINE,
                    "متوقع سطرًا جديدًا بعد تعبير 'بدّل'")
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
            self.error("'بدّل' يحتاج 'حالة' واحدة على الأقل أو 'افتراض'")
        return Switch(subject, cases, default_body, tok.line)

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
                    self.error('الجهة اليمين من الإسناد يجب أن تكون اسمًا أو عنصرًا مفهرسًا أو خاصية')
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
            return BinOp('ليس في', e, right, tok.line)
        if self.cur().type in CMP_OPS:
            tok = self.advance()
            right = self.additive()
            return BinOp(CMP_OPS[tok.type], e, right, tok.line)
        return e

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
        """معامل استدعاء واحد: تعبير أو اسم = تعبير (معامل بالاسم)."""
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
        name = self.expect_ident("متوقع اسم خاصية أو طريقة بعد '.'")
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

    def lambda_expr(self):
        """دالة سهمية: دالة(س، ص) => س + ص"""
        tok = self.advance()                       # دالة
        params = self.parse_params()
        self.expect(T.ARROW, "متوقع '=>' بعد معاملات الدالة السهمية")
        if self.check(T.NEWLINE) or self.check(T.EOF):
            self.error('جسم الدالة السهمية يجب أن يكون تعبيرًا واحدًا على نفس السطر')
        body = self.expression()
        return Lambda(params, body, tok.line)

    def list_literal(self):
        tok = self.advance()                       # [
        items = []
        if not self.check(T.RBRACKET):
            items.append(self.expression())
            while self.match(T.COMMA):
                if self.check(T.RBRACKET):
                    break
                items.append(self.expression())
        self.expect(T.RBRACKET, "متوقع ']' لإغلاق القائمة")
        return ListLit(items, tok.line)

    def dict_literal(self):
        tok = self.advance()                       # {
        keys = []
        values = []
        if not self.check(T.RBRACE):
            keys.append(self.expression())
            self.expect(T.COLON, "متوقع ':' بين مفتاح القاموس وقيمته")
            values.append(self.expression())
            while self.match(T.COMMA):
                if self.check(T.RBRACE):
                    break
                keys.append(self.expression())
                self.expect(T.COLON, "متوقع ':' بين مفتاح القاموس وقيمته")
                values.append(self.expression())
        self.expect(T.RBRACE, "متوقع '}' لإغلاق القاموس")
        return DictLit(keys, values, tok.line)

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
                        "قوس '}' غير مغلق داخل النص المنسق", tok.line)
                expr_src = text[i + 1:j - 1].strip()
                if not expr_src:
                    raise ParseError(
                        'تعبير فارغ داخل {} في النص المنسق', tok.line)
                parts.append(('expr', self._sub_expression(expr_src, tok.line)))
                i = j
            elif c == '}':
                if i + 1 < n and text[i + 1] == '}':
                    buf.append('}')
                    i += 2
                    continue
                raise ParseError(
                    "قوس '}' بدون '{' مقابلة في النص المنسق — استخدم }} لطباعة قوس", tok.line)
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
