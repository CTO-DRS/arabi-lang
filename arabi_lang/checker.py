# -*- coding: utf-8 -*-
"""المدقق الساكن v1 للغة عربي (الإصدار 1.36 — أفق التمكين).

يغلق الفجوة التي أثبتها المسبار (scripts/checker_probe.py — ١١/١١):
التوصيفات في نظام الأنواع التدريجي (1.26) تُحسم وقت التشغيل عند أول
استدعاء حصرًا (ق١٣) — فدالة موصّفة خطأ ولم تُستدعَ تمر بلا كشف أبدًا،
وكذلك مخالفة إرجاع حرفية في دالة صامتة. هذا المدقق يفحص عقود الدوال
الموثقة **قبل التشغيل** من الشجرة النحوية وحدها.

قرارات v1 (ص١–ص٥ في المسبار):
  ص١: أسماء التوصيفات تُحل ساكنًا — العائلات المدمجة فورًا، والأصناف
      والواجهات من نطاق الوحدة (بجمع استباقي: الترتيب لا يهم لأن الحسم
      وقت التشغيل يقع بعد اكتمال التحميل).
  ص٢: كل «أعد» بقيمة يُصنَّف بالأدلة الساكنة حصرًا: الحرفيات، العمليات
      الحسابية/النصية على حرفيات، استدعاء دوال التحويل المدمجة، النصوص
      المنسقة، والثلاثي متى حُسم فرعاه. ما لا يُحسم يُتخطى صامتًا —
      لا استنتاج أنواع في v1 (بند مؤرخ لأفق ٣ — المدقق v2).
  ص٣: صفر «أعد» في دالة تعلن إرجاعًا غير «عدم/أي» = سقوط ضمني مضمون =
      مخالفة ساكنة (المرآة الثابتة لعقد ق١٥).
  ص٤: قطع النطاق عند كل دالة/صنف متداخل — «أعد» الداخلية لا تعود
      لأمها، وكل عقد يفحص في نطاقه.
  ص٥: أي مخالفة = رمز خروج 1 — عقد خطوط الاستمرارية.

التوافق مع دلالات وقت التشغيل مقصود حرفيًا: رسائل المخالفات تستعير
صياغة فاحص 1.26، وقواعد القبول نفسها (صحيح يمر لعدد/عشري، والمنطقي لا
يُعد عددًا أبدًا — ق١٥).
"""

from .errors import ArabiError
from .lexer import Lexer
from .parser import Parser
from .runtime import TYPE_FAMILIES

# مدى التشكيل الذي يمحوه المعجم نفسه (ق٢) — ولا حرف أكثر
_TASHKEEL = set(chr(c) for c in range(0x064B, 0x0656)) | {chr(0x0670)}


def strip_tashkeel(text):
    """محو التشكيل بمدى المعجم نفسه — قاعدة ق٢ حرفيًا."""
    return ''.join(ch for ch in text if ch not in _TASHKEEL)

# دلالات القبول: النموذج يمر لما يقبل أوسع منه (ق١٥ — برج PEP 484)
_ACCEPTS = {
    'عدد': {'عدد', 'صحيح'},
    'عشري': {'عشري', 'عدد', 'صحيح'},
    'صحيح': {'صحيح'},
}

# دوال التحويل المدمجة التي يستدعيها الاسم مباشرة تعطي دليل العائلة
_CONVERSION_FAMILIES = ('عدد', 'صحيح', 'عشري', 'نص', 'منطقي',
                        'قائمة', 'قاموس', 'مدى')


class StaticIssue:
    """مخالفة ساكنة واحدة — سطر ودالة ورسالة عربية."""

    __slots__ = ('line', 'func', 'message')

    def __init__(self, line, func, message):
        self.line = line
        self.func = func
        self.message = message

    def __repr__(self):
        return f'سطر {self.line}: {self.message}'


class _Stats:
    """عدادات الجلسة — تظهر في الملخص لا تُخفى."""

    def __init__(self):
        self.documented = 0       # دوال تحمل توصيفًا
        self.evidenced = 0        # مواضع أعد حُسم دليلها
        self.skipped = 0          # مواضع أعد بلا دليل ساكن (حد v1)


