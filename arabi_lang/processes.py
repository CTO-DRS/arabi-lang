# -*- coding: utf-8 -*-
"""توازي العمليات (الإصدار 1.17) — تشغيل الأعمال المكثفة حسابيًا في
معالجات منفصلة حقيقية تتجاوز قفل التفسير العالمي لبايثون (GIL).

الفلسفة:
- وحدة 'عمليات' تحاكي واجهة 'خيوط' و'تجمع' المعروفتين: شغّل/تجمع/قدّم/
  إنهاء/حجم، مع طرق نتيجة/الخطأ/جاهز/انتظر/معرف — فمن يعرف الخيوط
  يعرف العمليات، والفرق الوحيد أن كل عمل يعمل في معالج مستقل ب内اكرة
  معزولة، فتستفيد الأعمال الحسابية الخالصة من كل أنوية المعالج.
- النقل بين العمليات يتم بترميز القيم (encode/decode) إلى بنى بيانات
  بسيطة قابلة للتنقيط (pickle): الأعداد والنصوص والقوائم والقواميس
  والدوال العربية (بجسمها وإغلاقها بالكامل) والأصناف والكائنات
  والتعدادات. أما الكائنات الحية المرتبطة بخيوط المفسّر (خيوط ومهام
  وأقفال وطوابير ومولدات وتواريخ وقواعد بيانات) فلا تعبر حدود العملية
  — وتُرفض برسالة عربية واضحة لحظة التقديم لا بعد فوات الأوان.
- العملية الابنة تبني مفسّرًا جديدًا كاملًا (بكل الوحدات الجاهزة)، ثم
  تعيد بناء الربط العالمي المرسل وترمّز النتيجة عائدة — فالدالة التي
  تستدعي دوالًا عالمية أخرى أو أصنافًا تعمل في الابن كما تعمل في الأب.
- كل التوظيف عبر multiprocessing بنمط 'spawn' على كل الأنظمة — دلالات
  موحدة، وآمن مع خيوط المفسّر (التشعب fork مع خيوط نشطة مصدر تعليق).

هذا الملف يحمّل من runtime.py اسماء القيم فقط — وruntime لا يستورد
هذا الملف إلا داخل دالة التثبيت (بعد اكتمال تعريفه) تفاديًا للدورانية.
"""

import os
import pickle
import threading

import multiprocessing

_CTX = None            # سياق multiprocessing الموحد (spawn على كل الأنظمة)


def _mp():
    """يعيد سياق multiprocessing الموحد ('spawn' على كل الأنظمة)."""
    global _CTX
    if _CTX is None:
        _CTX = multiprocessing.get_context('spawn')
    return _CTX


from .errors import ArabiError, ArabiRuntimeError, ArabiUserError
from .runtime import (
    ArabiFunc, BuiltinFunc, BoundMethod, ClassValue, InstanceValue,
    Property, NativeCtor, EnumValue, EnumMember, Env, NO_DEFAULT,
    _VM_PENDING, TaskValue, typename, ModuleValue, GeneratorValue,
    DBValue, SuperValue, ThreadValue, LockValue, QueueValue, PoolValue,
    ProcessValue, ProcessTaskValue, ProcessPoolValue, DateValue,
    DispatcherValue, DistributedTaskValue,
)

# القيم الحية المرتبطة بخيوط/عمليات الأب — تُتخطى صامتة في الربط
# العالمي (لا معنى لها في الابن)، وتُرفض صراحة كوسائط/نتائج.
# والقيم الموزعة (الموزع ومهامه) حية كذلك: مرتبطة بخادم الشبكة (1.18).
LIVE_TYPES = (GeneratorValue, DBValue, SuperValue, ThreadValue,
              LockValue, QueueValue, TaskValue, PoolValue, ProcessValue,
              ProcessTaskValue, ProcessPoolValue, DateValue,
              DispatcherValue, DistributedTaskValue)

