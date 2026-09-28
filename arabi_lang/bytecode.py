# -*- coding: utf-8 -*-
"""الكود الوسيط (Bytecode) — ترجمة شجرة الصياغة إلى صيغة مخزنة وإعادة تحميلها.

المبدأ: تحليل المصدر (لفظيًا ونحويًا) هو أبطأ مرحلة عند تشغيل البرامج
الكبيرة ومشاريع الوحدات المتعددة. هذه الوحدة تسلسل شجرة الصياغة كاملة
بالصيغة الثنائية pickle، وتخزنها في مجلد __بايت__ بجانب المصدر:

    ملف.عربي  →  __بايت__/ملف.بيت

التشغيلات التالية تتحقق من صلاحية الذاكرة (السحر + إصدار اللغة + حجم
المصدر وزمن تعديله) وتحمّل الشجرة مباشرة متجاوزة التحليل. أي تعديل
على المصدر يُبطل الذاكرة تلقائيًا — كما في __pycache__ في بايثون.

الصيغة متسلسلة بلا فقد (lossless): كل عقدة تُكتب باسم صنفها وحقولها،
والصفوف (tuples) تُوسم بعلامة 'صف' حتى تعود كما كانت (معاملات مسماه،
أجزاء النصوص المنسقة، عبارات فهم القوائم…).

مجلد الذاكرة يستعمل الصيغة الثنائية pickle (محرك C) — أسرع ٣ أضعاف من
JSON في إعادة البناء، أي تسريع ٥× وما فوق مقابل التحليل الكامل. وهي
فلسفة __pycache__ في بايثون: ذاكرة محلية موثوقة، تتلف وتُعاد كتابتها
تلقائيًا عند أي تعديل للمصدر أو تغيّر إصدار اللغة.
"""

import os
import pickle

from . import nodes as N
from .errors import ArabiError

MAGIC = 'عربي-بايت'                # بصمة الصيغة للتحقق من النوع
CACHE_DIR = '__بايت__'             # مجلد الذاكرة بجانب المصدر
CACHE_EXT = '.بيت'                 # امتداد ملفات الكود الوسيط

__all__ = ['MAGIC', 'CACHE_DIR', 'CACHE_EXT', 'ast_to_dict', 'dict_to_ast',
           'cache_path_for', 'write_cache', 'read_program', 'compile_file']


# ---------- التسلسل (شجرة → قواميس قابلة للتفريغ في JSON) ----------

def ast_to_dict(node):
    """يحوّل شجرة الصياغة (أو أي حقل منها) إلى بنية قواميس/قوائم نقية."""
    if isinstance(node, N.Node):
        fields = {k: ast_to_dict(v) for k, v in vars(node).items()}
        return {'عقدة': type(node).__name__, 'حقول': fields}
    if isinstance(node, tuple):
        # وسم الصفوف — JSON يفقد نوعها فيرجع معوّمًا
        return {'صف': [ast_to_dict(x) for x in node]}
    if isinstance(node, list):
        return [ast_to_dict(x) for x in node]
    if isinstance(node, dict):
        return {str(k): ast_to_dict(v) for k, v in node.items()}
    if isinstance(node, (str, int, float, bool)) or node is None:
        return node
    raise ArabiError(
        f'لا يمكن تسلسل القيمة {node!r} في الكود الوسيط')


# جدول العقد جاهز مسبقًا — أسرع من getattr والتحقق في كل عقدة أثناء التحميل
_NODE_CLASSES = {
    name: cls for name, cls in vars(N).items()
    if isinstance(cls, type) and issubclass(cls, N.Node)
}


def dict_to_ast(data):
    """يعيد بناء الشجرة من البنية المتسلسلة — عكس ast_to_dict تمامًا."""
    if isinstance(data, dict):
        tag = data.get('عقدة')
        if tag is not None:
            cls = _NODE_CLASSES.get(tag)
            if cls is None:
                raise ArabiError(f"عقدة مجهولة في الكود الوسيط: '{tag}'")
            obj = cls.__new__(cls)
            obj.__dict__ = {
                k: dict_to_ast(v) for k, v in data['حقول'].items()
            }
            return obj
        if 'صف' in data:
            return tuple(dict_to_ast(x) for x in data['صف'])
        return {k: dict_to_ast(v) for k, v in data.items()}
    if isinstance(data, list):
        return [dict_to_ast(x) for x in data]
    return data


# ---------- الذاكرة المؤقتة ----------

def cache_path_for(src_path):
    """مسار ملف الكود الوسيط المتوقع لمصدر معين: __بايت__/الاسم.بيت."""
    src_path = os.path.abspath(src_path)
    base = os.path.splitext(os.path.basename(src_path))[0]
    return os.path.join(os.path.dirname(src_path), CACHE_DIR, base + CACHE_EXT)


def _version():
    from . import __version__
    return __version__


def write_cache(tree, src_path):
    """يكتب الشجرة في الذاكرة — كتابة ذرية عبر ملف مؤقت ثم استبدال.

    الصيغة الثنائية pickle (بمحرك C) لأن التحميل أسرع ٣ أضعاف من JSON،
    وهي كما هي فلسفة ملفات __pycache__ في بايثون: ذاكرة محلية موثوقة.
    """
    cpath = cache_path_for(src_path)
    os.makedirs(os.path.dirname(cpath), exist_ok=True)
    st = os.stat(src_path)
    payload = (MAGIC, _version(), st.st_size, st.st_mtime_ns, tree)
    tmp = cpath + '.مؤقت'
    with open(tmp, 'wb') as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, cpath)
    return cpath


def _is_fresh(payload, src_path):
    """يتحقق من صلاحية الذاكرة: البصمة والإصدار وحجم المصدر وزمن تعديله."""
    if not isinstance(payload, tuple) or len(payload) != 5:
        return False
    magic, version, size, mtime, _tree = payload
    if magic != MAGIC or version != _version():
        return False
    st = os.stat(src_path)
    return size == st.st_size and mtime == st.st_mtime_ns


def read_program(src_path, source=None):
    """يعيد (الشجرة، من_الذاكرة) مع تحديث الذاكرة تلقائيًا عند القِدَم.

    إن كانت الذاكرة صالحة عادت الشجرة منها فورًا (True)؛ وإلا ترجم
    المصدر وكتب ذاكرة جديدة (False). المصدر الممرر اختياريًا يوفر
    إعادة قراءة الملف عند الترجمة. أي ذاكرة تالفة تُتجاهل بأمان.
    """
    cpath = cache_path_for(src_path)
    if os.path.exists(cpath):
        try:
            with open(cpath, 'rb') as f:
                payload = pickle.load(f)
            if _is_fresh(payload, src_path):
                return payload[4], True
        except Exception:
            pass                       # ذاكرة تالفة/قديمة — إعادة الترجمة
    from .lexer import Lexer
    from .parser import Parser
    if source is None:
        with open(src_path, encoding='utf-8-sig') as f:
            source = f.read()
    tree = Parser(Lexer(source).tokenize()).parse()
    try:
        write_cache(tree, src_path)
    except OSError:
        pass                           # فشل التخزين لا يمنع التشغيل
    return tree, False


def compile_file(src_path):
    """يترجم ملفًا إلى كود وسيط ويكتب ذاكرته دون تنفيذ — يعيد مسارها."""
    from .lexer import Lexer
    from .parser import Parser
    with open(src_path, encoding='utf-8-sig') as f:
        source = f.read()
    tree = Parser(Lexer(source).tokenize()).parse()
    return write_cache(tree, src_path)
