# -*- coding: utf-8 -*-
"""خادم لغة عربي — بروتوكول خادم اللغة (LSP) عبر القنوات القياسية.

يُشغَّل من سطر الأوامر:  python arabi.py --لغة

يتواصل عبر stdin/stdout بصيغة JSON-RPC 2.0 كما يتطلب مواصفة LSP،
فيوفر للمحررات (VS Code وغيرها):

- تشخيص لحظي: أخطاء الصياغة وتحذيرات الفاحص (publishDiagnostics)
- الإكمال التلقائي: كلمات محجوزة، جاهزات، أعضاء الوحدات والأصناف،
  أسماء معرفة في الملف، ومقتطفات جاهزة
- تلميح عند التعليق: تواقيع الدوال وتوثيقها وأعضاء الوحدات
- رموز المستند: الدوال والأصناف والواجهات والتعدادات والمتغيرات
- الانتقال إلى التعريف داخل الملف نفسه

هذا الملف مستقل عن بقية المفسر عمدًا: كل أدوات التحليل تُستدعى
من lexer وparser وtools دون تشغيل أي كود للمستخدم (أمان كامل).
"""

import json
import sys

from . import tools
from .errors import ArabiError
from .interpreter import Interpreter, BUILTIN_MODULES
from .lexer import Lexer
from .nodes import (Assign, AugAssign, Call, ClassDef, EnumDef, FuncDef,
                    Import, InterfaceDef, Name, PropertyDef)
from .parser import Parser

# ================== الديباجة ==================

# إصدار الخادم = إصدار اللغة نفسها — كان ثابتًا يدويًا قديمًا يضلل
# تكاملات المحررات (تقرير التدقيق م18)
try:
    from . import __version__ as VERSION
except Exception:                          # حارس نظري — لا يحدث عمليًا
    VERSION = '1.0.0'

# سقف حجم رسالة LSP الواحدة — رأس Content-Length مزور أو معطوب
# لا يبتلع ذاكرة غير محدودة (تقرير التدقيق م12-4)
MAX_MESSAGE_BYTES = 64 * 1024 * 1024

# رموز LSP للأنواع (SymbolKind)
KIND_FUNCTION = 12
KIND_CLASS = 5
KIND_METHOD = 6
KIND_INTERFACE = 11
KIND_ENUM = 10
KIND_ENUM_MEMBER = 22
KIND_VARIABLE = 13
KIND_MODULE = 2
KIND_PROPERTY = 7

# ================== الطبقة الناقلة (JSON-RPC) ==================


