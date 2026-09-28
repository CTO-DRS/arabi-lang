# -*- coding: utf-8 -*-
"""طبقة التشغيل: البيئات، القيم، الدوال الجاهزة، الوحدات، وطرق الأنواع."""

import base64
import csv
import datetime
import hashlib
import http.server
import io
import json
import math
import os
import pickle
import queue
import re
import sqlite3
import sys
import threading
import time
import random
import urllib.parse

from .errors import ArabiError, ArabiRuntimeError, ArabiUserError

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


# ================== إشارات التحكم الداخلية ==================

# تُرفع لكسر تدفق التنفيذ وتلتقط في المواضع الصحيحة فقط (حلقات/دوال).
# تعيش هنا ليستوردها المفسّر والدولاب الافتراضي معًا بلا استيراد دائري.

class BreakSignal(Exception):
    """إشارة داخلية لجملة كسر."""


class ContinueSignal(Exception):
    """إشارة داخلية لجملة استمر."""


class ReturnSignal(Exception):
    """إشارة داخلية لجملة أعد."""

    def __init__(self, value):
        self.value = value


# حالات ترجمة الدولاب الافتراضي لدالة عربي:
# _VM_PENDING — لم تُترجم بعد (تُترجم عند أول استدعاء)
# VmCode     — مترجمة وتنفذ عبر الدولاب
# _VM_NO     — فشلت الترجمة، تنفذ دائمًا عبر الممسح الشجري
_VM_PENDING = object()
_VM_NO = object()


# ================== البيئات (النطاقات) ==================

class Env:
    """بيئة متغيرات مرتبطة بسلسلة أبوية للنطاقات المتداخلة."""

    __slots__ = ('vars', 'parent', 'global_decls')

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent
        self.global_decls = set()      # أسماء أعلنت بجملة 'عالمي'

    def get(self, name, line=None):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise ArabiRuntimeError(
            f"المتغير '{name}' غير معرّف — تأكد من تعريفه أولًا", line)

    def set(self, name, value):
        """يعدّل المتغير إن وُجد في أي نطاق، وإلا ينشئه في النطاق الحالي.

        إذا أُعلن الاسم بجملة 'عالمي' في هذا النطاق يذهب التعيين للجذر مباشرة.
        """
        if name in self.global_decls:
            root = self
            while root.parent is not None:
                root = root.parent
            root.vars[name] = value
            return
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        self.vars[name] = value

    def define(self, name, value):
        self.vars[name] = value

    def remove(self, name, line=None):
        """يحذف المتغير من النطاق الذي وُجد فيه (لجملة 'احذف')."""
        env = self
        while env is not None:
            if name in env.vars:
                del env.vars[name]
                return
            env = env.parent
        raise ArabiRuntimeError(
            f"لا يمكن حذف '{name}' — المتغير غير معرّف", line)


# ================== القيم ==================

class ArabiFunc:
    """دالة معرفة بلغة عربي نفسها.

    params قائمة أزواج (الاسم، القيمة الافتراضية أو NO_DEFAULT) —
    تُقيّم الافتراضات مرة واحدة عند التعريف (كما في بايثون).
    is_generator صح إذا يحوي الجسم 'أنتج' — استدعاؤها يعيد مولدًا.
    rest اسم المعامل المتغير (...الاسم) الذي يجمع ما زاد من الوسائط.
    is_async صح للدوال غير المتزامنة (الإصدار 1.15) — استدعاؤها
    يشغّلها في خيط مستقل فورًا ويعيد 'مهمة' تنتظر نتيجتها بـ 'انتظر'.
    """

    __slots__ = ('name', 'params', 'body', 'env', 'is_lambda',
                 'is_generator', 'rest', 'is_async', 'vm_code')

    def __init__(self, name, params, body, env, is_lambda=False,
                 is_generator=False, rest=None, is_async=False):
        self.name = name
        self.params = params
        self.body = body
        self.env = env
        self.is_lambda = is_lambda
        self.is_generator = is_generator
        self.rest = rest
        self.is_async = is_async
        self.vm_code = _VM_PENDING       # الدولاب الافتراضي: ترجمة عند الطلب


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
    mro ترتيب حل الطرق (C3) — قائمة تبدأ بالصنف نفسه، أو None للصنف بلا أصول.
    is_interface صح للواجهات — عقد مجرد لا يمكن إنشاء كائنات منه مباشرة.
    abstract أسماء الطرق المجردة المعلنة في الواجهة (بلا جسم).
    """

    __slots__ = ('name', 'superclass', 'members', 'env', 'mro',
                 'is_interface', 'abstract')

    def __init__(self, name, superclass, members, env, mro=None,
                 is_interface=False, abstract=()):
        self.name = name
        self.superclass = superclass      # ClassValue أو None
        self.members = members
        self.env = env
        self.mro = mro
        self.is_interface = is_interface
        self.abstract = frozenset(abstract)


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


class Property:
    """خاصية محسوبة داخل صنف — تُقيّم عند الوصول إليها بلا أقواس."""

    __slots__ = ('func',)

    def __init__(self, func):
        self.func = func


class NativeCtor:
    """مُنشئ أصلي مدمج (مثل مُنشئ الصنف المدمج 'خطأ').

    تتعامل معه المفسّر بشكل خاص بدل تنفيذه كدالة عربية.
    """

    __slots__ = ('name', 'kind')

    def __init__(self, name, kind):
        self.name = name
        self.kind = kind


class EnumMember:
    """عضو في تعداد — يحمل اسمه وقيمته واسم تعداده."""

    __slots__ = ('name', 'value', 'enum_name')

    def __init__(self, name, value, enum_name):
        self.name = name
        self.value = value
        self.enum_name = enum_name

    def __eq__(self, other):
        if not isinstance(other, EnumMember):
            return NotImplemented
        return (self.enum_name == other.enum_name
                and self.name == other.name)

    def __hash__(self):
        return hash((self.enum_name, self.name))


class EnumValue:
    """تعداد معرف من قبل المستخدم — مجموعة أعضاء ثابتة مسماة."""

    __slots__ = ('name', 'members')

    def __init__(self, name, members):
        self.name = name
        self.members = members          # {الاسم: EnumMember}


# سياق خيوط المولدات: كل خيط عامل يرى مولده فقط
_gen_tls = threading.local()


class GeneratorClose(Exception):
    """إشارة داخلية لإغلاق مولد قبل انتهائه (كسر خارج حلقة 'لكل')."""


class GeneratorValue:
    """مولد — كائن ينتج قيمًا تباعًا عبر جملة 'أنتج' داخل دالة.

    التنفيذ: خيط عامل يشغل جسم الدالة، وكل 'أنتج' تسلم القيمة
    للمستهلك وتنتظر إشارة الاستئناف (مصافحة تضمن التنفيذ التسلسلي).
    """

    __slots__ = ('interp', 'func', 'env', '_queue', '_gate', '_thread',
                 '_started', '_done', '_error')

    def __init__(self, interp, func, env):
        self.interp = interp
        self.func = func
        self.env = env
        self._queue = queue.Queue()     # من العامل إلى المستهلك
        self._gate = queue.Queue()      # إشارات الاستئناف والإغلاق
        self._thread = None
        self._started = False
        self._done = False
        self._error = None

    # ---------- تشغيل خيط العامل ----------

    def _worker(self):
        _gen_tls.gen = self
        try:
            self.interp.exec_statements(self.func.body, self.env)
        except ReturnSignal:
            self._queue.put(('نهاية', None))
        except GeneratorClose:
            pass                        # إغلاق مبكر — المستهلك بدأه
        except BreakSignal:
            self._queue.put(('خطأ', ArabiRuntimeError(
                "جملة 'كسر' استُخدمت خارج حلقة")))
        except ContinueSignal:
            self._queue.put(('خطأ', ArabiRuntimeError(
                "جملة 'استمر' استُخدمت خارج حلقة")))
        except ArabiError as exc:
            self._queue.put(('خطأ', exc))
        except Exception as exc:        # شبكة أمان — لا يموت الخيط بصمت
            self._queue.put(('خطأ', ArabiRuntimeError(f'خطأ داخلي: {exc}')))
        else:
            self._queue.put(('نهاية', None))
        finally:
            _gen_tls.gen = None

    def _start(self):
        self._started = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True,
            name=f'مولد-{self.func.name}')
        self._thread.start()

    # ---------- الواجهة ----------

    def next(self, line=None):
        """القيمة التالية — يرفع خطأ عربي عند النهاية أو عند خطأ داخلي."""
        if self._error is not None:
            raise ArabiRuntimeError(self._error.message, line)
        if not self._started:
            self._start()
        elif self._done:
            raise ArabiRuntimeError('انتهى المولد — لا مزيد من القيم', line)
        else:
            self._gate.put('تابع')      # استئناف العامل لطلب القيمة التالية
        kind, value = self._queue.get()
        if kind == 'قيمة':
            return value
        self._done = True
        if kind == 'خطأ':
            self._error = value
            raise ArabiRuntimeError(value.message, line)
        raise ArabiRuntimeError('انتهى المولد — لا مزيد من القيم', line)

    def _next_pair(self):
        """يعيد (صح، القيمة) أو (خطأ، ولا شيء) عند النهاية الطبيعية.

        يرفع الخطأ الحقيقي إذا فشل جسم المولد — للاستخدام الداخلي.
        """
        try:
            return True, self.next()
        except ArabiRuntimeError as exc:
            if self._done and self._error is None:
                return False, None
            raise

    def _emit(self, value, line=None):
        """يستقبل قيمة من exec_Yield ويسلمها للمستهلك ثم ينتظر الاستئناف."""
        self._queue.put(('قيمة', value))
        cmd = self._gate.get()
        if cmd == 'أغلق':
            raise GeneratorClose()

    def close(self):
        """يغلق المولد مبكرًا وينتظر انتهاء خيط العامل."""
        if self._done or not self._started:
            self._done = True
            return
        self._gate.put('أغلق')
        self._thread.join(timeout=5)
        self._done = True


class DBValue:
    """اتصال قاعدة بيانات SQLite مفتوح من وحدة 'قاعدة'."""

    __slots__ = ('conn', 'name')

    def __init__(self, conn, name):
        self.conn = conn
        self.name = name


class SuperValue:
    """الأصل داخل طريقة — يربط صنف الأصل بالكائن الحالي.

    استدعاء الأصل.طريقة(وسائط) ينفذ طريقة الأصل مرتبطة بالكائن تلقائيًا
    (والنمط القديم الأصل.طريقة(هذا، وسائط) ما زال يعمل).
    """

    __slots__ = ('cls', 'instance')

    def __init__(self, cls, instance):
        self.cls = cls
        self.instance = instance


class ThreadValue:
    """خيط تنفيذ من وحدة 'خيوط' — يشغل دالة عربية بالتوازي.

    _queue يستلم ('نهاية'، النتيجة) أو ('خطأ'، استثناء) من الخيط العامل،
    ونتيجة() تنتظر الانتهاء وتعيد النتيجة أو تعيد رفع الخطأ.
    """

    __slots__ = ('thread', '_queue', '_done', '_error', '_result')

    def __init__(self):
        self.thread = None
        self._queue = queue.Queue()
        self._done = False
        self._error = None
        self._result = None

    def _finish(self, kind, value):
        self._queue.put((kind, value))

    def result(self, line=None):
        """ينتظر انتهاء الخيط ويعيد نتيجته — يعيد رفع الخطأ إن وقع."""
        if self._error is not None:
            raise ArabiRuntimeError(self._error.message, line)
        if not self._done:
            kind, value = self._queue.get()
            self._done = True
            if kind == 'خطأ':
                self._error = value
                raise ArabiRuntimeError(value.message, line)
            self._result = value
        return self._result

    def join(self, line=None):
        """ينتظر انتهاء الخيط دون إعادة النتيجة (ويبتلع الخطأ)."""
        if not self._done:
            kind, value = self._queue.get()
            self._done = True
            if kind == 'خطأ':
                self._error = value
                return
            self._result = value

    def alive(self):
        if self._done:
            return False
        if self.thread is not None:
            return self.thread.is_alive()
        return True


class LockValue:
    """قفل حصر من وحدة 'خيوط' — يحمي بيانات مشتركة بين الخيوط."""

    __slots__ = ('lock',)

    def __init__(self):
        self.lock = threading.Lock()


class QueueValue:
    """طابور آمن بين الخيوط من وحدة 'خيوط' — لتمرير الرسائل."""

    __slots__ = ('q',)

    def __init__(self):
        self.q = queue.Queue()


class TaskValue:
    """مهمة غير متزامنة (الإصدار 1.15) — نتيجة استدعاء دالة غير متزامنة.

    الاستدعاء يشغّل الدالة في خيط مستقل فورًا ويعيد هذه المهمة.
    - 'انتظر مهمة' يوقف السطر حتى تنتهي المهمة ويعيد نتيجتها
      (أو يعيد رفع خطأها إن فشلت).
    - جاهز() تفحص الانتهاء دون انتظار، الخطأ() يعيد رسالة فشل
      المهمة بعد انتهائها أو 'ولا شيء'، وانتظر() تنتظر بلا نتيجة.
    """

    __slots__ = ('thread', '_event', '_lock', '_done', '_error', '_result')

    def __init__(self):
        self.thread = None
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._done = False
        self._error = None
        self._result = None

    def _finish(self, result, error):
        """يسجل النتيجة أو الخطأ مرة واحدة ويوقظ كل المنتظرين."""
        with self._lock:
            if self._done:
                return
            self._result = result
            self._error = error
            self._done = True
        self._event.set()

    def result(self, line=None):
        """ينتظر انتهاء المهمة ويعيد نتيجتها — يعيد رفع خطأها إن فشلت.

        الخطأ يُرفع بكائنه الأصلي (بخطأه وأصله) كي تحفظ دلالات 'جرب'
        وترابط الأخطاء المخصصة كما لو حدثت في السطر نفسه.
        """
        self._event.wait()
        if self._error is not None:
            raise self._error
        return self._result

    def error(self):
        """ينتظر انتهاء المهمة ويعيد رسالة الخطأ أو 'ولا شيء' إذا نجحت."""
        self._event.wait()
        return self._error.message if self._error is not None else None

    def ready(self):
        """هل انتهت المهمة؟ فحص فوري دون انتظار."""
        return self._done


class PoolValue:
    """تجمع خيوط محدود الحجم (الإصدار 1.16) — نتاج الجاهزة تجمع(عدد).

    عدد ثابت من الخيوط العاملة يُعاد استخدامه لتنفيذ المهام المقدَّمة
    بـ 'قدّم' بدل فتح خيط جديد لكل مهمة — يحفظ الموارد ويحد التزامن.
    - قدّم(دالة، معاملات...) تعيد مهمة (TaskValue) تنتظرها بـ 'انتظر'
      أو تجمع نتائجها بـ 'انتظر_الجميع' — سواء كانت الدالة عادية أو
      غير متزامنة؛ التنفيذ يحدث على خيوط التجمع في كل الأحوال.
    - إنهاء() توقف قبول مهام جديدة وتنتظر تصفية الجاري منها.
    - حجم() تعيد عدد الخيوط العاملة.
    """

    __slots__ = ('size', '_interp', '_queue', '_closed', '_lock', '_threads')

    def __init__(self, size):
        self.size = size
        self._interp = None            # يربطه باني التجمع (الجاهزة تجمع)
        self._queue = queue.Queue()
        self._closed = False
        self._lock = threading.Lock()
        self._threads = []
        for i in range(size):
            worker = threading.Thread(target=self._worker, daemon=True,
                                      name=f'تجمع-عربي-{i + 1}')
            worker.start()
            self._threads.append(worker)

    def _worker(self):
        """حلقة الخيط العامل: يسحب أعمالًا من الطابور حتى إشارة الإنهاء."""
        while True:
            job = self._queue.get()
            if job is None:            # إشارة إنهاء
                break
            try:
                job()
            finally:
                self._queue.task_done()

    def _make_job(self, func, local, this_val, task):
        """يبني عملًا ينفذ جسم دالة عربية على خيط التجمع — بنفس دلالات
        _spawn_task تمامًا (رفع الأخطاء بكائنها، و'هذا' على المكدس)."""
        interp = self._interp

        def job():
            stack = None
            try:
                if this_val is not None:
                    stack = getattr(interp._tls, 'this_stack', None)
                    if stack is None:
                        stack = []
                        interp._tls.this_stack = stack
                    stack.append(this_val)
                try:
                    result = interp._run_func(func, local)
                finally:
                    if stack is not None:
                        stack.pop()
                task._finish(result, None)
            except ArabiError as exc:
                task._finish(None, exc)
            except Exception as exc:      # شبكة أمان — لا تموت المهمة بصمت
                task._finish(None, ArabiRuntimeError(
                    f'خطأ داخل مهمة التجمع: {exc}'))

        return job


class ProcessValue:
    """عملية منفصلة من وحدة 'عمليات' (الإصدار 1.17) — نتاج عمليات.شغّل.

    العمل تعمل في معالج مستقل بذاكرة معزولة تمامًا فيتجاوز قفل
    التفسير العالمي، والنتيجة تعود مرمزة عبر أنبوب (Pipe).
    - 'انتظر عملية' يوقف السطر حتى تنتهي ويعيد نتيجتها (أو يرفع خطأها).
    - جاهز() فحص فوري، الخطأ() رسالة الفشل أو 'ولا شيء'، انتظر()
      انتظار بلا نتيجة، ومعرف() معرف العملية في نظام التشغيل.
    """

    __slots__ = ('process', 'conn', '_root', '_received', '_outcome')

    def __init__(self, process, conn, root):
        self.process = process
        self.conn = conn
        self._root = root               # جذر الأب لفك ترميز النتيجة
        self._received = False
        self._outcome = None

    def _receive(self, line=None):
        """يستلم النتيجة مرة واحدة (وخزّنها) — ('نهاية'|'خطأ'|'عطل'، بيانات)."""
        if self._received:
            return self._outcome
        if not self.conn.poll(PROCESS_TIMEOUT):
            raise ArabiRuntimeError(
                'انتهت مهلة انتظار العملية المنفصلة دون نتيجة — '
                'ربما علقت في عمل طويل جدًا', line)
        try:
            kind, blob = self.conn.recv()
        except (EOFError, OSError):
            raise ArabiRuntimeError(
                'انتهت العملية المنفصلة فجأة دون أن ترسل نتيجة', line)
        self.process.join()
        self._received = True
        self._outcome = (kind, blob)
        return self._outcome

    def result(self, line=None):
        """ينتظر انتهاء العملية ويعيد نتيجتها المفكوكة — أو يرفع خطأها."""
        from .processes import decode_value
        kind, blob = self._receive(line)
        if kind == 'نهاية':
            return decode_value(pickle.loads(blob),
                                {'root': self._root, 'raw': None,
                                 'memo': {}})
        if kind == 'خطأ':
            from .processes import _error_from_record
            raise _error_from_record(pickle.loads(blob), self._root)
        raise ArabiRuntimeError(pickle.loads(blob), line)

    def join(self, line=None):
        """ينتظر انتهاء العملية دون إعادة النتيجة (يبتلع الخطأ)."""
        try:
            self._receive(line)
        except ArabiError:
            pass

    def ready(self):
        """هل انتهت العملية؟ فحص فوري دون انتظار."""
        if self._received:
            return True
        try:
            return self.conn.poll(0)
        except (EOFError, OSError):
            return True

    def pid(self):
        """معرف العملية في نظام التشغيل (قبل الإطلاق: ولا شيء)."""
        return self.process.pid


class ProcessTaskValue:
    """مهمة عملية — نتاج قدّم على تجمع العمليات (الإصدار 1.17).

    الواجهة نفسها لمهام الخيوط: نتيجة/الخطأ/جاهز/انتظر — فتعمل مع
    'انتظر' و'انتظر_الجميع' و'سباق' دون أي فرق في الاستخدام.
    """

    __slots__ = ('_event', '_lock', '_done', '_error', '_result')

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._done = False
        self._error = None
        self._result = None

    def _finish(self, result, error):
        """يسجل النتيجة أو الخطأ مرة واحدة ويوقظ كل المنتظرين."""
        with self._lock:
            if self._done:
                return
            self._result = result
            self._error = error
            self._done = True
        self._event.set()

    def result(self, line=None):
        """ينتظر انتهاء المهمة ويعيد نتيجتها — يعيد رفع خطأها إن فشلت."""
        self._event.wait()
        if self._error is not None:
            self._error.line = self._error.line or line
            raise self._error
        return self._result

    def error(self):
        """ينتظر الانتهاء ويعيد رسالة الخطأ أو 'ولا شيء' إذا نجحت."""
        self._event.wait()
        return self._error.message if self._error is not None else None

    def ready(self):
        """هل انتهت المهمة؟ فحص فوري دون انتظار."""
        return self._done


class ProcessPoolValue:
    """تجمع عمليات محدود الحجم (الإصدار 1.17) — نتاج عمليات.تجمع(عدد).

    عدد ثابت من العمليات العاملة يُعاد استخدامه لكل المهام المقدَّمة
    بـ 'قدّم' — كل عملية بمفسّرها المعزول، والنتائج تعود مرمزة عبر
    طابور مرقّم يوزعه خيط مستقبِل في الأب على مهامها.
    - قدّم(دالة، معاملات...) تعيد مهمة عملية تنتظرها بـ 'انتظر'.
    - إنهاء() توقف قبول مهام جديدة وتنتظر تصفية الجاري منها.
    - حجم() تعيد عدد العمليات العاملة.
    """

    __slots__ = ('size', '_root', '_ctx', '_job_q', '_result_q', '_procs',
                 '_closed', '_lock', '_next_id', '_tasks', '_dispatcher')

    def __init__(self, size, ctx, root):
        self.size = size
        self._root = root
        self._ctx = ctx
        self._job_q = ctx.Queue()
        self._result_q = ctx.Queue()
        self._procs = []
        self._closed = False
        self._lock = threading.Lock()
        self._next_id = 0
        self._tasks = {}
        for i in range(size):
            p = ctx.Process(target=_pool_worker_target,
                            args=(self._job_q, self._result_q),
                            daemon=True, name=f'تجمع-عمليات-عربي-{i + 1}')
            p.start()
            self._procs.append(p)
        self._dispatcher = threading.Thread(target=self._dispatch,
                                            daemon=True,
                                            name='موزع-تجمع-العمليات')
        self._dispatcher.start()

    def _dispatch(self):
        """حلقة الموزع في الأب: يسلم كل نتيجة واصلة لمهمتها بالرقم."""
        while True:
            item = self._result_q.get()
            if item is None:            # إشارة إيقاف بعد إنهاء التجمع
                break
            job_id, kind, blob = item
            with self._lock:
                task = self._tasks.pop(job_id, None)
            if task is None:
                continue
            try:
                if kind == 'نهاية':
                    from .processes import decode_value
                    value = decode_value(
                        pickle.loads(blob),
                        {'root': self._root, 'raw': None, 'memo': {}})
                    task._finish(value, None)
                elif kind == 'خطأ':
                    from .processes import _error_from_record
                    task._finish(None, _error_from_record(
                        pickle.loads(blob), self._root))
                else:
                    task._finish(None, ArabiRuntimeError(
                        pickle.loads(blob)))
            except Exception as exc:    # فشل فك الترميز نفسه — لا صمت
                task._finish(None, ArabiRuntimeError(
                    f'تعذر فك نتيجة العملية: {exc}'))

    def shutdown(self, line=None):
        """يغلق التجمع: لا مهام جديدة، والعمليات تخرج بعد تصفية الجاري."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for _ in self._procs:
                self._job_q.put(None)   # إشارة إنهاء لكل عملية عاملة
        for p in self._procs:
            p.join()
        self._result_q.put(None)        # أوقف الموزع بعد تصفية النتائج
        self._dispatcher.join()


