# -*- coding: utf-8 -*-
"""طبقة التشغيل: البيئات، القيم، الدوال الجاهزة، الوحدات، وطرق الأنواع."""

import json
import math
import os
import time
import random

from .errors import ArabiRuntimeError

AR2EN = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')


class _NoDefault:
    """حارس داخلي يمثل معاملًا بلا قيمة افتراضية."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return '<بلا افتراضي>'


NO_DEFAULT = _NoDefault()


def ar2en(text):
    return str(text).translate(AR2EN)


# ================== البيئات (النطاقات) ==================

class Env:
    """بيئة متغيرات مرتبطة بسلسلة أبوية للنطاقات المتداخلة."""

    __slots__ = ('vars', 'parent')

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def get(self, name, line=None):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise ArabiRuntimeError(
            f"المتغير '{name}' غير معرّف — تأكد من تعريفه أولًا", line)

    def set(self, name, value):
        """يعدّل المتغير إن وُجد في أي نطاق، وإلا ينشئه في النطاق الحالي."""
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        self.vars[name] = value

    def define(self, name, value):
        self.vars[name] = value


# ================== القيم ==================

class ArabiFunc:
    """دالة معرفة بلغة عربي نفسها.

    params قائمة أزواج (الاسم، القيمة الافتراضية أو NO_DEFAULT) —
    تُقيّم الافتراضات مرة واحدة عند التعريف (كما في بايثون).
    """

    __slots__ = ('name', 'params', 'body', 'env', 'is_lambda')

    def __init__(self, name, params, body, env, is_lambda=False):
        self.name = name
        self.params = params
        self.body = body
        self.env = env
        self.is_lambda = is_lambda


class BuiltinFunc:
    """دالة جاهزة مكتوبة بلغة بايثون.

    fn يستقبل (args: list, line: int) ويعيد قيمة.
    الدوال ذات الترتيب الأعلى (خريطة/مرشّح/اختزل) تستقبل
    المفسّر كأول معامل لتستطيع استدعاء دوال المستخدم:
    fn(interp, args, line).
    """

    __slots__ = ('name', 'fn', 'takes_interp')

    def __init__(self, name, fn, takes_interp=False):
        self.name = name
        self.fn = fn
        self.takes_interp = takes_interp


class ModuleValue:
    """وحدة (مكتبة) تحتوي على دوال وثوابت."""

    __slots__ = ('name', 'members')

    def __init__(self, name, members):
        self.name = name
        self.members = members


class ClassValue:
    """صنف معرّف من قبل المستخدم — قالب لإنشاء الكائنات.

    members يجمع الطرق (ArabiFunc) وثوابت الصنف.
    """

    __slots__ = ('name', 'superclass', 'members', 'env')

    def __init__(self, name, superclass, members, env):
        self.name = name
        self.superclass = superclass      # ClassValue أو None
        self.members = members
        self.env = env


class InstanceValue:
    """كائن (نموذج) منشأ من صنف — يحمل حقوله الخاصة."""

    __slots__ = ('cls', 'fields')

    def __init__(self, cls):
        self.cls = cls
        self.fields = {}


class BoundMethod:
    """طريقة مرتبطة بكائن — جاهزة للاستدعاء لاحقًا."""

    __slots__ = ('instance', 'func')

    def __init__(self, instance, func):
        self.instance = instance
        self.func = func


def typename(v):
    if v is None:
        return 'ولا شيء'
    if isinstance(v, bool):
        return 'قيمة منطقية'
    if isinstance(v, int):
        return 'عدد صحيح'
    if isinstance(v, float):
        return 'عدد عشري'
    if isinstance(v, str):
        return 'نص'
    if isinstance(v, list):
        return 'قائمة'
    if isinstance(v, dict):
        return 'قاموس'
    if isinstance(v, range):
        return 'مدى'
    if isinstance(v, (ArabiFunc, BuiltinFunc)):
        return 'دالة'
    if isinstance(v, ModuleValue):
        return 'وحدة'
    if isinstance(v, ClassValue):
        return 'صنف'
    if isinstance(v, InstanceValue):
        return 'كائن'
    if isinstance(v, BoundMethod):
        return 'طريقة'
    return type(v).__name__


def display(v):
    """عرض القيمة بشكل عربي جميل."""
    if isinstance(v, str):
        return v
    if v is None:
        return 'ولا شيء'
    if isinstance(v, bool):
        return 'صح' if v else 'خطأ'
    if isinstance(v, list):
        return '[' + '، '.join(display(x) for x in v) + ']'
    if isinstance(v, dict):
        return '{' + '، '.join(
            f'{display(k)}: {display(val)}' for k, val in v.items()) + '}'
    if isinstance(v, range):
        return f'مدى({v.start}, {v.stop}, {v.step})'
    if isinstance(v, ArabiFunc):
        if v.is_lambda:
            return '<دالة سهمية>'
        return f'<دالة {v.name}>'
    if isinstance(v, BuiltinFunc):
        return f'<دالة جاهزة {v.name}>'
    if isinstance(v, ModuleValue):
        return f'<وحدة {v.name}>'
    if isinstance(v, ClassValue):
        return f'<صنف {v.name}>'
    if isinstance(v, InstanceValue):
        return f'<كائن من صنف {v.cls.name}>'
    if isinstance(v, BoundMethod):
        return f'<طريقة {v.func.name}>'
    return str(v)


# ================== طرق الأنواع المدمجة ==================

def _require_args(name, args, minimum, maximum, line):
    if not (minimum <= len(args) <= maximum):
        if minimum == maximum:
            expected = f'{minimum}'
        else:
            expected = f'من {minimum} إلى {maximum}'
        raise ArabiRuntimeError(
            f"الطريقة '{name}' تتوقع {expected} معاملًا لكنها استلمت {len(args)}", line)


def _list_append(obj, args, line):
    _require_args('أضف', args, 1, 1, line)
    obj.append(args[0])
    return None


def _list_remove(obj, args, line):
    _require_args('أزل', args, 1, 1, line)
    try:
        obj.remove(args[0])
    except ValueError:
        raise ArabiRuntimeError(
            f"العنصر '{display(args[0])}' غير موجود في القائمة", line)
    return None


def _list_pop(obj, args, line):
    _require_args('انبثق', args, 0, 1, line)
    try:
        return obj.pop(args[0]) if args else obj.pop()
    except IndexError:
        raise ArabiRuntimeError('القائمة فارغة أو الفهرس خارج النطاق', line)


def _list_sort(obj, args, line):
    _require_args('رتب', args, 0, 0, line)
    try:
        obj.sort()
    except TypeError:
        raise ArabiRuntimeError('لا يمكن ترتيب عناصر من أنواع مختلفة', line)
    return None


def _list_reverse(obj, args, line):
    _require_args('اعكس', args, 0, 0, line)
    obj.reverse()
    return None


def _list_clear(obj, args, line):
    _require_args('امسح', args, 0, 0, line)
    obj.clear()
    return None


def _list_count(obj, args, line):
    _require_args('عدد_التكرار', args, 1, 1, line)
    return obj.count(args[0])


def _list_copy(obj, args, line):
    _require_args('انسخ', args, 0, 0, line)
    return obj.copy()


def _str_replace(obj, args, line):
    _require_args('استبدل', args, 2, 2, line)
    old, new = args
    if not isinstance(old, str) or not isinstance(new, str):
        raise ArabiRuntimeError("طريقة 'استبدل' تحتاج نصين", line)
    return obj.replace(old, new)


def _str_split(obj, args, line):
    _require_args('قسّم', args, 1, 1, line)
    sep = args[0]
    if not isinstance(sep, str) or sep == '':
        raise ArabiRuntimeError("طريقة 'قسّم' تحتاج فاصلًا نصيًا غير فارغ", line)
    return obj.split(sep)


def _str_strip(obj, args, line):
    _require_args('شريط', args, 0, 0, line)
    return obj.strip()


def _str_startswith(obj, args, line):
    _require_args('يبدأ_بـ', args, 1, 1, line)
    if not isinstance(args[0], str):
        raise ArabiRuntimeError("طريقة 'يبدأ_بـ' تحتاج نصًا", line)
    return obj.startswith(args[0])


def _str_endswith(obj, args, line):
    _require_args('ينتهي_بـ', args, 1, 1, line)
    if not isinstance(args[0], str):
        raise ArabiRuntimeError("طريقة 'ينتهي_بـ' تحتاج نصًا", line)
    return obj.endswith(args[0])


def _str_upper(obj, args, line):
    _require_args('كبير', args, 0, 0, line)
    return obj.upper()


def _str_lower(obj, args, line):
    _require_args('صغير', args, 0, 0, line)
    return obj.lower()


def _str_join(obj, args, line):
    _require_args('اجمع', args, 1, 1, line)
    seq = args[0]
    if not isinstance(seq, list):
        raise ArabiRuntimeError("طريقة 'اجمع' تحتاج قائمة نصوص", line)
    for item in seq:
        if not isinstance(item, str):
            raise ArabiRuntimeError('جميع عناصر القائمة يجب أن تكون نصوصًا', line)
    return obj.join(seq)


def _str_find(obj, args, line):
    """أوجد(نص) — فهرس أول ظهور أو ١- إذا لم يوجد."""
    _require_args('أوجد', args, 1, 1, line)
    if not isinstance(args[0], str):
        raise ArabiRuntimeError("طريقة 'أوجد' تحتاج نصًا", line)
    return obj.find(args[0])


def _str_contains(obj, args, line):
    """يحتوي(نص) — صح إذا كان النص المطلوب جزءًا من النص."""
    _require_args('يحتوي', args, 1, 1, line)
    if not isinstance(args[0], str):
        raise ArabiRuntimeError("طريقة 'يحتوي' تحتاج نصًا", line)
    return args[0] in obj


def _str_count(obj, args, line):
    """عدد_التكرار(نص) — كم مرة يظهر النص المطلوب."""
    _require_args('عدد_التكرار', args, 1, 1, line)
    if not isinstance(args[0], str):
        raise ArabiRuntimeError("طريقة 'عدد_التكرار' تحتاج نصًا", line)
    return obj.count(args[0])


def _str_reverse(obj, args, line):
    """اعكس() — يعيد النص معكوسًا (النصوص غير قابلة للتعديل)."""
    _require_args('اعكس', args, 0, 0, line)
    return obj[::-1]


def _dict_keys(obj, args, line):
    _require_args('مفاتيح', args, 0, 0, line)
    return list(obj.keys())


def _dict_values(obj, args, line):
    _require_args('قيم', args, 0, 0, line)
    return list(obj.values())


def _dict_items(obj, args, line):
    _require_args('عناصر', args, 0, 0, line)
    return [[k, v] for k, v in obj.items()]


def _dict_delete(obj, args, line):
    _require_args('احذف', args, 1, 1, line)
    key = args[0]
    if key in obj:
        del obj[key]
        return None
    raise ArabiRuntimeError(f"المفتاح '{display(key)}' غير موجود في القاموس", line)


def _dict_clear(obj, args, line):
    _require_args('امسح', args, 0, 0, line)
    obj.clear()
    return None


LIST_METHODS = {
    'أضف': _list_append,
    'أزل': _list_remove,
    'انبثق': _list_pop,
    'رتب': _list_sort,
    'اعكس': _list_reverse,
    'امسح': _list_clear,
    'عدد_التكرار': _list_count,
    'انسخ': _list_copy,
}

STR_METHODS = {
    'استبدل': _str_replace,
    'قسّم': _str_split,
    'شريط': _str_strip,
    'يبدأ_بـ': _str_startswith,
    'ينتهي_بـ': _str_endswith,
    'كبير': _str_upper,
    'صغير': _str_lower,
    'اجمع': _str_join,
    'أوجد': _str_find,
    'يحتوي': _str_contains,
    'عدد_التكرار': _str_count,
    'اعكس': _str_reverse,
}

DICT_METHODS = {
    'مفاتيح': _dict_keys,
    'قيم': _dict_values,
    'عناصر': _dict_items,
    'احذف': _dict_delete,
    'امسح': _dict_clear,
}


# ================== الدوال الجاهزة ==================

def _num_check(v, what, line):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ArabiRuntimeError(f'{what} يحتاج عددًا لكن استلم {typename(v)}', line)
    return v


def _bi_print(args, line):
    print(' '.join(display(a) for a in args))
    return None


def _bi_len(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError(f"'طول' تتوقع معاملًا واحدًا لكنها استلمت {len(args)}", line)
    v = args[0]
    if isinstance(v, (str, list, dict, range)):
        return len(v)
    raise ArabiRuntimeError(f"لا يمكن حساب طول {typename(v)}", line)


def _bi_range(args, line):
    if not 1 <= len(args) <= 3:
        raise ArabiRuntimeError(f"'مدى' تتوقع من 1 إلى 3 معاملات لكنها استلمت {len(args)}", line)
    nums = []
    for a in args:
        if isinstance(a, bool) or not isinstance(a, int):
            raise ArabiRuntimeError(f"'مدى' تحتاج أعدادًا صحيحة لكن استلمت {typename(a)}", line)
        nums.append(a)
    try:
        return range(*nums)
    except ValueError as exc:
        raise ArabiRuntimeError(f"مدى غير صالح: {exc}", line)


def _bi_input(args, line):
    if len(args) > 1:
        raise ArabiRuntimeError(f"'إدخال' تتوقع معاملًا واحدًا كحد أقصى", line)
    prompt = display(args[0]) if args else ''
    try:
        return input(prompt)
    except EOFError:
        return ''


def _bi_int(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError(f"'عدد' تتوقع معاملًا واحدًا", line)
    v = args[0]
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = ar2en(v).strip()
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                raise ArabiRuntimeError(
                    f"لا يمكن تحويل النص '{v}' إلى عدد صحيح", line)
    raise ArabiRuntimeError(f'لا يمكن تحويل {typename(v)} إلى عدد صحيح', line)


def _bi_float(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError(f"'عشري' تتوقع معاملًا واحدًا", line)
    v = args[0]
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(ar2en(v).strip())
        except ValueError:
            raise ArabiRuntimeError(
                f"لا يمكن تحويل النص '{v}' إلى عدد عشري", line)
    raise ArabiRuntimeError(f'لا يمكن تحويل {typename(v)} إلى عدد عشري', line)


def _bi_str(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError(f"'نص' تتوقع معاملًا واحدًا", line)
    return display(args[0])


def _bi_list(args, line):
    if len(args) > 1:
        raise ArabiRuntimeError(f"'قائمة' تتوقع معاملًا واحدًا كحد أقصى", line)
    if not args:
        return []
    v = args[0]
    if isinstance(v, (list, range)):
        return list(v)
    if isinstance(v, str):
        return list(v)
    if isinstance(v, dict):
        return list(v.keys())
    raise ArabiRuntimeError(f'لا يمكن تحويل {typename(v)} إلى قائمة', line)


def _bi_dict(args, line):
    if not args:
        return {}
    if len(args) == 1 and isinstance(args[0], list):
        result = {}
        for i, pair in enumerate(args[0]):
            if isinstance(pair, list) and len(pair) == 2:
                result[pair[0]] = pair[1]
            else:
                raise ArabiRuntimeError(
                    f'العنصر رقم {i + 1} ليس زوجًا [مفتاح، قيمة]', line)
        return result
    raise ArabiRuntimeError("'قاموس' تقبل لا معاملات أو قائمة أزواج", line)


def _bi_sum(args, line):
    if len(args) != 1 or not isinstance(args[0], (list, range)):
        raise ArabiRuntimeError("'جمع' تحتاج قائمة أعداد", line)
    total = 0
    for x in args[0]:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ArabiRuntimeError(
                f"'جمع' تحتاج أعدادًا فقط لكن وجدت {typename(x)}", line)
        total += x
    return total


def _min_max(args, line, fn, name):
    seq = args[0] if len(args) == 1 else list(args)
    if len(args) == 1 and not isinstance(seq, (list, range)):
        raise ArabiRuntimeError(f"'{name}' تقبل قائمة أو عدة أعداد", line)
    items = list(seq)
    if not items:
        raise ArabiRuntimeError(f"'{name}' لا تقبل قائمة فارغة", line)
    for x in items:
        if isinstance(x, bool) or not isinstance(x, (int, float, str)):
            raise ArabiRuntimeError(
                f"'{name}' تحتاج أعدادًا أو نصوصًا فقط لكن وجدت {typename(x)}", line)
    try:
        return fn(items)
    except TypeError:
        raise ArabiRuntimeError('لا يمكن المقارنة بين أنواع مختلفة', line)


def _bi_max(args, line):
    return _min_max(args, line, max, 'أكبر')


def _bi_min(args, line):
    return _min_max(args, line, min, 'أصغر')


def _bi_abs(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError("'مطلق' تتوقع معاملًا واحدًا", line)
    return abs(_num_check(args[0], "'مطلق'", line))


def _bi_round(args, line):
    if not 1 <= len(args) <= 2:
        raise ArabiRuntimeError("'تقريب' تتوقع معاملًا أو معاملين", line)
    x = _num_check(args[0], "'تقريب'", line)
    if len(args) == 2:
        n = args[1]
        if isinstance(n, bool) or not isinstance(n, int):
            raise ArabiRuntimeError("معامل المنازل في 'تقريب' يجب أن يكون عددًا صحيحًا", line)
        return round(x, n)
    return round(x)


def _bi_random(args, line):
    if len(args) != 2:
        raise ArabiRuntimeError("'عشوائي' تحتاج عددين (الأدنى والأعلى)", line)
    a = args[0]
    b = args[1]
    for x in (a, b):
        if isinstance(x, bool) or not isinstance(x, int):
            raise ArabiRuntimeError("'عشوائي' تحتاج عددين صحيحين", line)
    if a > b:
        a, b = b, a
    return random.randint(a, b)


def _bi_type(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError("'نوع' تتوقع معاملًا واحدًا", line)
    return typename(args[0])


def _bi_sorted(args, line):
    if len(args) != 1 or not isinstance(args[0], (list, range)):
        raise ArabiRuntimeError("'رتّب' تحتاج قائمة", line)
    items = list(args[0])
    for x in items:
        if isinstance(x, bool) or not isinstance(x, (int, float, str)):
            raise ArabiRuntimeError(
                f"'رتّب' تحتاج أعدادًا أو نصوصًا فقط لكن وجدت {typename(x)}", line)
    try:
        return sorted(items)
    except TypeError:
        raise ArabiRuntimeError('لا يمكن ترتيب عناصر من أنواع مختلفة', line)


def install_builtins(env):
    """يثبت الدوال الجاهزة والوحدات في البيئة العامة."""
    builtins_list = [
        ('اطبع', _bi_print),
        ('طول', _bi_len),
        ('مدى', _bi_range),
        ('إدخال', _bi_input),
        ('عدد', _bi_int),
        ('عشري', _bi_float),
        ('نص', _bi_str),
        ('قائمة', _bi_list),
        ('قاموس', _bi_dict),
        ('جمع', _bi_sum),
        ('أكبر', _bi_max),
        ('أصغر', _bi_min),
        ('مطلق', _bi_abs),
        ('تقريب', _bi_round),
        ('عشوائي', _bi_random),
        ('اختر', _bi_choose),
        ('نوع', _bi_type),
        ('رتّب', _bi_sorted),
        ('خريطة', BuiltinFunc('خريطة', _hi_map, takes_interp=True)),
        ('مرشّح', BuiltinFunc('مرشّح', _hi_filter, takes_interp=True)),
        ('اختزل', BuiltinFunc('اختزل', _hi_reduce, takes_interp=True)),
    ]
    for name, fn in builtins_list:
        if isinstance(fn, BuiltinFunc):          # دوال جاهزة مغلفة مسبقًا
            env.define(name, fn)
        else:
            env.define(name, BuiltinFunc(name, fn))

    env.define('رياضيات', ModuleValue('رياضيات', {
        'جذر': BuiltinFunc('جذر', _math_sqrt),
        'سقف': BuiltinFunc('سقف', _math_ceil),
        'أرضية': BuiltinFunc('أرضية', _math_floor),
        'لوغاريتم': BuiltinFunc('لوغاريتم', _math_log),
        'جيب': BuiltinFunc('جيب', _math_sin),
        'جيب_التام': BuiltinFunc('جيب_التام', _math_cos),
        'ظل': BuiltinFunc('ظل', _math_tan),
        'بي': math.pi,
        'نيبير': math.e,
    }))

    env.define('وقت', ModuleValue('وقت', {
        'زمن': BuiltinFunc('زمن', _time_now),
        'نوم': BuiltinFunc('نوم', _time_sleep),
    }))

    env.define('ملفات', ModuleValue('ملفات', {
        'اقرأ': BuiltinFunc('اقرأ', _file_read),
        'اكتب': BuiltinFunc('اكتب', _file_write),
        'أضف': BuiltinFunc('أضف', _file_append),
        'أسطر': BuiltinFunc('أسطر', _file_lines),
        'موجود': BuiltinFunc('موجود', _file_exists),
        'احذف': BuiltinFunc('احذف', _file_delete),
    }))

    env.define('جيسون', ModuleValue('جيسون', {
        'حلل': BuiltinFunc('حلل', _json_parse),
        'نص': BuiltinFunc('نص', _json_text),
    }))


def _one_num(args, name, line):
    if len(args) != 1:
        raise ArabiRuntimeError(f"'{name}' تتوقع معاملًا واحدًا", line)
    return _num_check(args[0], f"'{name}'", line)


def _math_sqrt(args, line):
    x = _one_num(args, 'جذر', line)
    if x < 0:
        raise ArabiRuntimeError('لا يوجد جذر تربيعي لعدد سالب', line)
    return math.sqrt(x)


def _math_ceil(args, line):
    return math.ceil(_one_num(args, 'سقف', line))


def _math_floor(args, line):
    return math.floor(_one_num(args, 'أرضية', line))


def _math_log(args, line):
    if len(args) not in (1, 2):
        raise ArabiRuntimeError("'لوغاريتم' تتوقع معاملًا أو معاملين", line)
    x = _one_num(args[:1], 'لوغاريتم', line)
    base = _one_num(args[1:], 'لوغاريتم', line) if len(args) == 2 else math.e
    if x <= 0:
        raise ArabiRuntimeError('اللوغاريتم يحتاج عددًا أكبر من صفر', line)
    return math.log(x, base)


def _trig(fn, name):
    def wrapper(args, line):
        return fn(_one_num(args, name, line))
    return wrapper


_math_sin = _trig(math.sin, 'جيب')
_math_cos = _trig(math.cos, 'جيب_التام')
_math_tan = _trig(math.tan, 'ظل')


def _time_now(args, line):
    if args:
        raise ArabiRuntimeError("'زمن' لا تقبل معاملات", line)
    return time.time()


def _time_sleep(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError("'نوم' تتوقع معاملًا واحدًا (عدد الثواني)", line)
    seconds = _num_check(args[0], "'نوم'", line)
    if seconds < 0:
        raise ArabiRuntimeError('عدد الثواني يجب أن يكون موجبًا', line)
    time.sleep(seconds)
    return None


# ================== الدوال ذات الترتيب الأعلى ==================

_CALLABLES = (ArabiFunc, BuiltinFunc, BoundMethod)


def _callable(value, name, line):
    if not isinstance(value, _CALLABLES):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج دالة كمعامل أول لكن استلمت {typename(value)}", line)
    return value


def _iterable(value, name, line):
    if isinstance(value, (list, range)):
        return list(value)
    if isinstance(value, str):
        return list(value)
    raise ArabiRuntimeError(
        f"'{name}' تحتاج قائمة أو نصًا أو مدى لكن استلمت {typename(value)}", line)


def _hi_map(interp, args, line):
    """خريطة(دالة، تسلسل) — تطبق الدالة على كل عنصر وتعيد قائمة النتائج."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'خريطة' تحتاج معاملين (دالة وتسلسل) لكنها استلمت {len(args)}", line)
    func = _callable(args[0], 'خريطة', line)
    items = _iterable(args[1], 'خريطة', line)
    return [interp._call_value(func, [x], {}, line) for x in items]


