# -*- coding: utf-8 -*-
"""سجل الحزم (Package Registry) — نظام إدارة الحزم للغة عربي.

يُشبه نظام الحزم في اللغات الكبيرة لكن بعربية كاملة وببساطة مقصودة:

    حزم/                مجلد الحزم المثبتة (يشبه node_modules)
      احصاء_متقدم/
        حزمة.json      بيان الحزمة: الاسم والنسخة والمدخل والتبعيات
        احصاء_متقدم.عربي  كود الحزمة (المدخل)
    قفل.json            قفل التثبيت: النسخ المثبتة بالضبط (يشبه package-lock)
    الفهرس.json         فهرس السجل: اسم الحزمة ← نسختها ومصدرها

أوامر المدير (عبر المفسّر):
    python arabi.py حزمة تثبيت [اسم|مسار|رابط]   تثبيت حزمة أو تبعيات المشروع
    python arabi.py حزمة إزالة اسم               إزالة حزمة مثبتة
    python arabi.py حزمة قائمة                   عرض الحزم المثبتة
    python arabi.py حزمة بحث [كلمة]              البحث في فهرس السجل
    python arabi.py حزمة تحديث [اسم]             تحديث إلى أحدث نسخة في السجل

مصدر الفهرس: رابط افتراضي (مستودع arabi-registry على GitHub) يُستبدل
بمتغير البيئة عربي_الفهرس أو بالعلم --الفهرس — ويدعم المسارات المحلية
ليعمل النظام كاملًا دون شبكة.

الاستيراد بعد التثبيت تلقائي: استورد اسم_الحزمة — المفسّر يبحث في حزم/.

قيود النسخ: "1.2.3" تطابق تام، ">=1.0" وما شابه، "^1.2.3" أي متوافق
مع 1 (semver)، "~1.2.3" أي 1.2.x، و"*" أي نسخة.
"""

import json
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile

from .errors import ArabiError
from .lexer import Lexer
from .parser import Parser

# أسماء الملفات الثابتة للنظام
MANIFEST_NAME = 'حزمة.json'        # بيان الحزمة داخل مجلدها
LOCK_NAME = 'قفل.json'             # قفل التثبيت في جذر المشروع
PACKAGES_DIR = 'حزم'               # مجلد الحزم المثبتة
INDEX_NAME = 'الفهرس.json'         # اسم ملف فهرس السجل

# مصدر الفهرس الافتراضي وبيئة التجاوز
DEFAULT_INDEX = ('https://raw.githubusercontent.com/CTO-DRS/'
                 'arabi-registry/main/الفهرس.json')
INDEX_ENV = 'عربي_الفهرس'

# اسم حزمة صالح = معرف قابل للاستيراد (حروف/أرقام/شرطة سفلية، يبدأ بحرف)
NAME_RE = re.compile(r'^[^\W\d]\w*$', re.UNICODE)

__all__ = ['MANIFEST_NAME', 'LOCK_NAME', 'PACKAGES_DIR', 'INDEX_NAME',
           'DEFAULT_INDEX', 'INDEX_ENV',
           'parse_version', 'compare_versions', 'satisfies',
           'read_manifest', 'load_index', 'install', 'remove',
           'list_installed', 'update', 'search', 'read_lock']


# ================== النسخ والقيود ==================

def parse_version(text):
    """يحلل نسخة 'X.Y.Z' إلى صف أعداد — يقبل جزءًا أو جزأين (تكمل بصفر)."""
    if not isinstance(text, str) or not text.strip():
        raise ArabiError(f"نسخة غير صالحة: '{text}' — الصيغة X.Y.Z")
    parts = text.strip().split('.')
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        raise ArabiError(
            f"نسخة غير صالحة: '{text}' — الصيغة X.Y.Z بأرقام فقط")
    nums = [int(p) for p in parts]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def compare_versions(a, b):
    """يقارن نسختين — يعيد ‎-1 إذا a أقدم، 0 إذا متساويتان، 1 إذا أحدث."""
    va, vb = parse_version(a), parse_version(b)
    return (va > vb) - (va < vb)


