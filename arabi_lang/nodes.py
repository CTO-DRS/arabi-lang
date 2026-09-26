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


class FuncDef(Node):
    def __init__(self, name, params, body, line=None):
        super().__init__(line)
        self.name = name
        self.params = params      # [(الاسم، تعبير الافتراضي أو None)، ...]
        self.body = body


class Return(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value          # تعبير أو None


class Break(Node):
    pass


class Continue(Node):
    pass


class Pass(Node):
    pass


class Try(Node):
    def __init__(self, body, except_body, finally_body, line=None):
        super().__init__(line)
        self.body = body
        self.except_body = except_body    # [stmt] أو None
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
    """تعريف صنف: صنف الاسم من الأصل: ..."""

    def __init__(self, name, superclass, body, line=None):
        super().__init__(line)
        self.name = name
        self.superclass = superclass      # اسم الصنف الأصل أو None
        self.body = body                  # [FuncDef | Assign]


class Switch(Node):
    """بدّل التعبير: ينفذ كتلة الحالة المطابقة فقط (بدون تساقط).

    cases: [(تعبير القيمة، [جمل])، ...]
    """

    def __init__(self, subject, cases, default_body, line=None):
        super().__init__(line)
        self.subject = subject
        self.cases = cases
        self.default_body = default_body  # [stmt] أو None


# ================== تعبيرات (Expressions) ==================

class Num(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value


class Str(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value


class Bool(Node):
    def __init__(self, value, line=None):
        super().__init__(line)
        self.value = value


class Null(Node):
    pass


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


class Lambda(Node):
    """دالة سهمية على سطر واحد: دالة(س، ص) => س + ص"""

    def __init__(self, params, body, line=None):
        super().__init__(line)
        self.params = params          # [(الاسم، تعبير الافتراضي أو None)، ...]
        self.body = body              # تعبير واحد
