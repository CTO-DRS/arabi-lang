# -*- coding: utf-8 -*-
"""الحوسبة الموزعة (الإصدار 1.18) — توزيع المهمة الواحدة على عدة أجهزة
عبر الشبكة الحقيقية.

الفلسفة:
- وحدة 'موزعة' تُكمل سلسلة التوازي: خيوط (1.8) ثم غير المتزامن (1.15)
  ثم تجمع الخيوط (1.16) ثم عمليات منفصلة (1.17) — وها هي الأعمال تعبر
  حدود الجهاز الواحد: 'موزع' يستقبل اتصالات العمال، و'عامل' يخدم المهام
  على أي جهاز في الشبكة، و'قدّم' تعيد مهمة تنتظرها بـ'انتظر' أو
  'انتظر_الجميع' أو 'سباق' — الواجهة نفسها التي تعرفها.
- الحزمة العابرة للشبكة هي نفسها عابرة العمليات (ترميز القيم في
  processes.py): الدوال العربية بجسمها وإغلاقها، والأصناف والكائنات
  والتعدادات وأخطاء المستخدم بهويتها — والعامل يبني مفسّرًا كاملًا
  بكل الوحدات الجاهزة لكل عمل، فتجد الدالة كل ما تعتمد عليه.
- النقل عبر TCP بإطارات موسومة بالطول (٤ بايت + بيانات منقطّة)، وكل
  حالة الموزع محروسة بقفل واحد: طابور مهام مرتّب، وعمالة معطلة
  تُسحب منها الحزم فورًا، وانقطاع عامل يعيد أعماله الطائرة إلى الطابور
  فتخدمها عمالة أخرى — لا تضيع مهمة إلا إذا أغلق الموزع نفسه.
- الأمان (1.19): مصادقة عمالة اختيارية بمفتاح سري مشترك — مرر
  المفتاح معاملًا ثالثًا لـ 'موزع' و 'عامل' معًا فيصبح لا عامل يُسجّل
  إلا بتوقيع HMAC-SHA256 على تحدٍّ عشوائي (nonce) يرسله الموزع لحظة
  الاتصال، والتحقق بمقارنة زمن ثابت فلا يكشف التوقيت شيئًا — والموزع
  بلا مفتاح يعمل كالسابق (توافق كامل مع 1.18) مع رسالة ترحيب
  بلا_مفتاح تخبر العامل المفتاحي فورًا أن التكوين غير متوافق.
- التشفير الكامل (1.21): في الموزع المفتاحي لم تعد المصادقة تحمي
  التسجيل وحده — فبعد نجاحها تُشتق مفاتيح جلسة من المفتاح المشترك
  وتحدي المصافحة (HMAC بسياقين منفصلين: تشفير وتوثيق) ويُغلَّف المقبس
  بقناة مشفرة: كل إطار أعمال أو نتائج أو وداع يشفّر بتيار مفاتيح
  HMAC-SHA256 في نمط العدّاد ويُوقَّع Encrypt-then-MAC قبل الإرسال
  ويتحقق المستقبل من البصمة بمقارنة زمن ثابت قبل فك أي بايت — فلا
  يقرأ تنصّت على السلك كود مهامك ولا نتائجها. الإطارات المشفرة تبدأ
  بترويسة سحرية تميزها فميّز العامل رفض المصافحة (نص صريح) من
  قناة مفعلة، والمسار الحر يبقى pickle خامًا كما في 1.18 تمامًا.
  الوضع المفتاحي يتطلب الموزع والعامل كليهما نسخة 1.21 على الأقل —
  عامل قديم عند موزع 1.21 مفتاحي يُسقط اتصاله فورًا (فشل مغلق لا
  صمت أمني)، والمسار الحر متوافق بالاتجاهين كما كان.

هذا الملف يحمّل أسماء القيم من runtime فقط — وruntime لا يستورد
هذا الملف إلا داخل دالة التثبيت (بعد اكتمال تعريفه) تفاديًا للدورانية.
"""

import os
import pickle
import secrets as _secrets
import socket
import struct
import threading
import time
from collections import deque

from .crypto import (sign_challenge, verify_challenge, _channel_keys,
                     encrypt_payload, decrypt_payload, _CIPHER_MAGIC,
                     _CIPHER_NONCE_BYTES, _TAG_BYTES)
from .errors import ArabiError, ArabiRuntimeError
from .processes import (
    _run_job, _encode_error, _validate_callable,
    encode_value, decode_value, _make_enc_ctx, _encode_root,
)