def _pool_worker_target(job_q, result_q):
    """غلاف مستوى الوحدة لنقطة دخول العامل — يستوردها التنقيط بالاسم."""
    from .processes import _pool_worker
    _pool_worker(job_q, result_q)


class DistributedTaskValue:
    """مهمة موزعة — نتاج قدّم على موزع (الإصدار 1.18).

    الواجهة نفسها لمهام الخيوط والعمليات: نتيجة/الخطأ/جاهز/انتظر
    — فتعمل مع 'انتظر' و'انتظر_الجميع' و'سباق' دون أي فرق في
    الاستخدام، لكن عملها قد ينفذ على أي جهاز في الشبكة.
    """

    __slots__ = ('_event', '_lock', '_done', '_error', '_result', 'id')

    def __init__(self, task_id):
        self.id = task_id               # المعرف العالمي للمهمة
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._done = False
        self._error = None
        self._result = None

    def _finish(self, result, error):
        """يسجل النتيجة أو الخطأ مرة واحدة ويوقظ كل المنتظرين."""
        with self._lock:
            if self._done:
                return
            self._result = result
            self._error = error
            self._done = True
        self._event.set()

    def result(self, line=None):
        """ينتظر انتهاء المهمة ويعيد نتيجتها — يعيد رفع خطأها إن فشلت."""
        if not self._event.wait(DISTRIBUTED_TIMEOUT):
            raise ArabiRuntimeError(
                'انتهت مهلة انتظار المهمة الموزعة دون نتيجة — ربما لا '
                'يوجد عالِم متصل بالموزع أو علق العمل طويلًا جدًا', line)
        if self._error is not None:
            self._error.line = self._error.line or line
            raise self._error
        return self._result

    def error(self):
        """ينتظر الانتهاء ويعيد رسالة الخطأ أو 'ولا شيء' إذا نجحت."""
        if not self._event.wait(DISTRIBUTED_TIMEOUT):
            return 'انتهت مهلة انتظار المهمة الموزعة'
        return self._error.message if self._error is not None else None

    def ready(self):
        """هل انتهت المهمة؟ فحص فوري دون انتظار."""
        return self._done


class DispatcherValue:
    """موزع مهام — نتاج موزعة.موزع(الإصدار 1.18).

    خادم توزيع يستقبل اتصالات العمالة من أي جهاز ويسلمها المهام
    المقدَّمة بـ 'قدّم' — والنتائج تعود للنادل مهما نُفذ عملها.
    - قدّم(دالة، معاملات...) تعيد مهمة موزعة تنتظرها بـ 'انتظر'.
    - عمال() عدد العمالة المتصلة الآن، منفذ() المنفذ الفعلي
      (بعد الاختيار التلقائي)، حجم() عدد المهام المقدَّمة كله.
    - انتظر_العمال(عدد، مهلة) يحجب حتى تكتمل العمالة المطلوبة.
    - إنهاء() يوقف قبول المهام وينتظر تصفية الجاري ثم يودّع العمالة.
    - مشفّر() هل بدأ الموزع بمفتاح سري؟ (قناته مشفرة بالكامل — 1.21).
    """

    __slots__ = ('_server',)

    def __init__(self, server):
        self._server = server

    # تفويض مباشر للخادم — بواجهة عربية قصيرة للاستخدام الداخلي والاختبارات

    def submit(self, func, args, kwargs, line=None):
        return self._server.submit(func, args, kwargs, line)

    def workers(self):
        return self._server.workers()

    def port(self):
        return self._server.port()

    def host(self):
        return self._server.host()

    def total(self):
        return self._server.total()

    def encrypted(self):
        return self._server.encrypted()

    def wait_workers(self, count, timeout, line=None):
        return self._server.wait_workers(count, timeout, line)

    def shutdown(self, line=None):
        return self._server.shutdown(line)


class DateValue:
    """قيمة تاريخ ووقت — تغلف datetime.datetime (الإصدار 1.9)."""

    __slots__ = ('dt',)

    def __init__(self, dt):
        self.dt = dt


DB_METHODS = {}       # تُملأ بعد تعريف دوال قاعدة البيانات
GENERATOR_METHODS = {}  # تُملأ بعد تعريف طرق المولدات
THREAD_METHODS = {}   # تُملأ بعد تعريف طرق الخيوط
LOCK_METHODS = {}     # تُملأ بعد تعريف طرق القفل
QUEUE_METHODS = {}    # تُملأ بعد تعريف طرق الطابور
TASK_METHODS = {}     # تُملأ بعد تعريف طرق المهام غير المتزامنة (1.15)
POOL_METHODS = {}     # تُملأ بعد تعريف طرق تجمع الخيوط (1.16)
PROCESS_METHODS = {}  # تُملأ بعد تعريف طرق العمليات المنفصلة (1.17)
PROCESS_TASK_METHODS = {}  # تُملأ بعد تعريف طرق مهام العمليات (1.17)
PROCESS_POOL_METHODS = {}  # تُملأ بعد تعريف طرق تجمع العمليات (1.17)
DISPATCHER_METHODS = {}   # تُملأ بعد تعريف طرق الموزع (1.18)
DIST_TASK_METHODS = {}    # تُملأ بعد تعريف طرق المهام الموزعة (1.18)