# أنواع القيم الحية التي لا تعبر حدود العملية — تُتخطى صامتة في الربط
# العالمي (الابن يبني وحداته الخاصة)، وتُرفض صراحة كوسائط/نتائج.

PROCESS_TIMEOUT = 120        # مهلة انتظار نتيجة العملية الواحدة (ثوان)
POOL_MAX_SIZE = 64           # حد أعلى لعدد عمليات التجمع (العمليات أثقل من الخيوط)


# ================== ترميز القيم (الاتجاه: قيمة ← بنية قابلة للتنقيط) ==================
#
# كل ترميز بقاموس يحمل مفتاحًا مميزًا يبدأ بـ '__' ليمنح التصادم مع
# القواميس العادية، والقواميس العادية نفسها تُغلَّف بـ '__قاموس__'.

def _make_enc_ctx(root):
    """يبني سياق ترميز كاملًا: الجذر + كشف التعود + خريطة الدوال
    الجاهزة بمواقعها — الدالة المستوردة من وحدة (مثل شغّل من عمليات)
    تُرمّز بموقعها (الوحدة، العضو) ليجدها الابن في وحداته الخاصة."""
    from .runtime import ModuleValue
    ctx = {'root': root, 'stack': set(), 'builtins_map': {}}
    bmap = ctx['builtins_map']
    # الوحدات أولًا — مواقعها لها الأولوية (الاسم المستورد في الجذر
    # هو نفس كائن العضو، فلا يجوز أن يطغى عليّه تسجيل «عليا مباشرة»)
    for name, val in root.vars.items():
        if isinstance(val, ModuleValue):
            for mname, member in val.members.items():
                if isinstance(member, BuiltinFunc):
                    bmap[id(member)] = (name, mname)
    for name, val in root.vars.items():
        if isinstance(val, BuiltinFunc) and id(val) not in bmap:
            bmap[id(val)] = None            # جاهزة عليا مباشرة (طباعة...)
    return ctx


def encode_value(v, ctx, line=None):
    """يرمز قيمة عربية إلى بنية قابلة للتنقيط تعبر العملية.

    ctx قاموس فيه: 'root' البيئة العالمية المصدر، و'stack' مجموعة
    معرفات النطاقات قيد الترميز لكشف الإغلاق المتعود.
    القيم غير القابلة للنقل تُرفض بخطأ تشغيلي عربي واضح.
    """
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, list):
        return [encode_value(x, ctx, line) for x in v]
    if isinstance(v, dict):
        return {'__قاموس__': {
            encode_value(k, ctx, line): encode_value(x, ctx, line)
            for k, x in v.items()}}
    if isinstance(v, range):
        return {'__مدى__': [v.start, v.stop, v.step]}
    if isinstance(v, ArabiFunc):
        return {'__دالة__': _encode_func(v, ctx, line)}
    if isinstance(v, BuiltinFunc):
        loc = ctx.get('builtins_map', {}).get(id(v))
        if loc:
            return {'__جاهزة__': [loc[0], loc[1]]}
        return {'__جاهزة__': v.name}
    if isinstance(v, BoundMethod):
        return {'__مربوطة__': (encode_value(v.instance, ctx, line),
                               encode_value(v.func, ctx, line))}
    if isinstance(v, ClassValue):
        return {'__صنف__': _encode_class(v, ctx, line)}
    if isinstance(v, InstanceValue):
        return {'__كائن__': (v.cls.name,
                             {k: encode_value(x, ctx, line)
                              for k, x in v.fields.items()})}
    if isinstance(v, EnumValue):
        return {'__تعداد__': (v.name,
                              {k: encode_value(m.value, ctx, line)
                               for k, m in v.members.items()})}
    if isinstance(v, EnumMember):
        return {'__عضو__': (v.enum_name, v.name)}
    raise ArabiRuntimeError(
        f'لا يمكن إرسال {typename(v)} إلى عملية منفصلة — القيم '
        'القابلة للنقل: الأعداد والنصوص والقوائم والقواميس والدوال '
        'والأصناف والكائنات والتعدادات (الكائنات الحية كالخيوط '
        'والمهام والأقفال والمولدات تعمل داخل العملية الواحدة فقط)',
        line)