DEFAULT_PORT = 7700        # المنفذ الافتراضي للموزع والعامل
DISPATCH_TIMEOUT = 120     # مهلة انتظار نتيجة المهمة الموزعة (ثوانٍ)
SHUTDOWN_GRACE = 30        # مهلة تصفية المهام عند إنهاء الموزع (ثوانٍ)
WORKER_TIMEOUT = 30        # دورة استطلاع العامل (يتحقق بعدها من الإيقاف)
CONNECT_TIMEOUT = 10       # مهلة الاتصال الأولي والعمالة المفتاحية
NONCE_BYTES = 32           # طول تحدي المصادقة العشوائي (بايتات)
POLL_INTERVAL = 0.01       # نبضة استطلاع حلقات الانتظار (ثوانٍ)
MAX_FRAME = 256 * 1024 * 1024   # الحد الأعلى لحجم الإطار الواحد (256 م.ب)

_HEAD = struct.Struct('>I')    # رأس الإطار: طول بياناته بأربعة بايتات
_CHANNEL_OVERHEAD = (len(_CIPHER_MAGIC) + _CIPHER_NONCE_BYTES
                     + _TAG_BYTES)   # زيادة الإطار المشفر على الأصل


# ================== الإطارات الشبكية ==================
#
# كل رسالة قائمة منقطّة تسبقها ٤ بايتات بطولها — فالقارئ يعرف متى
# تكتمل الرسالة مهما تجاورت الحزم، والقيمة القصوى تحرس الحجم الوهمي.
# الإطار المشفر (1.21) يحمل البايتات المشفرة الموثقة نفسها داخل طول
# الـ ٤ بايتات — فالطول الشبكي يشمل ترويسة القناة وراوندها وبصمتها.

def send_raw_frame(sock, blob):
    """يرسل بايتات خامًا في إطار موسوم بالطول — ٤ بايتات رأسًا ثمها."""
    if len(blob) > MAX_FRAME:
        raise ArabiRuntimeError(
            f'حجم الرسالة الموزعة ({len(blob)} بايتًا) يتجاوز الحد '
            f'الأعلى المسموح ({MAX_FRAME} بايتًا)')
    sock.sendall(_HEAD.pack(len(blob)) + blob)


def send_frame(sock, obj):
    """يرسل رسالة منقطّة في إطار موسوم بالطول — مسار حر (بلا تشفير)."""
    send_raw_frame(sock, pickle.dumps(obj))


def _recv_exact(sock, count):
    """يقرأ عددًا محددًا من البايتات مهما تجاورت الحزم الواصلة."""
    chunks = []
    left = count
    while left > 0:
        chunk = sock.recv(min(left, 65536))
        if not chunk:
            raise ConnectionError('انقطع الاتصال قبل اكتمال الرسالة')
        chunks.append(chunk)
        left -= len(chunk)
    return b''.join(chunks)


def recv_raw_frame(sock, extra=0):
    """يقرأ إطارًا كاملًا ويعيد بايتاته الخام — دون فك أي ترميز.

    extra سماح الحجم الإضافي للإطارات المشفرة (ترويسة القناة وراوند
    وبصمة فوق الأصل) — فالحد الأعلى يحمي الأصل لا يرفض المشفر.
    """
    (size,) = _HEAD.unpack(_recv_exact(sock, _HEAD.size))
    if size > MAX_FRAME + extra:
        raise ArabiRuntimeError(
            f'حجم الإطار الواصل ({size} بايتًا) يتجاوز الحد الأعلى '
            f'المسموح ({MAX_FRAME + extra} بايتًا) — اتصال غير صالح')
    return _recv_exact(sock, size)


def recv_frame(sock):
    """يقرأ إطارًا كاملًا ويعيد رسالته المنقطّة — مسار حر (بلا تشفير)."""
    return pickle.loads(recv_raw_frame(sock))


# ================== القناة المشفرة (1.21) ==================

class SecureChannel:
    """مقبس مغلَّف بقناة مشفرة موثقة — يظهر للطرفين إرسالًا واستقبالًا.

    كل رسالة: pickle ثم تشفير بتيار HMAC-SHA256 العدّادي (راوند عشوائي
    لكل رسالة) ثم توقيع Encrypt-then-MAC — والمستقبل يتحقق من البصمة
    بمقارنة زمن ثابت قبل فك أي بايت فلا تعديل أو مفتاح خاطئ يمر صامتًا.
    مفاتيح الجلسة مشتقة من المفتاح المشترك وتحدي المصافحة فكل اتصال
    له تيار مستقل — وإعادة إرسال إطار قديم على اتصال جديد تُرفض بصمة.
    """

    __slots__ = ('sock', '_enc', '_mac')

    def __init__(self, sock, enc_key, mac_key):
        self.sock = sock
        self._enc = enc_key
        self._mac = mac_key

    @classmethod
    def from_master(cls, sock, master, salt):
        """يشتق مفاتيح الجلسة من السر المشترك وتحدي الاتصال ويغلف."""
        enc, mac = _channel_keys(master, salt)
        return cls(sock, enc, mac)

    def send(self, obj):
        """يشفر الرسالة ويوثقها ثم يرسلها في إطار موسوم بالطول."""
        send_raw_frame(self.sock,
                       encrypt_payload(pickle.dumps(obj),
                                       self._enc, self._mac))

    def recv(self):
        """يقرأ إطارًا ويتحقق من بصمته ثم يفكه ويعيد رسالته."""
        blob = recv_raw_frame(self.sock, extra=_CHANNEL_OVERHEAD)
        return pickle.loads(decrypt_payload(blob, self._enc, self._mac))