def _caret_bounds(v):
    """حدود الرتّب ^: أقل تغيير قد يكسر التوافق — بدلالة semver."""
    major, minor, patch = v
    if major > 0:
        return (major + 1, 0, 0)
    if minor > 0:
        return (0, minor + 1, 0)
    return (0, 0, patch + 1)


def satisfies(version, constraint):
    """هل تلبي النسخة القيد؟ يدعم = و >= و > و <= و < و ^ و ~ و *."""
    constraint = (constraint or '*').strip()
    if constraint in ('*', ''):
        return True
    m = re.match(r'^(>=|<=|==|>|<|=|\^|~)\s*(.+)$', constraint)
    if m:
        op, target = m.group(1), m.group(2)
    else:
        # قيد بلا معامل = تطابق تام
        op, target = '=', constraint
    cmp = compare_versions(version, target)
    if op in ('=', '=='):
        return cmp == 0
    if op == '>=':
        return cmp >= 0
    if op == '>':
        return cmp > 0
    if op == '<=':
        return cmp <= 0
    if op == '<':
        return cmp < 0
    if op == '^' or op == '~':
        if compare_versions(version, target) < 0:
            return False
        upper = _caret_bounds(parse_version(target)) if op == '^' \
            else (parse_version(target)[0], parse_version(target)[1] + 1, 0)
        return compare_versions(version, '.'.join(map(str, upper))) < 0
    raise ArabiError(f"قيد غير مفهوم: '{constraint}'")


# ================== بيان الحزمة ==================

def read_manifest(pkg_dir):
    """يقرأ بيان حزمة.json ويتحقق من حقوله — يعيد قاموسًا مكتملًا."""
    path = os.path.join(pkg_dir, MANIFEST_NAME)
    if not os.path.isfile(path):
        raise ArabiError(
            f"لا بيان حزمة في '{pkg_dir}' — المطلوب ملف {MANIFEST_NAME}")
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except ValueError as exc:
        raise ArabiError(f"بيان غير صالح في '{path}': {exc}")
    except OSError as exc:
        raise ArabiError(f"لا يمكن قراءة البيان '{path}': {exc}")
    if not isinstance(data, dict):
        raise ArabiError(f"البيان '{path}' يجب أن يكون كائن JSON")
    name = data.get('الاسم')
    if not name or not isinstance(name, str):
        raise ArabiError(f"البيان '{path}' يفتقد حقل 'الاسم' النصي")
    if not NAME_RE.match(name):
        raise ArabiError(
            f"اسم الحزمة '{name}' غير صالح — يجب أن يكون معرفًا قابلًا "
            "للاستيراد (حروف وأرقام و_ ويبدأ بحرف)")
    version = data.get('النسخة') or '0.0.0'
    parse_version(version)                       # تحقق مبكر من الصيغة
    entry = data.get('المدخل') or (name + '.عربي')
    data['الاسم'] = name
    data['النسخة'] = version
    data['المدخل'] = entry
    deps = data.get('التبعيات') or {}
    if not isinstance(deps, dict):
        raise ArabiError(
            f"حقل 'التبعيات' في '{path}' يجب أن يكون قاموس اسم ← قيد")
    for dep, constraint in deps.items():
        if not NAME_RE.match(dep):
            raise ArabiError(f"اسم تبعية غير صالح في '{path}': '{dep}'")
        satisfies('0.0.0', constraint)           # تحقق من صيغة القيد
    data['التبعيات'] = deps
    return data