# مرجع ذاتي: عند ترميز دالة فإذا ظهرت هي نفسها بين قيم إغلاقها
# (نمط المصنع: الدالة المعادة تُحفظ في نطاقها المحلي) تُرمّز بهذه
# العلامة وتُستبدل بعد بناء الدالة في الجهة المقابلة.
class _SelfMarker:
    """حارس داخلي للمرجع الذاتي في سلاسل الإغلاق."""


_SELF_MARKER = _SelfMarker()
_SELF_PLACEHOLDER = _SelfMarker()


def _encode_func(f, ctx, line, top=None):
    """يرمز دالة عربية: ترويستها وجسمها (شجرة الجمل تُنقّط كما هي)
    وسلسلة نطاقات إغلاقها طبقة طبقة حتى الجذر (الجذر يُشار إليه
    بمفتاح مستقل لأن الابن يعيد بناءه من قسم 'عالمي' في الحزمة).
    top هي الدالة قيد الترميز — ظهورها في نطاقاتها يُرمّز مرجعًا ذاتيًا."""
    top = top if top is not None else f
    layers, pushed = [], []
    cur = f.env
    while cur.parent is not None:
        if id(cur) in ctx['stack']:
            raise ArabiRuntimeError(
                "لا يمكن إرسال دالة إغلاقها متعود — نطاق يحتوي الدالة "
                'يشير إليها بدوره', line)
        ctx['stack'].add(id(cur))
        pushed.append(id(cur))
        layers.append({
            name: (_SELF_MARKER if val is top
                   else encode_value(val, ctx, line))
            for name, val in cur.vars.items()})
        cur = cur.parent
    params = []
    for name, default in f.params:
        if default is NO_DEFAULT:
            params.append([name, False, None])
        else:
            params.append([name, True, encode_value(default, ctx, line)])
    payload = {
        'الاسم': f.name,
        'المعاملات': params,
        'المتغير': f.rest,
        'الجسم': f.body,
        'سهمية': f.is_lambda,
        'مولدة': f.is_generator,
        'غير_متزامنة': f.is_async,
        'السلسلة': layers,
    }
    for pid in pushed:
        ctx['stack'].discard(pid)
    return payload


def _encode_class(cls, ctx, line):
    """يرمز صنفًا بنيويًا: اسمه وأصوله بالأسماء وأعضاؤه (طرق/خصائص/
    منشئ أصلي/ثوابت). الأسلاف الكاملة (mro) تُنقل بالأسماء ويُعاد
    بناؤها في الجهة المقابلة فتعمل الوراثة المتعددة كما هي."""
    members = {}
    for name, m in cls.members.items():
        if isinstance(m, ArabiFunc):
            members[name] = {'__دالة__': _encode_func(m, ctx, line)}
        elif isinstance(m, Property):
            members[name] = {'__خاصية__': _encode_func(m.func, ctx, line)}
        elif isinstance(m, NativeCtor):
            members[name] = {'__منشئ__': m.kind}
        else:
            members[name] = encode_value(m, ctx, line)
    ancestors = [c.name for c in cls.mro[1:]] if cls.mro else []
    return {
        'الاسم': cls.name,
        'الأصل': cls.superclass.name if cls.superclass else None,
        'الأسلاف': ancestors,
        'الأعضاء': members,
        'واجهة': cls.is_interface,
        'مجردة': list(cls.abstract),
    }