# ================== العامل ==================

def run_worker(host, port, stop_event=None, key=None):
    """يربط عاملاً بالموزع ويخدمه حتى إغلاق الموزع — يحجب الاستدعاء.

    كل عمل يُنفذ في مفسّر نظيف كامل (بنفس دلالات عمليات.شغّل)،
    والنتيجة تعود مرمزة بالهوية: نتيجة ناجحة أو خطأ عربي أو عطل داخلي.
    يعيد 'ولا شيء' عند إغلاق الموزع بنظافة (رسالة وداع) — ويرفع خطأً
    عربيًا إذا فشل الاتصال أو انقطع فجأة أو رفضه الموزع مفتاحًا.

    المفتاح (1.19): إذا مرر فينتظر العامل تحدي الموزع ويوقعه
    HMAC-SHA256 بالمفتاح المشترك — والموزع بلا مفتاح (أو بمفتاح
    آخر) يرسل رفضًا واضحًا فلا جدال صامت في أي اتجاه.
    التشفير (1.21): بعد قبول المصافحة تشتق مفاتيح الجلسة من المفتاح
    وتحديها فيغلف الاتصال بقناة مشفرة موثقة — أول إطار بعد الترحيب
    هو الدليل: ترويسته السحرية تفعّل القناة، وغير المشفر يكون رفضًا
    نصيًا يعرض كما هو. عامل قديم (<1.21) عند موزع 1.21 مفتاحي لا
    يفهم الإطارات المشفرة فيُسقط — فشل مغلق حصين لا صمت أمني.
    """
    _check_key(key)
    try:
        sock = socket.create_connection((host, port),
                                        timeout=CONNECT_TIMEOUT)
    except OSError as exc:
        raise ArabiRuntimeError(
            f'تعذر الاتصال بالموزع {host}:{port} — {exc}')
    sock.settimeout(CONNECT_TIMEOUT)      # مهلة المصافحة ثم استطلاع طويل
    try:
        challenge = None                  # تحدي المصافحة لمشتقات القناة
        if key is not None:
            # العامل المفتاحي ينتظر تحدي الموزع أولًا ثم يوقع
            try:
                msg = recv_frame(sock)
            except socket.timeout:
                raise ArabiRuntimeError(
                    'انتهت مهلة مصافحة المفتاح — الموزع لا يستخدم '
                    'مفتاحًا أو لا يفهم البروتوكول')
            except (ConnectionError, OSError):
                raise ArabiRuntimeError(
                    'انقطع الاتصال بالموزع أثناء المصافحة')
            if isinstance(msg, tuple) and msg and msg[0] == 'بلا_مفتاح':
                raise ArabiRuntimeError(
                    'الموزع لا يستخدم مفتاحًا — أعد تشغيله بالمفتاح '
                    'نفسه أو اربط العامل بلا مفتاح')
            if not (isinstance(msg, tuple) and len(msg) == 2
                    and msg[0] == 'تحدٍ'):
                raise ArabiRuntimeError(
                    'أول رسالة من الموزع ليست تحدي مصافحة — '
                    'البروتوكولان غير متوافقين')
            challenge = msg[1]
            signature = sign_challenge(key, challenge)
            send_frame(sock, ('مرحبا', os.getpid(),
                              socket.gethostname(), signature))
        else:
            # التسجيل: الوصف (معرف العملية واسم الجهاز) للتوثيق والتشخيص
            send_frame(sock, ('مرحبا', os.getpid(), socket.gethostname()))
        sock.settimeout(WORKER_TIMEOUT)
        chan = None                       # القناة المشفرة بعد التسجيل
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                blob = recv_raw_frame(
                    sock, extra=_CHANNEL_OVERHEAD if chan is not None
                    else 0)
            except socket.timeout:
                continue          # نبضة استطلاع — تحقق من الإيقاف ثم عُد
            except (ConnectionError, OSError):
                raise ArabiRuntimeError(
                    'انقطع الاتصال بالموزع فجأة دون رسالة وداع')
            except ArabiError:
                raise
            if chan is None:
                if blob[:len(_CIPHER_MAGIC)] == _CIPHER_MAGIC:
                    # أول إطار مشفر — الموزع قبلك وفعّل قناته
                    if key is None or challenge is None:
                        raise ArabiRuntimeError(
                            'وصل إطار مشفر لعامل بلا مفتاح — بروتوكول '
                            'غير متوافق')
                    chan = SecureChannel.from_master(
                        sock, key, challenge)
                    msg = pickle.loads(
                        decrypt_payload(blob, chan._enc, chan._mac))
                else:
                    msg = pickle.loads(blob)   # رفض مصافحة نصي كما كان
            else:
                msg = pickle.loads(
                    decrypt_payload(blob, chan._enc, chan._mac))
            if not (isinstance(msg, tuple) and msg):
                continue          # رسالة شاذة — تجاهل صامت (توافق مستقبلي)
            kind = msg[0]
            if kind == 'وداع':
                break             # الموزع أغلق بنظافة
            if kind == 'رفض':
                reason = msg[1] if len(msg) > 1 else 'غير معلوم'
                raise ArabiRuntimeError(f'رفض الموزع ربط العامل — {reason}')
            if kind == 'تحدٍ':
                raise ArabiRuntimeError(
                    'الموزع يتطلب مفتاحًا — مرر المفتاح نفسه معاملًا '
                    'ثالثًا لعامل()')
            if kind == 'عمل':
                job_id, blob = msg[1], msg[2]
                try:
                    data = pickle.loads(blob)
                    rkind, rblob = _run_job(data)
                except ArabiError as exc:
                    rkind, rblob = 'خطأ', pickle.dumps(_encode_error(exc))
                except Exception as exc:      # شبكة أمان — لا صمت أبدًا
                    rkind, rblob = 'عطل', pickle.dumps(
                        f'عطل داخل العامل: {exc}')
                try:
                    result = ('نتيجة', job_id, rkind, rblob)
                    if chan is not None:
                        chan.send(result)
                    else:
                        send_frame(sock, result)
                except OSError:
                    raise ArabiRuntimeError(
                        'تعذر إرسال نتيجة المهمة إلى الموزع — انقطع '
                        'الاتصال')
            # أنواع أخرى من الرسائل: تجاهل صامت (توافق مستقبلي)
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def run_worker_cli(target, key=None):
    """نقطة دخول العامل من سطر الأوامر: --عامل المضيف:منفذ — تُطبع
    حالة الاتصال بالعربية وتُغلق بهدوء عند وداع الموزع."""
    host, port = parse_target(target)
    try:
        run_worker(host, port, key=key)
    except ArabiError as exc:
        print(f'خطأ: {exc.message}', flush=True)
        return 1
    return 0


