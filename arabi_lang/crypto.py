# -*- coding: utf-8 -*-
"""الأمان والتشفير (الإصدار 1.19) — وحدة «تشفير» اللغة العربية.

الفلسفة:
- كل ما يحتاجه برنامج عربي لحماية بياناته من مكتبة بايثون القياسية
  وحدها (hashlib وhmac وsecrets) — بلا أي تبعيات خارجية، التزامًا
  بمبدأ الحزمة «بلا تبعيات».
- دوال الحماية الشائعة بصيغة عربية مباشرة: بصمات قوية (هش و هش512)،
  توقيعات الرسائل (هوماك)، مقارنة زمن ثابت تفشل في التوقيت، مفاتيح
  ورموز عشوائية آمنة تشفيريًا (مفتاح_آمن و رمز_آمن و عدد_آمن)، وتشفير
  كلمات المرور بـ PBKDF2 (شفر_كلمة و تحقق_كلمة) واشتقاق المفاتيح
  (مشتق) — البصمة لا تُخزَّن أبدًا، الملح عشوائي لكل كلمة.
- الدوال موقّعة بنفس عقد الوحدات الجاهزة: (المعاملات، رقم السطر)
  وترفع ArabiRuntimeError برسائل عربية واضحة عند كل خطأ.

هذا الملف لا يستورد من runtime — وتسجيل الوحدة يتم في runtime داخل
install_builtins، فلا دورانية في الاستيراد.
"""

import base64
import hashlib
import hmac
import secrets as _secrets

from .errors import ArabiRuntimeError

# الخوارزميات المدعومة للبصمات والتوقيعات — بالأسماء القياسية
_HASH_ALGOS = {
    'sha256': 'sha256',
    'sha512': 'sha512',
    'sha384': 'sha384',
    'sha224': 'sha224',
    'sha1': 'sha1',
    'md5': 'md5',
}

# حدود أمان كلمات المرور والمفاتيح المشتقة
MIN_ROUNDS = 1000            # أقل عدد جولات مقبول لـ PBKDF2
MAX_ROUNDS = 10_000_000      # سقف الحماية من الاستنزاف
DEFAULT_ROUNDS = 100_000     # الافتراضي الموصى به (OWASP)
SALT_BYTES = 16              # طول الملح العشوائي لكل كلمة مرور
MIN_KEY_BYTES = 1            # أقل طول مفتاح عشوائي
MAX_KEY_BYTES = 1024         # أقصى طول مفتاح عشوائي


# ================== أدوات داخلية ==================

def _text(value, name, line):
    """يتحقق أن القيمة نص ويضبط نوع الخطأ العربي — يعيد النص نفسه."""
    if not isinstance(value, str):
        raise ArabiRuntimeError(
            f"'{name}' تتوقع نصًا لكنها استلمت "
            f'{type(value).__name__}', line)
    return value


def _algo(name, line):
    """يحل اسم الخوارزمية العربية/القياسية إلى اسم hashlib."""
    if not isinstance(name, str):
        raise ArabiRuntimeError(
            f'الخوارزمية يجب أن تكون نصًا لكنها استلمت '
            f'{type(name).__name__}', line)
    key = name.lower().strip()
    if key in _HASH_ALGOS:
        return _HASH_ALGOS[key]
    raise ArabiRuntimeError(
        f"خوارزمية البصمة '{name}' غير مدعومة — المدعوم: "
        f"{'، '.join(_HASH_ALGOS)}", line)


