# -*- coding: utf-8 -*-
"""اختبارات المنقّح التفاعلي (الإصدار 1.35 — أفق التمكين).

ثلاث طبقات كما البنية نفسها:
  ١. المحرك مع واجهة مجدولة (ScriptedFrontend) — دلالات التوقف والأوامر
  ٢. سطر الأوامر العربي --نقح عبر subprocess كما يفعله المستخدم تمامًا
  ٣. بروتوكول DAP عبر subprocess بمحادثات مؤطرة حقيقية
(المعيار: معيار إغلاق أفق ١ — نقطة توقف وخطوة وفحص إطار عبر سطر
الأوامر وبروتوكول المحررات مع اختباراتها)
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARABI = os.path.join(ROOT, 'arabi.py')
sys.path.insert(0, ROOT)

from arabi_lang.debugger import (Debugger, DebugQuit, ScriptedFrontend,
                                 RESUME_CONTINUE, RESUME_FINISH,
                                 RESUME_NEXT, RESUME_STEP)
from arabi_lang.interpreter import Interpreter
from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser

PROGRAM = '''دالة احسب(ن):
    مجموع = 0
    لكل م في [1، 2، 3]:
        مجموع = مجموع + م
    أعد مجموع
النتيجة = احسب(5)
اطبع("النتيجة:"، النتيجة)
'''


def _parse(source):
    return Parser(Lexer(source).tokenize()).parse()


class DebuggerEngineTestCase(unittest.TestCase):
    """الطبقة ١: المحرك بلا عمليات خارجية — سريع وحاسم."""

    def _run(self, source, actions):
        tree = _parse(source)
        frontend = ScriptedFrontend(actions)
        interpreter = Interpreter(script_dir=ROOT, use_bytecode=False)
        debugger, last = __import__('arabi_lang.debugger',
                                    fromlist=['debug_program']
                                    ).debug_program(
            interpreter, tree, source, 'اختبار.عربي', frontend)
        return debugger, frontend, last

    # ---------- عقد التركيب ----------

    def test_attach_forces_tree_walker(self):
        """قرار د٣: ركوب المنقّح يعطل الدولاب."""
        debugger = Debugger(PROGRAM)
        interpreter = Interpreter(script_dir=ROOT)
        self.assertTrue(interpreter.use_vm)
        debugger.attach(interpreter)
        self.assertFalse(interpreter.use_vm)
        self.assertIs(interpreter.debug_hook, debugger)

    def test_attach_snapshots_builtin_names(self):
        """«عالمي» تعرض زيادات المستخدم لا المدمجات."""
        debugger, frontend, _ = self._run(
            'س = 1\nاطبع(س)\n', [(RESUME_CONTINUE,), (RESUME_CONTINUE,)])
        names = [n for n, _v in debugger.global_variables()]
        self.assertIn('س', names)
        self.assertNotIn('اطبع', names)

    # ---------- التوقف على البداية والخطوات ----------

    def test_entry_stop_and_step_lines(self):
        """توقف البداية على أول جملة، والخطوة تمر بكل جملة بالترتيب."""
        actions = [(RESUME_STEP,)] * 20
        debugger, frontend, _ = self._run(PROGRAM, actions)
        lines = [s['line'] for s in frontend.snapshots]
        # الجملة الأولى تعريف الدالة (سطر ١) ثم الاستدعاء (سطر ٦)
        self.assertEqual(lines[0], 1)
        self.assertEqual(lines[1], 6)
        # داخل الدالة: سطر ٢ ثم ٣ ثم جسم لكل (٤)
        self.assertEqual(lines[2], 2)
        self.assertEqual(lines[3], 3)
        self.assertIn(4, lines)
        # سبب أول توقف: البداية
        self.assertEqual(frontend.snapshots[0]['reason'], 'entry')

    def test_step_into_function_frame(self):
        """الخطوة تدخل الدالة — والإطار الأعمق يظهر في «أين»."""
        actions = [(RESUME_STEP,), (RESUME_STEP,), ('أين',),
                   (RESUME_CONTINUE,)]
        debugger, frontend, _ = self._run(PROGRAM, actions)
        stack_report = frontend.reports[0]
        self.assertIn('احسب', stack_report)
        self.assertIn('البرنامج', stack_report)
        self.assertIn('استدعاء من السطر 6', stack_report)

    def test_next_skips_function_body(self):
        """«تالية» فوق استدعاء دالة — تهبط للجملة التالية لا لأجسامها."""
        source = '''دالة ثقيلة():
    س = 1
    أعد س
أ = ثقيلة()
ب = ثقيلة()
اطبع(أ + ب)
'''
        actions = [(RESUME_STEP,), (RESUME_NEXT,), (RESUME_NEXT,),
                   (RESUME_NEXT,)]
        _, frontend, _ = self._run(source, actions)
        lines = [s['line'] for s in frontend.snapshots]
        # سطر ١ (التعريف) ثم ٤ ثم ٥ ثم ٦ — بلا سطري ٢ و٣
        self.assertEqual(lines, [1, 4, 5, 6])

    def test_finish_exits_function(self):
        """«من_الدالة» يخرج إلى المستدعي."""
        actions = [(RESUME_STEP,), (RESUME_STEP,), ('من_الدالة',)]
        _, frontend, _ = self._run(PROGRAM, actions)
        lines = [s['line'] for s in frontend.snapshots]
        # بعد الخروج: الجملة التالية بعد الاستدعاء = السطر ٧
        self.assertEqual(lines[-1], 7)

    # ---------- نقاط التوقف ----------

    def test_breakpoint_hits_and_reason(self):
        actions = [('توقف_سطر', 4), (RESUME_CONTINUE,), ('اطبع', 'م'),
                   (RESUME_CONTINUE,), ('اطبع', 'م'), (RESUME_CONTINUE,),
                   ('اطبع', 'م')]
        debugger, frontend, _ = self._run(PROGRAM, actions)
        lines = [s['line'] for s in frontend.snapshots]
        # ثلاث توقفات على سطر ٤ (دورات الحلقة) — سببها نقطة توقف
        bp_lines = [s['line'] for s in frontend.snapshots
                    if s['reason'] == 'breakpoint']
        self.assertEqual(bp_lines, [4, 4, 4])
        # قيم م في الدورات الثلاث
        values = [r for r in frontend.reports if r.isdigit()]
        self.assertEqual(values, ['1', '2', '3'])

    def test_breakpoint_verified_against_ast(self):
        """نقطة على سطر بلا جملة تنبّه بأنها لن تُوقف."""
        actions = [('توقف_سطر', 99), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run('اطبع(1)\n', actions)
        self.assertIn('تنبيه', frontend.reports[0])
        actions = [('توقف_سطر', 1), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run('اطبع(1)\n', actions)
        self.assertIn('فعّالة', frontend.reports[0])

    def test_func_breakpoint(self):
        """توقف عند دخول الدالة بالاسم."""
        actions = [('توقف_دالة', 'احسب'), (RESUME_CONTINUE,),
                   ('أين',), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run(PROGRAM, actions)
        hit = [s for s in frontend.snapshots
               if s['reason'] == 'function breakpoint']
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]['line'], 2)
        self.assertIn('احسب', frontend.reports[0])

    def test_remove_breakpoints(self):
        actions = [('توقف_سطر', 4), ('احذف_سطر', 4), ('نقاط',),
                   ('توقف_دالة', 'احسب'), ('احذف_دالة', 'احسب'),
                   ('نقاط',), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run(PROGRAM, actions)
        # التقارير: إضافة، حذف، نقاط، توقف دالة، حذف دالة، نقاط
        self.assertIn('فعّالة', frontend.reports[0])
        self.assertIn('حُذفت', frontend.reports[1])
        self.assertIn('لا نقاط توقف', frontend.reports[2])
        self.assertIn('حُذف توقف', frontend.reports[4])
        self.assertIn('لا نقاط توقف', frontend.reports[5])

    # ---------- فحص الأُطر والمتغيرات ----------

    def test_variables_in_frame(self):
        actions = [('توقف_سطر', 4), (RESUME_CONTINUE,), ('متغيرات',),
                   (RESUME_CONTINUE,)]
        _, frontend, _ = self._run(PROGRAM, actions)
        report = frontend.reports[1]      # بعد تقرير إضافة النقطة
        self.assertIn('مجموع', report)
        self.assertIn('م', report)
        self.assertIn('ن', report)

    def test_variables_at_top_level_shows_user_globals(self):
        """التوقف في المستوى العلوي يعرض متغيرات المستخدم."""
        source = 'س = 7\nاطبع(س)\n'
        actions = [(RESUME_STEP,), ('متغيرات',), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run(source, actions)
        self.assertIn('س = 7', frontend.reports[0])
        self.assertNotIn('اطبع', frontend.reports[0])

    def test_evaluate_expression_in_frame(self):
        actions = [('توقف_سطر', 4), (RESUME_CONTINUE,),
                   ('اطبع', 'مجموع + م * 10'), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run(PROGRAM, actions)
        # مجموع=0 وم=1 في أول دورة: 0 + 1*10 = 10
        self.assertEqual(frontend.reports[1], '10')

    def test_evaluate_rejects_statements(self):
        """«اطبع» يقبل تعبيرًا فقط — لا إسناد ولا جمل."""
        actions = [('توقف_سطر', 4), (RESUME_CONTINUE,),
                   ('اطبع', 'مجموع = 5'), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run(PROGRAM, actions)
        self.assertIn('تعبيرًا واحدًا فقط', frontend.reports[1])

    def test_evaluate_error_message(self):
        actions = [('توقف_سطر', 4), (RESUME_CONTINUE,),
                   ('اطبع', 'غير_موجود + 1'), (RESUME_CONTINUE,)]
        _, frontend, _ = self._run(PROGRAM, actions)
        self.assertIn('خطأ', frontend.reports[1])
        self.assertIn('غير_موجود', frontend.reports[1])

    # ---------- الإنهاء والحدود ----------

    def test_quit_raises_debug_quit(self):
        actions = [('إنهاء',)]
        with self.assertRaises(DebugQuit):
            self._run(PROGRAM, actions)

    def test_generator_body_not_stopped(self):
        """قرار د٤: أجسام المولدات بخيوط عامل — لا توقف فيها."""
        source = '''دالة توليد():
    أنتج 1
    أنتج 2
مجموع = 0
لكل قيمة في توليد():
    مجموع = مجموع + قيمة
اطبع(مجموع)
'''
        actions = [('توقف_سطر', 2), ('نقاط',), (RESUME_CONTINUE,)]
        _, frontend, _last = self._run(source, actions)
        # البرنامج اكتمل رغم نقطة التوقف داخل جسم المولد —
        # ولا توقف ثالث: جسم المولد بخيط عامل لا يُوقف (قرار د٤)
        self.assertIn('أسطر: 2', frontend.reports[1])
        # توقف واحد فقط في الجلسة كلها (البداية) — جسم المولد لم يوقف
        self.assertEqual(len(frontend.snapshots), 1)


class CliParseTestCase(unittest.TestCase):
    """محلل أوامر الواجهة النصية — بلا عمليات."""

    def _parse(self, line):
        import io
        from arabi_lang.debugger import CliFrontend
        out = io.StringIO()
        frontend = CliFrontend(stdin=io.StringIO(''),
                               stdout=out)
        return frontend.parse_command(line), out.getvalue()

    def test_resume_aliases(self):
        for line, expected in [('م', 'متابعة'), ('خ', 'خطوة'),
                               ('ت', 'تالية'), ('ن', 'من_الدالة'),
                               ('متابعة', 'متابعة'), ('c', 'متابعة')]:
            action, _ = self._parse(line)
            self.assertEqual(action[0], expected, line)

    def test_quit_aliases(self):
        for line in ('إنهاء', 'خروج', 'q', 'exit'):
            action, _ = self._parse(line)
            self.assertEqual(action[0], 'إنهاء')

    def test_breakpoint_commands(self):
        action, _ = self._parse('توقف عند 5')
        self.assertEqual(action, ('توقف_سطر', 5))
        action, _ = self._parse('توقف عند دالة احسب')
        self.assertEqual(action, ('توقف_دالة', 'احسب'))
        action, _ = self._parse('احذف 5')
        self.assertEqual(action, ('احذف_سطر', 5))
        action, _ = self._parse('احذف دالة احسب')
        self.assertEqual(action, ('احذف_دالة', 'احسب'))

    def test_malformed_commands_prompt_usage(self):
        action, out = self._parse('توقف')
        self.assertIsNone(action)
        self.assertIn('استخدام', out)
        action, out = self._parse('توقف عند بلا_رقم')
        self.assertIsNone(action)
        self.assertIn('استخدام', out)

    def test_unknown_command(self):
        action, out = self._parse('حلّق')
        self.assertIsNone(action)
        self.assertIn('غير معروف', out)

    def test_print_command_carries_expression(self):
        action, _ = self._parse('اطبع س + 2')
        self.assertEqual(action, ('اطبع', 'س + 2'))


class DebuggerCliTestCase(unittest.TestCase):
    """الطبقة ٢: سطر الأوامر من الخارج — كما يفعل المستخدم تمامًا."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='نقح_')
        cls.program = os.path.join(cls.tmp, 'دخان.عربي')
        with open(cls.program, 'w', encoding='utf-8') as f:
            f.write(PROGRAM)
        cls.bad = os.path.join(cls.tmp, 'مفسود.عربي')
        with open(cls.bad, 'w', encoding='utf-8') as f:
            f.write('اطبع(ناقص\n')

    def _run_session(self, commands, path, timeout=90):
        return subprocess.run(
            [sys.executable, ARABI, '--نقح', path],
            input=commands, capture_output=True, text=True,
            timeout=timeout, cwd=ROOT)

    def test_full_session_breakpoint_and_inspect(self):
        commands = ('توقف عند 4\nمتابعة\nاطبع م\nمتغيرات\nمتابعة\n'
                    'متابعة\nمتابعة\n')
        r = self._run_session(commands, self.program)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('منقّح عربي', r.stdout)
        self.assertIn('توقف (نقطة توقف) في السطر 4', r.stdout)
        self.assertIn('(منقّح)', r.stdout)
        # قيمة م في أول دورة + المتغيرات
        self.assertIn('1', r.stdout)
        self.assertIn('مجموع = 0', r.stdout)
        # البرنامج اكتمل في النهاية وطباعة البرنامج ظهرت
        self.assertIn('النتيجة: 6', r.stdout)
        self.assertIn('انتهى تنفيذ البرنامج', r.stdout)

    def test_eof_ends_session_cleanly(self):
        r = self._run_session('', self.program)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('انتهت الجلسة بطلب المستخدم', r.stdout)

    def test_quit_command(self):
        r = self._run_session('إنهاء\n', self.program)
        self.assertEqual(r.returncode, 0)
        self.assertIn('انتهت الجلسة بطلب المستخدم', r.stdout)

    def test_help_lists_commands(self):
        r = self._run_session('مساعدة\n', self.program)
        self.assertIn('متابعة', r.stdout)
        self.assertIn('توقف عند', r.stdout)
        self.assertIn('أين', r.stdout)

    def test_syntax_error_reports_arabic(self):
        r = self._run_session('', self.bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn('خطأ لفظي', r.stderr)
        self.assertIn('قوس', r.stderr)

    def test_missing_file(self):
        r = subprocess.run([sys.executable, ARABI, '--نقح',
                            'غير_موجود.عربي'],
                           capture_output=True, text=True, timeout=90,
                           cwd=ROOT)
        self.assertEqual(r.returncode, 1)
        self.assertIn('غير موجود', r.stderr)

    def test_option_requires_path(self):
        r = subprocess.run([sys.executable, ARABI, '--نقح'],
                           capture_output=True, text=True, timeout=90,
                           cwd=ROOT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("يحتاج مسار ملف", r.stderr)

    def test_help_flag_mentions_debugger(self):
        r = subprocess.run([sys.executable, ARABI, '--مساعدة'],
                           capture_output=True, text=True, timeout=90,
                           cwd=ROOT)
        self.assertIn('--نقح', r.stdout)
        self.assertIn('--منقح-بروتوكول', r.stdout)


class DapClient:
    """عميل DAP مصغّر للمحادثات الحقيقية عبر subprocess."""

    def __init__(self, program_path):
        self.proc = subprocess.Popen(
            [sys.executable, ARABI, '--منقح-بروتوكول'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        self.events = []
        self.responses = {}
        self._reader = threading.Thread(target=self._read_loop,
                                        daemon=True)
        self._reader.start()
        self._seq = 1
        self.program_path = program_path

    def send(self, command, arguments=None):
        request = {'seq': self._seq, 'type': 'request',
                   'command': command}
        if arguments is not None:
            request['arguments'] = arguments
        body = json.dumps(request, ensure_ascii=False).encode('utf-8')
        self.proc.stdin.write(
            f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii') + body)
        self.proc.stdin.flush()
        self._seq += 1
        return request['seq']

    def _read_loop(self):
        try:
            while True:
                message = self._read_one()
                if message is None:
                    return
                if message.get('type') == 'event':
                    self.events.append(message)
                    if message.get('event') == 'terminated':
                        return
                elif message.get('type') == 'response':
                    self.responses[message.get('request_seq')] = message
        except (OSError, ValueError):
            pass

    def _read_one(self):
        headers = {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                break
            key, _sep, value = line.decode('ascii').partition(':')
            headers[key.strip().lower()] = value.strip()
        length = int(headers['content-length'])
        body = self.proc.stdout.read(length)
        return json.loads(body.decode('utf-8'))

    def wait_event(self, name, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for event in self.events:
                if event.get('event') == name:
                    return event
            time.sleep(0.02)
        raise AssertionError(f'انتهت المهلة بلا حدث {name}')

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        # بلا communicate — stdin مغلق وflushه يرفع ValueError
        for stream in (self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except OSError:
                pass


class DebugAdapterTestCase(unittest.TestCase):
    """الطبقة ٣: بروتوكول DAP عبر قناة مؤطرة حقيقية."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dap_')
        cls.program = os.path.join(cls.tmp, 'برنامج.عربي')
        with open(cls.program, 'w', encoding='utf-8') as f:
            f.write(PROGRAM)

    def _session(self):
        client = DapClient(self.program)
        self.addCleanup(client.close)
        client.send('initialize', {'adapterID': 'اختبار'})
        client.wait_event('initialized')
        client.send('launch', {'program': self.program})
        return client

    def test_initialize_capabilities(self):
        client = self._session()
        response = client.responses[1]
        self.assertTrue(response['success'])
        self.assertTrue(response['body']['capabilities']
                        ['supportsConfigurationDoneRequest'])

    def test_launch_missing_program_fails(self):
        client = DapClient(self.program)
        self.addCleanup(client.close)
        client.send('initialize', {})
        client.wait_event('initialized')
        seq = client.send('launch', {'program': 'غائب.عربي'})
        deadline = time.time() + 15
        while time.time() < deadline and seq not in client.responses:
            time.sleep(0.02)
        response = client.responses.get(seq)
        self.assertIsNotNone(response)
        self.assertFalse(response['success'])
        self.assertIn('غير موجود', response['message'])

    def test_breakpoint_verification(self):
        client = self._session()
        seq = client.send('setBreakpoints', {
            'source': {'path': self.program}, 'lines': [4, 99]})
        deadline = time.time() + 15
        while time.time() < deadline and seq not in client.responses:
            time.sleep(0.02)
        breakpoints = client.responses[seq]['body']['breakpoints']
        self.assertTrue(breakpoints[0]['verified'])      # سطر ٤ جملة
        self.assertFalse(breakpoints[1]['verified'])     # سطر ٩٩ لا شيء

    def test_full_flow_breakpoint_frames_variables_output(self):
        client = self._session()
        client.send('setBreakpoints', {
            'source': {'path': self.program}, 'lines': [4]})
        client.send('configurationDone', {})
        stopped = client.wait_event('stopped')
        self.assertEqual(stopped['body']['reason'], 'breakpoint')

        seq = client.send('stackTrace', {'threadId': 1})
        deadline = time.time() + 15
        while time.time() < deadline and seq not in client.responses:
            time.sleep(0.02)
        frames = client.responses[seq]['body']['stackFrames']
        self.assertEqual(frames[0]['name'], 'احسب')
        self.assertEqual(frames[0]['line'], 4)
        self.assertEqual(frames[1]['name'], '<البرنامج>')
        self.assertEqual(frames[1]['line'], 6)   # سطر الاستدعاء

        seq = client.send('scopes', {'frameId': 0})
        deadline = time.time() + 15
        while time.time() < deadline and seq not in client.responses:
            time.sleep(0.02)
        scopes = client.responses[seq]['body']['scopes']
        self.assertEqual(scopes[0]['name'], 'المتغيرات المحلية')
        locals_ref = scopes[0]['variablesReference']

        seq = client.send('variables',
                          {'variablesReference': locals_ref})
        deadline = time.time() + 15
        while time.time() < deadline and seq not in client.responses:
            time.sleep(0.02)
        names = {v['name'] for v in
                 client.responses[seq]['body']['variables']}
        self.assertLessEqual({'مجموع', 'م', 'ن'}, names)

        # تالية → توقف جديد، ثم تصفير النقاط ومتابعة حتى النهاية
        client.send('next', {'threadId': 1})
        client.wait_event('stopped')
        client.send('setBreakpoints',
                    {'source': {'path': self.program}, 'lines': []})
        client.send('continue', {'threadId': 1})
        client.wait_event('exited')
        self.assertEqual(
            client.wait_event('terminated')['event'], 'terminated')

    def test_program_output_forwarded(self):
        client = self._session()
        client.send('setBreakpoints',
                    {'source': {'path': self.program}, 'lines': []})
        client.send('configurationDone', {})
        client.wait_event('terminated')
        outputs = ''.join(
            e['body']['output'] for e in client.events
            if e.get('event') == 'output'
            and e['body'].get('category') == 'stdout')
        self.assertIn('النتيجة: 6', outputs)

    def test_disconnect_terminates(self):
        client = self._session()
        client.send('setBreakpoints', {
            'source': {'path': self.program}, 'lines': [4]})
        client.send('configurationDone', {})
        client.wait_event('stopped')
        client.send('disconnect', {})
        deadline = time.time() + 15
        while time.time() < deadline:
            if client.proc.poll() is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(client.proc.poll())
        self.assertEqual(client.proc.returncode, 0)

    def test_unsupported_command_rejected(self):
        client = self._session()
        seq = client.send('restartFrame', {'frameId': 0})
        deadline = time.time() + 15
        while time.time() < deadline and seq not in client.responses:
            time.sleep(0.02)
        response = client.responses.get(seq)
        self.assertIsNotNone(response)
        self.assertFalse(response['success'])
        self.assertIn('غير مدعومة', response['message'])


if __name__ == '__main__':
    unittest.main()
