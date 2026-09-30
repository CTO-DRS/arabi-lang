# -*- coding: utf-8 -*-
"""عقد شجرة الصياغة التجريدية (AST) للغة عربي.

كل عقدة تحمل رقم السطر الذي ظهرت فيه لتقارير الأخطاء الدقيقة.
"""


class Node:
    def __init__(self, line=None):
        self.line = line


# ================== جمل (Statements) ==================

class Program(Node):
    def __init__(self, statements, line=None):
        super().__init__(line)
        self.statements = statements


class ExprStmt(Node):
    def __init__(self, expr, line=None):
        super().__init__(line)
        self.expr = expr


class Assign(Node):
    """الإسناد: هدف أو أكثر (تفكيك) = قيمة أو عدة قيم."""

    def __init__(self, targets, value, line=None):
        super().__init__(line)
        self.targets = targets
        self.value = value


class AugAssign(Node):
    """إسناد مركب: += -= *= /="""

    def __init__(self, target, op, value, line=None):
        super().__init__(line)
        self.target = target
        self.op = op
        self.value = value


class If(Node):
    def __init__(self, test, body, elifs, orelse, line=None):
        super().__init__(line)
        self.test = test
        self.body = body            # [stmt]
        self.elifs = elifs          # [(test, [stmt]), ...]
        self.orelse = orelse        # [stmt] أو None


class While(Node):
    def __init__(self, test, body, line=None):
        super().__init__(line)
        self.test = test
        self.body = body


class For(Node):
    def __init__(self, targets, iterable, body, line=None):
        super().__init__(line)
        self.targets = targets      # [Name] أو [Name, Name] للتفكيك
        self.iterable = iterable
        self.body = body


class TypeSpec(Node):
    """توصيف نوع (نظام الأنواع التدريجي — الإصدار 1.26).

    name اسم النوع كما كُتب (معرف، أو 'ولا شيء'، أو 'دالة').
    element عنصر التعمية لقائمة[نوع]، أو (key, value) لقاموس[مفتاح: قيمة]
    — كائنات TypeSpec بدورها، وكلها None إن كان النوع بلا تعمية.

    الحسم ليس هنا: المفسر يحل الاسم عند أول استدعاء (قرار ق١٣).
    """

    def __init__(self, name, line=None, element=None, key=None, value=None):
        super().__init__(line)
        self.name = name
        self.element = element     # TypeSpec لقائمة[...] أو None
        self.key = key             # TypeSpec لقاموس[...:...] أو None
        self.value = value         # TypeSpec لقاموس[...:...] أو None

    @property
    def text(self):
        """الصيغة النصية للتوصيف كما تُعرض في رسائل الأخطاء."""
        if self.element is not None:
            return f'{self.name}[{self.element.text}]'
        if self.key is not None:
            return f'{self.name}[{self.key.text}: {self.value.text}]'
        return self.name


class FuncDef(Node):
    def __init__(self, name, params, body, line=None, decorators=None,
                 is_generator=False, rest=None, is_async=False,
                 anns=None, ret=None):
        super().__init__(line)
        self.name = name
        self.params = params      # [(الاسم، تعبير الافتراضي أو None)، ...]
        self.body = body
        self.decorators = decorators or []   # [تعبير، ...] بترتيب الكتابة
        self.is_generator = is_generator     # صح إذا يحوي 'أنتج'
        self.rest = rest          # اسم المعامل المتغير ... أو None
        self.is_async = is_async  # صح إذا سبقها 'غير متزامنة' (الإصدار 1.15)
        self.anns = anns or {}    # {الاسم: TypeSpec} — توصيفات المعاملات (1.26)
        self.ret = ret            # TypeSpec لنوع الإرجاع أو None (1.26)