def _rounds(value, name, line):
    """يتحقق من عدد جولات PBKDF2 داخل حدود الأمان."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArabiRuntimeError(
            f"'{name}' تتوقع عدد جولات عددًا صحيحًا لكنها استلمت "
            f'{value!r}', line)
    if not MIN_ROUNDS <= value <= MAX_ROUNDS:
        raise ArabiRuntimeError(
            f"عدد الجولات {value} خارج المدى المسموح "
            f'({MIN_ROUNDS} إلى {MAX_ROUNDS})', line)
    return value


def _hex_bytes(value, name, line):
    """يفك نصًا ستر عشريًا إلى بايتات — برسالة عربية عند الفساد."""
    if not isinstance(value, str):
        raise ArabiRuntimeError(
            f"'{name}' تتوقع بصمة ستر عشري (نصًا) لكنها استلمت "
            f'{type(value).__name__}', line)
    try:
        return bytes.fromhex(value)
    except ValueError:
        raise ArabiRuntimeError(
            f"'{name}' استلمت ستر عشري فاسدًا — بصمات الملح والبصمة "
            'تُكتب بأحرف 0-9 وa-f فقط', line)


# ================== البصمات ==================

def _crypto_hash(args, line):
    """تشفير.هش(النص، الخوارزمية؟) — بصمة ستر عشري بأي خوارزمية
    مدعومة (الافتراضي sha256)."""
    if not 1 <= len(args) <= 2:
        raise ArabiRuntimeError(
            f"'هش' تأخذ معاملين على الأكثر (النص ثم الخوارزمية) لكنها "
            f'استلمت {len(args)}', line)
    text = _text(args[0], 'هش', line)
    algo = _algo(args[1] if len(args) == 2 else 'sha256', line)
    return hashlib.new(algo, text.encode('utf-8')).hexdigest()


def _crypto_hash512(args, line):
    """تشفير.هش512(النص) — بصمة sha512 السترة عشرية."""
    if len(args) != 1:
        raise ArabiRuntimeError(
            f"'هش512' تأخذ معاملًا واحدًا لكنها استلمت {len(args)}", line)
    text = _text(args[0], 'هش512', line)
    return hashlib.sha512(text.encode('utf-8')).hexdigest()


# ================== توقيع الرسائل ==================

def _crypto_hmac(args, line):
    """تشفير.هوماك(النص، المفتاح، الخوارزمية؟) — توقيع HMAC ستر عشري.

    المرسل والمستقبل يتشاركان المفتاح السري نفسه — فالرسالة التي لا
    توقع بمفتاحها الصحيح تُكشف حتى لو عدّلها مخترق في الطريق.
    """
    if not 2 <= len(args) <= 3:
        raise ArabiRuntimeError(
            f"'هوماك' تأخذ معاملين على الأقل (النص ثم المفتاح) وثلاثة "
            f'على الأكثر لكنها استلمت {len(args)}', line)
    text = _text(args[0], 'هوماك', line)
    key = _text(args[1], 'هوماك', line)
    algo = _algo(args[2] if len(args) == 3 else 'sha256', line)
    return hmac.new(key.encode('utf-8'), text.encode('utf-8'),
                    algo).hexdigest()


def _crypto_compare(args, line):
    """تشفير.مقارنة_آمنة(أ، ب) — مقارنة زمن ثابت للبصمات والأسرار.

    مقارنة == العادية تكشف طول السر المتطابق عبر توقيت الرد؛ هذه
    تقارن بزمن ثابت فلا يتسرب أي شيء — عيّنها للتحقق من البصمات.
    """
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'مقارنة_آمنة' تأخذ معاملين لكنها استلمت {len(args)}", line)
    a, b = args
    if not (isinstance(a, str) and isinstance(b, str)):
        raise ArabiRuntimeError(
            f"'مقارنة_آمنة' تقارن نصين بالزمن الثابت لكنها استلمت "
            f'{type(a).__name__} و{type(b).__name__}', line)
    # compare_digest يرفض النصوص غير الآسكية — نرمّز إلى بايتات فتظل
    # المقارنة بزمن ثابت وتقبل العربية واللاتينية على السواء
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


# ================== العشوائية الآمنة ==================

def _crypto_key(args, line):
    """تشفير.مفتاح_آمن(طول؟) — مفتاح عشوائي آمن تشفيريًا ستر عشري.

    الطول بالبايتات (الافتراضي 32 = 64 حرفًا ستر عشري) — يستحيل
    تخمينه، مناسب كسر مشترك للموزع والعمالة أو كرمز جلسات.
    """
    if len(args) > 1:
        raise ArabiRuntimeError(
            f"'مفتاح_آمن' تأخذ معاملًا واحدًا على الأكثر لكنها استلمت "
            f'{len(args)}', line)
    length = 32
    if args:
        length = args[0]
        if isinstance(length, bool) or not isinstance(length, int):
            raise ArabiRuntimeError(
                f"'مفتاح_آمن' تتوقع طولًا عددًا صحيحًا لكنها استلمت "
                f'{length!r}', line)
        if not MIN_KEY_BYTES <= length <= MAX_KEY_BYTES:
            raise ArabiRuntimeError(
                f'طول المفتاح {length} خارج المدى المسموح '
                f'({MIN_KEY_BYTES} إلى {MAX_KEY_BYTES} بايتًا)', line)
    return _secrets.token_hex(length)


def _crypto_token(args, line):
    """تشفير.رمز_آمن(طول؟) — رمز عشوائي بترميز 64 الأساسي للروابط
    (base64url) — مناسب لروابط إعادة الضبط والتوكنات المرسلة نصيًا."""
    if len(args) > 1:
        raise ArabiRuntimeError(
            f"'رمز_آمن' تأخذ معاملًا واحدًا على الأكثر لكنها استلمت "
            f'{len(args)}', line)
    length = 32
    if args:
        length = args[0]
        if isinstance(length, bool) or not isinstance(length, int):
            raise ArabiRuntimeError(
                f"'رمز_آمن' يتوقع طولًا عددًا صحيحًا لكنه استلم "
                f'{length!r}', line)
        if not MIN_KEY_BYTES <= length <= MAX_KEY_BYTES:
            raise ArabiRuntimeError(
                f'طول الرمز {length} خارج المدى المسموح '
                f'({MIN_KEY_BYTES} إلى {MAX_KEY_BYTES} بايتًا)', line)
    return _secrets.token_urlsafe(length)


def _crypto_rand(args, line):
    """تشفير.عدد_آمن(حد؟، أقصى؟) — عدد عشوائي آمن تشفيريًا.

    بمعامل واحد: 0 <= ن < حد — بمعاملين: حد <= ن < أقصى — المصدر
    os.urandom لا مولد اللاحظ العشوائي، فهو صالح للأسرار والقرارات
    الأمنية (عكس عشوائية.عدد المخصص للألعاب والمحاكاة).
    """
    if not 1 <= len(args) <= 2:
        raise ArabiRuntimeError(
            f"'عدد_آمن' تأخذ معاملًا أو معاملين لكنها استلمت "
            f'{len(args)}', line)
    first = args[0]
    if isinstance(first, bool) or not isinstance(first, int):
        raise ArabiRuntimeError(
            f"'عدد_آمن' تتوقع حدًا عددًا صحيحًا لكنها استلمت "
            f'{first!r}', line)
    if len(args) == 1:
        if first <= 0:
            raise ArabiRuntimeError(
                f"حد 'عدد_آمن' يجب أن يكون موجبًا لكنه استلم {first}", line)
        return _secrets.randbelow(first)
    second = args[1]
    if isinstance(second, bool) or not isinstance(second, int):
        raise ArabiRuntimeError(
            f"'عدد_آمن' تتوقع حدها الأعلى عددًا صحيحًا لكنها استلمت "
            f'{second!r}', line)
    if second <= first:
        raise ArabiRuntimeError(
            f"الحد الأعلى في 'عدد_آمن' يجب أن يتجاوز الأدنى لكنه "
            f'استلم {second} بعد {first}', line)
    span = second - first
    return first + _secrets.randbelow(span)


# ================== كلمات المرور ==================

def _crypto_pw_hash(args, line):
    """تشفير.شفر_كلمة(كلمة، جولات؟) — سجل تخزين آمن لكلمة مرور.

    يعيد قاموسًا {الخوارزمية، الجولات، الملح، البصمة} — الملح عشوائي
    جديد في كل نداء (فكلمتان متماثلتان تنتجان سجلين مختلفين)، والبصمة
    PBKDF2-HMAC-SHA256 — خزّن السجل كما هو، ولا تخزّن الكلمة أبدًا.
    """
    if not 1 <= len(args) <= 2:
        raise ArabiRuntimeError(
            f"'شفر_كلمة' تأخذ معاملين على الأكثر (الكلمة ثم عدد "
            f'الجولات) لكنها استلمت {len(args)}', line)
    password = _text(args[0], 'شفر_كلمة', line)
    rounds = DEFAULT_ROUNDS
    if len(args) == 2:
        rounds = _rounds(args[1], 'شفر_كلمة', line)
    salt = _secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                 salt, rounds)
    return {
        'الخوارزمية': 'pbkdf2_sha256',
        'الجولات': rounds,
        'الملح': salt.hex(),
        'البصمة': digest.hex(),
    }


_PW_FIELDS = ('الخوارزمية', 'الجولات', 'الملح', 'البصمة')


def _crypto_pw_verify(args, line):
    """تشفير.تحقق_كلمة(كلمة، سجل) — يتحقق من كلمة مرور مقابل سجل
    شفر_كلمة — يعيد صح أو خطأ بلا أي استثناء عند الخطأ الصحيح."""
    if len(args) != 2:
        raise ArabiRuntimeError(
            f"'تحقق_كلمة' تأخذ معاملين (الكلمة ثم السجل) لكنها استلمت "
            f'{len(args)}', line)
    password = _text(args[0], 'تحقق_كلمة', line)
    record = args[1]
    if not isinstance(record, dict):
        raise ArabiRuntimeError(
            f"'تحقق_كلمة' تتوقع سجل قاموسًا من مخرجات 'شفر_كلمة' لكنها "
            f'استلمت {type(record).__name__}', line)
    missing = [f for f in _PW_FIELDS if f not in record]
    if missing:
        raise ArabiRuntimeError(
            f"سجل كلمة المرور ناقص الحقول: {'، '.join(missing)} — "
            'السجل يجب أن يأتي من تشفير.شفر_كلمة دون حذف أي حقل', line)
    algo = record['الخوارزمية']
    if not isinstance(algo, str) or algo != 'pbkdf2_sha256':
        raise ArabiRuntimeError(
            f"خوارزمية السجل '{display_safe(algo)}' غير مدعومة في "
            f"'تحقق_كلمة' — المدعوم: pbkdf2_sha256", line)
    rounds = record['الجولات']
    rounds = _rounds(rounds, 'تحقق_كلمة', line)
    salt = _hex_bytes(record['الملح'], 'الملح', line)
    expected = _hex_bytes(record['البصمة'], 'البصمة', line)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                 salt, rounds)
    return hmac.compare_digest(digest, expected)


def display_safe(value):
    """عرض آمن لقيمة داخل رسالة خطأ (نصية أو أي شيء آخر)."""
    if isinstance(value, str):
        return value
    return type(value).__name__


# ================== اشتقاق المفاتيح ==================

def _crypto_derive(args, line):
    """تشفير.مشتق(كلمة، ملح، طول؟، جولات؟) — اشتقاق مفتاح من سر.

    يحول كلمة سر بشرية إلى مفتاح بحجم بايتات محدد (ستر عشري) بواسطة
    PBKDF2 — مناسب لاشتقاق مفتاح قناة موزعة من كلمة يتفق عليها
    البشر: مشتق("سرّ الفريق"، "منفذ-7700") — نفس المدخلات تعطي
    المفتاح نفسه دائمًا، وتغيير حرف واحد يغير المفتاح كله.
    """
    if not 2 <= len(args) <= 4:
        raise ArabiRuntimeError(
            f"'مشتق' تأخذ معاملين على الأقل (الكلمة ثم الملح) وأربعة "
            f'على الأكثر لكنها استلمت {len(args)}', line)
    password = _text(args[0], 'مشتق', line)
    salt_text = _text(args[1], 'مشتق', line)
    length = 32
    if len(args) >= 3:
        length = args[2]
        if isinstance(length, bool) or not isinstance(length, int):
            raise ArabiRuntimeError(
                f"'مشتق' يتوقع طول المفتاح عددًا صحيحًا لكنه استلم "
                f'{length!r}', line)
        if not MIN_KEY_BYTES <= length <= MAX_KEY_BYTES:
            raise ArabiRuntimeError(
                f'طول المفتاح المشتق {length} خارج المدى المسموح '
                f'({MIN_KEY_BYTES} إلى {MAX_KEY_BYTES} بايتًا)', line)
    rounds = DEFAULT_ROUNDS
    if len(args) == 4:
        rounds = _rounds(args[3], 'مشتق', line)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                 salt_text.encode('utf-8'), rounds,
                                 dklen=length)
    return digest.hex()


# ================== التوقيع الداخلي للشبكة الموزعة (1.19) ==================

# بادئة سياق التوقيع — تربط بصمة الربط بالغرض (توقيع التحدي) فلا
# يعاد استخدام بصمة بيانات عابرة كإجابة تحدي أو العكس
_AUTH_CONTEXT = 'عربي-موزع-تحدٍ-1'.encode('utf-8')


def sign_challenge(key, nonce):
    """يوقع تحدي الموزع بمفتاح سري — HMAC-SHA256(key, سياق+nonce).

    يُستخدم في مصادقة العمالة للموزع (1.19): الموزع يرسل nonce عشوائي
    والعامل يوقعه بالمفتاح المشترك، والموزع يتحقق بمقارنة زمن ثابت.
    """
    if isinstance(key, str):
        key = key.encode('utf-8')
    return hmac.new(_AUTH_CONTEXT + key, nonce, hashlib.sha256).hexdigest()


def verify_challenge(key, nonce, signature):
    """يتحقق من توقيع التحدي بمقارنة زمن ثابت — يعيد صح أو خطأ."""
    try:
        expected = sign_challenge(key, nonce)
    except (TypeError, AttributeError):
        return False
    if not isinstance(signature, str):
        return False
    # المقارنة على بايتات utf-8 — ترفض شكلاً بالضبط ولا تستثني أبدًا
    return hmac.compare_digest(expected.encode('utf-8'),
                               signature.encode('utf-8'))