class _Checker:
    def __init__(self):
        self.issues = []
        self.stats = _Stats()

    # ================== الدخول ==================

    def check_program(self, tree):
        """يفحص شجرة كاملة — يجمع أسماء الأصناف استباقيًا ثم يمشي."""
        module_classes = self._collect_classes(tree.statements)
        self._walk_scope(tree.statements, [module_classes])
        return self.issues, self.stats

    def _collect_classes(self, statements):
        """أسماء الأصناف والواجهات المعرفة مباشرة في هذا النطاق."""
        names = set()
        for stmt in statements:
            kind = type(stmt).__name__
            if kind in ('ClassDef', 'InterfaceDef'):
                names.add(stmt.name)
        return names

    # ================== المشي بالنطاقات ==================

    def _walk_scope(self, statements, scopes):
        """يمشي جمل نطاق: يفحص الدوال ويفتح نطاقات المتداخلات."""
        local_classes = []
        for stmt in statements:
            kind = type(stmt).__name__
            if kind == 'FuncDef':
                local_classes.append(stmt)
            elif kind in ('ClassDef', 'InterfaceDef'):
                local_classes.append(stmt)

        for stmt in local_classes:
            if type(stmt).__name__ == 'FuncDef':
                self._check_function(stmt, scopes)
                # دالة داخلية/طريقة: نطاقها الخاص نطاقًا مستقلًا (ص٤)
                inner = self._collect_classes(stmt.body)
                self._walk_scope(stmt.body, scopes + [inner])
            else:
                # جسم الصنف: طرقه عقود مستقلة
                inner = self._collect_classes(stmt.body)
                self._walk_scope(stmt.body, scopes + [inner])

        # الدوال المعرفة داخل جمل تحكم في هذا النطاق تُفحص كذلك
        for stmt in statements:
            kind = type(stmt).__name__
            nested = []
            if kind == 'If':
                nested = [stmt.body, *(b for _t, b in (stmt.elifs or []))]
                if stmt.orelse:
                    nested.append(stmt.orelse)
            elif kind in ('While', 'For', 'With'):
                nested = [stmt.body]
            elif kind == 'Try':
                nested = [stmt.body] + [c[2] for c in (stmt.clauses or [])]
                if stmt.finally_body:
                    nested.append(stmt.finally_body)
            for body in nested:
                self._walk_scope(body, scopes)

    def _check_function(self, func, scopes):
        """يفحص عقد دالة موثقة واحدة — الصامتة تُتجاهل بلا كلفة."""
        if not func.anns and func.ret is None:
            return
        self.stats.documented += 1

        # ص١: حل أسماء التوصيفات ساكنًا
        for spec in func.anns.values():
            self._resolve_spec(spec, func, scopes)
        ret_desc = None
        if func.ret is not None:
            ret_desc = self._resolve_spec(func.ret, func, scopes)

        if ret_desc is None:
            return
        kind = ret_desc[0]
        if kind == 'family' and ret_desc[1] in ('أي',):
            return          # أي تقبل كل شيء — لا فحص مسار
        if kind == 'family' and ret_desc[1] == 'عدم':
            # عدم: أعد بقيمة مخالفة، والسقوط مقبول
            for node in self._returns(func.body):
                if node.value is not None:
                    self.issues.append(StaticIssue(
                        node.line, func.name,
                        f"الدالة '{func.name}' تعلن إرجاع 'عدم' لكن "
                        'أعد تحمل قيمة — احذف القيمة أو غيّر النوع'))
            return
        if func.is_async:
            # أجسام غير المتزامنة تعمل كمهام — فحصها بعد الاستنتاج (v2)
            return

        # ص٣: صفر أعد = سقوط ضمني مضمون (مرآة ق١٥ الساكنة)
        returns = self._returns(func.body)
        if not returns:
            self.issues.append(StaticIssue(
                func.line, func.name,
                f"الدالة '{func.name}' تعلن إرجاع "
                f"'{func.ret.text}' لكن جسمها بلا أي أعد — السقوط "
                'الضمني يعيد عدمًا ومخالفة مضمونة عند أول استدعاء'))
            return

        # ص٢: فحص كل أعد بدليله الساكن
        for node in returns:
            self._check_return(func, node, ret_desc, scopes)

    # ================== مسار الأعد ==================

    def _returns(self, body):
        """كل جمل أعد في هذا النطاق حصرًا — المتداخلات مقطوعة (ص٤)."""
        out = []
        self._collect_returns(body, out)
        return out

    def _collect_returns(self, statements, out):
        for stmt in statements:
            kind = type(stmt).__name__
            if kind == 'Return':
                out.append(stmt)
            elif kind in ('If',):
                self._collect_returns(stmt.body, out)
                for _test, branch in (stmt.elifs or []):
                    self._collect_returns(branch, out)
                if stmt.orelse:
                    self._collect_returns(stmt.orelse, out)
            elif kind in ('While', 'For'):
                self._collect_returns(stmt.body, out)
            elif kind == 'Try':
                self._collect_returns(stmt.body, out)
                for clause in (stmt.clauses or []):
                    self._collect_returns(clause[2], out)
                if stmt.finally_body:
                    self._collect_returns(stmt.finally_body, out)
            elif kind == 'With':
                self._collect_returns(stmt.body, out)
            # FuncDef/ClassDef/InterfaceDef: مقطوعة — أعد الداخلية
            # تعود لتعريفها لا لأمها (ص٤)

    # ================== الأدلة الساكنة ==================

    def _evidence(self, expr):
        """دليل نوع ساكن لتعبير — اسم عائلة أو None (لا تخمين)."""
        kind = type(expr).__name__
        if kind == 'Num':
            return 'صحيح' if isinstance(expr.value, int) else 'عدد'
        if kind == 'Str' or kind == 'FString':
            return 'نص'
        if kind == 'Bool':
            return 'منطقي'
        if kind == 'Null':
            return 'عدم'
        if kind == 'ListLit':
            return 'قائمة'
        if kind == 'DictLit':
            return 'قاموس'
        if kind == 'UnaryOp':
            inner = self._evidence(expr.operand)
            if inner in ('صحيح', 'عدد'):
                return inner
            return None
        if kind == 'BinOp':
            return self._evidence_binop(expr)
        if kind == 'Ternary':
            both = (self._evidence(expr.if_true),
                    self._evidence(expr.if_false))
            if None not in both and both[0] == both[1]:
                return both[0]
            return None
        if kind == 'Call' and type(expr.func).__name__ == 'Name':
            name = strip_tashkeel(expr.func.name)
            single = (len(expr.args) == 1
                      and expr.args[0][0] is None)
            if name in _CONVERSION_FAMILIES and single:
                return name
        return None

    def _evidence_binop(self, expr):
        left = self._evidence(expr.left)
        right = self._evidence(expr.right)
        if left is None or right is None:
            return None
        op = expr.op
        if op in ('+', '-', '*', '**', '٪', '%'):
            numeric = {'صحيح', 'عدد'}
            if left in numeric and right in numeric:
                return 'صحيح' if left == right == 'صحيح' else 'عدد'
            if op == '+' and left == 'نص' and right == 'نص':
                return 'نص'
            return None
        if op in ('/', '//'):
            numeric = {'صحيح', 'عدد'}
            if left in numeric and right in numeric:
                return 'عدد'
            return None
        return None

    def _check_return(self, func, node, ret_desc, scopes):
        """موضع أعد واحد: دليل أم تخطي، ثم مقارنة بالعقد."""
        if node.value is None:
            # أعد سقوط صريح بلا قيمة مع نوع غير عدم — مخالفة
            self.issues.append(StaticIssue(
                node.line, func.name,
                f"الدالة '{func.name}' تعلن إرجاع '{func.ret.text}' "
                'لكن هذا أعد بلا قيمة — يعيد عدمًا'))
            return
        evidence = self._evidence(node.value)
        if evidence is None:
            self.stats.skipped += 1     # حد v1: لا استنتاج — صمت
            return
        self.stats.evidenced += 1
        self._compare(func, node, ret_desc, evidence)

    def _compare(self, func, node, ret_desc, evidence):
        kind = ret_desc[0]
        if kind == 'class':
            # دليل ساكن (حرف/حساب/تحويل) لا يمكن أن يكون كائن صنف
            self.issues.append(StaticIssue(
                node.line, func.name,
                f"الدالة '{func.name}' تعلن إرجاع صنف "
                f"'{func.ret.text}' لكن أعد يعطي دليلًا من عائلة "
                f"'{evidence}' — مخالفة ساكنة"))
            return
        if kind == 'list':
            self._compare_list(func, node, ret_desc[1], evidence)
            return
        if kind == 'dict':
            self._compare_dict(func, node, ret_desc, evidence)
            return
        family = ret_desc[1]
        accepts = _ACCEPTS.get(family, {family})
        if evidence not in accepts:
            label = self._evidence_label(node.value, evidence)
            self.issues.append(StaticIssue(
                node.line, func.name,
                f"الدالة '{func.name}' تعلن إرجاع '{func.ret.text}' "
                f'لكن أعد يعطي دليل {label} — '
                f'{self._clash_note(family, evidence)}'))

    def _evidence_label(self, value, evidence):
        if evidence == 'نص':
            return f"نص (حرف: \"{value.value}\")"
        if evidence == 'منطقي':
            return 'منطقي (حرف)'
        if evidence == 'قائمة':
            return 'قائمة (حرف)'
        if evidence == 'قاموس':
            return 'قاموس (حرف)'
        if evidence == 'عدم':
            return 'عدم (حرف)'
        return f'{evidence} (حرف أو حساب حرفي)'

    def _clash_note(self, family, evidence):
        if family in ('عدد', 'عشري', 'صحيح') and evidence == 'منطقي':
            return 'المنطقي لا يُعد عددًا أبدًا (ق١٥)'
        return 'مخالفة ساكنة قبل التشغيل'

    def _compare_list(self, func, node, elem_desc, evidence):
        if evidence != 'قائمة':
            self.issues.append(StaticIssue(
                node.line, func.name,
                f"الدالة '{func.name}' تعلن إرجاع '{func.ret.text}' "
                f'لكن أعد يعطي دليل {evidence} — مخالفة ساكنة'))
            return
        # العناصر الحرفية القابلة للحسم تفحص ضد توصيف العنصر
        desc = elem_desc
        if desc[0] != 'family':
            return          # عناصر صنف — لا دليل ساكن لها في v1
        family = desc[1]
        accepts = _ACCEPTS.get(family, {family})
        for item in node.value.items:
            item_ev = self._evidence(item)
            if item_ev is None:
                continue
            if item_ev not in accepts:
                self.issues.append(StaticIssue(
                    node.line, func.name,
                    f"الدالة '{func.name}' تعلن إرجاع "
                    f"'{func.ret.text}' لكن القائمة الحرفية تحوي عنصرًا "
                    f'دليله {item_ev} — مخالف لتوصيف العنصر '
                    f"'{desc[1]}'"))
                return

    def _compare_dict(self, func, node, ret_desc, evidence):
        if evidence != 'قاموس':
            self.issues.append(StaticIssue(
                node.line, func.name,
                f"الدالة '{func.name}' تعلن إرجاع '{func.ret.text}' "
                f'لكن أعد يعطي دليل {evidence} — مخالفة ساكنة'))
            return

    # ================== حل الأسماء (ص١) ==================

    def _resolve_spec(self, spec, func, scopes):
        """مرآة ساكنة لترتيب الحسم ق١٣: عائلات فورًا ثم النطاقات."""
        name = strip_tashkeel(spec.name)
        if name in TYPE_FAMILIES:
            if spec.element is not None:
                return ('list', self._resolve_spec(spec.element, func,
                                                   scopes))
            if spec.key is not None:
                kd = self._resolve_spec(spec.key, func, scopes)
                vd = self._resolve_spec(spec.value, func, scopes)
                return ('dict', kd, vd)
            return ('family', name)
        # صنف/واجهة من نطاقات الإحاطة (جمع استباقي — الترتيب لا يهم)
        for scope in reversed(scopes):
            if name in scope:
                if spec.element is not None or spec.key is not None:
                    self.issues.append(StaticIssue(
                        spec.line, func.name,
                        f"التعمية '{spec.text}' لا تنطبق على '{name}' — "
                        'الأصناف والواجهات توصّف بلا أقواس'))
                    return None
                return ('class', name)
        families = '، '.join(sorted(TYPE_FAMILIES))
        self.issues.append(StaticIssue(
            spec.line, func.name,
            f"اسم النوع '{spec.name}' في '{func.name}' غير معروف — ليس "
            f'صنفًا مرئيًا من نطاق التعريف ولا عائلة مدمجة '
            f'(العائلات: {families})'))
        return None


def check_source(source):
    """يفحص نص برنامج: يعيد (قائمة المخالفات، العدادات).

    خطأ اللفظ أو النحو يعيد مخالفة واحدة برسالة المفسر — الملف المكسور
    مخالفة بحد ذاته وعقد رمز الخروج واحد.
    """
    checker = _Checker()
    try:
        tree = Parser(Lexer(source).tokenize()).parse()
    except ArabiError as exc:
        return ([StaticIssue(getattr(exc, 'line', None) or 0, None,
                             f'الملف لا يُحلل ساكنًا: {exc}')],
                checker.stats)
    issues, stats = checker.check_program(tree)
    return issues, stats


def check_path(path):
    """يقرأ ملفًا ويفحصه — يرفع OSError للمسار الغائب."""
    with open(path, encoding='utf-8-sig') as f:
        return check_source(f.read())