def _check_key(key):
    """يتحقق من صحة المفتاح السري المشترك — نص غير فارغ."""
    if key is None:
        return None
    if not isinstance(key, str):
        raise ArabiRuntimeError(
            f'المفتاح السري للموزع والعامل نصًا لكنه استلم '
            f'{type(key).__name__}')
    if not key:
        raise ArabiRuntimeError(
            'المفتاح السري لا يكون فارغًا — مرر نصًا يحمل السر أو '
            'اترك المعامل حاضرًا تمامًا للربط بلا مصادقة')
    return key


def parse_target(target):
    """يحلل 'المضيف:منفذ' إلى (مضيف، منفذ) — المنفذ اختياري."""
    if isinstance(target, str) and ':' in target:
        host, _, raw = target.rpartition(':')
        try:
            port = int(raw)
        except ValueError:
            raise ArabiRuntimeError(
                f"المنفذ '{raw}' ليس عددًا صحيحًا صالحًا")
        if not 0 <= port <= 65535:
            raise ArabiRuntimeError(
                f'المنفذ {port} خارج المدى المسموح (٠ إلى ٦٥٥٣٥)')
        return host, port
    return str(target), DEFAULT_PORT


# ================== خادم الموزع ==================

class _WorkerConn:
    """اتصال عامل مسجل — بمقبسه وعنوانه ووصفه وقناته وعمله الطائر."""

    __slots__ = ('sock', 'addr', 'info', 'chan', 'inflight')

    def __init__(self, sock, addr, info, chan=None):
        self.sock = sock
        self.addr = addr
        self.info = info
        self.chan = chan            # قناة مشفرة (موزع مفتاحي) أو لا شيء
        self.inflight = None        # (معرف المهمة، حزمتها) أو لا شيء

    def send(self, obj):
        """يرسل رسالة عبر القناة المشفرة أو الحرة بحسب وضع الاتصال."""
        if self.chan is not None:
            self.chan.send(obj)
        else:
            send_frame(self.sock, obj)