def _hi_filter(interp, args, line):
    """مرشّح(دالة، تسلسل) — يعيد العناصر التي أعادت الدالة لها صح."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'مرشّح' تحتاج معاملين (دالة وتسلسل) لكنها استلمت {len(args)}", line)
    func = _callable(args[0], 'مرشّح', line)
    items = _iterable(args[1], 'مرشّح', line)
    return [x for x in items if interp._call_value(func, [x], {}, line)]


def _hi_reduce(interp, args, line):
    """اختزل(دالة، تسلسل، بداية؟) — يطوي التسلسل لقيمة واحدة.

    بدون قيمة بداية يستخدم أول عنصر كنقطة انطلاق.
    """
    if not 2 <= len(args) <= 3:
        raise ArabiRuntimeError(
            f"'اختزل' تحتاج معاملين أو ثلاثة (دالة وتسلسل وقيمة بداية اختيارية) "
            f'لكنها استلمت {len(args)}', line)
    func = _callable(args[0], 'اختزل', line)
    items = list(_iterable(args[1], 'اختزل', line))
    if len(args) == 3:
        acc = args[2]
    else:
        if not items:
            raise ArabiRuntimeError(
                "'اختزل' لا تقبل تسلسلًا فارغًا بدون قيمة بداية", line)
        acc = items.pop(0)
    for x in items:
        acc = interp._call_value(func, [acc, x], {}, line)
    return acc


def _bi_choose(args, line):
    """اختر(قائمة) — يعيد عنصرًا عشوائيًا."""
    if len(args) != 1:
        raise ArabiRuntimeError("'اختر' تتوقع معاملًا واحدًا", line)
    if not isinstance(args[0], (list, range, str)):
        raise ArabiRuntimeError(
            f"'اختر' تحتاج قائمة أو نصًا أو مدى لكن استلمت {typename(args[0])}", line)
    items = list(args[0])
    if not items:
        raise ArabiRuntimeError("'اختر' لا تقبل تسلسلًا فارغًا", line)
    return random.choice(items)


# ================== وحدة ملفات ==================

def _path_str(value, name, line):
    if not isinstance(value, str):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج مسار نصي لكن استلمت {typename(value)}", line)
    return value


def _file_read(args, line):
    """اقرأ(مسار) — يعيد محتوى الملف كنص."""
    if len(args) != 1:
        raise ArabiRuntimeError("'اقرأ' تتوقع معاملًا واحدًا (المسار)", line)
    path = _path_str(args[0], 'اقرأ', line)
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise ArabiRuntimeError(f"الملف '{path}' غير موجود", line)
    except UnicodeDecodeError:
        raise ArabiRuntimeError(
            f"الملف '{path}' يجب أن يكون بترميز UTF-8", line)
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن قراءة الملف '{path}': {exc}", line)


def _file_write(args, line):
    """اكتب(مسار، نص) — يكتب النص فوق محتوى الملف (أو ينشئه)."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'اكتب' تحتاج معاملين (المسار والنص) لكنها استلمت {len(args)}", line)
    path = _path_str(args[0], 'اكتب', line)
    text = args[1]
    if not isinstance(text, str):
        raise ArabiRuntimeError(
            f"محتوى الملف يجب أن يكون نصًا لكن استلمت {typename(text)}", line)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return None
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن كتابة الملف '{path}': {exc}", line)