def _contains_live(v, depth=0):
    """هل تحوي القيمة (عبر قوائم وقواميس متداخلة) كائنًا حيًا لا يعبر
    العملية؟ تُستخدم لتخطي هذه الربطات العالمي صامتة — أما الوظائف
    فسلاسلها تُفحص في ترميزها الخاص."""
    if depth > 12:
        return True
    if isinstance(v, LIVE_TYPES):
        return True
    if isinstance(v, list):
        return any(_contains_live(x, depth + 1) for x in v)
    if isinstance(v, dict):
        return any(_contains_live(k, depth + 1)
                   or _contains_live(x, depth + 1)
                   for k, x in v.items())
    return False


def _encode_root(root, ctx, line=None):
    """يرمز الربط العالمي المرافق للحزمة: كل تعريفات المستخدم العليا.

    يُتخطى: صنف 'استثناء' المدمج (الابن يبني مثيله الخاص)، والوحدات
    (الابن يبني وحداتها الكاملة)، والقيم الحية المرتبطة بخيوط الأب.
    الدوال الجاهزة تُرمَّز بالاسم فيجدها الابن في وحداته.
    """
    out = {}
    for name, val in root.vars.items():
        if name == 'استثناء' or isinstance(val, ModuleValue):
            continue
        if isinstance(val, LIVE_TYPES) or _contains_live(val):
            continue          # خيوط/مهام/عمليات/مولدات... لا تعبر أصلًا
        out[name] = encode_value(val, ctx, line)
    return out


# ================== فك الترميز (الاتجاه: بنية منقطّة ← قيمة) ==================

def decode_value(enc, ctx, line=None):
    """يفك بنية مرمزة إلى قيمة عربية حية في البيئة الهدف ctx['root'].

    ctx['raw'] قسم 'عالمي' الخام في الحزمة (لإيجاد الأصناف التي لم
    تُفك بعد)، وctx['memo'] ذاكرة الأصناف المفكوكة (للوراثة المتشعبة).
    """
    if isinstance(enc, dict):
        if '__قاموس__' in enc:
            return {decode_value(k, ctx, line): decode_value(v, ctx, line)
                    for k, v in enc['__قاموس__'].items()}
        if '__مدى__' in enc:
            return range(*enc['__مدى__'])
        if '__دالة__' in enc:
            return _decode_func(enc['__دالة__'], ctx, line)
        if '__جاهزة__' in enc:
            loc = enc['__جاهزة__']
            if isinstance(loc, list):       # (الوحدة، العضو)
                mod_name, fn_name = loc
                try:
                    module = ctx['root'].get(mod_name)
                except ArabiError:
                    module = None
                member = (module.members.get(fn_name)
                          if isinstance(module, ModuleValue) else None)
                if isinstance(member, BuiltinFunc):
                    return member
                raise ArabiRuntimeError(
                    f"الدالة الجاهزة '{fn_name}' غير متوفرة في وحدة "
                    f"'{mod_name}' بالجهة المستقبِلة", line)
            name = loc
            try:
                return ctx['root'].get(name)
            except ArabiError:
                raise ArabiRuntimeError(
                    f"الدالة الجاهزة '{name}' غير متوفرة في الجهة "
                    'المستقبِلة', line)
        if '__مربوطة__' in enc:
            inst, fn = enc['__مربوطة__']
            return BoundMethod(decode_value(inst, ctx, line),
                               decode_value(fn, ctx, line))
        if '__صنف__' in enc:
            return _decode_class(enc['__صنف__'], ctx, line)
        if '__كائن__' in enc:
            return _decode_instance(enc['__كائن__'], ctx, line)
        if '__تعداد__' in enc:
            ename, members = enc['__تعداد__']
            mv = {}
            for k, v in members.items():
                mv[k] = EnumMember(k, decode_value(v, ctx, line), ename)
            return EnumValue(ename, mv)
        if '__عضو__' in enc:
            ename, mname = enc['__عضو__']
            try:
                enum = ctx['root'].get(ename)
            except ArabiError:
                raise ArabiRuntimeError(
                    f"التعداد '{ename}' غير معروف في الجهة المستقبِلة", line)
            if isinstance(enum, EnumValue) and mname in enum.members:
                return enum.members[mname]
            raise ArabiRuntimeError(
                f"العضو '{mname}' من التعداد '{ename}' غير متوفر في "
                'الجهة المستقبِلة', line)
        # قاموس غير مميز — أعده كما هو (بنية داخلية)
        return {k: decode_value(v, ctx, line) for k, v in enc.items()}
    if isinstance(enc, list):
        return [decode_value(x, ctx, line) for x in enc]
    return enc