class _Server:
    """خادم التوزيع: يستقبل العمالة، يرتب طابورًا للمهام، ويسلم كل
    حزمة لعامل معطل فورًا، ويوجه النتائج الواصلة إلى مهامها.

    كل الحالة محروسة بقفل واحد — والإرسال يقع خارج القفل (بعد
    اقتطاع المهمة لعميلها) فلا يعلن عامل بطيء التوزيع كله.
    """

    def __init__(self, host, port, interp, key=None):
        self._interp = interp
        self._root = interp.globals
        self._key = _check_key(key)
        self._lock = threading.RLock()
        self._stopping = False
        self._closed = False
        self._next_id = 0
        self._total = 0
        self._queue = deque()          # (معرف المهمة، الحزمة) بانتظار عامل
        self._tasks = {}               # معرف المهمة ← قيمتها
        self._workers = {}             # معرف العامل ← اتصاله
        self._idle = deque()           # معرفات العمالة المستعدة (بترتيب)
        self._worker_seq = 0
        try:
            self._server_sock = socket.socket(socket.AF_INET,
                                              socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET,
                                         socket.SO_REUSEADDR, 1)
            self._server_sock.bind((host, port))
            self._server_sock.listen(16)
            self._server_sock.settimeout(0.5)
        except OSError as exc:
            raise ArabiRuntimeError(
                f'تعذر بدء الموزع على {host}:{port} — {exc}')
        self._bound_host, self._bound_port = self._server_sock.getsockname()
        self._accept_thread = threading.Thread(
            target=self._accept_loop, daemon=True, name='موزع-عربي-قبول')
        self._accept_thread.start()

    # ---------- قياس ----------

    def workers(self):
        with self._lock:
            return len(self._workers)

    def port(self):
        return self._bound_port

    def host(self):
        return self._bound_host

    def total(self):
        with self._lock:
            return self._total

    def encrypted(self):
        """هل قناة هذا الموزع مشفرة؟ (الصح إذا بدأ بمفتاح سري)."""
        return self._key is not None

    # ---------- الاستقبال والتسجيل ----------

    def _accept_loop(self):
        """حلقة قبول الاتصالات — كل اتصال يديره قارئ خيطي مستقل."""
        while not self._stopping:
            try:
                sock, addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break                    # أُغلق المقبس — انتهى الخادم
            sock.settimeout(WORKER_TIMEOUT)
            threading.Thread(target=self._reader_loop, args=(sock, addr),
                             daemon=True,
                             name='موزع-عربي-عامل').start()

    def _reader_loop(self, sock, addr):
        """يدير اتصال عامل واحد: مصافحة ثم تسجيل ثم قراءة النتائج.

        الموزع المفتاحي (1.19) يرسل تحديًا عشوائيًا أولًا ولا يسجّل
        إلا عاملًا وقّعه بالمفتاح المشترك — والباقي يرفض برسالة عربية
        واضحة. الموزع الحر يرسل إعلان بلا_مفتاح فيعرف العامل المفتاحي
        فورًا أن التكوين غير متوافق بلا أي انتظار.
        التشفير (1.21): بعد قبول توقيع العامل تُشتق مفاتيح الجلسة من
        المفتاح وتحديه ويغلَّف الاتصال بقناة مشفرة — فمهما قرأ تنصّت
        لاحقًا لن يفهم إطارًا واحدًا من أعمال العمالة أو نتائجها.
        """
        if self._key is not None:
            nonce = _secrets.token_bytes(NONCE_BYTES)
            try:
                send_frame(sock, ('تحدٍ', nonce))
            except OSError:
                self._close_quietly(sock)
                return
        else:
            nonce = None
            try:
                send_frame(sock, ('بلا_مفتاح',))
            except OSError:
                self._close_quietly(sock)
                return
        try:
            msg = recv_frame(sock)
        except Exception:
            self._close_quietly(sock)
            return
        hello_ok = (isinstance(msg, tuple) and msg
                    and msg[0] == 'مرحبا')
        chan = None
        if hello_ok and self._key is not None:
            hello_ok = (len(msg) == 4
                        and verify_challenge(self._key, nonce, msg[3]))
            if not hello_ok:
                try:
                    send_frame(sock, ('رفض',
                                      'المفتاح المرسل غير صحيح — '
                                      'مرر المفتاح نفسه للعامل وللموزع'))
                except OSError:
                    pass
                self._close_quietly(sock)
                return
            # توقيع سليم — القناة تُشتق من المفتاح وتحديه فتفرّد الجلسة
            chan = SecureChannel.from_master(sock, self._key, nonce)
        if not hello_ok:
            self._close_quietly(sock)     # أول رسالة ليست تسجيلًا صالحًا
            return
        with self._lock:
            if self._stopping:
                try:
                    if chan is not None:
                        chan.send(('وداع',))
                    else:
                        send_frame(sock, ('وداع',))
                except OSError:
                    pass
                self._close_quietly(sock)
                return
            self._worker_seq += 1
            wid = self._worker_seq
            self._workers[wid] = _WorkerConn(sock, addr, msg[1:3], chan)
            self._idle.append(wid)
        self._pump()
        while True:
            try:
                if chan is not None:
                    msg = chan.recv()
                else:
                    msg = recv_frame(sock)
            except socket.timeout:
                if self._stopping:
                    break
                continue                  # نبضة استطلاع
            except Exception:
                break                     # انقطاع العامل — تُدار في الإسقاط
            if not (isinstance(msg, tuple) and msg):
                continue
            kind = msg[0]
            if kind == 'نتيجة':
                self._handle_result(wid, msg[1], msg[2], msg[3])
            elif kind == 'وداع':
                break
            # أنواع أخرى: تجاهل صامت (توافق مستقبلي)
        self._drop_worker(wid)

    def _drop_worker(self, wid):
        """يسقط عاملًا منقطعًا ويعيد أعماله الطائرة إلى رأس الطابور."""
        conn = None
        with self._lock:
            conn = self._workers.pop(wid, None)
            try:
                self._idle.remove(wid)
            except ValueError:
                pass
            if conn is not None and conn.inflight is not None:
                job_id, blob = conn.inflight
                self._queue.appendleft((job_id, blob))
                conn.inflight = None
        if conn is not None:
            self._close_quietly(conn.sock)
        self._pump()

    # ---------- الجدولة والنتائج ----------

    def _pump(self):
        """يسلّم كل مهمة منتظرة لعامل معطل — أطول ما يمكن في كل نداء.

        يعمل أثناء الإيقاف أيضًا: 'إنهاء' تمنع التقديم الجديد فقط،
        أما المهام المنتظرة فتستمر في التصريف حتى ترحيل الخادم.
        """
        sends = []
        with self._lock:
            while self._idle and self._queue:
                wid = self._idle.popleft()
                job_id, blob = self._queue.popleft()
                conn = self._workers.get(wid)
                if conn is None:
                    continue              # زال العامل — تجاوزه
                conn.inflight = (job_id, blob)
                sends.append((wid, conn.sock, job_id, blob))
        for wid, sock, job_id, blob in sends:
            try:
                conn = self._workers.get(wid)
                if conn is not None:
                    conn.send(('عمل', job_id, blob))
                else:
                    continue              # زال العامل — أُعيد عمله
            except OSError:
                self._send_failed(wid, job_id, blob)

    def _send_failed(self, wid, job_id, blob):
        """فشل إرسال حزمة لعامل — أعد المهمة للطابور واسقط العامل."""
        with self._lock:
            conn = self._workers.get(wid)
            if conn is None:
                return                    # أُسقط سلفًا وأعيدت المهمة
            self._workers.pop(wid, None)
            try:
                self._idle.remove(wid)
            except ValueError:
                pass
            if conn.inflight is not None and conn.inflight[0] == job_id:
                conn.inflight = None
            self._queue.appendleft((job_id, blob))
            sock = conn.sock
        self._close_quietly(sock)
        self._pump()

    def _handle_result(self, wid, job_id, rkind, rblob):
        """يوجه نتيجة واصلة إلى مهمتها ويوقظ منتظريها."""
        task = None
        with self._lock:
            conn = self._workers.get(wid)
            if (conn is not None and conn.inflight is not None
                    and conn.inflight[0] == job_id):
                conn.inflight = None
                task = self._tasks.pop(job_id, None)
                if wid not in self._idle:
                    self._idle.append(wid)     # العامل حر من جديد
        if task is None:
            return                             # نتيجة مكررة أو لمهمة ساقطة
        try:
            if rkind == 'نهاية':
                value = decode_value(
                    pickle.loads(rblob),
                    {'root': self._root, 'raw': None, 'memo': {}})
                task._finish(value, None)
            elif rkind == 'خطأ':
                from .processes import _error_from_record
                task._finish(None, _error_from_record(
                    pickle.loads(rblob), self._root))
            else:
                task._finish(None, ArabiRuntimeError(pickle.loads(rblob)))
        except Exception as exc:               # فشل الفك نفسه — لا صمت
            task._finish(None, ArabiRuntimeError(
                f'تعذر فك نتيجة المهمة الموزعة: {exc}'))
        self._pump()

    # ---------- التقديم والإيقاف ----------

    def submit(self, func, args, kwargs, line):
        """يقدّم مهمة موزعة: يرمز الحزمة لحظة التقديم (فترفض القيم
        الحية فورًا قبل إشغال أي عامل) ويصفها في الطابور."""
        from .runtime import DistributedTaskValue
        _validate_callable(func, 'قدّم', line)
        enc_ctx = _make_enc_ctx(self._root)
        payload = {
            'عالمي': _encode_root(self._root, enc_ctx, line),
            'دالة': encode_value(func, enc_ctx, line),
            'وسائط': [encode_value(a, enc_ctx, line) for a in args[1:]],
            'كلمات': {k: encode_value(v, enc_ctx, line)
                      for k, v in kwargs.items()},
        }
        with self._lock:
            if self._closed:
                raise ArabiRuntimeError(
                    "الموزع مغلق — لا يقبل مهامًا جديدة بعد 'إنهاء'",
                    line)
            self._next_id += 1
            job_id = self._next_id
            self._total += 1
            task = DistributedTaskValue(job_id)
            self._tasks[job_id] = task
            self._queue.append((job_id, pickle.dumps(payload)))
        self._pump()
        return task

    def wait_workers(self, count, timeout, line=None):
        """يحجب حتى يتصل عدد كافٍ من العمالة — وإلا رفع خطأ واضح."""
        if isinstance(count, bool) or not isinstance(count, int) \
                or count < 1:
            raise ArabiRuntimeError(
                f"'انتظر_العمال' تتوقع عددًا صحيحًا موجبًا لكنها استلمت "
                f'{count!r}', line)
        if isinstance(timeout, bool) or \
                not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ArabiRuntimeError(
                f"'انتظر_العمال' تتوقع مهلة عددًا موجبًا لكنها استلمت "
                f'{timeout!r}', line)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._stopping:
                    raise ArabiRuntimeError(
                        'أُغلق الموزع أثناء انتظار العمالة', line)
                if len(self._workers) >= count:
                    return None
            time.sleep(POLL_INTERVAL)
        with self._lock:
            got = len(self._workers)
        raise ArabiRuntimeError(
            f'انتهت مهلة انتظار العمالة — المطلوب {count} والمتصل '
            f'{got}', line)

    def shutdown(self, line=None):
        """يغلق الموزع بنظافة: لا مهام جديدة، ثم ينتظر تصفية الجاري
        والممنتظر (حتى مهلة سماح)، فما لم يُنفذ يُرفض بوضوح، ثم يودّع
        العمالة ويغلق مقبس الاستماع."""
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            self._closed = True
            workers = list(self._workers.values())
        deadline = time.time() + SHUTDOWN_GRACE
        while time.time() < deadline:
            with self._lock:
                if not self._tasks:
                    break
            time.sleep(POLL_INTERVAL)
        with self._lock:
            remaining = list(self._tasks.values())
            self._tasks.clear()
            self._queue.clear()
        for task in remaining:               # ما لم يُنفذ — رفض صريح
            task._finish(None, ArabiRuntimeError(
                'أُغلق الموزع قبل تنفيذ هذه المهمة'))
        for conn in workers:                 # وداع بنظافة ثم إغلاق
            try:
                conn.sock.settimeout(2)
                conn.send(('وداع',))
            except OSError:
                pass
            except ArabiError:
                pass                # قناة مشفرة رفض وداعًا — يُغلق كذلك
            self._close_quietly(conn.sock)
        try:
            self._server_sock.close()
        except OSError:
            pass
        self._accept_thread.join(timeout=2)

    @staticmethod
    def _close_quietly(sock):
        try:
            sock.close()
        except OSError:
            pass