def _file_append(args, line):
    """أضف(مسار، نص) — يضيف النص إلى نهاية الملف."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'أضف' تحتاج معاملين (المسار والنص) لكنها استلمت {len(args)}", line)
    path = _path_str(args[0], 'أضف', line)
    text = args[1]
    if not isinstance(text, str):
        raise ArabiRuntimeError(
            f"محتوى الإضافة يجب أن يكون نصًا لكن استلمت {typename(text)}", line)
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(text)
        return None
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن الإضافة إلى الملف '{path}': {exc}", line)


def _file_lines(args, line):
    """أسطر(مسار) — يعيد أسطر الملف قائمة (دون رموز السطر الجديد)."""
    if len(args) != 1:
        raise ArabiRuntimeError("'أسطر' تتوقع معاملًا واحدًا (المسار)", line)
    path = _path_str(args[0], 'أسطر', line)
    try:
        with open(path, encoding='utf-8') as f:
            return f.read().splitlines()
    except FileNotFoundError:
        raise ArabiRuntimeError(f"الملف '{path}' غير موجود", line)
    except UnicodeDecodeError:
        raise ArabiRuntimeError(
            f"الملف '{path}' يجب أن يكون بترميز UTF-8", line)
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن قراءة الملف '{path}': {exc}", line)


def _file_exists(args, line):
    """موجود(مسار) — صح إن كان المسار موجودًا."""
    if len(args) != 1:
        raise ArabiRuntimeError("'موجود' تتوقع معاملًا واحدًا (المسار)", line)
    path = _path_str(args[0], 'موجود', line)
    return os.path.exists(path)


def _file_delete(args, line):
    """احذف(مسار) — يحذف الملف ويعيد صح، أو خطأ إن لم يوجد."""
    if len(args) != 1:
        raise ArabiRuntimeError("'احذف' تتوقع معاملًا واحدًا (المسار)", line)
    path = _path_str(args[0], 'احذف', line)
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن حذف الملف '{path}': {exc}", line)


# ================== وحدة جيسون ==================

def _json_parse(args, line):
    """حلل(نص) — يحلل نص JSON ويعيد القيمة المقابلة.

    يقبل JSON القياسي أولًا، وإن فشل يعيد المحاولة بعد تحويل
    الأرقام العربية الشرقية (٠-٩) إلى غربية — رحمةً بالمستخدم العربي.
    """
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError(
            f"'حلل' تحتاج نصًا واحدًا لكنها استلمت "
            f"{typename(args[0]) if args else 'لا معاملات'}", line)
    try:
        return json.loads(args[0])
    except json.JSONDecodeError:
        pass
    # محاولة ثانية: تحويل الأرقام الشرقية والفاصلة العربية
    try:
        return json.loads(ar2en(args[0]).replace('،', ','))
    except json.JSONDecodeError as exc:
        raise ArabiRuntimeError(
            f"نص JSON غير صالح عند الموضع {exc.pos}: {exc.msg}", line)


def _json_text(args, line):
    """نص(قيمة) — يحول قيمة إلى نص JSON (يحافظ على العربية)."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'نص' تتوقع معاملًا واحدًا لكنها استلمت {len(args)}", line)
    try:
        return json.dumps(args[0], ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ArabiRuntimeError(
            f"لا يمكن تحويل {typename(args[0])} إلى JSON: {exc}", line)