class Return(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value          # تعبير أو None


class Yield(Node):
    """جملة أنتج — تُنتج قيمة من مولد وتوقف التنفيذ حتى الطلب التالي."""

    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value          # تعبير أو None


class Break(Node):
    def __init__(self, line=None):
        super().__init__(line)


class Continue(Node):
    def __init__(self, line=None):
        super().__init__(line)


class Pass(Node):
    def __init__(self, line=None):
        super().__init__(line)


class Try(Node):
    def __init__(self, body, clauses, finally_body, line=None):
        super().__init__(line)
        self.body = body
        # كتل باستثناء: [(فلتر_صنف|None، ربط|None، [stmt])] —
        # الفلتر تعبير اسم/مسار يُقيَّم وقت الالتقاط (المواصفة ق٦)
        self.clauses = clauses
        self.finally_body = finally_body  # [stmt] أو None


class Raise(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value


class Import(Node):
    """الاستيراد.

    استورد وحدة        →  module='وحدة'، path=None، names=None
    استورد "م/ملف.عربي" →  module=None، path='م/ملف.عربي'، names=None
    من وحدة استورد أ، ب →  module='وحدة'، names=['أ'، 'ب']
    """

    def __init__(self, module, path, names, bound_name, line=None):
        super().__init__(line)
        self.module = module          # اسم الوحدة أو None
        self.path = path              # مسار نصي أو None
        self.names = names            # قائمة أسماء (من...استورد) أو None
        self.bound_name = bound_name  # الاسم المرتبط في البيئة (للاستيراد الكامل)


class ClassDef(Node):
    """تعريف صنف: صنف الاسم من أصل₁، أصل₂: ... (وراثة متعددة مسموحة)."""

    def __init__(self, name, superclass, body, line=None):
        super().__init__(line)
        self.name = name
        self.superclass = superclass      # اسم أو قائمة أسماء أو None
        self.body = body                  # [FuncDef | Assign]


class InterfaceDef(Node):
    """تعريف واجهة: واجهة الاسم من واجهة_أصل: ...

    طرق بلا جسم = طرق مجردة يجب على الأصناف المنفذة توفيرها.
    طرق بجسم = تنفيذ افتراضي يورث. الثوابت مسموحة.
    """

    def __init__(self, name, superclass, body, abstract, line=None):
        super().__init__(line)
        self.name = name
        self.superclass = superclass      # اسم أو قائمة أسماء أو None
        self.body = body                  # [FuncDef | Assign] (المجردة بجسم None)
        self.abstract = abstract          # [أسماء الطرق المجردة]


class Switch(Node):
    """بدّل التعبير: ينفذ كتلة الحالة المطابقة فقط (بدون تساقط).

    cases: [(تعبير القيمة، [جمل])، ...]
    """

    def __init__(self, subject, cases, default_body, line=None):
        super().__init__(line)
        self.subject = subject
        self.cases = cases
        self.default_body = default_body  # [stmt] أو None


class Match(Node):
    """مطابقة الأنماط: طابق تعبير ثم كتل حالة بنمط وربما حارس.

    cases: [(نمط، حارس أو None، [جمل])، ...]
    """

    def __init__(self, subject, cases, default_body, line=None):
        super().__init__(line)
        self.subject = subject
        self.cases = cases
        self.default_body = default_body  # [stmt] أو None


# ================== عقد أنماط المطابقة (الإصدار 1.9) ==================

class PLiteral(Node):
    """نمط قيمة: حرفية أو مسار خصائص (تعداد.عضو) — يُقارن بالمساواة."""

    def __init__(self, expr, line=None):
        super().__init__(line)
        self.expr = expr


class PCapture(Node):
    """نمط التقاط: اسم يربط القيمة، أو الاسم '_' للرمز البديل (لا يربط)."""

    def __init__(self, name, line=None):
        super().__init__(line)
        self.name = name          # None يعني '_' — يطابق كل شيء بلا ربط


class POr(Node):
    """نمط بديل: ١ أو ٢ أو ٣ — أول نمط يطابق هو المعتمد بروابطه."""

    def __init__(self, patterns, line=None):
        super().__init__(line)
        self.patterns = patterns


class PList(Node):
    """نمط قائمة: [أ، ب] أو [أ، ...الباقي] أو [أ، ...]."""

    def __init__(self, items, rest, line=None):
        super().__init__(line)
        self.items = items        # [نمط]
        self.rest = rest          # اسم ربط أو False (…) أو None (لا يوجد)


class PDict(Node):
    """نمط قاموس: {الاسم: نمط، ...} — المفاتيح يجب أن توجد، والزائد مسموح."""

    def __init__(self, keys, patterns, line=None):
        super().__init__(line)
        self.keys = keys          # [تعبير]
        self.patterns = patterns  # [نمط]


class EnumDef(Node):
    """تعريف تعداد: أعضاء [(الاسم، تعبير القيمة أو None) للقراءة التلقائية]."""

    def __init__(self, name, members, line=None):
        super().__init__(line)
        self.name = name
        self.members = members


class PropertyDef(Node):
    """خاصية محسوبة داخل صنف: خاصية الاسم: ... جسم ..."""

    def __init__(self, name, body, line=None):
        super().__init__(line)
        self.name = name
        self.body = body


class Global(Node):
    """جملة عالمي — تعيينات الأسماء التالية تذهب للنطاق العام."""

    def __init__(self, names, line=None):
        super().__init__(line)
        self.names = names


class Assert(Node):
    """جملة تحقق شرط مع رسالة اختيارية تظهر عند الفشل."""

    def __init__(self, test, message, line=None):
        super().__init__(line)
        self.test = test
        self.message = message      # تعبير أو None


class Delete(Node):
    """جملة احذف — الهدف: اسم أو فهرسة أو خاصية."""

    def __init__(self, target, line=None):
        super().__init__(line)
        self.target = target


# ================== تعبيرات (Expressions) ==================

class Num(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value


class Str(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value


class FString(Node):
    """نص منسق: ق"مرحبا {الاسم}، الناتج {أ + ب}"

    parts: [('str', نص حرفي) | ('expr', عقدة تعبير)، ...]
    """

    def __init__(self, parts, line=None):
        super().__init__(line)
        self.parts = parts


class Bool(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value


class Null(Node):
    def __init__(self, line=None):
        super().__init__(line)


class Name(Node):
    def __init__(self, name, line=None):
        super().__init__(line)
        self.name = name


class ListLit(Node):
    def __init__(self, items, line=None):
        super().__init__(line)
        self.items = items


class DictLit(Node):
    def __init__(self, keys, values, line=None):
        super().__init__(line)
        self.keys = keys
        self.values = values


class ListComp(Node):
    """فهم قائمة: [تعبير لكل س في متتالية إن شرط لكل ص في أخرى].

    clauses: [(targets, iterable, cond)، ...] — شرط كل عبارة اختياري (None).
    """
    def __init__(self, elt, clauses, line=None):
        super().__init__(line)
        self.elt = elt              # تعبير العنصر
        self.clauses = clauses


class DictComp(Node):
    """فهم قاموس: {مفتاح: قيمة لكل س في متتالية إن شرط}."""
    def __init__(self, key, value, clauses, line=None):
        super().__init__(line)
        self.key = key              # تعبير المفتاح
        self.value = value          # تعبير القيمة
        self.clauses = clauses


class BinOp(Node):
    def __init__(self, op, left, right, line=None):
        super().__init__(line)
        self.op = op
        self.left = left
        self.right = right


class UnaryOp(Node):
    def __init__(self, op, operand, line=None):
        super().__init__(line)
        self.op = op
        self.operand = operand


class Call(Node):
    def __init__(self, func, args, line=None):
        super().__init__(line)
        self.func = func
        self.args = args              # [(الاسم أو None، تعبير)، ...]


class Index(Node):
    def __init__(self, obj, index, line=None):
        super().__init__(line)
        self.obj = obj
        self.index = index


class Slice(Node):
    def __init__(self, obj, start, stop, step, line=None):
        super().__init__(line)
        self.obj = obj
        self.start = start
        self.stop = stop
        self.step = step


class MethodCall(Node):
    """استدعاء طريقة: الكائن.الطريقة(معاملات)"""

    def __init__(self, obj, name, args, line=None):
        super().__init__(line)
        self.obj = obj
        self.name = name
        self.args = args


class Attribute(Node):
    """وصول لخاصية بدون استدعاء: الوحدة.الثابت أو الكائن.الخاصية"""

    def __init__(self, obj, name, line=None):
        super().__init__(line)
        self.obj = obj
        self.name = name


class This(Node):
    """الكلمة المفتاحية 'هذا' — الكائن الحالي داخل طرق الصنف."""


class Super(Node):
    """الكلمة المفتاحية 'الأصل' — الصنف الأب داخل جسم الصنف."""


class Ternary(Node):
    """التعبير الثلاثي: لو شرط: قيمة1 وإلا قيمة2"""

    def __init__(self, test, if_true, if_false, line=None):
        super().__init__(line)
        self.test = test
        self.if_true = if_true
        self.if_false = if_false


class SpreadArg(Node):
    """تفكيك في استدعاء أو قائمة: دالة(...قائمة) أو [١، ...أخرى]."""

    def __init__(self, expr, line=None):
        super().__init__(line)
        self.expr = expr


class Await(Node):
    """انتظر مهمة — يوقف السطر الحالي حتى تنتهي المهمة ويعيد نتيجتها.

    المعامل يجب أن يكون قيمة 'مهمة' (نتيجة استدعاء دالة غير متزامنة).
    """

    def __init__(self, operand, line=None):
        super().__init__(line)
        self.operand = operand


class Lambda(Node):
    """دالة سهمية على سطر واحد: دالة(س، ص) => س + ص"""

    def __init__(self, params, body, line=None, rest=None, anns=None):
        super().__init__(line)
        self.params = params          # [(الاسم، تعبير الافتراضي أو None)، ...]
        self.body = body              # تعبير واحد
        self.rest = rest              # اسم المعامل المتغير ... أو None
        self.anns = anns or {}        # توصيفات المعاملات (1.26) — بلا إرجاع