# ================== الجاهزات: موزع / عامل / قدّم ==================

def _dist_create(interp, args, line):
    """موزعة.موزع(منفذ؟، عنوان؟، مفتاح؟) — يبدأ خادم توزيع ويعيد قيمته.

    المنفذ الافتراضي 7700 والصفر يعني اختيارًا تلقائيًا من النظام
    (مفيد للاختبارات والبرامج المتعددة)، والعنوان الافتراضي 127.0.0.1
    (محلي فقط) — للشبكة العامة مرر '0.0.0.0' بوعي كامل. المفتاح
    الثالث (1.19) يشغل المصادقة والتشفير معًا: لا عامل يُسجّل إلا
    بتوقيع HMAC على تحدي عشوائي بمفتاحه، وبعد القبول تُشتق مفاتيح
    الجلسة من المفتاح وتحديه فتُشفَّر كل أعمال العمالة ونتائجها
    (1.21) — أنشئ المفتاح بتشفير.مفتاح_آمن() وشاركه سرًا. موزع.مشفّر()
    تعيد صح في هذا الوضع، والموزع الحر يبقى كما هو بلا تشفير.
    """
    port = DEFAULT_PORT
    host = '127.0.0.1'
    key = None
    if len(args) > 3:
        raise ArabiRuntimeError(
            f"'موزع' تأخذ ثلاثة معاملات على الأكثر (المنفذ ثم العنوان "
            f'ثم المفتاح) لكنها استلمت {len(args)}', line)
    if len(args) >= 1:
        port = args[0]
        if isinstance(port, bool) or not isinstance(port, int):
            raise ArabiRuntimeError(
                f"'موزع' تتوقع منفذًا عددًا صحيحًا لكنها استلمت "
                f'{port!r} من نوع {type(port).__name__}', line)
        if not 0 <= port <= 65535:
            raise ArabiRuntimeError(
                f'المنفذ {port} خارج المدى المسموح (٠ إلى ٦٥٥٣٥)', line)
    if len(args) == 2:
        host = args[1]
        if not isinstance(host, str):
            raise ArabiRuntimeError(
                f"'موزع' تتوقع عنوانًا نصيًا لكنها استلمت "
                f'{type(host).__name__}', line)
    if len(args) == 3:
        key = args[2]
        if not isinstance(key, str) or not key:
            raise ArabiRuntimeError(
                f"'موزع' تتوقع مفتاحًا نصيًا غير فارغ في المعامل الثالث "
                f'— أنشئه بتشفير.مفتاح_آمن()', line)
    from .runtime import DispatcherValue
    return DispatcherValue(_Server(host, port, interp, key))