PROCESS_TIMEOUT = 120  # مهلة انتظار نتيجة العملية الواحدة (ثوانٍ)
DISTRIBUTED_TIMEOUT = 120  # مهلة انتظار نتيجة المهمة الموزعة (ثوانٍ)


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
    if isinstance(v, ProcessValue):
        return 'عملية'
    if isinstance(v, ProcessTaskValue):
        return 'مهمة عملية'
    if isinstance(v, ProcessPoolValue):
        return 'تجمع عمليات'
    if isinstance(v, DispatcherValue):
        return 'موزع'
    if isinstance(v, DistributedTaskValue):
        return 'مهمة موزعة'
    if isinstance(v, (ArabiFunc, BuiltinFunc)):
        if isinstance(v, ArabiFunc) and v.is_async:
            return 'دالة غير متزامنة'
        return 'دالة'
    if isinstance(v, ModuleValue):
        return 'وحدة'
    if isinstance(v, ClassValue):
        return 'واجهة' if v.is_interface else 'صنف'
    if isinstance(v, InstanceValue):
        return 'كائن'
    if isinstance(v, BoundMethod):
        return 'طريقة'
    if isinstance(v, EnumValue):
        return 'تعداد'
    if isinstance(v, EnumMember):
        return 'عضو تعداد'
    if isinstance(v, GeneratorValue):
        return 'مولد'
    if isinstance(v, DBValue):
        return 'قاعدة بيانات'
    if isinstance(v, SuperValue):
        return 'الأصل'
    if isinstance(v, ThreadValue):
        return 'خيط'
    if isinstance(v, TaskValue):
        return 'مهمة'
    if isinstance(v, PoolValue):
        return 'تجمع خيوط'
    if isinstance(v, LockValue):
        return 'قفل'
    if isinstance(v, QueueValue):
        return 'طابور'
    if isinstance(v, DateValue):
        return 'تاريخ'
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
        if v.is_async:
            return f'<دالة غير متزامنة {v.name}>'
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
    if isinstance(v, EnumValue):
        return f'<تعداد {v.name}>'
    if isinstance(v, EnumMember):
        return f'{v.enum_name}.{v.name}'
    if isinstance(v, GeneratorValue):
        return f'<مولد {v.func.name}>'
    if isinstance(v, DBValue):
        return f'<قاعدة بيانات {v.name}>'
    if isinstance(v, SuperValue):
        return f'<الأصل {v.cls.name}>'
    if isinstance(v, ThreadValue):
        return '<خيط>'
    if isinstance(v, TaskValue):
        return '<مهمة>'
    if isinstance(v, PoolValue):
        return f'<تجمع خيوط {v.size}>'
    if isinstance(v, LockValue):
        return '<قفل>'
    if isinstance(v, QueueValue):
        return '<طابور>'
    if isinstance(v, DispatcherValue):
        return f'<موزع على المنفذ {v._server.port()}>'
    if isinstance(v, DistributedTaskValue):
        return f'<مهمة موزعة {v.id}>'
    if isinstance(v, DateValue):
        return v.dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(v)


# أسماء الطرق الخاصة لتحميل العوامل على الكائنات
OVERLOAD_METHODS = {
    '+': 'اجمع', '-': 'اطرح', '*': 'اضرب', '/': 'اقسم',
    '%': 'باقي', '**': 'قوة',
    '<': 'أصغر_من', '>': 'أكبر_من',
    '<=': 'أصغر_يساوي', '>=': 'أكبر_يساوي',
}


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


def _bi_print(interp, args, line):
    print(' '.join(interp._display(a) for a in args))
    return None


def _bi_len(interp, args, line):
    if len(args) != 1:
        raise ArabiRuntimeError(f"'طول' تتوقع معاملًا واحدًا لكنها استلمت {len(args)}", line)
    v = args[0]
    if isinstance(v, (str, list, dict, range)):
        return len(v)
    # كائن من صنف يعرّف الطريقة الخاصة 'طول'
    if isinstance(v, InstanceValue):
        result = interp._call_special(v, 'طول', line)
        if isinstance(result, bool) or not isinstance(result, int):
            raise ArabiRuntimeError(
                "الطريقة الخاصة 'طول' يجب أن تعيد عددًا صحيحًا", line)
        return result
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