def _write_manifest(pkg_dir, data):
    """يكتب بيان حزمة.json بترميز مقروء."""
    os.makedirs(pkg_dir, exist_ok=True)
    path = os.path.join(pkg_dir, MANIFEST_NAME)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _validate_source(source):
    """يفحص صياغة كل ملفات .عربي في مصدر — لا تثبت لكود غير سليم."""
    for name in sorted(os.listdir(source)):
        if not name.endswith('.عربي'):
            continue
        path = os.path.join(source, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8') as f:
            content = f.read()
        try:
            Parser(Lexer(content).tokenize()).parse()
        except ArabiError as exc:
            raise ArabiError(
                f"الحزمة تحتوي كودًا غير سليم في '{name}': {exc}")


# ================== فهرس السجل ==================

def load_index(index_source=None):
    """يحمّل فهرس السجل من مسار محلي أو رابط — يعيد قاموس اسم ← بيانات."""
    if index_source is None:
        index_source = os.environ.get(INDEX_ENV) or DEFAULT_INDEX
    is_url = index_source.startswith(('http://', 'https://', 'file://'))
    if is_url:
        try:
            with urllib.request.urlopen(index_source, timeout=30) as resp:
                content = resp.read().decode('utf-8')
        except (OSError, ValueError) as exc:
            raise ArabiError(f"فشل تحميل فهرس السجل: {exc}")
    else:
        if not os.path.isfile(index_source):
            raise ArabiError(
                f"ملف فهرس السجل '{index_source}' غير موجود")
        with open(index_source, encoding='utf-8') as f:
            content = f.read()
    try:
        index = json.loads(content)
    except ValueError as exc:
        raise ArabiError(f"فهرس سجل غير صالح ({index_source}): {exc}")
    if not isinstance(index, dict):
        raise ArabiError('الفهرس يجب أن يكون كائن JSON: اسم ← بيانات')
    for name, info in index.items():
        if not isinstance(info, dict) or 'المصدر' not in info:
            raise ArabiError(
                f"مدخل الفهرس للحزمة '{name}' يفتقد حقل 'المصدر'")
    return index


def search(term, index_source=None):
    """يبحث في الفهرس بالاسم أو الوصف — يعيد قائمة (اسم، بيانات)."""
    index = load_index(index_source)
    term = (term or '').strip()
    results = []
    for name, info in sorted(index.items()):
        if not term or term in name or term in (info.get('الوصف') or ''):
            results.append((name, info))
    return results


# ================== جلب المصدر ==================

def _fetch_source(source, expected_name=None, index_info=None):
    """يجلب مصدر الحزمة إلى مجلد مؤقت ويعيد مساره المحلي.

    يدعم: مجلدًا محليًا ببيان، ملف .عربي مفرد (يُغلَّف ببيان تلقائي)،
    أرشيف .zip، أو رابط http(s)/file لأيٍّ من ذلك.
    """
    tmp = tempfile.mkdtemp(prefix='عربي-حزمة-')
    try:
        return _fetch_into(source, tmp, expected_name, index_info)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _fetch_into(source, tmp, expected_name, index_info):
    """المنطق الفعلي للجلب — يُستدعى من _fetch_source فقط."""
    if source.startswith('file://'):
        # رابط ملف محلي — يتحول لمسارًا ويُعامل محليًا (مجلدًا أو ملفًا)
        local = urllib.request.url2pathname(
            urllib.parse.urlsplit(source).path)
        return _fetch_local(local, tmp, expected_name, index_info)
    if source.startswith(('http://', 'https://')):
        # حفظ باسمه الأصلي من الرابط حتى تُعرف صيغته (.عربي أو .zip)
        basename = os.path.basename(urllib.parse.urlsplit(source).path) \
            or '_تنزيل'
        local = os.path.join(tmp, basename)
        try:
            urllib.request.urlretrieve(source, local)
        except OSError as exc:
            raise ArabiError(f"فشل تنزيل الحزمة من '{source}': {exc}")
        return _fetch_local(local, tmp, expected_name, index_info,
                            downloaded=True)
    return _fetch_local(source, tmp, expected_name, index_info)


def _fetch_local(source, tmp, expected_name, index_info, downloaded=False):
    """يعالج مصدرًا محليًا (بعد التنزيل إن كان رابطًا)."""
    version = (index_info or {}).get('النسخة') or '0.0.0'
    if os.path.isdir(source) and os.path.isfile(
            os.path.join(source, MANIFEST_NAME)):
        # مجلد حزمة كامل — انسخه كما هو
        dest = os.path.join(tmp, 'حزمة')
        shutil.copytree(source, dest)
        return dest
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as zf:
            zf.extractall(tmp)
        # البيان إما في الجذر أو في مجلد واحد داخله
        if os.path.isfile(os.path.join(tmp, MANIFEST_NAME)):
            return tmp
        for entry in sorted(os.listdir(tmp)):
            sub = os.path.join(tmp, entry)
            if os.path.isdir(sub) and os.path.isfile(
                    os.path.join(sub, MANIFEST_NAME)):
                return sub
        raise ArabiError(
            f"الأرشيف '{os.path.basename(source)}' لا يحتوي {MANIFEST_NAME}")
    if os.path.isfile(source) and source.endswith('.عربي'):
        # ملف مفرد — غلّفه ببيان تلقائي
        name = expected_name or os.path.splitext(
            os.path.basename(source))[0]
        if not NAME_RE.match(name):
            raise ArabiError(
                f"اسم الحزمة '{name}' غير صالح — يجب أن يكون معرفًا "
                "قابلًا للاستيراد")
        dest = os.path.join(tmp, 'حزمة')
        os.makedirs(dest, exist_ok=True)
        fname = name + '.عربي'
        shutil.copy(source, os.path.join(dest, fname))
        _write_manifest(dest, {
            'الاسم': name,
            'النسخة': version,
            'الوصف': (index_info or {}).get('الوصف', ''),
            'المدخل': fname,
        })
        return dest
    raise ArabiError(
        f"مصدر غير مفهوم للحزمة: '{source}' — المطلوب مجلد ببيان، "
        "أو ملف .عربي، أو أرشيف .zip، أو رابط إليها")


# ================== التثبيت والقفل ==================

def _packages_root(project_dir):
    """مسار مجلد الحزم في المشروع."""
    return os.path.join(project_dir, PACKAGES_DIR)


def _pkg_dir(project_dir, name):
    """مسار مجلد حزمة معينة داخل المشروع."""
    return os.path.join(_packages_root(project_dir), name)


def list_installed(project_dir):
    """يفحص مجلد الحزم — يعيد {اسم: {نسخة، تبعيات، وصف}} للمثبت."""
    root = _packages_root(project_dir)
    result = {}
    if not os.path.isdir(root):
        return result
    for entry in sorted(os.listdir(root)):
        sub = os.path.join(root, entry)
        if os.path.isdir(sub) and os.path.isfile(
                os.path.join(sub, MANIFEST_NAME)):
            data = read_manifest(sub)
            result[data['الاسم']] = {
                'نسخة': data['النسخة'],
                'تبعيات': data.get('التبعيات', {}),
                'وصف': data.get('الوصف', ''),
            }
        elif entry.endswith('.عربي') and os.path.isfile(sub):
            result[entry[:-len('.عربي')]] = {
                'نسخة': None, 'تبعيات': {}, 'وصف': 'ملف مفرد',
            }
    return result


def _write_lock(project_dir):
    """يعيد بناء قفل.json من بيانات الحزم المثبتة فعليًا."""
    installed = list_installed(project_dir)
    lock = {'الحزم': {
        name: {
            'النسخة': info['نسخة'],
            'التبعيات': info['تبعيات'],
        }
        for name, info in installed.items()
    }}
    path = os.path.join(project_dir, LOCK_NAME)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(lock, f, ensure_ascii=False, indent=2)
    return path


def read_lock(project_dir):
    """يقرأ قفل.json — يعيد القاموس أو {} إذا لا قفل."""
    path = os.path.join(project_dir, LOCK_NAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (ValueError, OSError):
        return {}
    return data.get('الحزم', {}) if isinstance(data, dict) else {}


def install(request, project_dir=None, index_source=None, _stack=None):
    """يثبت حزمة بالاسم (من الفهرس) أو بمصدر مباشر، مع تبعياتها.

    يعيد قائمة رسائل النتائج [(نص، نوع)] حيث نوع: ثُبتت/موجودة.
    القيد الاختياري يمر مع الاسم بصيغة 'اسم>=1.0' — أو استخدم install_dep.
    """
    if project_dir is None:
        project_dir = os.getcwd()
    if _stack is None:
        _stack = []
    return _install_one(request, '*', project_dir, index_source, _stack)


def install_dep(name, constraint, project_dir, index_source, _stack):
    """يثبت تبعية باسم وقيده — نقطة الدخول لحل التبعيات."""
    return _install_one(name, constraint, project_dir, index_source, _stack)


def _install_one(request, constraint, project_dir, index_source, _stack):
    """يثبت حزمة واحدة + تبعياتها تعاوديًا — مع كشف الدورات والتعارضات."""
    messages = []

    # هل الطلب اسمًا في الفهرس أم مصدرًا مباشرًا (مسار/رابط)؟
    is_source = ('/' in request or '\\' in request
                 or request.startswith(('http://', 'https://', 'file://'))
                 or os.path.exists(request))

    if is_source:
        # مصدر مباشر: الاسم من البيان داخل المصدر
        fetched = _fetch_source(request)
        try:
            data = read_manifest(fetched)
            messages.extend(_commit_package(
                fetched, data, constraint, project_dir, index_source,
                _stack))
        finally:
            shutil.rmtree(fetched, ignore_errors=True)
        return messages

    # اسم من الفهرس
    name = request
    if not NAME_RE.match(name):
        raise ArabiError(
            f"اسم الحزمة '{name}' غير صالح — يجب أن يكون معرفًا "
            "قابلًا للاستيراد")
    if name in _stack:
        chain = ' ← '.join(_stack + [name])
        raise ArabiError(f'تبعية دائرية في الحزم: {chain}')

    index = load_index(index_source)
    if name not in index:
        raise ArabiError(
            f"الحزمة '{name}' غير موجودة في سجل الحزم — استخدم "
            "'حزمة بحث' لعرض المتاح")

    info = index[name]
    version = info.get('النسخة') or '0.0.0'
    if not satisfies(version, constraint):
        raise ArabiError(
            f"الحزمة '{name}' نسختها {version} في السجل لا تلبي القيد "
            f"'{constraint}' — لا نسخة متوافقة")

    installed = list_installed(project_dir)
    if name in installed:
        current = installed[name]['نسخة']
        if current is not None and satisfies(current, constraint):
            # مثبتة وتلبي القيد — لكن تأكد من التبعيات إن قيد جديد
            if not _stack:
                messages.extend(_ensure_deps(
                    name, project_dir, index_source, _stack))
            messages.append(
                (f"{name} v{current} مثبتة بالفعل وتلبي القيد", 'موجودة'))
            return messages
        raise ArabiError(
            f"الحزمة '{name}' مثبتة بنسخة {current} لا تلبي القيد "
            f"'{constraint}' — أزلها أولًا: حزمة إزالة {name}")

    # اجلب المصدر واقرأ البيان الحقيقي
    fetched = _fetch_source(info['المصدر'], expected_name=name,
                            index_info=info)
    try:
        data = read_manifest(fetched)
        if data['الاسم'] != name:
            raise ArabiError(
                f"بيان الحزمة يقول '{data['الاسم']}' والمطلوب '{name}' "
                "— اسم في الفهرس لا يطابق البيان")
        if not satisfies(data['النسخة'], constraint):
            raise ArabiError(
                f"نسخة '{data['الاسم']}' الفعلية {data['النسخة']} لا تلبي "
                f"القيد '{constraint}'")
        messages.extend(_commit_package(
            fetched, data, constraint, project_dir, index_source, _stack))
    finally:
        shutil.rmtree(fetched, ignore_errors=True)
    return messages


def _commit_package(fetched, data, constraint, project_dir, index_source,
                    _stack):
    """يثبت حزمة مجلبة: فحص الكود ثم تبعياتها ثم انسخها واكتب القفل."""
    name = data['الاسم']
    messages = []

    # لا تثبت لكود غير سليم — قبل أي شيء آخر حتى لا تُثبت تبعيات بلا فائدة
    _validate_source(fetched)

    # التبعيات أولًا — تُثبت قبل الحزمة نفسها
    for dep, dep_constraint in data.get('التبعيات', {}).items():
        messages.extend(_install_one(
            dep, dep_constraint, project_dir, index_source,
            _stack + [name]))

    dest = _pkg_dir(project_dir, name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(fetched, dest)
    _write_lock(project_dir)
    messages.append((f"{name} v{data['النسخة']} — ثُبتت في "
                     f"{PACKAGES_DIR}/{name}", 'ثُبتت'))
    return messages


def _ensure_deps(name, project_dir, index_source, _stack):
    """يعالج تبعيات حزمة مثبتة أصلًا (عند تثبيت صريح متكرر)."""
    manifest_path = os.path.join(_pkg_dir(project_dir, name), MANIFEST_NAME)
    try:
        with open(manifest_path, encoding='utf-8') as f:
            data = json.load(f)
    except (ValueError, OSError):
        return []
    messages = []
    for dep, dep_constraint in (data.get('التبعيات') or {}).items():
        messages.extend(_install_one(
            dep, dep_constraint, project_dir, index_source, _stack + [name]))
    return [m for m in messages if m[1] == 'ثُبتت']


def remove(name, project_dir=None, _force=False):
    """يزيل حزمة مثبتة — يرفض إن كانت تبعية لحزمة أخرى.

    _force للتحديث الداخلي: يسمح بالإزالة رغم المعتمدين لأن
    إعادة التثبيت تليها فورًا (ولا تُستخدم من CLI).
    """
    if project_dir is None:
        project_dir = os.getcwd()
    installed = list_installed(project_dir)
    if name not in installed:
        raise ArabiError(
            f"الحزمة '{name}' غير مثبتة — المثبت: "
            + ('، '.join(sorted(installed)) or 'لا شيء'))
    if not _force:
        dependents = []
        for other, info in installed.items():
            if other != name and name in info.get('تبعيات', {}):
                dependents.append(other)
        if dependents:
            raise ArabiError(
                f"لا يمكن إزالة '{name}' — الحزم "
                f"'{'، '.join(sorted(dependents))}' تعتمد عليها؛ أزلها أولًا")
    dest = _pkg_dir(project_dir, name)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    elif os.path.isfile(dest + '.عربي'):
        # ملف مفرد
        os.remove(dest + '.عربي')
    else:
        raise ArabiError(
            f"ملفات الحزمة '{name}' مفقودة من الحزم — أعِد التثبيت")
    _write_lock(project_dir)
    return f"أُزيلت الحزمة '{name}'"


def update(name=None, project_dir=None, index_source=None):
    """يحدث حزمة (أو كل الحزم) إلى أحدث نسخة في الفهرس."""
    if project_dir is None:
        project_dir = os.getcwd()
    installed = list_installed(project_dir)
    targets = [name] if name else sorted(installed)
    if name and name not in installed:
        raise ArabiError(f"الحزمة '{name}' غير مثبتة — لا شيء لتحديثه")
    messages = []
    for target in targets:
        # أزل ثم ثبت من جديد = تحديث إلى الأحدث — الإزالة القسرية
        # مطلوبة لأن حزمًا معتمدة قد تحجبها، والتثبيت يليها فورًا
        remove(target, project_dir, _force=True)
        messages.extend(install(target, project_dir, index_source))
    return messages