def _decode_func(data, ctx, line=None, env_override=None):
    """يفك دالة عربية: يعيد بناء سلسلة الإغلاق طبقة طبقة حتى الجذر
    الهدف، أو يستخدم نطاق صنف مشتركًا جاهزًا (لطُرق الأصناف).
    المرجع الذاتي (__نفسها__) يُستبدل بالدالة بعد بنائها."""
    root = ctx['root']
    if env_override is not None:
        env = env_override
    else:
        env = root
        for layer in reversed(data['السلسلة']):
            e = Env(env)
            for k, v in layer.items():
                e.vars[k] = (_SELF_PLACEHOLDER if isinstance(v, _SelfMarker)
                             else decode_value(v, ctx, line))
            env = e
    params = []
    for name, has_default, d_enc in data['المعاملات']:
        params.append((name, decode_value(d_enc, ctx, line) if has_default
                       else NO_DEFAULT))
    f = ArabiFunc(data['الاسم'], params, data['الجسم'], env,
                  is_lambda=data['سهمية'], is_generator=data['مولدة'],
                  rest=data['المتغير'], is_async=data['غير_متزامنة'])
    f.vm_code = _VM_PENDING       # تُترجم من جديد في العملية عند أول نداء
    if env_override is None:
        # استبدال المراجع الذاتية بالدالة المكتملة
        cur = env
        while cur is not root:
            for k, v in cur.vars.items():
                if isinstance(v, _SelfMarker):
                    cur.vars[k] = f
            cur = cur.parent
    return f


def _decode_class(data, ctx, line=None):
    """يفك صنفًا: يعيد بناء نطاقه ('الأصل' وثوابته) وأعضائه، ويحل
    أسلافه بالأسماء من البيئة الهدف أو من قسم 'عالمي' الخام."""
    memo = ctx['memo']
    key = ('صنف', data['الاسم'])
    if key in memo:
        return memo[key]
    root = ctx['root']
    sup = None
    if data['الأصل']:
        sup = _resolve_class(data['الأصل'], ctx, line)
    class_env = Env(root)
    class_env.define('الأصل', sup)
    members = {}
    for name, m_enc in data['الأعضاء'].items():
        if isinstance(m_enc, dict) and '__دالة__' in m_enc:
            members[name] = _decode_func(m_enc['__دالة__'], ctx, line,
                                         env_override=class_env)
        elif isinstance(m_enc, dict) and '__خاصية__' in m_enc:
            members[name] = Property(
                _decode_func(m_enc['__خاصية__'], ctx, line,
                             env_override=class_env))
        elif isinstance(m_enc, dict) and '__منشئ__' in m_enc:
            members[name] = NativeCtor(name, m_enc['__منشئ__'])
        else:
            val = decode_value(m_enc, ctx, line)
            members[name] = val
            class_env.define(name, val)
    cls = ClassValue(data['الاسم'], sup, members, class_env,
                     is_interface=data['واجهة'], abstract=data['مجردة'])
    if data['الأسلاف']:
        cls.mro = [cls] + [_resolve_class(n, ctx, line)
                           for n in data['الأسلاف']]
    memo[key] = cls
    root.define(cls.name, cls)    # يتاح فورًا لمن يحله بالاسم
    return cls