def _bi_str(interp, args, line):
    if len(args) != 1:
        raise ArabiRuntimeError(f"'نص' تتوقع معاملًا واحدًا", line)
    return interp._display(args[0])


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
    if isinstance(v, GeneratorValue):
        # استهلاك المولد بالكامل إلى قائمة
        return _drain_generator(v)
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
        ('اطبع', BuiltinFunc('اطبع', _bi_print, takes_interp=True)),
        ('طول', BuiltinFunc('طول', _bi_len, takes_interp=True)),
        ('مدى', _bi_range),
        ('إدخال', _bi_input),
        ('عدد', _bi_int),
        ('عشري', _bi_float),
        ('نص', BuiltinFunc('نص', _bi_str, takes_interp=True)),
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
        # غير المتزامن (الإصدار 1.15)
        ('انتظر_الجميع', _async_wait_all),
        ('سباق', _async_race),
        ('انتظر_زمن', _async_sleep),
        # تجمع الخيوط (الإصدار 1.16)
        ('تجمع', BuiltinFunc('تجمع', _pool_create, takes_interp=True)),
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
        'لوغاريتم_عشري': BuiltinFunc('لوغاريتم_عشري', _math_log10),
        'جيب': BuiltinFunc('جيب', _math_sin),
        'جيب_التام': BuiltinFunc('جيب_التام', _math_cos),
        'ظل': BuiltinFunc('ظل', _math_tan),
        'مشترك_الأكبر': BuiltinFunc('مشترك_الأكبر', _math_gcd),
        'مشترك_الأصغر': BuiltinFunc('مشترك_الأصغر', _math_lcm),
        'علامة': BuiltinFunc('علامة', _math_sign),
        'بي': math.pi,
        'نيبير': math.e,
    }))

    env.define('وقت', ModuleValue('وقت', {
        'زمن': BuiltinFunc('زمن', _time_now),
        'نوم': BuiltinFunc('نوم', _time_sleep),
        'الآن': BuiltinFunc('الآن', _time_details),
        'تنسيق': BuiltinFunc('تنسيق', _time_format),
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

    env.define('عشوائية', ModuleValue('عشوائية', {
        'صحيح': BuiltinFunc('صحيح', _rand_int),
        'عشري': BuiltinFunc('عشري', _rand_float),
        'اختيار': BuiltinFunc('اختيار', _rand_choice),
        'خلط': BuiltinFunc('خلط', _rand_shuffle),
        'عينة': BuiltinFunc('عينة', _rand_sample),
        'بذرة': BuiltinFunc('بذرة', _rand_seed),
    }))

    env.define('نظام', ModuleValue('نظام', {
        'مجلد_العمل': BuiltinFunc('مجلد_العمل', _sys_cwd),
        'متغير': BuiltinFunc('متغير', _sys_env),
        'المتغيرات': BuiltinFunc('المتغيرات', _sys_env_all),
        'ملفات_في': BuiltinFunc('ملفات_في', _sys_listdir),
        'مجلد_موجود': BuiltinFunc('مجلد_موجود', _sys_isdir),
        'انشاء_مجلد': BuiltinFunc('انشاء_مجلد', _sys_mkdir),
        'فصل': BuiltinFunc('فصل', _sys_join),
        'اسم_الملف': BuiltinFunc('اسم_الملف', _sys_basename),
        'المجلد': BuiltinFunc('المجلد', _sys_dirname),
        'المسار_الكامل': BuiltinFunc('المسار_الكامل', _sys_abspath),
        'النظام': BuiltinFunc('النظام', _sys_platform),
        'وسيطات': BuiltinFunc('وسيطات', _sys_args),
        'خروج': BuiltinFunc('خروج', _sys_exit),
    }))

    env.define('تنظيم', ModuleValue('تنظيم', {
        'يجد': BuiltinFunc('يجد', _re_find),
        'كل_المطابقات': BuiltinFunc('كل_المطابقات', _re_findall),
        'يستبدل': BuiltinFunc('يستبدل', _re_sub),
        'ينقسم': BuiltinFunc('ينقسم', _re_split),
        'يطابق': BuiltinFunc('يطابق', _re_fullmatch),
        'يبدأ': BuiltinFunc('يبدأ', _re_match),
    }))

    env.define('شبكة', ModuleValue('شبكة', {
        'اطلب': BuiltinFunc('اطلب', _net_request),
        'نص_الصفحة': BuiltinFunc('نص_الصفحة', _net_text),
        'تنزيل': BuiltinFunc('تنزيل', _net_download),
    }))

    env.define('تحويل', ModuleValue('تحويل', {
        'إلى_شرقية': BuiltinFunc('إلى_شرقية', _conv_eastern),
        'إلى_غربية': BuiltinFunc('إلى_غربية', _conv_western),
        'كلمات': BuiltinFunc('كلمات', _conv_words),
    }))

    # ============ وحدات الإصدار 1.7 ============

    env.define('قاعدة', ModuleValue('قاعدة', {
        'افتح': BuiltinFunc('افتح', _db_open),
        'نفذ': BuiltinFunc('نفذ', _db_execute),
        'استعلم': BuiltinFunc('استعلم', _db_query),
        'أعمدة': BuiltinFunc('أعمدة', _db_columns),
        'أغلق': BuiltinFunc('أغلق', _db_close),
    }))

    env.define('ترميز', ModuleValue('ترميز', {
        'شفّر64': BuiltinFunc('شفّر64', _enc_b64encode),
        'فك64': BuiltinFunc('فك64', _enc_b64decode),
        'هش256': BuiltinFunc('هش256', _enc_hash('sha256', 'هش256')),
        'هش1': BuiltinFunc('هش1', _enc_hash('sha1', 'هش1')),
        'ام_دي_5': BuiltinFunc('ام_دي_5', _enc_hash('md5', 'ام_دي_5')),
    }))

    env.define('جداول', ModuleValue('جداول', {
        'اقرأ': BuiltinFunc('اقرأ', _csv_read),
        'اكتب': BuiltinFunc('اكتب', _csv_write),
        'حلل': BuiltinFunc('حلل', _csv_parse),
        'نص': BuiltinFunc('نص', _csv_text),
    }))

    # ============ وحدة الخيوط (الإصدار 1.8) ============

    env.define('خيوط', ModuleValue('خيوط', {
        'شغّل': BuiltinFunc('شغّل', _thr_spawn, takes_interp=True),
        'انتظر_الكل': BuiltinFunc('انتظر_الكل', _thr_join_all),
        'قفل': BuiltinFunc('قفل', _thr_lock),
        'طابور': BuiltinFunc('طابور', _thr_queue),
        'معالجات': BuiltinFunc('معالجات', _thr_cpu_count),
    }))

    # ============ وحدة العمليات (الإصدار 1.17) ============
    # الاستيراد هنا (وليس أعلى الملف) تفاديًا للدورانية — processes
    # يستورد أسماء القيم من runtime، وهو مكتمل قبل أي استدعاء لهذه الدالة.

    from .processes import (_proc_spawn, _ppool_create,
                            _proc_cpu_count, _proc_pid)
    env.define('عمليات', ModuleValue('عمليات', {
        'شغّل': BuiltinFunc('شغّل', _proc_spawn, takes_interp=True),
        'تجمع': BuiltinFunc('تجمع', _ppool_create, takes_interp=True),
        'معالجات': BuiltinFunc('معالجات', _proc_cpu_count),
        'معرفي': BuiltinFunc('معرفي', _proc_pid),
    }))

    # ============ وحدة الموزعة (الإصدار 1.18) ============
    # الاستيراد هنا (وليس أعلى الملف) تفاديًا للدورانية — distributed
    # يستورد أسماء القيم من processes وruntime، وهي مكتملة قبل أي استدعاء.

    from .distributed import _dist_create, _dist_worker
    env.define('موزعة', ModuleValue('موزعة', {
        'موزع': BuiltinFunc('موزع', _dist_create, takes_interp=True),
        'عامل': BuiltinFunc('عامل', _dist_worker, takes_interp=True),
    }))

    # ============ وحدة التشفير (الإصدار 1.19، والتشفير التماثلي 1.21) ============
    # استيراد آمن: crypto لا يستورد من runtime فلا دورانية أبدًا

    from .crypto import (_crypto_hash, _crypto_hash512, _crypto_hmac,
                         _crypto_compare, _crypto_key, _crypto_token,
                         _crypto_rand, _crypto_pw_hash, _crypto_pw_verify,
                         _crypto_derive, _crypto_encrypt, _crypto_decrypt)
    env.define('تشفير', ModuleValue('تشفير', {
        'هش': BuiltinFunc('هش', _crypto_hash),
        'هش512': BuiltinFunc('هش512', _crypto_hash512),
        'هوماك': BuiltinFunc('هوماك', _crypto_hmac),
        'مقارنة_آمنة': BuiltinFunc('مقارنة_آمنة', _crypto_compare),
        'مفتاح_آمن': BuiltinFunc('مفتاح_آمن', _crypto_key),
        'رمز_آمن': BuiltinFunc('رمز_آمن', _crypto_token),
        'عدد_آمن': BuiltinFunc('عدد_آمن', _crypto_rand),
        'شفر_كلمة': BuiltinFunc('شفر_كلمة', _crypto_pw_hash),
        'تحقق_كلمة': BuiltinFunc('تحقق_كلمة', _crypto_pw_verify),
        'مشتق': BuiltinFunc('مشتق', _crypto_derive),
        'شفّر': BuiltinFunc('شفّر', _crypto_encrypt),
        'فكّ': BuiltinFunc('فكّ', _crypto_decrypt),
    }))

    # ============ وحدة التواريخ (الإصدار 1.9) ============

    env.define('تواريخ', ModuleValue('تواريخ', {
        'الآن': BuiltinFunc('الآن', _dt_now),
        'أنشئ': BuiltinFunc('أنشئ', _dt_create),
        'حلل': BuiltinFunc('حلل', _dt_parse),
        'فرق': BuiltinFunc('فرق', _dt_diff),
        'أضف': BuiltinFunc('أضف', _dt_add),
        'يوم_الأسبوع': BuiltinFunc('يوم_الأسبوع', _dt_weekday),
    }))

    # ============ وحدة الإحصاء (الإصدار 1.10) ============

    env.define('إحصاء', ModuleValue('إحصاء', {
        'معدل': BuiltinFunc('معدل', _st_mean),
        'وسيط': BuiltinFunc('وسيط', _st_median),
        'منوال': BuiltinFunc('منوال', _st_mode),
        'تباين': BuiltinFunc('تباين', _st_variance),
        'انحراف': BuiltinFunc('انحراف', _st_stddev),
        'مدى': BuiltinFunc('مدى', _st_range),
    }))

    # ============ إطار الاختبارات (الإصدار 1.6) ============

    _tests = _TestState()
    env.define('اختبارات', ModuleValue('اختبارات', {
        'ابدأ': BuiltinFunc('ابدأ', _tests_start(_tests)),
        'يساوي': BuiltinFunc('يساوي', _tests_check(_tests, 'eq')),
        'يختلف': BuiltinFunc('يختلف', _tests_check(_tests, 'ne')),
        'يصح': BuiltinFunc('يصح', _tests_check(_tests, 'truthy')),
        'يخطئ': BuiltinFunc('يخطئ', _tests_check(_tests, 'falsy')),
        'يرفع': BuiltinFunc('يرفع', _tests_raises(_tests), takes_interp=True),
        'ملخص': BuiltinFunc('ملخص', _tests_summary(_tests)),
    }))

    # ============ خادم الويب (الإصدار 1.6) ============

    _srv = _ServerState()
    env.define('خادم', ModuleValue('خادم', {
        'ابدأ': BuiltinFunc('ابدأ', _srv.start, takes_interp=True),
        'قف': BuiltinFunc('قف', _srv.stop),
        'المنفذ': BuiltinFunc('المنفذ', _srv.get_port),
        'انتظر': BuiltinFunc('انتظر', _srv.wait),
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


def _drain_generator(gen, line=None):
    """يستهلك مولدًا بالكامل ويغلق نهائيًا — لتحويله لقائمة."""
    out = []
    try:
        while True:
            has, item = gen._next_pair()
            if not has:
                break
            out.append(item)
    finally:
        gen.close()
    return out


def _iterable(value, name, line):
    if isinstance(value, (list, range)):
        return list(value)
    if isinstance(value, str):
        return list(value)
    if isinstance(value, GeneratorValue):
        return _drain_generator(value)
    raise ArabiRuntimeError(
        f"'{name}' تحتاج قائمة أو نصًا أو مدى أو مولدًا لكن استلمت {typename(value)}", line)


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
        if isinstance(args[0], GeneratorValue):
            items = _drain_generator(args[0])
        else:
            raise ArabiRuntimeError(
                f"'اختر' تحتاج قائمة أو نصًا أو مدى أو مولدًا لكن استلمت {typename(args[0])}", line)
    else:
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


# ================== توسيع وحدة رياضيات ==================

def _math_log10(args, line):
    x = _one_num(args, 'لوغاريتم_عشري', line)
    if x <= 0:
        raise ArabiRuntimeError('اللوغاريتم يحتاج عددًا أكبر من صفر', line)
    return math.log10(x)


def _two_ints(args, name, line):
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'{name}' تحتاج عددين صحيحين لكنها استلمت {len(args)}", line)
    for x in args:
        if isinstance(x, bool) or not isinstance(x, int):
            raise ArabiRuntimeError(
                f"'{name}' تحتاج عددين صحيحين لكن استلمت {typename(x)}", line)
    return args[0], args[1]


def _math_gcd(args, line):
    a, b = _two_ints(args, 'مشترك_الأكبر', line)
    return math.gcd(abs(a), abs(b))


def _math_lcm(args, line):
    a, b = _two_ints(args, 'مشترك_الأصغر', line)
    if a == 0 or b == 0:
        return 0
    return abs(a * b) // math.gcd(abs(a), abs(b))


def _math_sign(args, line):
    x = _one_num(args, 'علامة', line)
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


# ================== توسيع وحدة وقت ==================

_AR_WEEKDAYS = ('الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس',
                'الجمعة', 'السبت', 'الأحد')


def _time_details(args, line):
    """الآن() — يعيد قاموسًا بتفاصيل الوقت الحالي."""
    if args:
        raise ArabiRuntimeError("'الآن' لا تقبل معاملات", line)
    t = time.localtime()
    return {
        'السنة': t.tm_year,
        'الشهر': t.tm_mon,
        'اليوم': t.tm_mday,
        'الساعة': t.tm_hour,
        'الدقيقة': t.tm_min,
        'الثانية': t.tm_sec,
        'يوم_الأسبوع': _AR_WEEKDAYS[t.tm_wday],
    }


_TIME_TOKENS = {
    '%س': 'year', '%ش': 'mon', '%ي': 'mday',
    '%ع': 'hour', '%د': 'min', '%ث': 'sec', '%أ': 'wday',
}


def _time_format(args, line):
    """تنسيق(قالب) — ينظم الوقت الحالي وفق رموز: %س سنة، %ش شهر، %ي يوم،
    %ع ساعة، %د دقيقة، %ث ثانية، %أ اسم يوم الأسبوع."""
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError(
            f"'تنسيق' تحتاج قالبًا نصيًا لكنها استلمت "
            f"{typename(args[0]) if args else 'لا معاملات'}", line)
    t = time.localtime()
    values = {
        'year': f'{t.tm_year:04d}', 'mon': f'{t.tm_mon:02d}',
        'mday': f'{t.tm_mday:02d}', 'hour': f'{t.tm_hour:02d}',
        'min': f'{t.tm_min:02d}', 'sec': f'{t.tm_sec:02d}',
        'wday': _AR_WEEKDAYS[t.tm_wday],
    }
    result = args[0]
    for token, key in _TIME_TOKENS.items():
        result = result.replace(token, values[key])
    return result


# ================== وحدة عشوائية ==================

def _rand_int(args, line):
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'صحيح' تحتاج عددين (الأدنى والأعلى) لكنها استلمت {len(args)}", line)
    a, b = _two_ints(args, 'صحيح', line)
    if a > b:
        a, b = b, a
    return random.randint(a, b)


def _rand_float(args, line):
    if args:
        raise ArabiRuntimeError("'عشري' لا تقبل معاملات — تعيد عددًا بين 0 و 1", line)
    return random.random()


def _rand_choice(args, line):
    if len(args) != 1 or not isinstance(args[0], (list, range, str)):
        raise ArabiRuntimeError(
            f"'اختيار' تحتاج قائمة أو نصًا أو مدى لكنها استلمت "
            f"{typename(args[0]) if args else 'لا معاملات'}", line)
    items = list(args[0])
    if not items:
        raise ArabiRuntimeError("'اختيار' لا تقبل تسلسلًا فارغًا", line)
    return random.choice(items)


def _rand_shuffle(args, line):
    """خلط(قائمة) — يعيد نسخة جديدة مخلوطة (لا يعدل الأصل)."""
    if len(args) != 1 or not isinstance(args[0], (list, range, str)):
        raise ArabiRuntimeError(
            f"'خلط' تحتاج قائمة أو نصًا أو مدى لكنها استلمت "
            f"{typename(args[0]) if args else 'لا معاملات'}", line)
    items = list(args[0])
    random.shuffle(items)
    return items


def _rand_sample(args, line):
    if len(args) != 2 or not isinstance(args[0], (list, range, str)):
        raise ArabiRuntimeError(
            f"'عينة' تحتاج قائمة وعددًا صحيحًا لكنها استلمت {len(args)} معاملًا", line)
    n = args[1]
    if isinstance(n, bool) or not isinstance(n, int):
        raise ArabiRuntimeError(
            f"معامل العدد في 'عينة' يجب أن يكون عددًا صحيحًا لكن استلمت {typename(n)}", line)
    items = list(args[0])
    if n < 0 or n > len(items):
        raise ArabiRuntimeError(
            f"عدد العينة ({n}) يجب أن يكون بين 0 وطول التسلسل ({len(items)})", line)
    return random.sample(items, n)


def _rand_seed(args, line):
    if len(args) != 1:
        raise ArabiRuntimeError("'بذرة' تتوقع معاملًا واحدًا", line)
    x = _num_check(args[0], "'بذرة'", line)
    random.seed(x)
    return None


# ================== وحدة نظام ==================

def _sys_cwd(args, line):
    if args:
        raise ArabiRuntimeError("'مجلد_العمل' لا تقبل معاملات", line)
    return os.getcwd()


def _sys_env(args, line):
    if not 1 <= len(args) <= 2 or not isinstance(args[0], str):
        raise ArabiRuntimeError(
            "'متغير' تحتاج اسم متغير نصيًا وقيمة افتراضية اختيارية", line)
    name = args[0]
    default = args[1] if len(args) == 2 else None
    return os.environ.get(name, default)


def _sys_env_all(args, line):
    if args:
        raise ArabiRuntimeError("'المتغيرات' لا تقبل معاملات", line)
    return dict(os.environ)


def _sys_listdir(args, line):
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError("'ملفات_في' تحتاج مسار مجلد نصيًا", line)
    path = args[0]
    try:
        return sorted(os.listdir(path))
    except FileNotFoundError:
        raise ArabiRuntimeError(f"المجلد '{path}' غير موجود", line)
    except NotADirectoryError:
        raise ArabiRuntimeError(f"'{path}' ملف وليس مجلدًا", line)
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن قراءة المجلد '{path}': {exc}", line)


def _sys_isdir(args, line):
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError("'مجلد_موجود' تحتاج مسارًا نصيًا", line)
    return os.path.isdir(args[0])


def _sys_mkdir(args, line):
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError("'انشاء_مجلد' تحتاج مسارًا نصيًا", line)
    try:
        os.makedirs(args[0], exist_ok=True)
        return None
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن إنشاء المجلد '{args[0]}': {exc}", line)


def _sys_join(args, line):
    if not args:
        raise ArabiRuntimeError("'فصل' تحتاج مسارًا واحدًا على الأقل", line)
    for x in args:
        if not isinstance(x, str):
            raise ArabiRuntimeError(
                f"'فصل' تحتاج نصوصًا فقط لكن استلمت {typename(x)}", line)
    return os.path.join(*args)


def _sys_basename(args, line):
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError("'اسم_الملف' تحتاج مسارًا نصيًا", line)
    return os.path.basename(args[0])


def _sys_dirname(args, line):
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError("'المجلد' تحتاج مسارًا نصيًا", line)
    return os.path.dirname(args[0])


def _sys_abspath(args, line):
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError("'المسار_الكامل' تحتاج مسارًا نصيًا", line)
    return os.path.abspath(args[0])


def _sys_platform(args, line):
    if args:
        raise ArabiRuntimeError("'النظام' لا تقبل معاملات", line)
    import platform
    return platform.system()


def _sys_args(args, line):
    """وسيطات() — قائمة الوسائط الممررة للبرنامج بعد اسم الملف."""
    if args:
        raise ArabiRuntimeError("'وسيطات' لا تقبل معاملات", line)
    return list(sys.argv[2:])


def _sys_exit(args, line):
    """خروج(كود؟) — ينهي البرنامج بكود خروج (افتراضيًا ٠)."""
    if len(args) > 1:
        raise ArabiRuntimeError("'خروج' تقبل معاملًا واحدًا على الأكثر (كود الخروج)", line)
    code = args[0] if args else 0
    if isinstance(code, bool) or not isinstance(code, int):
        raise ArabiRuntimeError(
            f"كود الخروج يجب أن يكون عددًا صحيحًا لكنه {typename(code)}", line)
    raise SystemExit(code)


# ================== وحدة تنظيم (التعبيرات النمطية) ==================

def _re_compile(pattern, name, line):
    if not isinstance(pattern, str):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج نمطًا نصيًا لكن استلمت {typename(pattern)}", line)
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ArabiRuntimeError(f"نمط غير صالح '{pattern}': {exc}", line)


def _re_text(value, name, line):
    if not isinstance(value, str):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج نصًا لكن استلمت {typename(value)}", line)
    return value


def _re_find(args, line):
    """يجد(نمط، نص) — أول تطابق أو ولا شيء."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'يجد' تحتاج معاملين (نمط ونص) لكنها استلمت {len(args)}", line)
    rx = _re_compile(args[0], 'يجد', line)
    text = _re_text(args[1], 'يجد', line)
    m = rx.search(text)
    return m.group(0) if m else None


def _re_findall(args, line):
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'كل_المطابقات' تحتاج معاملين (نمط ونص) لكنها استلمت {len(args)}", line)
    rx = _re_compile(args[0], 'كل_المطابقات', line)
    text = _re_text(args[1], 'كل_المطابقات', line)
    return rx.findall(text)


def _re_sub(args, line):
    """يستبدل(نمط، بديل، نص)."""
    if len(args) != 3:
        raise ArabiRuntimeError(
            f"'يستبدل' تحتاج ثلاثة معاملات (نمط، بديل، نص) لكنها استلمت {len(args)}", line)
    rx = _re_compile(args[0], 'يستبدل', line)
    repl = _re_text(args[1], 'يستبدل', line)
    text = _re_text(args[2], 'يستبدل', line)
    return rx.sub(repl, text)


def _re_split(args, line):
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'ينقسم' تحتاج معاملين (نمط ونص) لكنها استلمت {len(args)}", line)
    rx = _re_compile(args[0], 'ينقسم', line)
    text = _re_text(args[1], 'ينقسم', line)
    return rx.split(text)


def _re_fullmatch(args, line):
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'يطابق' تحتاج معاملين (نمط ونص) لكنها استلمت {len(args)}", line)
    rx = _re_compile(args[0], 'يطابق', line)
    text = _re_text(args[1], 'يطابق', line)
    return rx.fullmatch(text) is not None


def _re_match(args, line):
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'يبدأ' تحتاج معاملين (نمط ونص) لكنها استلمت {len(args)}", line)
    rx = _re_compile(args[0], 'يبدأ', line)
    text = _re_text(args[1], 'يبدأ', line)
    return rx.match(text) is not None


# ================== وحدة شبكة ==================

_NET_METHODS = ('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'PATCH')


def _net_request(args, line):
    """اطلب(رابط، طريقة؟، ترويسة؟، بيانات؟، مهلة؟) — طلب HTTP ويعيد قاموسًا:
    {الحالة، النص، الترويسات}. الأخطاء الشبكية ترفع خطأ، والحالات غير ٢٠٠ تعاد كناتج."""
    if not 1 <= len(args) <= 5:
        raise ArabiRuntimeError(
            f"'اطلب' تقبل من ١ إلى ٥ معاملات لكنها استلمت {len(args)}", line)
    import urllib.request
    import urllib.error

    url = args[0]
    if not isinstance(url, str):
        raise ArabiRuntimeError(f"'اطلب' تحتاج رابطًا نصيًا لكن استلمت {typename(url)}", line)
    if not url.startswith(('http://', 'https://')):
        raise ArabiRuntimeError(
            f"الرابط يجب أن يبدأ بـ http:// أو https:// — استلمت '{url}'", line)
    # علامة الاستفهام العربية تُعامل كفاصل استعلام قياسي
    url = url.replace('؟', '?')
    # ترميز المحارف غير اللاتينية (مثل المسارات العربية) كما يتطلب HTTP
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")

    method = 'GET'
    if len(args) >= 2:
        method = args[1]
        if not isinstance(method, str) or method.upper() not in _NET_METHODS:
            raise ArabiRuntimeError(
                f"طريقة الطلب يجب أن تكون واحدة من: {', '.join(_NET_METHODS)}", line)
        method = method.upper()

    headers = {}
    if len(args) >= 3:
        if not isinstance(args[2], dict):
            raise ArabiRuntimeError(
                f"الترويسات يجب أن تكون قاموسًا لكن استلمت {typename(args[2])}", line)
        for k, v in args[2].items():
            headers[str(k)] = str(v)

    data = None
    if len(args) >= 4 and args[3] is not None:
        payload = args[3]
        if isinstance(payload, str):
            data = payload.encode('utf-8')
        elif isinstance(payload, dict):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers.setdefault('Content-Type', 'application/json; charset=utf-8')
        else:
            raise ArabiRuntimeError(
                f"البيانات يجب أن تكون نصًا أو قاموسًا لكن استلمت {typename(payload)}", line)

    timeout = 10.0
    if len(args) == 5:
        timeout = _num_check(args[4], "مهلة 'اطلب'", line)
        if timeout <= 0:
            raise ArabiRuntimeError("المهلة يجب أن تكون عددًا موجبًا", line)

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode('utf-8', errors='replace')
            resp_headers = dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        # أخطاء HTTP (٤٠٤ وغيرها) تعاد كناتج طبيعي ليقرر المستخدم
        try:
            body = exc.read().decode('utf-8', errors='replace')
        except Exception:
            body = ''
        return {'الحالة': exc.code, 'النص': body,
                'الترويسات': dict(exc.headers.items() if exc.headers else [])}
    except urllib.error.URLError as exc:
        raise ArabiRuntimeError(
            f"تعذر الاتصال بالرابط '{url}': {exc.reason}", line)
    except OSError as exc:
        raise ArabiRuntimeError(f"فشل طلب الشبكة '{url}': {exc}", line)

    return {'الحالة': status, 'النص': body, 'الترويسات': resp_headers}


def _net_text(args, line):
    """نص_الصفحة(رابط) — يعيد نص استجابة الرابط مباشرة."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'نص_الصفحة' تحتاج رابطًا واحدًا لكنها استلمت {len(args)}", line)
    return _net_request([args[0]], line)['النص']


def _net_download(args, line):
    """تنزيل(رابط، مسار، مهلة؟) — ينزّل محتوى الرابط إلى ملف (ثنائي آمن)
    ويعيد عدد البايتات المكتوبة. يشارك 'اطلب' نفس قواعد الروابط والمهلة.
    (الإصدار 1.15)
    """
    if not 2 <= len(args) <= 3:
        raise ArabiRuntimeError(
            f"'تنزيل' تقبل رابطًا ومسارًا ومهلة اختيارية لكنها استلمت "
            f'{len(args)} معاملات', line)
    url = args[0]
    if not isinstance(url, str):
        raise ArabiRuntimeError(
            f"'تنزيل' تحتاج رابطًا نصيًا لكن استلمت {typename(url)}", line)
    path = args[1]
    if not isinstance(path, str):
        raise ArabiRuntimeError(
            f"مسار التنزيل يجب أن يكون نصًا لكن استلم {typename(path)}", line)
    timeout = 10.0
    if len(args) == 3:
        timeout = _num_check(args[2], "مهلة 'تنزيل'", line)
        if timeout <= 0:
            raise ArabiRuntimeError('المهلة يجب أن تكون عددًا موجبًا', line)
    import urllib.request
    import urllib.error
    if not url.startswith(('http://', 'https://')):
        raise ArabiRuntimeError(
            f"الرابط يجب أن يبدأ بـ http:// أو https:// — استلمت '{url}'", line)
    url = url.replace('؟', '?')
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise ArabiRuntimeError(
            f"فشل تنزيل '{url}': رمز الحالة {exc.code}", line)
    except Exception as exc:
        raise ArabiRuntimeError(
            f"فشل تنزيل '{url}': {exc}", line)
    try:
        with open(path, 'wb') as f:
            f.write(data)
    except OSError as exc:
        raise ArabiRuntimeError(
            f"تعذّرت كتابة ملف التنزيل '{path}': {exc}", line)
    return len(data)


# ================== المهام غير المتزامنة (الإصدار 1.15) ==================

def _task_list(args, name, line):
    """يتحقق من معامل قائمة مهام لـ انتظر_الجميع/سباق ويعيدها.

    المهام نتاج دوال غير متزامنة أو قدّم على تجمع الخيوط أو تجمع
    العمليات (1.17) أو موزع (1.18) — الأربعة بواجهة واحدة.
    """
    from .processes import ProcessTaskValue
    if len(args) != 1 or not isinstance(args[0], list):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج قائمة مهام — مثال: {name}([م١، م٢])", line)
    for i, t in enumerate(args[0]):
        if not isinstance(t, (TaskValue, ProcessTaskValue,
                              DistributedTaskValue)):
            raise ArabiRuntimeError(
                f'العنصر رقم {i + 1} ليس مهمة بل {typename(t)} — '
                'المهام نتاج استدعاء دوال غير متزامنة أو قدّم على تجمع '
                'أو موزع',
                line)
    return args[0]


def _async_wait_all(args, line):
    """انتظر_الجميع([م١، م٢، ...]) — ينتظر كل المهام ويعيد قائمة النتائج
    بترتيبها الأصلي. يرفع خطأ أول مهمة فشلت (بعد انتظار الجميع)."""
    tasks = _task_list(args, 'انتظر_الجميع', line)
    results = []
    first_error = None
    for t in tasks:
        try:
            results.append(t.result(line))
        except ArabiRuntimeError as exc:
            if first_error is None:
                first_error = exc
            results.append(None)
    if first_error is not None:
        raise first_error
    return results


def _async_race(args, line):
    """سباق([م١، م٢، ...]) — يعيد أول مهمة تنتهي (نجحت أو فشلت)،
    والبقية تواصل عملها في الخلفية حتى النهاية.
    انتظر النتيجة: نتيجة = انتظر سباق([م١، م٢])."""
    tasks = _task_list(args, 'سباق', line)
    if not tasks:
        raise ArabiRuntimeError(
            "'سباق' تحتاج مهمة واحدة على الأقل في القائمة", line)
    done_q = queue.Queue()

    def _watch(task):
        try:
            task.result()            # ينتظر الانتهاء (الخطأ يُبتلع هنا)
        except ArabiError:
            pass
        done_q.put(task)

    for t in tasks:
        watcher = threading.Thread(target=_watch, args=(t,), daemon=True,
                                   name='سباق-عربي')
        watcher.start()
    return done_q.get()


def _async_sleep(args, line):
    """انتظر_زمن(ثوان) — يوقف المهمة الحالية (أو البرنامج) مدة محددة.
    داخل دالة غير متزامنة يوقف هذه المهمة وحدها دون غيرها."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'انتظر_زمن' تتوقع معاملًا واحدًا (عدد الثواني) لكنها استلمت "
            f'{len(args)}', line)
    seconds = _num_check(args[0], "'انتظر_زمن'", line)
    if seconds < 0:
        raise ArabiRuntimeError('عدد الثواني يجب أن يكون موجبًا', line)
    time.sleep(seconds)
    return None


def _task_result(obj, args, line):
    """مهمة.نتيجة() — ينتظر الانتهاء ويعيد النتيجة (أو يرفع الخطأ)."""
    _require_args('نتيجة', args, 0, 0, line)
    return obj.result(line)


def _task_error(obj, args, line):
    """مهمة.الخطأ() — ينتظر الانتهاء ويعيد رسالة الخطأ أو 'ولا شيء'."""
    _require_args('الخطأ', args, 0, 0, line)
    return obj.error()


def _task_ready(obj, args, line):
    """مهمة.جاهز() — هل انتهت المهمة؟ فحص فوري بلا انتظار."""
    _require_args('جاهز', args, 0, 0, line)
    return obj.ready()


def _task_wait(obj, args, line):
    """مهمة.انتظر() — ينتظر انتهاء المهمة دون إعادة النتيجة."""
    _require_args('انتظر', args, 0, 0, line)
    try:
        obj.result(line)
    except ArabiError:
        pass                        # يبتلع الخطأ — من يريد النتيجة أو الخطأ يجدها بطريقته
    return None


TASK_METHODS.update({
    'نتيجة': _task_result,
    'الخطأ': _task_error,
    'جاهز': _task_ready,
    'انتظر': _task_wait,
})


# ================== تجمع الخيوط (الإصدار 1.16) ==================

POOL_MAX_SIZE = 512          # حد أعلى معقول يمنع استهلاك الخيوط الجامح

def _pool_create(interp, args, line):
    """تجمع(عدد) — ينشئ تجمع خيوط محدود الحجم يعاد استخدام خيوطه.

    قدّم أعمالًا بـ قدّم على الناتج، واجمع النتائج بـ انتظر أو
    انتظر_الجميع. الإنهاء بـ إنهاء() — ينتظر تصفية كل المقدَّم.
    """
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'تجمع' تتوقع معاملًا واحدًا (عدد الخيوط) لكنها استلمت "
            f'{len(args)}', line)
    size = args[0]
    if isinstance(size, bool) or not isinstance(size, int):
        raise ArabiRuntimeError(
            f"'تجمع' تتوقع عددًا صحيحًا موجبًا لكنها استلمت {typename(size)}",
            line)
    if size < 1:
        raise ArabiRuntimeError(
            f"'تجمع' يحتاج عددًا موجبًا من الخيوط (استلم {size})", line)
    if size > POOL_MAX_SIZE:
        raise ArabiRuntimeError(
            f'الحد الأعلى لعدد خيوط التجمع هو {POOL_MAX_SIZE} (استلم {size})',
            line)
    pool = PoolValue(size)
    pool._interp = interp
    return pool


def _pool_submit(obj, args, kwargs, line):
    """تجمع.قدّم(دالة، معاملات...) — يقدّم عملًا للتجمع ويعيد مهمة.

    المعاملات تُربط لحظة التقديم، والتنفيذ على خيوط التجمع بترتيب
    التقديم كلما انفضّ خيط. الدالة قد تكون عادية أو غير متزامنة أو
    سهمية أو طريقة مرتبطة أو حتى دالة جاهزة.
    """
    if not args:
        raise ArabiRuntimeError(
            "'قدّم' تحتاج دالة على الأقل — مثال: تج.قدّم(حسب، ٥)", line)
    with obj._lock:
        if obj._closed:
            raise ArabiRuntimeError(
                "التجمع مغلق — لا يقبل مهامًا جديدة بعد 'إنهاء'", line)
    interp = obj._interp
    func = args[0]
    rest = args[1:]
    task = TaskValue()

    if isinstance(func, ArabiFunc):
        local = interp._bind_call_args(func, rest, kwargs, line)
        this_val = None
        job = obj._make_job(func, local, this_val, task)
    elif isinstance(func, BoundMethod):
        inner = func.func
        if not isinstance(inner, ArabiFunc):
            raise ArabiRuntimeError(
                f"'قدّم' تتوقع دالة لكنها استلمت {typename(func)}", line)
        local = interp._bind_call_args(inner, rest, kwargs, line)
        local.define('هذا', func.instance)   # كـ _invoke_bound تمامًا
        job = obj._make_job(inner, local, func.instance, task)
    elif isinstance(func, BuiltinFunc):
        fn = func

        def job():
            try:
                if fn.takes_interp:
                    result = fn.fn(interp, rest, line)
                else:
                    result = fn.fn(rest, line)
                task._finish(result, None)
            except ArabiError as exc:
                task._finish(None, exc)
            except Exception as exc:      # شبكة أمان — لا تموت المهمة بصمت
                task._finish(None, ArabiRuntimeError(
                    f'خطأ داخل مهمة التجمع: {exc}'))
    else:
        raise ArabiRuntimeError(
            f"'قدّم' تتوقع دالة لكنها استلمت {typename(func)}", line)

    obj._queue.put(job)
    return task


def _pool_shutdown(obj, args, line):
    """تجمع.إنهاء() — يغلق التجمع وينتظر تصفية كل المهام المقدَّمة.

    مهام قيد التنفيذ تكمل حتى النهاية ثم تخرج الخيوط العاملة.
    الاستدعاء بعد إغلاق آمن (تكرار بلا أثر).
    """
    _require_args('إنهاء', args, 0, 0, line)
    with obj._lock:
        if obj._closed:
            return None
        obj._closed = True
        for _ in obj._threads:
            obj._queue.put(None)          # إشارة إنهاء لكل خيط
    current = threading.current_thread()
    for worker in obj._threads:
        if worker is not current:         # إنهاء من داخل مهمة — لا ينتظر نفسه
            worker.join()
    return None


def _pool_size(obj, args, line):
    """تجمع.حجم() — يعيد عدد الخيوط العاملة في التجمع."""
    _require_args('حجم', args, 0, 0, line)
    return obj.size


POOL_METHODS.update({
    'إنهاء': _pool_shutdown,
    'حجم': _pool_size,
})


# ================== طرق العمليات المنفصلة (الإصدار 1.17) ==================

def _proc_result(obj, args, line):
    """عملية.نتيجة() — ينتظر الانتهاء ويعيد النتيجة (أو يرفع الخطأ)."""
    _require_args('نتيجة', args, 0, 0, line)
    return obj.result(line)


def _proc_ready(obj, args, line):
    """عملية.جاهز() — هل انتهت العملية؟ فحص فوري بلا انتظار."""
    _require_args('جاهز', args, 0, 0, line)
    return obj.ready()


def _proc_wait(obj, args, line):
    """عملية.انتظر() — ينتظر انتهاء العملية دون إعادة النتيجة."""
    _require_args('انتظر', args, 0, 0, line)
    try:
        obj.result(line)
    except ArabiError:
        pass                    # يبتلع الخطأ — النتيجة أو الخطأ يجدها صاحبها
    return None


def _proc_pid(obj, args, line):
    """عملية.معرف() — معرف العملية في نظام التشغيل."""
    _require_args('معرف', args, 0, 0, line)
    return obj.pid()


def _proc_error_method(obj, args, line):
    """عملية.الخطأ() — ينتظر الانتهاء ويعيد رسالة الخطأ أو 'ولا شيء'."""
    _require_args('الخطأ', args, 0, 0, line)
    try:
        obj.result(line)
    except ArabiError as exc:
        return exc.message
    return None


PROCESS_METHODS.update({
    'نتيجة': _proc_result,
    'الخطأ': _proc_error_method,
    'جاهز': _proc_ready,
    'انتظر': _proc_wait,
    'معرف': _proc_pid,
})


def _ptask_result(obj, args, line):
    """مهمة العملية.نتيجة() — ينتظر ويعيد النتيجة (أو يرفع الخطأ)."""
    _require_args('نتيجة', args, 0, 0, line)
    return obj.result(line)


def _ptask_error(obj, args, line):
    """مهمة العملية.الخطأ() — ينتظر ويعيد رسالة الخطأ أو 'ولا شيء'."""
    _require_args('الخطأ', args, 0, 0, line)
    return obj.error()


def _ptask_ready(obj, args, line):
    """مهمة العملية.جاهز() — فحص فوري بلا انتظار."""
    _require_args('جاهز', args, 0, 0, line)
    return obj.ready()


def _ptask_wait(obj, args, line):
    """مهمة العملية.انتظر() — انتظار بلا إعادة النتيجة."""
    _require_args('انتظر', args, 0, 0, line)
    try:
        obj.result(line)
    except ArabiError:
        pass
    return None


PROCESS_TASK_METHODS.update({
    'نتيجة': _ptask_result,
    'الخطأ': _ptask_error,
    'جاهز': _ptask_ready,
    'انتظر': _ptask_wait,
})


def _ppool_shutdown(obj, args, line):
    """تجمع العمليات.إنهاء() — يغلق التجمع وينتظر تصفية الجاري منه."""
    _require_args('إنهاء', args, 0, 0, line)
    obj.shutdown(line)
    return None


def _ppool_size(obj, args, line):
    """تجمع العمليات.حجم() — عدد العمليات العاملة."""
    _require_args('حجم', args, 0, 0, line)
    return obj.size


PROCESS_POOL_METHODS.update({
    'إنهاء': _ppool_shutdown,
    'حجم': _ppool_size,
})


# ================== طرق الموزع والمهام الموزعة (الإصدار 1.18) ==================

def _dist_workers(obj, args, line):
    """موزع.عمال() — عدد العمالة المتصلة بالموزع الآن."""
    _require_args('عمال', args, 0, 0, line)
    return obj._server.workers()


def _dist_port(obj, args, line):
    """موزع.منفذ() — المنفذ الفعلي بعد الربط (للاختيار التلقائي 0)."""
    _require_args('منفذ', args, 0, 0, line)
    return obj._server.port()


def _dist_host(obj, args, line):
    """موزع.عنوان() — العنوان المرتبط به الخادم."""
    _require_args('عنوان', args, 0, 0, line)
    return obj._server.host()


def _dist_size(obj, args, line):
    """موزع.حجم() — عدد المهام المقدَّمة إلى الموزع منذ بدئه."""
    _require_args('حجم', args, 0, 0, line)
    return obj._server.total()


def _dist_encrypted(obj, args, line):
    """موزع.مشفّر() — هل قناة الموزع مشفرة؟ (بدأ بمفتاح سري — 1.21).

    الموزع المفتاحي يشتق مفاتيح جلسة من مفتاحه وتحدي كل اتصال فتُشفّر
    كل الأعمال والنتائج العابرة للشبكة — والحر يعمل كالسابق بلا تشفير.
    """
    _require_args('مشفّر', args, 0, 0, line)
    return obj._server.encrypted()


def _dist_wait_workers(obj, args, line):
    """موزع.انتظر_العمال(عدد؟، مهلة؟) — يحجب حتى يتصل عدد كافٍ من
    العمالة (الافتراضي: عامل واحد حتى 30 ثانية) — وإلا رفع خطأ
    (التحقق من المعاملات داخل الخادم نفسه)."""
    count, timeout = 1, 30
    if len(args) > 2:
        raise ArabiRuntimeError(
            f"'انتظر_العمال' تأخذ معاملين على الأكثر (العدد ثم المهلة) "
            f'لكنها استلمت {len(args)}', line)
    if len(args) >= 1:
        count = args[0]
    if len(args) == 2:
        timeout = args[1]
    obj._server.wait_workers(count, timeout, line)
    return None


def _dist_shutdown(obj, args, line):
    """موزع.إنهاء() — يوقف قبول المهام وينتظر تصفية الجاري ثم يودّع
    العمالة — فتعود حلقة كل عامل بلا نتائج أعمال جديدة."""
    _require_args('إنهاء', args, 0, 0, line)
    obj._server.shutdown(line)
    return None


DISPATCHER_METHODS.update({
    'عمال': _dist_workers,
    'منفذ': _dist_port,
    'عنوان': _dist_host,
    'حجم': _dist_size,
    'مشفّر': _dist_encrypted,
    'انتظر_العمال': _dist_wait_workers,
    'إنهاء': _dist_shutdown,
})


def _dtask_result(obj, args, line):
    """المهمة الموزعة.نتيجة() — ينتظر ويعيد النتيجة (أو يرفع الخطأ)."""
    _require_args('نتيجة', args, 0, 0, line)
    return obj.result(line)


def _dtask_error(obj, args, line):
    """المهمة الموزعة.الخطأ() — ينتظر ويعيد رسالة الخطأ أو 'ولا شيء'."""
    _require_args('الخطأ', args, 0, 0, line)
    return obj.error()


def _dtask_ready(obj, args, line):
    """المهمة الموزعة.جاهز() — فحص فوري بلا انتظار."""
    _require_args('جاهز', args, 0, 0, line)
    return obj.ready()


def _dtask_wait(obj, args, line):
    """المهمة الموزعة.انتظر() — انتظار بلا إعادة النتيجة."""
    _require_args('انتظر', args, 0, 0, line)
    try:
        obj.result(line)
    except ArabiError:
        pass
    return None


def _dtask_id(obj, args, line):
    """المهمة الموزعة.معرف() — الرقم التسلسلي للمهمة لدى الموزع."""
    _require_args('معرف', args, 0, 0, line)
    return obj.id


DIST_TASK_METHODS.update({
    'نتيجة': _dtask_result,
    'الخطأ': _dtask_error,
    'جاهز': _dtask_ready,
    'انتظر': _dtask_wait,
    'معرف': _dtask_id,
})


# ================== وحدة تحويل (الأرقام العربية) ==================

EN2AR = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')

_ONES_AR = ('', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة',
            'ستة', 'سبعة', 'ثمانية', 'تسعة')
_TEENS_AR = ('عشرة', 'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر',
             'خمسة عشر', 'ستة عشر', 'سبعة عشر', 'ثمانية عشر', 'تسعة عشر')
_TENS_AR = ('', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون',
            'ستون', 'سبعون', 'ثمانون', 'تسعون')
_HUNDREDS_AR = ('', 'مئة', 'مئتان', 'ثلاثمئة', 'أربعمئة', 'خمسمئة',
                'ستمئة', 'سبعمئة', 'ثمانمئة', 'تسعمئة')
# (مفرد، مثنى، جمع ٣-١٠، منصوب ١١-٩٩، مجرور ١٠٠+)
_SCALES_AR = (
    ('مليار', 'ملياران', 'مليارات', 'مليارًا', 'مليار'),
    ('مليون', 'مليونان', 'ملايين', 'مليونًا', 'مليون'),
    ('ألف', 'ألفان', 'آلاف', 'ألفًا', 'ألف'),
)


def _three_digits_words(n):
    """يكتب عددًا من ١ إلى ٩٩٩ بكلمات عربية (الآحاد تسبق العشرات)."""
    parts = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append(_HUNDREDS_AR[hundreds])
    tens, ones = divmod(rest, 10)
    if tens == 1:
        parts.append(_TEENS_AR[ones])
    else:
        # العربية تقرأ الآحاد قبل العشرات: خمسة وستون
        if ones:
            parts.append(_ONES_AR[ones])
        if tens:
            parts.append(_TENS_AR[tens])
    return ' و'.join(parts)


def _scale_words(count, forms):
    singular, dual, plural, accusative, genitive = forms
    if count == 1:
        return singular
    if count == 2:
        return dual
    if count <= 10:
        return f'{_three_digits_words(count)} {plural}'
    if count <= 99:
        return f'{_three_digits_words(count)} {accusative}'
    return f'{_three_digits_words(count)} {genitive}'


def tafqit(n, line=None):
    """تفقيط: يحول عددًا صحيحًا إلى كلمات عربية (حتى ٩٩٩ مليارًا و٩٩٩...)."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise ArabiRuntimeError(
            f"'كلمات' تحتاج عددًا صحيحًا لكنها استلمت {typename(n)}", line)
    if n == 0:
        return 'صفر'
    prefix = ''
    if n < 0:
        prefix = 'سالب '
        n = -n
    if n >= 10 ** 12:
        raise ArabiRuntimeError(
            "'كلمات' تدعم الأعداد حتى ٩٩٩,٩٩٩,٩٩٩,٩٩٩ — العدد كبير جدًا", line)
    billions, rest = divmod(n, 10 ** 9)
    millions, rest = divmod(rest, 10 ** 6)
    thousands, units = divmod(rest, 10 ** 3)
    parts = []
    if billions:
        parts.append(_scale_words(billions, _SCALES_AR[0]))
    if millions:
        parts.append(_scale_words(millions, _SCALES_AR[1]))
    if thousands:
        parts.append(_scale_words(thousands, _SCALES_AR[2]))
    if units:
        parts.append(_three_digits_words(units))
    return prefix + ' و'.join(parts)


def _conv_eastern(args, line):
    """إلى_شرقية(قيمة) — يحول الأرقام الغربية إلى عربية مشرقية (٠-٩)."""
    if len(args) != 1:
        raise ArabiRuntimeError("'إلى_شرقية' تتوقع معاملًا واحدًا", line)
    v = args[0]
    if isinstance(v, str):
        return v.translate(EN2AR)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ArabiRuntimeError(
            f"'إلى_شرقية' تحتاج عددًا أو نصًا لكنها استلمت {typename(v)}", line)
    return str(v).translate(EN2AR)


def _conv_western(args, line):
    """إلى_غربية(نص) — يحول الأرقام العربية الشرقية إلى غربية ويعيد نصًا."""
    if len(args) != 1 or not isinstance(args[0], str):
        raise ArabiRuntimeError(
            f"'إلى_غربية' تحتاج نصًا واحدًا لكنها استلمت "
            f"{typename(args[0]) if args else 'لا معاملات'}", line)
    return args[0].translate(AR2EN)


def _conv_words(args, line):
    """كلمات(عدد) — تفقيط العدد إلى كلمات عربية."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'كلمات' تتوقع معاملًا واحدًا لكنها استلمت {len(args)}", line)
    return tafqit(args[0], line)


# ================== وحدة قاعدة (SQLite) — الإصدار 1.7 ==================

def _db_open(args, line):
    """افتح(مسار؟) — يفتح قاعدة SQLite ويعيد اتصالًا.

    بدون معاملات تُنشأ قاعدة في الذاكرة تختفي عند انتهاء البرنامج.
    """
    if len(args) > 1:
        raise ArabiRuntimeError(
            f"'افتح' تقبل معاملًا واحدًا على الأكثر (مسار الملف) لكنها "
            f"استلمت {len(args)}", line)
    if args:
        path = _path_str(args[0], 'افتح', line)
        name = os.path.basename(path)
    else:
        path = ':memory:'
        name = 'في الذاكرة'
    try:
        # isolation_level=None → تنفيذ تلقائي (لا حاجة لأمر 'احفظ')
        conn = sqlite3.connect(path, isolation_level=None)
    except sqlite3.Error as exc:
        raise ArabiRuntimeError(f"تعذر فتح قاعدة البيانات '{path}': {exc}", line)
    return DBValue(conn, name)


def _db_check(db, line):
    if not isinstance(db, DBValue):
        raise ArabiRuntimeError(
            f"العملية تحتاج اتصال قاعدة بيانات لكن استلمت {typename(db)}", line)
    return db


def _db_sql(value, name, line):
    if not isinstance(value, str) or not value.strip():
        raise ArabiRuntimeError(
            f"'{name}' تحتاج استعلامًا نصيًا غير فارغ", line)
    return value


def _db_params(args, name, line):
    """معاملات الاستعلام الاختيارية — قائمة قيم بسيطة."""
    if not args:
        return ()
    if not isinstance(args[0], (list, tuple)):
        raise ArabiRuntimeError(
            f"معاملات '{name}' يجب أن تكون قائمة قيم لكنها "
            f"{typename(args[0])}", line)
    for x in args[0]:
        if isinstance(x, (list, dict, DBValue, GeneratorValue)):
            raise ArabiRuntimeError(
                f"معاملات الاستعلام يجب أن تكون قيمًا بسيطة "
                f'(أعداد ونصوص) لكن وجدت {typename(x)}', line)
    return tuple(args[0])


def _db_execute(args, line):
    """نفذ(اتصال، استعلام، معاملات؟) — ينفذ أمرًا ويعيد عدد الصفوف المتأثرة."""
    if not 2 <= len(args) <= 3:
        raise ArabiRuntimeError(
            f"'نفذ' تحتاج اتصالًا واستعلامًا (ومعاملات اختياريًا) "
            f"لكنها استلمت {len(args)}", line)
    db = _db_check(args[0], line)
    sql = _db_sql(args[1], 'نفذ', line)
    params = _db_params(args[2:], 'نفذ', line)
    try:
        cur = db.conn.execute(sql, params)
        return cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    except sqlite3.Error as exc:
        raise ArabiRuntimeError(f'خطأ في قاعدة البيانات: {exc}', line)


def _db_query(args, line):
    """استعلم(اتصال، استعلام، معاملات؟) — يعيد صفوف النتائج قوائم."""
    if not 2 <= len(args) <= 3:
        raise ArabiRuntimeError(
            f"'استعلم' تحتاج اتصالًا واستعلامًا (ومعاملات اختياريًا) "
            f"لكنها استلمت {len(args)}", line)
    db = _db_check(args[0], line)
    sql = _db_sql(args[1], 'استعلم', line)
    params = _db_params(args[2:], 'استعلم', line)
    try:
        cur = db.conn.execute(sql, params)
        return [list(row) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        raise ArabiRuntimeError(f'خطأ في قاعدة البيانات: {exc}', line)


def _db_columns(args, line):
    """أعمدة(اتصال، استعلام، معاملات؟) — يعيد أسماء أعمدة النتائج."""
    if not 2 <= len(args) <= 3:
        raise ArabiRuntimeError(
            f"'أعمدة' تحتاج اتصالًا واستعلامًا (ومعاملات اختياريًا) "
            f"لكنها استلمت {len(args)}", line)
    db = _db_check(args[0], line)
    sql = _db_sql(args[1], 'أعمدة', line)
    params = _db_params(args[2:], 'أعمدة', line)
    try:
        cur = db.conn.execute(sql, params)
        cur.fetchall()
        return [d[0] for d in cur.description or []]
    except sqlite3.Error as exc:
        raise ArabiRuntimeError(f'خطأ في قاعدة البيانات: {exc}', line)


def _db_close(args, line):
    """أغلق(اتصال) — يغلق الاتصال ويحرر الملف."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'أغلق' تحتاج اتصال قاعدة بيانات لكنها استلمت {len(args)}", line)
    db = _db_check(args[0], line)
    try:
        db.conn.close()
    except sqlite3.Error as exc:
        raise ArabiRuntimeError(f'تعذر إغلاق قاعدة البيانات: {exc}', line)
    return None


DB_METHODS.update({
    'نفذ': lambda db, args, line: _db_execute([db] + args, line),
    'استعلم': lambda db, args, line: _db_query([db] + args, line),
    'أعمدة': lambda db, args, line: _db_columns([db] + args, line),
    'أغلق': lambda db, args, line: _db_close([db], line),
})


def _gen_next(obj, args, line):
    """التالي() — القيمة التالية من المولد أو خطأ عند النهاية."""
    _require_args('التالي', args, 0, 0, line)
    return obj.next(line)


def _gen_close(obj, args, line):
    """أغلق() — يغلق المولد مبكرًا (ينفذ كتل 'اخيرا' في جسمه)."""
    _require_args('أغلق', args, 0, 0, line)
    obj.close()
    return None


GENERATOR_METHODS.update({
    'التالي': _gen_next,
    'أغلق': _gen_close,
})


# ================== وحدة ترميز (base64 والبصمات) — الإصدار 1.7 ==================

def _enc_text(value, name, line):
    if not isinstance(value, str):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج نصًا لكن استلمت {typename(value)}", line)
    return value


def _enc_b64encode(args, line):
    """شفّر64(نص) — يرمز النص بـ Base64 ويعيد نصًا."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'شفّر64' تحتاج نصًا واحدًا لكنها استلمت {len(args)}", line)
    text = _enc_text(args[0], 'شفّر64', line)
    return base64.b64encode(text.encode('utf-8')).decode('ascii')


def _enc_b64decode(args, line):
    """فك64(نص) — يفك ترميز Base64 ويعيد النص الأصلي."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'فك64' تحتاج نصًا واحدًا لكنها استلمت {len(args)}", line)
    text = _enc_text(args[0], 'فك64', line)
    try:
        return base64.b64decode(text, validate=True).decode('utf-8')
    except (base64.binascii.Error, ValueError):
        raise ArabiRuntimeError(f"النص '{text}' ليس ترميز Base64 صالحًا", line)
    except UnicodeDecodeError:
        raise ArabiRuntimeError(
            'محتوى Base64 ليس نصًا عربيًا/UTF-8 صالحًا', line)


def _enc_hash(algorithm, label):
    def fn(args, line):
        if len(args) != 1:
            raise ArabiRuntimeError(
                f"'{label}' تحتاج نصًا واحدًا لكنها استلمت {len(args)}", line)
        text = _enc_text(args[0], label, line)
        return hashlib.new(algorithm, text.encode('utf-8')).hexdigest()
    return fn


# ================== وحدة جداول (CSV) — الإصدار 1.7 ==================

def _csv_delim(args, index, line):
    """فاصل اختياري — حرف واحد (الافتراضي الفاصلة الغربية)."""
    if len(args) <= index:
        return ','
    delim = args[index]
    if not isinstance(delim, str) or len(delim) != 1:
        raise ArabiRuntimeError(
            "الفاصل يجب أن يكون حرفًا واحدًا مثل ',' أو '؛'", line)
    return delim


def _csv_rows(value, name, line):
    """يتأكد أن القيمة قائمة صفوف (قوائم)."""
    if not isinstance(value, list):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج قائمة صفوف لكن استلمت {typename(value)}", line)
    for i, row in enumerate(value, 1):
        if not isinstance(row, list):
            raise ArabiRuntimeError(
                f"الصف رقم {i} ليس قائمة — كل صف قائمة خلايا", line)
        for j, cell in enumerate(row):
            if isinstance(cell, (list, dict)):
                raise ArabiRuntimeError(
                    f"الخلية ({i}، {j + 1}) من نوع {typename(cell)} — "
                    'الخلايا تكون أعدادًا أو نصوصًا أو صح/خطأ', line)
    return value


def _csv_cell_text(cell):
    if cell is None:
        return ''
    if isinstance(cell, bool):
        return 'صح' if cell else 'خطأ'
    return display(cell)


def _csv_read(args, line):
    """اقرأ(مسار، فاصل؟) — يعيد صفوف الملف قوائم نصوص."""
    if not 1 <= len(args) <= 2:
        raise ArabiRuntimeError(
            f"'اقرأ' تحتاج مسارًا (وفاصلًا اختياريًا) لكنها استلمت {len(args)}", line)
    path = _path_str(args[0], 'اقرأ', line)
    delim = _csv_delim(args, 1, line)
    try:
        with open(path, encoding='utf-8', newline='') as f:
            return [list(row) for row in csv.reader(f, delimiter=delim)]
    except FileNotFoundError:
        raise ArabiRuntimeError(f"الملف '{path}' غير موجود", line)
    except UnicodeDecodeError:
        raise ArabiRuntimeError(f"الملف '{path}' يجب أن يكون بترميز UTF-8", line)
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن قراءة الملف '{path}': {exc}", line)
    except csv.Error as exc:
        raise ArabiRuntimeError(f"ملف CSV غير صالح '{path}': {exc}", line)


def _csv_write(args, line):
    """اكتب(مسار، صفوف، فاصل؟) — يكتب صفوف القوائم في ملف CSV."""
    if not 2 <= len(args) <= 3:
        raise ArabiRuntimeError(
            f"'اكتب' تحتاج مسارًا وقائمة صفوف (وفاصلًا اختياريًا) "
            f"لكنها استلمت {len(args)}", line)
    path = _path_str(args[0], 'اكتب', line)
    rows = _csv_rows(args[1], 'اكتب', line)
    delim = _csv_delim(args, 2, line)
    try:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=delim)
            for row in rows:
                writer.writerow([_csv_cell_text(c) for c in row])
        return None
    except OSError as exc:
        raise ArabiRuntimeError(f"لا يمكن كتابة الملف '{path}': {exc}", line)


def _csv_parse(args, line):
    """حلل(نص، فاصل؟) — يحلل نص CSV ويعيد صفوفه."""
    if not 1 <= len(args) <= 2:
        raise ArabiRuntimeError(
            f"'حلل' تحتاج نصًا (وفاصلًا اختياريًا) لكنها استلمت {len(args)}", line)
    text = _enc_text(args[0], 'حلل', line)
    delim = _csv_delim(args, 1, line)
    try:
        return [list(row) for row in csv.reader(text.splitlines(), delimiter=delim)]
    except csv.Error as exc:
        raise ArabiRuntimeError(f'نص CSV غير صالح: {exc}', line)


def _csv_text(args, line):
    """نص(صفوف، فاصل؟) — يحول صفوف القوائم إلى نص CSV."""
    if not 1 <= len(args) <= 2:
        raise ArabiRuntimeError(
            f"'نص' تحتاج قائمة صفوف (وفاصلًا اختياريًا) لكنها استلمت {len(args)}", line)
    rows = _csv_rows(args[0], 'نص', line)
    delim = _csv_delim(args, 1, line)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delim, lineterminator='\n')
    for row in rows:
        writer.writerow([_csv_cell_text(c) for c in row])
    return out.getvalue()