def _dist_worker(interp, args, line):
    """موزعة.عامل(المضيف، منفذ؟، مفتاح؟) — يربط عاملاً بالموزع ويخدمه.

    الاستدعاء يحجب حتى إغلاق الموزع (يعيد ولا شيء) — شغّله بخيط
    'خيوط.شغّل' أو في برنامج مستقل بالأمر: --عامل المضيف:منفذ.
    المفتاح الثالث (1.19) يوقّع تحدي الموزع بالمفتاح المشترك —
    والناقص أو المخالف يرفض برسالة عربية واضحة.
    """
    if not args:
        raise ArabiRuntimeError(
            "'عامل' تحتاج عنوان الموزع كمعامل أول — مثال: "
            'عامل("127.0.0.1"، 7700)', line)
    host = args[0]
    if not isinstance(host, str):
        raise ArabiRuntimeError(
            f"'عامل' تتوقع عنوان الموزع نصًا لكنها استلمت "
            f'{type(host).__name__}', line)
    port = DEFAULT_PORT
    key = None
    if len(args) > 3:
        raise ArabiRuntimeError(
            f"'عامل' تأخذ ثلاثة معاملات على الأكثر (المضيف ثم المنفذ "
            f'ثم المفتاح) لكنها استلمت {len(args)}', line)
    if len(args) >= 2:
        port = args[1]
        if isinstance(port, bool) or not isinstance(port, int):
            raise ArabiRuntimeError(
                f"'عامل' تتوقع منفذًا عددًا صحيحًا لكنها استلمت "
                f'{port!r}', line)
        if not 0 <= port <= 65535:
            raise ArabiRuntimeError(
                f'المنفذ {port} خارج المدى المسموح (٠ إلى ٦٥٥٣٥)', line)
    if len(args) == 3:
        key = args[2]
        if not isinstance(key, str) or not key:
            raise ArabiRuntimeError(
                f"'عامل' تتوقع مفتاحًا نصيًا غير فارغ في المعامل الثالث "
                f'— المفتاح نفسه الذي مرر للموزع', line)
    return run_worker(host, port, key=key)


def _dist_submit(obj, args, kwargs, line):
    """موزع.قدّم(دالة، معاملات...، كلمات_المفاتيح) — يقدّم مهمة موزعة
    ويعيد مهمة تنتظرها بـ'انتظر' أو 'انتظر_الجميع' أو 'سباق'.

    الترميز يقع لحظة التقديم في الموزع — فأي قيمة حية غير قابلة
    للعبور تُرفض فورًا قبل أن تشغل أي عامل على أي جهاز.
    """
    if not args:
        raise ArabiRuntimeError(
            "'قدّم' تحتاج دالة على الأقل — مثال: موز.قدّم(حسب، ٥)",
            line)
    return obj._server.submit(args[0], args, kwargs, line)