def _resolve_class(name, ctx, line):
    """يجد صنفًا بالاسم: في البيئة الهدف أولًا ثم في قسم 'عالمي' الخام."""
    try:
        existing = ctx['root'].get(name)
        if isinstance(existing, ClassValue):
            return existing
    except ArabiError:
        pass
    raw = ctx['raw']
    if raw and name in raw:
        enc = raw[name]
        if isinstance(enc, dict) and '__صنف__' in enc:
            return _decode_class(enc['__صنف__'], ctx, line)
    raise ArabiRuntimeError(
        f"الصنف '{name}' غير معروف في الجهة المستقبِلة — لا يمكن "
        'إعادة بناء الكائنات المرتبطة به', line)


def _decode_instance(data, ctx, line=None):
    cls_name, fields_enc = data
    try:
        cls = ctx['root'].get(cls_name)
    except ArabiError:
        cls = None
    if not isinstance(cls, ClassValue):
        raise ArabiRuntimeError(
            f"لا يمكن إعادة بناء كائن من الصنف '{cls_name}' — الصنف "
            'غير معروف في الجهة المستقبِلة', line)
    inst = InstanceValue(cls)
    for k, v in fields_enc.items():
        inst.fields[k] = decode_value(v, ctx, line)
    return inst


# ================== الأخطاء العابرة للعمليات ==================

def _encode_error(exc):
    """يحوّل خطأ عربي إلى سجل بيانات يعبر العملية محتفظًا بهويته."""
    if isinstance(exc, ArabiUserError):
        msg = exc.instance.fields.get('رسالة', '')
        msg = msg if isinstance(msg, str) else str(msg)
        return {'__خطأ__': True, 'صنف': exc.instance.cls.name,
                'رسالة': msg, 'سطر': exc.line}
    return {'__خطأ__': True, 'صنف': None,
            'رسالة': exc.message, 'سطر': exc.line}


def _error_from_record(rec, root):
    """يعيد بناء الخطأ في الجهة المستقبِلة: أخطاء المستخدم تعود
    بكائنها من صنفها (إن وُجد الصنف هناك) فتصلك 'جرب/باستثناء'
    بالهوية نفسها، وغيرها خطأ تشغيلي عادي."""
    line = rec.get('سطر')
    cls_name = rec.get('صنف')
    if cls_name:
        try:
            cls = root.get(cls_name)
        except ArabiError:
            cls = None
        if isinstance(cls, ClassValue) and _is_error_class(cls):
            inst = InstanceValue(cls)
            inst.fields['رسالة'] = rec.get('رسالة', '')
            return ArabiUserError(inst, line)
        return ArabiRuntimeError(f'{cls_name}: {rec.get("رسالة", "")}',
                                 line)
    return ArabiRuntimeError(rec.get('رسالة', 'خطأ في عملية منفصلة'),
                             line)


def _is_error_class(cls):
    """هل الصنف يرث (مباشرة أو عبر السلسلة) الصنف المدمج 'استثناء'؟"""
    cur = cls
    seen = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if cur.name == 'استثناء':
            return True
        cur = cur.superclass
    return False


# ================== بناء مفسّر الابن وتنفيذ الحزم ==================

def _build_child(payload):
    """يبني مفسّرًا جديدًا في العملية الابنة ويعيد (المفسّر، سياق الفك).

    الحزمة تحمل قسم 'عالمي' (ربطات المستخدم العليا) — تُفك وتُعرَّف
    في الجذر بالترتيب نفسه الذي عُرّفت به في الأب.
    """
    from .interpreter import Interpreter
    interp = Interpreter()
    raw = payload['عالمي']
    ctx = {'root': interp.globals, 'raw': raw, 'memo': {}}
    for name, enc in raw.items():
        interp.globals.define(name, decode_value(enc, ctx))
    return interp, ctx