# ================== وحدة خيوط (الإصدار 1.8) ==================

def _thr_spawn(interp, args, line):
    """شغّل(دالة، وسائط...) — يشغل دالة عربية في خيط مستقل ويعيد خيطًا.

    لو كانت الدالة غير متزامنة (1.15) يعيد مهمتها مباشرة — فالاستدعاء
    نفسه يشغّلها في خيط، ولا معنى لخيط ينتظر مهمة.
    """
    if not args:
        raise ArabiRuntimeError(
            "'شغّل' تحتاج الدالة المراد تشغيلها كمعامل أول", line)
    func = args[0]
    if not isinstance(func, (ArabiFunc, BuiltinFunc, BoundMethod)):
        raise ArabiRuntimeError(
            f"المعامل الأول لـ 'شغّل' يجب أن يكون دالة لكنه "
            f'{typename(func)}', line)
    rest_args = list(args[1:])
    if isinstance(func, ArabiFunc) and func.is_async:
        return interp._call_value(func, rest_args, {}, line)
    tv = ThreadValue()

    def _worker():
        try:
            result = interp._call_value(func, rest_args, {}, line)
            tv._finish('نهاية', result)
        except ArabiError as exc:
            tv._finish('خطأ', exc)
        except Exception as exc:            # شبكة أمان — لا يموت الخيط بصمت
            tv._finish('خطأ', ArabiRuntimeError(f'خطأ داخل الخيط: {exc}'))

    tv.thread = threading.Thread(target=_worker, daemon=True,
                                 name='خيط-عربي')
    tv.thread.start()
    return tv