def read_message(stream):
    """يقرأ رسالة JSON-RPC واحدة ويعيدها كقاموس — أو None عند انتهاء الدفق."""
    headers = {}
    while True:
        raw = stream.readline()
        if not raw:
            return None
        raw = raw.strip()
        if not raw:
            break                     # سطر فارغ: نهاية الترويسات
        text = raw.decode('ascii', errors='replace')
        key, _, value = text.partition(':')
        headers[key.strip().lower()] = value.strip()
    try:
        length = int(headers.get('content-length', '0'))
    except ValueError:
        return None
    if length <= 0 or length > MAX_MESSAGE_BYTES:
        return None              # مرفوض: صفر أو رأس مزور بحجم وحشي
    body = stream.read(length)
    if not body:
        return None
    try:
        return json.loads(body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {}


def write_message(stream, message):
    """يكتب رسالة JSON-RPC واحدة بترويسة Content-Length المطلوبة."""
    body = json.dumps(message, ensure_ascii=False).encode('utf-8')
    header = f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii')
    try:
        stream.write(header)
        stream.write(body)
        stream.flush()
    except (OSError, ValueError):
        pass                      # المحرر أغلق القناة — نتجاهل بهدوء


# ================== أدوات المواقع ==================


def line_range(lines, line_idx):
    """مدى يغطي السطر كاملًا (فهارس LSP صفرية)."""
    end_char = 0
    if 0 <= line_idx < len(lines):
        end_char = len(lines[line_idx])
    return {
        'start': {'line': line_idx, 'character': 0},
        'end': {'line': line_idx, 'character': end_char},
    }


def word_range(lines, line_idx, start_char, word):
    """مدى يغطي كلمة محددة داخل سطر."""
    end_char = start_char + len(word)
    if 0 <= line_idx < len(lines):
        end_char = min(end_char, len(lines[line_idx]))
    return {
        'start': {'line': line_idx, 'character': start_char},
        'end': {'line': line_idx, 'character': end_char},
    }


def word_at(lines, line_idx, char_idx):
    """يستخرج الكلمة (معرفًا عربيًا أو لاتينيًا) عند موضع المؤشر.

    يعيد (الكلمة، فهرس بدايتها) أو (None، 0) إن لم توجد كلمة.
    """
    if not 0 <= line_idx < len(lines):
        return None, 0
    text = lines[line_idx]
    if char_idx > len(text):
        char_idx = len(text)
    def _is_word(ch):
        # حرف/رقم أو شرطة سفلية أو حركة تشكيل عربية
        return ch.isalnum() or ch == '_' or '\u064B' <= ch <= '\u0652'
    start = char_idx
    while start > 0 and _is_word(text[start - 1]):
        start -= 1
    end = char_idx
    while end < len(text) and _is_word(text[end]):
        end += 1
    if start == end:
        return None, 0
    return text[start:end], start


def parse_source(text, lenient=False):
    """يحلل المصدر ويعيد (الشجرة أو None، قائمة مشكلات).

    المشكلات قائمة (السطر، النوع، الرسالة) كما يعيدها الفاحص.
    """
    try:
        tokens = Lexer(text, lenient_indent=lenient).tokenize()
        tree = Parser(tokens).parse()
    except ArabiError as exc:
        return None, [(exc.line or 1, 'خطأ', exc.message)]
    return tree, tools._Linter(tree, tools._builtin_names()).run()


# ================== خادم اللغة ==================


class ArabiLanguageServer:
    """خادم LSP يخدم مستندات .عربي مفتوحة في المحرر.

    لا يشغل كود المستخدم أبدًا: التحليل والفحص فقط.
    documents: uri ← {'text': النص، 'version': الإصدار}
    """

    def __init__(self, input_stream=None, output_stream=None):
        self.input = input_stream if input_stream is not None \
            else sys.stdin.buffer
        self.output = output_stream if output_stream is not None \
            else sys.stdout.buffer
        self.documents = {}
        self.shutdown_asked = False
        self.requests = {
            'initialize': self.on_initialize,
            'shutdown': self.on_shutdown,
            'textDocument/completion': self.on_completion,
            'textDocument/hover': self.on_hover,
            'textDocument/definition': self.on_definition,
            'textDocument/documentSymbol': self.on_document_symbol,
        }
        self.notifications = {
            'initialized': self.on_initialized,
            'textDocument/didOpen': self.on_did_open,
            'textDocument/didChange': self.on_did_change,
            'textDocument/didClose': self.on_did_close,
        }

    # ---------- حلقة التشغيل ----------

    def run(self):
        """يقرأ الرسائل ويوزعها حتى طلب الخروج أو انتهاء الدفق."""
        while True:
            message = read_message(self.input)
            if message is None:
                break
            method = message.get('method', '')
            if 'id' in message:
                # بعد 'shutdown' لا يُجاب إلا 'exit' بروتوكول LSP —
                # كان الراية تُضبط ولا تُقرأ فظل الخادم يخدم الطلبات
                # (تقرير التدقيق م15-28)
                if self.shutdown_asked and method != 'exit':
                    self._error(message['id'], -32600,
                                'الخادم أُوقف بـ shutdown — أرسل exit للإنهاء')
                elif method == 'exit':
                    pass                    # الخروج يُعالج بعد الحلقة
                else:
                    handler = self.requests.get(method)
                    if handler is not None:
                        try:
                            result = handler(message.get('params') or {})
                            self._reply(message['id'], result)
                        except RecursionError:
                            # التعاود العميق: رسالة عربية واضحة لا أثر خام (1.23)
                            self._error(message['id'], -32603,
                                        'تعاود عميق جدًا في الطلب — بسّط '
                                        'التعبير أو قسّمه')
                        except Exception as exc:            # حماية الخادم
                            self._error(message['id'], -32603, str(exc))
                    else:
                        self._error(message['id'], -32601,
                                    f'طريقة غير مدعومة: {method}')
            else:
                handler = self.notifications.get(method)
                if handler is not None:
                    try:
                        handler(message.get('params') or {})
                    except Exception:                   # حماية الخادم
                        pass
            if method == 'exit':
                break

    def _reply(self, msg_id, result):
        write_message(self.output, {'jsonrpc': '2.0', 'id': msg_id,
                                    'result': result})

    def _error(self, msg_id, code, message):
        write_message(self.output, {
            'jsonrpc': '2.0', 'id': msg_id,
            'error': {'code': code, 'message': message}})

    def _notify(self, method, params):
        write_message(self.output, {'jsonrpc': '2.0', 'method': method,
                                    'params': params})

    # ---------- الطلبات الأساسية ----------

    def on_initialize(self, _params):
        """يصرّح بقدرات الخادم للمحرر."""
        return {
            'capabilities': {
                'textDocumentSync': 1,          # مزامنة كاملة للمستند
                'completionProvider': {
                    'triggerCharacters': ['.'],
                    'resolveProvider': False,
                },
                'hoverProvider': True,
                'definitionProvider': True,
                'documentSymbolProvider': True,
            },
            'serverInfo': {'name': 'خادم لغة عربي', 'version': VERSION},
        }

    def on_shutdown(self, _params):
        self.shutdown_asked = True
        return None

    def on_initialized(self, _params):
        pass

    # ---------- المستندات والتشخيص ----------

    def _doc_lines(self, uri):
        doc = self.documents.get(uri)
        if doc is None:
            return None
        return doc['text'].split('\n')

    def _publish(self, uri, diagnostics):
        self._notify('textDocument/publishDiagnostics',
                     {'uri': uri, 'diagnostics': diagnostics})

    def _diagnostics(self, text):
        """يحول مخرجات الفاحص إلى قائمة تشخيصات LSP."""
        _tree, issues = parse_source(text, lenient=True)
        result = []
        for line_no, kind, message in issues:
            severity = 1 if kind == 'خطأ' else 2     # 1 خطأ، 2 تحذير
            result.append({
                'range': line_range(text.split('\n'), max(0, line_no - 1)),
                'severity': severity,
                'source': 'عربي',
                'message': message,
            })
        return result

    def on_did_open(self, params):
        doc = params.get('textDocument') or {}
        uri = doc.get('uri')
        if not uri:
            return
        self.documents[uri] = {'text': doc.get('text') or '',
                               'version': doc.get('version', 0)}
        self._publish(uri, self._diagnostics(self.documents[uri]['text']))

    def on_did_change(self, params):
        doc = params.get('textDocument') or {}
        uri = doc.get('uri')
        if not uri:
            return
        changes = params.get('contentChanges') or []
        text = changes[-1].get('text') if changes else ''
        version = doc.get('version', 0)
        entry = self.documents.get(uri)
        if entry is None:
            self.documents[uri] = {'text': text, 'version': version}
        else:
            entry['text'] = text
            entry['version'] = version
        self._publish(uri, self._diagnostics(text))

    def on_did_close(self, params):
        uri = (params.get('textDocument') or {}).get('uri')
        if uri:
            self.documents.pop(uri, None)
            # إخلاء التشخيصات بعد الإغلاق
            self._publish(uri, [])

    # ---------- الإكمال التلقائي ----------

    def on_completion(self, params):
        uri = (params.get('textDocument') or {}).get('uri')
        position = params.get('position') or {}
        lines = self._doc_lines(uri)
        if lines is None:
            return []
        text = self.documents[uri]['text']
        line_idx = position.get('line', 0)
        char_idx = position.get('character', 0)
        items = self._completion_items(text, lines, line_idx, char_idx)
        return {'isIncomplete': False, 'items': items}

    def _completion_items(self, text, lines, line_idx, char_idx):
        """يبني قائمة الإكمال حسب السياق (بعد نقطة أو وضع عام)."""
        current = lines[line_idx] if 0 <= line_idx < len(lines) else ''
        before = current[:char_idx].rstrip()
        # سياق عضو: كائن. ← أعضاء الوحدة أو الصنف
        if before.endswith('.'):
            dot_idx = len(before) - 1
            owner_word, _start = word_at(lines, line_idx, dot_idx)
            return self._member_items(text, owner_word or '',
                                      line_idx, dot_idx)
        return self._default_items(text, line_idx)

    def _member_items(self, text, owner_word, line_idx=None, dot_idx=None):
        """إكمال أعضاء بعد النقطة: وحدة أو صنف أو متغير معروف صنفه."""
        if line_idx is not None and dot_idx is not None:
            text = self._repair_member_line(text, line_idx, dot_idx)
        members = self._module_members(owner_word)
        if members is None:
            members = self._class_members(text, owner_word)
        if members is None:
            # استدلال خفيف: الطالب = طالب(...) → أعضاء الصنف الطالب
            cls_name = self._infer_class_of(text, owner_word)
            if cls_name is not None:
                members = self._class_members(text, cls_name)
        if members is None:
            members = self._all_function_names(text)
        return [
            {'label': name, 'kind': KIND_FUNCTION, 'detail': 'عضو'}
            for name in sorted(members)
        ]

    @staticmethod
    def _repair_member_line(text, line_idx, dot_idx):
        """يصلح سطر الإكمال غير المكتمل ليقبل التحليل.

        يقص كل ما بعد الكائن قبل النقطة ويغلق الأقواس المفتوحة:
        'اطبع(ن.مس' → 'اطبع(ن)' — فينجو تحليل الملف أثناء الكتابة.
        """
        lines = text.split('\n')
        prefix = lines[line_idx][:dot_idx]
        closers = []
        openers = {'(': ')', '[': ']', '{': '}'}
        pairs = {')': '(', ']': '[', '}': '{'}
        for ch in prefix:
            if ch in openers:
                closers.append(ch)
            elif ch in ')]}' and closers and pairs[ch] == closers[-1]:
                closers.pop()
        lines[line_idx] = prefix + ''.join(
            openers[c] for c in reversed(closers))
        return '\n'.join(lines)

    def _infer_class_of(self, text, var_name):
        """يستدل صنف متغير من إسناده: الاسم = صنف(...) → 'صنف'.

        يفحص الإسنادات العليا قبل استعمال الدالة — بلا تشغيل أي كود.
        """
        tree, _issues = parse_source(text, lenient=True)
        if tree is None:
            return None
        for stmt in tree.statements:
            if not isinstance(stmt, Assign):
                continue
            targets = [t.name for t in stmt.targets if isinstance(t, Name)]
            if var_name not in targets:
                continue
            value = stmt.value
            if isinstance(value, Call) and isinstance(value.func, Name):
                return value.func.name
        return None

    def _module_members(self, name):
        """أعضاء وحدة قياسية بالاسم، أو None إن لم تكن وحدة."""
        env = builtin_globals()
        value = env.vars.get(name)
        if value is None and name == 'استثناء':
            return {'رسالة'}
        if not hasattr(value, 'members') or not hasattr(value, 'name'):
            return None
        return set(value.members.keys())

    def _class_members(self, text, name):
        """أعضاء صنف معرف في الملف نفسه (طرق وحقول)."""
        tree, _issues = parse_source(text, lenient=True)
        if tree is None:
            return None
        for stmt in tree.statements:
            if isinstance(stmt, ClassDef) and stmt.name == name:
                members = set()
                for member in stmt.body:
                    if isinstance(member, FuncDef):
                        members.add(member.name)
                    elif isinstance(member, Assign):
                        for target in member.targets:
                            if hasattr(target, 'name'):
                                members.add(target.name)
                return members
        return None

    def _file_definitions(self, tree):
        """يجمع الأسماء المعرفة في الملف: (الاسم، النوع، العقدة)."""
        found = []
        for stmt in tree.statements:
            if isinstance(stmt, (FuncDef, ClassDef, InterfaceDef, EnumDef)):
                kind = 'دالة' if isinstance(stmt, FuncDef) else 'صنف'
                found.append((stmt.name, kind, stmt))
            elif isinstance(stmt, Assign):
                for target in stmt.targets:
                    if hasattr(target, 'name'):
                        found.append((target.name, 'متغير', stmt))
            elif isinstance(stmt, AugAssign):
                if hasattr(stmt.target, 'name'):
                    found.append((stmt.target.name, 'متغير', stmt))
            elif isinstance(stmt, Import):
                if stmt.names is not None:
                    # صيغة من...استورد: الأسماء المستوردة فقط مرتبطة
                    for name in stmt.names:
                        found.append((name, 'اسم مستورد', stmt))
                elif stmt.bound_name:
                    found.append((stmt.bound_name, 'وحدة', stmt))
        return found

    def _find_definition(self, tree, word):
        """يبحث عن تعريف الاسم: عليا أو أعضاء أصناف.

        يعيد (العقدة، النوع، اسم الصنف المالك أو None) أو None.
        """
        for name, kind, node in self._file_definitions(tree):
            if name == word:
                return node, kind, None
        for stmt in tree.statements:
            if isinstance(stmt, ClassDef):
                for member in stmt.body:
                    if isinstance(member, (FuncDef, PropertyDef)) \
                            and member.name == word:
                        return member, 'طريقة', stmt.name
                    if isinstance(member, Assign):
                        for target in member.targets:
                            if hasattr(target, 'name') \
                                    and target.name == word:
                                return member, 'حقل', stmt.name
        return None

    def _all_function_names(self, text):
        """أسماء الدوال الجاهزة + دوال الملف (احتياط الإكمال بعد النقطة)."""
        names = set()
        for name, value in builtin_globals().vars.items():
            if value.__class__.__name__ in ('BuiltinFunc', 'ArabiFunc'):
                names.add(name)
        tree, _issues = parse_source(text, lenient=True)
        if tree is not None:
            for stmt in tree.statements:
                if isinstance(stmt, FuncDef):
                    names.add(stmt.name)
        return names

    def _default_items(self, text, line_idx):
        """الإكمال العام: محجوزات + جاهزات + أسماء الملف + مقتطفات."""
        items = []
        for word in KEYWORDS:
            items.append({'label': word, 'kind': 14, 'detail': 'كلمة محجوزة'})
        env = builtin_globals()
        for name, value in env.vars.items():
            items.append(self._builtin_item(name, value))
        items.append({'label': 'استثناء', 'kind': 7,
                      'detail': 'الصنف الأساسي للأخطاء المخصصة'})
        tree, _issues = parse_source(text, lenient=True)
        if tree is not None:
            for name, kind, _node in self._file_definitions(tree):
                items.append({'label': name, 'kind': KIND_VARIABLE,
                              'detail': f'معرف في الملف ({kind})'})
        for snippet in SNIPPETS:
            items.append(dict(snippet))
        return items

    def _builtin_item(self, name, value):
        """يبند إكمال لجاهزة مدمجة أو وحدة أو صنف."""
        cls = value.__class__.__name__
        if cls == 'BuiltinFunc' or cls == 'ArabiFunc':
            return {'label': name, 'kind': 3, 'detail': 'جاهزة مدمجة'}
        if cls == 'ModuleValue':
            return {'label': name, 'kind': 9, 'detail': 'وحدة قياسية'}
        if cls == 'ClassValue':
            return {'label': name, 'kind': 7, 'detail': 'صنف جاهز'}
        return {'label': name, 'kind': 6, 'detail': cls}

    # ---------- التلميح عند التعليق ----------

    def on_hover(self, params):
        uri = (params.get('textDocument') or {}).get('uri')
        position = params.get('position') or {}
        lines = self._doc_lines(uri)
        if lines is None:
            return None
        text = self.documents[uri]['text']
        word, _start = word_at(lines, position.get('line', 0),
                               position.get('character', 0))
        if not word:
            return None
        markdown = self._hover_markdown(text, word)
        if not markdown:
            return None
        return {
            'contents': {'kind': 'markdown', 'value': markdown},
            'range': word_range(lines, position.get('line', 0), 0, word),
        }

    def _hover_markdown(self, text, word):
        """يبند توثيق الاسم: جاهزة، وحدة، صنف، أو تعريف في الملف."""
        env = builtin_globals()
        value = env.vars.get(word)
        if value is not None and value.__class__.__name__ == 'ModuleValue':
            members = '، '.join(sorted(value.members.keys()))
            return f'**{word}** — وحدة قياسية\n\nالأعضاء: {members}'
        if value is not None and value.__class__.__name__ == 'ClassValue':
            return f'**{word}** — صنف جاهز في اللغة'
        if word == 'استثناء':
            return '**استثناء** — الصنف الأساسي للأخطاء المخصصة: ' \
                   'صنف خطائي من استثناء'
        tree, _issues = parse_source(text, lenient=True)
        if tree is None:
            return None
        hit = self._find_definition(tree, word)
        if hit is None:
            return None
        node, kind = hit[0], hit[1]
        if isinstance(node, FuncDef):
            return self._function_doc(node)
        if isinstance(node, ClassDef):
            return f'**{word}** — صنف معرف في الملف'
        if isinstance(node, InterfaceDef):
            return f'**{word}** — واجهة (عقد مجرد)'
        if isinstance(node, EnumDef):
            return f'**{word}** — تعداد'
        if isinstance(node, PropertyDef):
            return f'**{word}** — خاصية محسوبة'
        if kind == 'وحدة':
            return f'**{word}** — وحدة مستوردة'
        return f'**{word}** — {kind} معرف في الملف'

    def _function_doc(self, node):
        """توثيق دالة معرفة في الملف: التوقيع + الوسوم + التوثيق."""
        params = tools._render_params(node.params, node.rest)
        tags = []
        if node.is_generator:
            tags.append('مولد')
        if node.decorators:
            tags.append('مزخرف')
        ret = getattr(node, 'ret', None)
        ret_txt = f' → {ret.text}' if ret is not None else ''
        head = f'**{node.name}**({params}){ret_txt}'
        if tags:
            head += '  \n' + '، '.join(tags)
        doc = tools._docstring(node.body)
        if doc:
            head += f'\n\n{doc}'
        return head

    # ---------- رموز المستند ----------

    def on_document_symbol(self, params):
        uri = (params.get('textDocument') or {}).get('uri')
        lines = self._doc_lines(uri)
        if lines is None:
            return []
        text = self.documents[uri]['text']
        tree, _issues = parse_source(text, lenient=True)
        if tree is None:
            return []
        symbols = []
        for node in tree.statements:
            symbol = self._symbol_of(node, lines)
            if symbol is not None:
                symbols.append(symbol)
        return symbols

    def _symbol_of(self, node, lines):
        """يحول جملة عليا إلى رمز مستند (مع الأبناء للأصناف والتعدادات)."""
        line_idx = (node.line or 1) - 1
        name_range = self._name_range(lines, line_idx, self._symbol_name(node))
        if isinstance(node, FuncDef):
            return {'name': node.name, 'kind': KIND_FUNCTION,
                    'range': line_range(lines, line_idx),
                    'selectionRange': name_range}
        if isinstance(node, ClassDef):
            return {'name': node.name, 'kind': KIND_CLASS,
                    'range': line_range(lines, line_idx),
                    'selectionRange': name_range,
                    'children': self._class_symbols(node, lines)}
        if isinstance(node, InterfaceDef):
            return {'name': node.name, 'kind': KIND_INTERFACE,
                    'range': line_range(lines, line_idx),
                    'selectionRange': name_range}
        if isinstance(node, EnumDef):
            children = []
            for member_name, _value, member_line in node.members:
                idx = (member_line or node.line or 1) - 1
                children.append({
                    'name': member_name, 'kind': KIND_ENUM_MEMBER,
                    'range': line_range(lines, idx),
                    'selectionRange': self._name_range(
                        lines, idx, member_name)})
            return {'name': node.name, 'kind': KIND_ENUM,
                    'range': line_range(lines, line_idx),
                    'selectionRange': name_range, 'children': children}
        if isinstance(node, Import):
            title = node.bound_name or node.module or node.path or ''
            if not title:
                return None
            return {'name': title, 'kind': KIND_MODULE,
                    'range': line_range(lines, line_idx),
                    'selectionRange': self._name_range(lines, line_idx, title)}
        if isinstance(node, Assign) and len(node.targets) == 1 \
                and hasattr(node.targets[0], 'name'):
            return {'name': node.targets[0].name, 'kind': KIND_VARIABLE,
                    'range': line_range(lines, line_idx),
                    'selectionRange': name_range}
        return None

    def _class_symbols(self, node, lines):
        """رموز أعضاء الصنف: طرق وخصائص وحقول."""
        children = []
        base = (node.line or 1) - 1
        for member in node.body:
            if isinstance(member, FuncDef):
                idx = (member.line or base + 1) - 1
                children.append({
                    'name': member.name, 'kind': KIND_METHOD,
                    'range': line_range(lines, idx),
                    'selectionRange': self._name_range(
                        lines, idx, member.name)})
            elif isinstance(member, PropertyDef):
                idx = (member.line or base + 1) - 1
                children.append({
                    'name': member.name, 'kind': KIND_PROPERTY,
                    'range': line_range(lines, idx),
                    'selectionRange': self._name_range(
                        lines, idx, member.name)})
            elif isinstance(member, Assign):
                for target in member.targets:
                    if not hasattr(target, 'name'):
                        continue
                    idx = (member.line or base + 1) - 1
                    children.append({
                        'name': target.name, 'kind': KIND_VARIABLE,
                        'range': line_range(lines, idx),
                        'selectionRange': self._name_range(
                            lines, idx, target.name)})
        return children

    def _symbol_name(self, node):
        if hasattr(node, 'name'):
            return node.name or ''
        if isinstance(node, Import):
            return node.bound_name or node.module or node.path or ''
        return ''

    def _name_range(self, lines, line_idx, name):
        """يحدد موضع الاسم داخل سطره (أول ظهور)."""
        start = 0
        if name and 0 <= line_idx < len(lines):
            start = lines[line_idx].find(name)
            if start < 0:
                start = 0
        return word_range(lines, line_idx, start, name or ' ')

    # ---------- الانتقال إلى التعريف ----------

    def on_definition(self, params):
        uri = (params.get('textDocument') or {}).get('uri')
        position = params.get('position') or {}
        lines = self._doc_lines(uri)
        if lines is None:
            return None
        text = self.documents[uri]['text']
        word, _start = word_at(lines, position.get('line', 0),
                               position.get('character', 0))
        if not word:
            return None
        tree, _issues = parse_source(text, lenient=True)
        if tree is None:
            return None
        hit = self._find_definition(tree, word)
        if hit is None:
            return None
        node = hit[0]
        line_idx = (node.line or 1) - 1
        start = lines[line_idx].find(word) if 0 <= line_idx < len(lines) \
            else 0
        if start < 0:
            start = 0
        return {
            'uri': uri,
            'range': word_range(lines, line_idx, start, word),
        }


# ================== مساعدات على مستوى الوحدة ==================

_ENV_CACHE = None


def builtin_globals():
    """البيئة العالمية للجاهزات (محسوبة مرة واحدة — بلا تشغيل كود مستخدم)."""
    global _ENV_CACHE
    if _ENV_CACHE is None:
        _ENV_CACHE = Interpreter().globals
    return _ENV_CACHE


KEYWORDS = (
    'دالة', 'أعد', 'لو', 'وإلا إذا', 'وإلا', 'طالما', 'لكل', 'في', 'كسر',
    'استمر', 'صح', 'خطأ', 'ولا شيء', 'و', 'أو', 'ليس', 'جرب', 'باستثناء',
    'اخيرا', 'ارفع', 'استورد', 'تجاهل', 'صنف', 'هذا', 'الأصل', 'بدل',
    'حالة', 'افتراض', 'تعداد', 'خاصية', 'عالمي', 'تحقق', 'احذف', 'أنتج',
    'واجهة', 'طابق', 'غير ذلك',
    'غير متزامنة', 'انتظر',
)

SNIPPETS = [
    {'label': 'صنف', 'kind': 15,
     'insertText': 'صنف ${1:الاسم}:\n\t${2:الجسم}',
     'detail': 'مقتطف: تعريف صنف', 'insertTextFormat': 2},
    {'label': 'دالة', 'kind': 15,
     'insertText': 'دالة ${1:الاسم}(${2:المعاملات}):\n\t${3:الجسم}',
     'detail': 'مقتطف: تعريف دالة', 'insertTextFormat': 2},
    {'label': 'غير متزامنة دالة', 'kind': 15,
     'insertText': 'غير متزامنة دالة ${1:الاسم}(${2:المعاملات}):\n\t${3:الجسم}',
     'detail': 'مقتطف: دالة غير متزامنة (جديد في 1.15)', 'insertTextFormat': 2},
    {'label': 'لكل', 'kind': 15,
     'insertText': 'لكل ${1:عنصر} في ${2:التسلسل}:\n\t${3:الجسم}',
     'detail': 'مقتطف: حلقة لكل', 'insertTextFormat': 2},
    {'label': 'جرب', 'kind': 15,
     'insertText': 'جرب:\n\t${1:الجسم}\nباستثناء ${2:هـ}:\n\t${3:المعالجة}',
     'detail': 'مقتطف: جرب وباستثناء', 'insertTextFormat': 2},
    {'label': 'طابق', 'kind': 15,
     'insertText': 'طابق ${1:القيمة}:\nحالة ${2:النمط}:\n\t${3:الجسم}\n'
                   'غير ذلك:\n\t${4:الجسم}',
     'detail': 'مقتطف: مطابقة أنماط', 'insertTextFormat': 2},
]


def main():
    """نقطة تشغيل الخادم: يخدم القنوات القياسية حتى الإنهاء."""
    server = ArabiLanguageServer()
    server.run()


if __name__ == '__main__':
    main()