def _run_job(payload):
    """ينفذ حزمة عمل داخل عملية: استدعاء مباشر بنفس دلالات المفسّر.

    الدوال غير المتزامنة تُنتظر داخل العملية (خيطها الخاص يكمل ثم
    تعود نتيجتها) — فالاستدعاء من الأب شفاف تمامًا.
    """
    interp, ctx = _build_child(payload)
    func = decode_value(payload['دالة'], ctx)
    args = [decode_value(a, ctx) for a in payload['وسائط']]
    kwargs = {k: decode_value(v, ctx)
              for k, v in payload.get('كلمات', {}).items()}
    result = interp._call_value(func, args, kwargs, None)
    if isinstance(result, TaskValue):
        result = result.result()
    return ('نهاية',
            pickle.dumps(encode_value(result, _make_enc_ctx(ctx['root']))))


def _proc_entry(blob, conn):
    """نقطة دخول عملية 'شغّل' — تعمل في عملية مستقلة تمامًا."""
    try:
        data = pickle.loads(blob)
        kind, payload_blob = _run_job(data)
    except ArabiError as exc:
        kind, payload_blob = 'خطأ', pickle.dumps(_encode_error(exc))
    except Exception as exc:                    # شبكة أمان — لا صمت أبدًا
        kind, payload_blob = 'عطل', pickle.dumps(
            f'عطل داخل العملية المنفصلة: {exc}')
    try:
        conn.send((kind, payload_blob))
    finally:
        conn.close()


def _pool_worker(job_q, result_q):
    """حلقة عاملة تجمع العمليات: يسحب حزمًا ويعيد نتائج مرقمة حتى
    إشارة الإنهاء (None). كل عمل يحصل على مفسّر نظيف تمامًا."""
    while True:
        job = job_q.get()
        if job is None:
            break
        job_id, blob = job
        try:
            data = pickle.loads(blob)
            kind, payload_blob = _run_job(data)
        except ArabiError as exc:
            kind, payload_blob = 'خطأ', pickle.dumps(_encode_error(exc))
        except Exception as exc:
            kind, payload_blob = 'عطل', pickle.dumps(
                f'عطل داخل عملية التجمع: {exc}')
        result_q.put((job_id, kind, payload_blob))


# ================== الجاهزات: شغّل / تجمع / معالجات / معرفي ==================

def _collect_root(interp):
    return interp.globals


def _validate_callable(func, name, line):
    if not isinstance(func, (ArabiFunc, BuiltinFunc, BoundMethod,
                             ClassValue)):
        raise ArabiRuntimeError(
            f"المعامل الأول لـ '{name}' يجب أن يكون دالة أو صنفًا لكنه "
            f'{typename(func)}', line)
    if isinstance(func, ArabiFunc) and func.is_generator:
        raise ArabiRuntimeError(
            "لا يمكن إرسال دالة مولدة إلى عملية منفصلة — المولدات "
            'تعمل داخل العملية الواحدة فقط', line)


def _proc_spawn(interp, args, line):
    """عمليات.شغّل(دالة، وسائط...) — يشغل العمل في عملية مستقلة ويعيد
    عملية تنتظرها بـ 'انتظر' أو بطرقها نتيجة/الخطأ/جاهز/انتظر/معرف.

    القيم الحية (خيوط/مهام/عمليات أخرى/أقفال/مولدات/تواريخ/قواعد
    بيانات) لا تعبر حدود العملية — تُرفض برسالة واضحة لحظة التقديم.
    """
    if not args:
        raise ArabiRuntimeError(
            "'شغّل' تحتاج الدالة المراد تشغيلها كمعامل أول", line)
    func = args[0]
    _validate_callable(func, 'شغّل', line)
    root = _collect_root(interp)
    enc_ctx = _make_enc_ctx(root)
    payload = {
        'عالمي': _encode_root(root, enc_ctx, line),
        'دالة': encode_value(func, enc_ctx, line),
        'وسائط': [encode_value(a, enc_ctx, line) for a in args[1:]],
    }
    blob = pickle.dumps(payload)
    recv_conn, send_conn = _mp().Pipe(duplex=False)
    proc = _mp().Process(target=_proc_entry, args=(blob, send_conn),
                         daemon=True, name='عملية-عربي')
    proc.start()
    send_conn.close()                 # الطرف المرسل للأب مغلق بعد الإطلاق
    from .runtime import ProcessValue
    return ProcessValue(proc, recv_conn, root)