def _thr_join_all(args, line):
    """انتظر_الكل(قائمة_خيوط) — ينتظر كل الخيوط ويعيد قائمة النتائج."""
    if len(args) != 1 or not isinstance(args[0], list):
        raise ArabiRuntimeError(
            "'انتظر_الكل' تحتاج قائمة خيوط — مثال: انتظر_الكل(المهام)", line)
    results = []
    for i, t in enumerate(args[0]):
        if not isinstance(t, ThreadValue):
            raise ArabiRuntimeError(
                f'العنصر رقم {i + 1} ليس خيطًا بل {typename(t)}', line)
        results.append(t.result(line))
    return results


def _thr_lock(args, line):
    """قفل() — ينشئ قفل حصر لحماية البيانات المشتركة."""
    if args:
        raise ArabiRuntimeError(
            f"'قفل' لا تأخذ معاملات لكنها استلمت {len(args)}", line)
    return LockValue()


def _thr_queue(args, line):
    """طابور() — ينشئ طابورًا آمنًا لتمرير الرسائل بين الخيوط."""
    if args:
        raise ArabiRuntimeError(
            f"'طابور' لا تأخذ معاملات لكنها استلمت {len(args)}", line)
    return QueueValue()


def _thr_cpu_count(args, line):
    """معالجات() — عدد أنوية المعالج المتوفرة."""
    if args:
        raise ArabiRuntimeError(
            f"'معالجات' لا تأخذ معاملات لكنها استلمت {len(args)}", line)
    return os.cpu_count() or 1


def _thr_result(obj, args, line):
    _require_args('نتيجة', args, 0, 0, line)
    return obj.result(line)


def _thr_join(obj, args, line):
    _require_args('انتظر', args, 0, 0, line)
    obj.join(line)
    return None


def _thr_alive(obj, args, line):
    _require_args('حي', args, 0, 0, line)
    return obj.alive()


THREAD_METHODS.update({
    'نتيجة': _thr_result,
    'انتظر': _thr_join,
    'حي': _thr_alive,
})


def _lock_acquire(obj, args, line):
    """احجز([مهلة؟]) — يحجز القفل ويعيد صح، أو خطأ إذا انتهت المهلة."""
    if len(args) > 1:
        raise ArabiRuntimeError(
            f"'احجز' تقبل مهلة واحدة اختيارية لكنها استلمت {len(args)}", line)
    timeout = -1                             # -1 = انتظر بلا مهلة
    if args:
        if isinstance(args[0], bool) or not isinstance(args[0], (int, float)):
            raise ArabiRuntimeError(
                'مهلة القفل يجب أن تكون عددًا (بالثواني)', line)
        timeout = args[0]
    try:
        return obj.lock.acquire(timeout=timeout)
    except ValueError as exc:
        raise ArabiRuntimeError(f'قيمة مهلة غير صالحة: {exc}', line)


def _lock_release(obj, args, line):
    _require_args('افرح', args, 0, 0, line)
    try:
        obj.lock.release()
    except RuntimeError:
        raise ArabiRuntimeError(
            'لا يمكن فتح قفل غير محجوز — احجزه أولًا', line)
    return None


def _lock_try(obj, args, line):
    _require_args('محاولة', args, 0, 0, line)
    return obj.lock.acquire(blocking=False)


LOCK_METHODS.update({
    'احجز': _lock_acquire,
    'افرح': _lock_release,
    'محاولة': _lock_try,
})


def _queue_put(obj, args, line):
    _require_args('أرسل', args, 1, 1, line)
    obj.q.put(args[0])
    return None


def _queue_get(obj, args, line):
    _require_args('استلم', args, 0, 0, line)
    return obj.q.get()


def _queue_get_nowait(obj, args, line):
    _require_args('استلم_الآن', args, 0, 0, line)
    try:
        return obj.q.get_nowait()
    except queue.Empty:
        raise ArabiRuntimeError('الطابور فارغ — لا رسائل لاستلامها', line)


def _queue_size(obj, args, line):
    _require_args('الحجم', args, 0, 0, line)
    return obj.q.qsize()


def _queue_empty(obj, args, line):
    _require_args('فارغ', args, 0, 0, line)
    return obj.q.empty()


QUEUE_METHODS.update({
    'أرسل': _queue_put,
    'استلم': _queue_get,
    'استلم_الآن': _queue_get_nowait,
    'الحجم': _queue_size,
    'فارغ': _queue_empty,
})


# ================== وحدة تواريخ (الإصدار 1.9) ==================

_DAY_NAMES = ('الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس',
              'الجمعة', 'السبت', 'الأحد')

_DATE_UNIT_KEYS = ('أيام', 'ساعات', 'دقائق', 'ثواني')


def _date_arg(value, name, line):
    if not isinstance(value, DateValue):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج تاريخًا لكنها استلمت {typename(value)}", line)
    return value.dt


def _dt_now(args, line):
    """الآن() — التاريخ والوقت الحاليان."""
    if args:
        raise ArabiRuntimeError("'الآن' لا تقبل معاملات", line)
    return DateValue(datetime.datetime.now())


def _dt_create(args, line):
    """أنشئ(سنة، شهر، يوم، ساعة=٠، دقيقة=٠، ثانية=٠) — تاريخ من أرقام."""
    if not 3 <= len(args) <= 6:
        raise ArabiRuntimeError(
            f"'أنشئ' تقبل من ٣ إلى ٦ معاملات لكنها استلمت {len(args)}", line)
    parts = []
    for i, v in enumerate(args):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ArabiRuntimeError(
                f"معامل 'أنشئ' رقم {i + 1} يجب أن يكون عددًا صحيحًا لكنه "
                f'{typename(v)}', line)
        parts.append(v)
    try:
        return DateValue(datetime.datetime(*parts))
    except ValueError as exc:
        raise ArabiRuntimeError(f'تاريخ غير صالح: {exc}', line)


def _dt_parse(args, line):
    """حلل(نص، صيغة) — يقرأ التاريخ من نص حسب صيغة مثل %Y-%m-%d."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'حلل' تحتاج معاملين (نص وصيغة) لكنها استلمت {len(args)}", line)
    text, fmt = args
    if not isinstance(text, str) or not isinstance(fmt, str):
        raise ArabiRuntimeError(
            f"'حلل' تحتاج نصين (التاريخ والصيغة) لكنها استلمت "
            f'{typename(text)} و {typename(fmt)}', line)
    try:
        return DateValue(datetime.datetime.strptime(text, fmt))
    except ValueError:
        raise ArabiRuntimeError(
            f"لا يمكن قراءة التاريخ '{text}' بصيغة '{fmt}'", line)


def _dt_diff(args, line):
    """فرق(أ، ب) — الفرق بالأيام (سالب إن كان ب بعدها)."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'فرق' تحتاج تاريخين لكنها استلمت {len(args)}", line)
    a = _date_arg(args[0], 'فرق', line)
    b = _date_arg(args[1], 'فرق', line)
    days = (a - b).total_seconds() / 86400
    return int(days) if days == int(days) else days


def _dt_add(args, line):
    """أضف(تاريخ، أيام=٠، ساعات=٠، دقائق=٠، ثواني=٠) — تاريخ جديد بعد الإضافة."""
    if not 1 <= len(args) <= 5:
        raise ArabiRuntimeError(
            f"'أضف' تقبل من ١ إلى ٥ معاملات لكنها استلمت {len(args)}", line)
    base = _date_arg(args[0], 'أضف', line)
    units = dict(zip(_DATE_UNIT_KEYS, (0, 0, 0, 0)))
    for i, v in enumerate(args[1:]):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ArabiRuntimeError(
                f"معامل '{_DATE_UNIT_KEYS[i]}' يجب أن يكون عددًا لكنه "
                f'{typename(v)}', line)
        units[_DATE_UNIT_KEYS[i]] = v
    delta = datetime.timedelta(
        days=units['أيام'], hours=units['ساعات'],
        minutes=units['دقائق'], seconds=units['ثواني'])
    return DateValue(base + delta)