def _ppool_create(interp, args, line):
    """عمليات.تجمع(عدد) — ينشئ تجمع عمليات محدود الحجم يعاد استخدام
    عملياته لكل المهام المقدَّمة بـ 'قدّم' حتى 'إنهاء'."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'تجمع' تتوقع معاملًا واحدًا (عدد العمليات) لكنها استلمت "
            f'{len(args)}', line)
    size = args[0]
    if isinstance(size, bool) or not isinstance(size, int):
        raise ArabiRuntimeError(
            f"'تجمع' تتوقع عددًا صحيحًا موجبًا لكنها استلمت "
            f'{typename(size)}', line)
    if size < 1:
        raise ArabiRuntimeError(
            f"'تجمع' يحتاج عددًا موجبًا من العمليات (استلم {size})", line)
    if size > POOL_MAX_SIZE:
        raise ArabiRuntimeError(
            f'الحد الأعلى لعدد عمليات التجمع هو {POOL_MAX_SIZE} '
            f'(استلم {size})', line)
    from .runtime import ProcessPoolValue
    pool = ProcessPoolValue(size, _mp(), interp.globals)
    return pool


def _ppool_submit(obj, args, kwargs, line):
    """تجمع.قدّم(دالة، معاملات...، كلمات_المفاتيح) — يقدّم حزمة عمل
    للتجمع ويعيد مهمة عملية تنتظرها بـ 'انتظر' أو 'انتظر_الجميع'.

    الترميز يحدث لحظة التقديم في الأب — فأي قيمة غير قابلة للنقل
    تُرفض فورًا قبل إشغال العمليات.
    """
    if not args:
        raise ArabiRuntimeError(
            "'قدّم' تحتاج دالة على الأقل — مثال: تج.قدّم(حسب، ٥)", line)
    func = args[0]
    _validate_callable(func, 'قدّم', line)
    root = obj._root
    enc_ctx = _make_enc_ctx(root)
    payload = {
        'عالمي': _encode_root(root, enc_ctx, line),
        'دالة': encode_value(func, enc_ctx, line),
        'وسائط': [encode_value(a, enc_ctx, line) for a in args[1:]],
        'كلمات': {k: encode_value(v, enc_ctx, line)
                  for k, v in kwargs.items()},
    }
    from .runtime import ProcessTaskValue
    task = ProcessTaskValue()
    with obj._lock:
        if obj._closed:
            raise ArabiRuntimeError(
                "تجمع العمليات مغلق — لا يقبل مهامًا جديدة بعد 'إنهاء'",
                line)
        job_id = obj._next_id
        obj._next_id += 1
        obj._tasks[job_id] = task
    obj._job_q.put((job_id, pickle.dumps(payload)))
    return task


def _proc_cpu_count(args, line):
    """عمليات.معالجات() — عدد أنوية المعالج المنطقية المتوفرة."""
    if args:
        raise ArabiRuntimeError(
            f"'معالجات' لا تأخذ معاملات لكنها استلمت {len(args)}", line)
    return os.cpu_count() or 1


def _proc_pid(args, line):
    """عمليات.معرفي() — معرف العملية الحالية في نظام التشغيل."""
    if args:
        raise ArabiRuntimeError(
            f"'معرفي' لا يأخذ معاملات لكنه استلم {len(args)}", line)
    return os.getpid()