def _dt_weekday(args, line):
    """يوم_الأسبوع(تاريخ) — اسم اليوم بالعربية."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'يوم_الأسبوع' تحتاج تاريخًا واحدًا لكنها استلمت {len(args)}", line)
    dt = _date_arg(args[0], 'يوم_الأسبوع', line)
    # بايثون: الاثنين = ٠ — قائمتنا بنفس الترتيب
    return _DAY_NAMES[dt.weekday()]


def _date_prop(prop):
    def method(obj, args, line):
        if args:
            raise ArabiRuntimeError(
                f"'{prop}' خاصية تُقرأ بلا معاملات", line)
        return getattr(obj.dt, prop)
    return method


def _date_weekday_method(obj, args, line):
    if args:
        raise ArabiRuntimeError("'يوم_الأسبوع' تُقرأ بلا معاملات", line)
    return _DAY_NAMES[obj.dt.weekday()]


def _date_format(obj, args, line):
    """نسق(صيغة) — ينسق التاريخ حسب صيغة مثل %Y/%m/%d."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'نسق' تحتاج صيغة نصية واحدة لكنها استلمت {len(args)}", line)
    fmt = args[0]
    if not isinstance(fmt, str):
        raise ArabiRuntimeError(
            f"الصيغة يجب أن تكون نصًا لكنها {typename(fmt)}", line)
    try:
        return obj.dt.strftime(fmt)
    except (ValueError, AttributeError) as exc:
        raise ArabiRuntimeError(f'صيغة غير صالحة: {exc}', line)


DATE_METHODS = {
    'السنة': _date_prop('year'),
    'الشهر': _date_prop('month'),
    'اليوم': _date_prop('day'),
    'الساعة': _date_prop('hour'),
    'الدقيقة': _date_prop('minute'),
    'الثانية': _date_prop('second'),
    'يوم_الأسبوع': _date_weekday_method,
    'نسق': _date_format,
}


# ================== وحدة اختبارات (إطار الاختبارات) ==================

class _TestState:
    """حالة إطار الاختبارات — نسخة مستقلة لكل مفسر (لكل عملية تشغيل)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.suite = 'الاختبارات'
        self.started = False
        self.passed = 0
        self.failed = 0
        self.failures = []

    @property
    def total(self):
        return self.passed + self.failed

    def record(self, ok, name, detail, line):
        """يسجل نتيجة اختبار ويطبعها فورًا (مع بداية تلقائية عند الحاجة)."""
        self.started = True
        if not isinstance(name, str) or not name:
            name = f'الاختبار رقم {self.total + 1}'
        if ok:
            self.passed += 1
            print(f'✓ {name}')
        else:
            self.failed += 1
            self.failures.append((name, detail, line))
            print(f'✗ {name} — {detail}' if detail else f'✗ {name}')
        return None


def _tests_start(state):
    def fn(args, line):
        if len(args) > 1:
            raise ArabiRuntimeError(
                f"'ابدأ' تقبل معاملًا واحدًا على الأكثر لكنها استلمت {len(args)}", line)
        name = 'الاختبارات'
        if args:
            if not isinstance(args[0], str):
                raise ArabiRuntimeError(
                    f"اسم المجموعة يجب أن يكون نصًا لكنه {typename(args[0])}", line)
            name = args[0]
        state.reset()
        state.started = True
        state.suite = name
        print(f'== {name} ==')
        return None
    return fn


def _tests_check(state, mode):
    """مصنع دوال الفحص: يساوي / يختلف / يصح / يخطئ."""
    required = 2 if mode in ('eq', 'ne') else 1
    label = {'eq': 'يساوي', 'ne': 'يختلف',
             'truthy': 'يصح', 'falsy': 'يخطئ'}[mode]

    def fn(args, line):
        if not required <= len(args) <= required + 1:
            raise ArabiRuntimeError(
                f"'{label}' تقبل {required} أو {required + 1} معاملات "
                f"لكنها استلمت {len(args)}", line)
        name = args[-1] if len(args) == required + 1 else None
        if name is not None and not isinstance(name, str):
            raise ArabiRuntimeError(
                f"اسم الاختبار يجب أن يكون نصًا لكنه {typename(name)}", line)
        values = args[:required]

        if mode == 'eq':
            ok = values[0] == values[1]
            detail = '' if ok else (
                f"المتوقع: {display(values[1])}، الفعلي: {display(values[0])}")
        elif mode == 'ne':
            ok = values[0] != values[1]
            detail = '' if ok else (
                f"القيمتان متساويتان: {display(values[0])}")
        elif mode == 'truthy':
            ok = bool(values[0])
            detail = '' if ok else f"القيمة {display(values[0])} ليست قيمة صحية"
        else:
            ok = not bool(values[0])
            detail = '' if ok else f"القيمة {display(values[0])} ليست خاطئة"
        state.record(ok, name, detail, line)
        return None
    return fn


def _tests_raises(state):
    """يرفع(دالة، اسم؟) — يستدعي الدالة ويؤكد أنها ترفع خطأ."""

    def fn(interp, args, line):
        if len(args) not in (1, 2):
            raise ArabiRuntimeError(
                f"'يرفع' تقبل معاملًا أو معاملين لكنها استلمت {len(args)}", line)
        name = args[1] if len(args) == 2 else None
        if name is not None and not isinstance(name, str):
            raise ArabiRuntimeError(
                f"اسم الاختبار يجب أن يكون نصًا لكنه {typename(name)}", line)
        func = args[0]
        if not isinstance(func, (ArabiFunc, BuiltinFunc, BoundMethod)):
            raise ArabiRuntimeError(
                f"'يرفع' تحتاج دالة لكنها استلمت {typename(func)}", line)
        try:
            interp._call_value(func, [], {}, line)
        except ArabiError as exc:
            state.record(True, name, '', line)
            return None
        state.record(False, name, 'لم ترفع الدالة أي خطأ', line)
        return None
    return fn


def _tests_summary(state):
    def fn(args, line):
        if args:
            raise ArabiRuntimeError("'ملخص' لا تقبل معاملات", line)
        if not state.started:
            state.reset()
        print(f"== الملخص: {state.passed} ناجحة، {state.failed} فاشلة "
              f"من {state.total} اختبارًا ==")
        return {
            'المجموعة': state.suite,
            'ناجح': state.passed,
            'فاشل': state.failed,
            'الكل': state.total,
        }
    return fn


# ================== وحدة خادم (خوادم الويب) ==================

# ترويسات الاستجابة الشائعة بأسمائها العربية ← الأسماء القياسية
_HEADER_AR = {
    'نوع_المحتوى': 'Content-Type',
    'الموقع': 'Location',
    'تخزين_مؤقت': 'Cache-Control',
    'كوكيز': 'Set-Cookie',
}


class _ServerState:
    """حالة خادم الويب — نسخة مستقلة لكل مفسر."""

    def __init__(self):
        self.server = None
        self.thread = None
        self.port = None
        self.interp = None
        self.handler = None

    # ---------- الدوال المعرّضة للغة ----------

    def start(self, interp, args, line):
        """ابدأ(منفذ، معالج) — يشغل الخادم ويعيد المنفذ الفعلي."""
        if self.server is not None:
            raise ArabiRuntimeError(
                "الخادم يعمل بالفعل — استدعِ 'خادم.قف' أولًا", line)
        if len(args) != 2:
            raise ArabiRuntimeError(
                f"'ابدأ' تحتاج معاملين (المنفذ ودالة المعالجة) "
                f"لكنها استلمت {len(args)}", line)
        port = args[0]
        if isinstance(port, bool) or not isinstance(port, int):
            raise ArabiRuntimeError(
                f"المنفذ يجب أن يكون عددًا صحيحًا لكنه {typename(port)}", line)
        if not 0 <= port <= 65535:
            raise ArabiRuntimeError(
                f'المنفذ يجب أن يكون بين ٠ و ٦٥٥٣٥ لكنه {port}', line)
        handler = args[1]
        if not isinstance(handler, (ArabiFunc, BuiltinFunc, BoundMethod)):
            raise ArabiRuntimeError(
                f"المعالج يجب أن يكون دالة لكنه {typename(handler)}", line)

        self.interp = interp
        self.handler = handler
        # صنف معالج فريد لكل خادم حتى لا تتعارض الخوادم المتعددة
        handler_cls = type(
            f'_ArabiHandler_{id(self):x}', (_ArabiHTTPRequestHandler,),
            {'state': self})
        try:
            self.server = http.server.ThreadingHTTPServer(
                ('127.0.0.1', port), handler_cls)
        except OSError as exc:
            self.server = None
            self.interp = None
            self.handler = None
            raise ArabiRuntimeError(f"تعذر فتح المنفذ {port}: {exc}", line)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.port

    def stop(self, args, line):
        """قف() — يوقف الخادم ويحرر المنفذ."""
        if args:
            raise ArabiRuntimeError("'قف' لا تقبل معاملات", line)
        if self.server is None:
            raise ArabiRuntimeError('لا يوجد خادم يعمل حاليًا', line)
        self.server.shutdown()
        self.server.server_close()
        self.server = None
        self.thread = None
        self.port = None
        self.interp = None
        self.handler = None
        return None

    def get_port(self, args, line):
        """المنفذ() — يعيد المنفذ الفعلي للخادم العامل أو ولا شيء."""
        if args:
            raise ArabiRuntimeError("'المنفذ' لا تقبل معاملات", line)
        return self.port

    def wait(self, args, line):
        """انتظر() — يبقى البرنامج معلقًا خدمةً للطلبات حتى مقاطعة (Ctrl+C)."""
        if args:
            raise ArabiRuntimeError("'انتظر' لا تقبل معاملات", line)
        if self.server is None:
            raise ArabiRuntimeError(
                "لا يوجد خادم يعمل — استدعِ 'خادم.ابدأ' أولًا", line)
        try:
            while self.server is not None:
                time.sleep(0.2)
        except KeyboardInterrupt:
            print('\n(أُوقف الخادم)')
        finally:
            if self.server is not None:
                self.server.shutdown()
                self.server.server_close()
                self.server = None
                self.thread = None
                self.port = None
                self.interp = None
                self.handler = None
        return None


class _ArabiHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """معالج HTTP يستدعي دالة معالجة مكتوبة بلغة عربي."""

    state = None       # _ServerState — يُضبط في صنف فرعي لكل خادم
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *log_args):
        pass                                        # كتم سجلات بايثون

    def _build_request(self):
        """يبني قاموس الطلب بلغة عربي من طلب HTTP الخام."""
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        params = {k: (v[0] if len(v) == 1 else v) for k, v in query.items()}
        length = int(self.headers.get('Content-Length') or 0)
        body = ''
        if length > 0:
            body = self.rfile.read(length).decode('utf-8', errors='replace')
        headers = {}
        for k, v in self.headers.items():
            key = k.lower()
            if key == 'نوع_المحتوى':
                key = 'نوع_المحتوى'
            elif key == 'content-type':
                key = 'نوع_المحتوى'
            headers[key] = v
        return {
            'الطريقة': self.command,
            'المسار': urllib.parse.unquote(parsed.path),
            'المعاملات': params,
            'الترويسات': headers,
            'النص': body,
        }

    def _respond(self, status, text, extra_headers):
        """يرسل الاستجابة (يدعم الاستمرار مع HTTP/1.1 بطول المحتوى)."""
        self.send_response(status)
        content_type = 'text/html; charset=utf-8'
        for k, v in extra_headers.items():
            real = _HEADER_AR.get(k, k)
            if real.lower() == 'content-type':
                content_type = v
            self.send_header(real, str(v))
        payload = text.encode('utf-8')
        if self.command == 'HEAD':
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            return
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _run(self):
        st = self.state
        request = self._build_request()
        try:
            result = st.interp._call_value(st.handler, [request], {}, 0)
            if isinstance(result, str):
                self._respond(200, result, {})
                return
            if isinstance(result, dict):
                status = result.get('الحالة', 200)
                if isinstance(status, bool) or not isinstance(status, int) \
                        or not 100 <= status <= 599:
                    raise ArabiRuntimeError(
                        f"حالة الاستجابة يجب أن تكون عددًا صحيحًا بين ١٠٠ و ٥٩٩ "
                        f"لكنها {display(status)}")
                text = result.get('النص', '')
                text = text if isinstance(text, str) else display(text)
                raw_headers = result.get('الترويسات', {}) or {}
                if not isinstance(raw_headers, dict):
                    raise ArabiRuntimeError(
                        f"الترويسات يجب أن تكون قاموسًا لكنها "
                        f"{typename(raw_headers)}")
                self._respond(status, text, raw_headers)
                return
            # أي قيمة أخرى تعاد كنص صفحة
            self._respond(200, display(result), {})
        except ArabiError as exc:
            self._respond(500, f'<pre>{exc.message}</pre>',
                          {'نوع_المحتوى': 'text/html; charset=utf-8'})
        except Exception as exc:                 # حماية خيط الخادم من الانهيار
            self._respond(500, f'<pre>خطأ داخلي: {exc}</pre>',
                          {'نوع_المحتوى': 'text/html; charset=utf-8'})

    # كل الطرق الشائعة تمر بنفس المسار
    def do_GET(self):
        self._run()

    def do_POST(self):
        self._run()

    def do_PUT(self):
        self._run()

    def do_DELETE(self):
        self._run()

    def do_PATCH(self):
        self._run()

    def do_HEAD(self):
        self._run()


# ================== وحدة إحصاء (الإصدار 1.10) ==================

def _st_numbers(args, name, line):
    """يتحقق من معامل واحد قائمة أعداد غير فارغة ويعيدها."""
    if len(args) != 1:
        raise ArabiRuntimeError(f"'{name}' تتوقع معاملًا واحدًا", line)
    values = args[0]
    if not isinstance(values, list):
        raise ArabiRuntimeError(
            f"'{name}' تحتاج قائمة أعداد لكنها استلمت {typename(values)}", line)
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ArabiRuntimeError(
                f"'{name}' تحتاج قائمة أعداد لكنها تحوي {typename(v)}", line)
    if not values:
        raise ArabiRuntimeError(f"'{name}' لا تقبل قائمة فارغة", line)
    return values


def _st_mean(args, line):
    """معدل(أعداد) — المتوسط الحسابي."""
    values = _st_numbers(args, 'معدل', line)
    return sum(values) / len(values)


def _st_median(args, line):
    """وسيط(أعداد) — القيمة الوسطى بعد الترتيب."""
    values = sorted(_st_numbers(args, 'وسيط', line))
    n = len(values)
    mid = n // 2
    if n % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _st_mode(args, line):
    """منوال(أعداد) — القيمة الأكثر تكرارًا (الأولى ظهورًا عند التعادل)."""
    values = _st_numbers(args, 'منوال', line)
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = None
    best_count = 0
    for v in values:                    # الأولى ظهورًا عند التعادل
        if counts[v] > best_count:
            best = v
            best_count = counts[v]
    return best


def _st_variance(args, line):
    """تباين(أعداد) — التباين المجتمعي (القسمة على العدد)."""
    values = _st_numbers(args, 'تباين', line)
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _st_stddev(args, line):
    """انحراف(أعداد) — الجذر التربيعي للتباين."""
    return math.sqrt(_st_variance(args, line))


def _st_range(args, line):
    """مدى(أعداد) — الفرق بين أكبر قيمة وأصغرها."""
    values = _st_numbers(args, 'مدى', line)
    return max(values) - min(values)
