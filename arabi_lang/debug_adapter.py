# -*- coding: utf-8 -*-
"""مهايئ بروتوكول محول التنقيح (DAP) للغة عربي — الإصدار 1.35.

البروتوكول الذي تتكلم به المحررات (VS Code وأشباهها) لتنقيح البرامج —
فهو ما يقصده بند الخارطة «وLSP»: المحررات القائمة على خادم اللغة
تُنقّح عبر DAP. القناة: JSON بترويسات Content-Length على الدخول/
الخروج القياسيين (نفس تأطير خادم اللغة — إعادة استخدام مقصودة).

المدعوم في 1.35 (حدود موثقة في المواصفة):
  initialize / launch / setBreakpoints / configurationDone
  threads / stackTrace / scopes / variables
  continue / next / stepIn / stepOut / disconnect
  أحداث: initialized / output / stopped / terminated / exited
نقاط التوقف أسطر الملف الرئيسي فقط — والتنقيح الخيط المُنقَّح فقط.

التشغيل: عربي --منقح-بروتوكول   (البرنامج يأتي في طلب launch)
"""

import os
import sys
import threading

from . import lsp as _lsp
from .debugger import (Debugger, DebugQuit, RESUME_CONTINUE, RESUME_NEXT,
                       RESUME_STEP, RESUME_FINISH)
from .errors import ArabiError
from .interpreter import Interpreter
from .lexer import Lexer
from .parser import Parser

THREAD_ID = 1
# ترميز مراجع المتغيرات: ٢ = عالمي المستخدم، ١٠٠٠+رقم_الإطار = محلي
GLOBAL_REF = 2
LOCAL_REF_BASE = 1000

_STOP_EVENT_REASONS = {
    'entry': 'entry',
    'breakpoint': 'breakpoint',
    'function breakpoint': 'function breakpoint',
    'step': 'step',
}


class _OutputCollector:
    """يجمع مخرجات البرنامج ويحولها أحداث output — قناة DAP لا تُلوث."""

    def __init__(self, adapter, category):
        self._adapter = adapter
        self._category = category
        self._lock = threading.Lock()

    def write(self, text):
        with self._lock:
            if text:
                self._adapter.send_output(self._category, text)
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False

    def writable(self):
        return True


class DapFrontend:
    """واجهة المحرك من جهة DAP — التوقف ينتظر أمر الاستئناف من العميل."""

    def __init__(self, adapter):
        self.adapter = adapter
        self._gate = threading.Event()
        self._action = (RESUME_CONTINUE,)

    def report(self, text):
        self.adapter.send_output('console', text + '\n')

    def pause(self, state, initial=True):
        # حدث stopped مرة واحدة لكل توقف — لا تكرار مع أوامر الفحص
        # (العميل يسأل بنفسه stackTrace/variables بعد الحدث)
        if initial:
            self.adapter.on_paused(state)
        self._gate.wait()
        action = self._action
        self._gate.clear()
        return action

    def resume_with(self, action):
        self._action = action
        self._gate.set()


class DebugAdapter:
    """حلقة البروتوكول: يقرأ الطلبات، يجيب، ويدفع الأحداث."""

    def __init__(self, input_stream=None, output_stream=None):
        import io
        self.input = input_stream if input_stream is not None \
            else sys.stdin.buffer
        self.output = output_stream if output_stream is not None \
            else sys.stdout.buffer
        self._seq = 1
        self._send_lock = threading.Lock()
        self.frontend = DapFrontend(self)
        self.debugger = None
        self.tree = None
        self.launch_args = {}
        self.started = False
        self.exit_code = 0
        self._real_stdout = None
        self._real_stderr = None

    # ---------- الإرسال ----------

    def _send(self, message):
        with self._send_lock:
            message['seq'] = self._seq
            self._seq += 1
            _lsp.write_message(self.output, message)

    def reply(self, request, body=None, success=True, message=None):
        response = {'type': 'response', 'request_seq': request.get('seq'),
                    'success': success, 'command': request.get('command')}
        if message:
            response['message'] = message
        if body is not None:
            response['body'] = body
        self._send(response)

    def event(self, name, body=None):
        evt = {'type': 'event', 'event': name}
        if body is not None:
            evt['body'] = body
        self._send(evt)

    def send_output(self, category, text):
        self.event('output', {'category': category, 'output': text})

    # ---------- الحلقة ----------

    def run(self):
        while True:
            request = _lsp.read_message(self.input)
            if request is None:
                break               # العميل أغلق القناة
            if not isinstance(request, dict) or 'command' not in request:
                continue
            if not self._dispatch(request):
                break

    def _dispatch(self, request):
        """يعالج طلبًا — يعيد False عند طلب إغلاق العملية."""
        command = request.get('command')
        args = request.get('arguments') or {}
        handler = getattr(self, 'on_' + command, None)
        if handler is None:
            self.reply(request, success=False,
                       message=f'طريقة غير مدعومة: {command}')
            return True
        return handler(request, args) is not False

    # ---------- الطلبات ----------

    def on_initialize(self, request, _args):
        self.reply(request, {
            'capabilities': {
                'supportsConfigurationDoneRequest': True,
                'supportsSetBreakpointsRequest': True,
                'supportsTerminateRequest': False,
                'supportTerminateDebuggee': False,
                'supportsStepBack': False,
                'supportsRestartRequest': False,
            },
        })
        self.event('initialized', {})
        return True

    def on_launch(self, request, args):
        path = args.get('program')
        if not path or not os.path.isfile(path):
            self.reply(request, success=False,
                       message=f"البرنامج غير موجود: {path}")
            return False            # بلا برنامج لا جلسة — نغلق
        try:
            with open(path, encoding='utf-8-sig') as f:
                source = f.read()
            self.tree = Parser(Lexer(source).tokenize()).parse()
        except (OSError, ArabiError) as exc:
            self.reply(request, success=False,
                       message=f'تعذر تحميل البرنامج: {exc}')
            return False
        self.launch_args = args
        self.debugger = Debugger(source, filename=os.path.abspath(path))
        self.debugger.frontend = self.frontend
        self.debugger._walk_lines(self.tree)
        if not args.get('stopOnEntry'):
            # بلا توقف على البداية: أول توقف يكون نقطة توقف فعلًا
            self.debugger._entry_stop = False
            self.debugger._mode = RESUME_CONTINUE
        self.reply(request, {})
        return True

    def on_setBreakpoints(self, request, args):
        lines = args.get('lines') or []
        # استبدال كامل لنقاط الملف الواحد (حد 1.35 الموثق)
        if self.debugger is not None:
            self.debugger.breakpoints = set()
            for line in lines:
                self.debugger.add_breakpoint(int(line))
        verified = bool(self.debugger is not None
                        and self.debugger.ast_lines)
        body = {'breakpoints': [
            {'verified': bool(self.debugger is not None
                              and int(line) in self.debugger.ast_lines),
             'line': int(line)}
            for line in lines]}
        self.reply(request, body)
        return True

    def on_configurationDone(self, request, _args):
        self.reply(request, {})
        worker = threading.Thread(target=self._run_program, daemon=True,
                                  name='منقّح-التنفيذ')
        worker.start()
        return True

    def on_threads(self, request, _args):
        self.reply(request, {'threads': [
            {'id': THREAD_ID, 'name': 'الخيط الرئيسي'}]})
        return True

    def on_stackTrace(self, request, args):
        if args.get('threadId') != THREAD_ID or self.debugger is None:
            self.reply(request, {'stackFrames': [], 'totalFrames': 0})
            return True
        dbg = self.debugger
        source = {'name': os.path.basename(dbg.filename),
                  'path': dbg.filename}
        total = len(dbg.frame_stack)
        frames = []
        # الإطار صفر = أعمق إطار (الجملة الحالية)، ثم السلسلة الصاعدة
        # نحو المستدعي — سطر كل إطار صاعد هو سطر الاستدعاء المخزون في
        # إطار المُستدَعَى (ما لا نتتبعه: سطر «التالية» للمستدعي)
        for frame_id in range(total + 1):
            if frame_id == 0:
                line = None
                if dbg._current_node is not None:
                    line = getattr(dbg._current_node, 'line', None)
                name = (dbg.frame_stack[-1][0] if total else '<البرنامج>')
            else:
                caller_index = total - 1 - frame_id
                line = dbg.frame_stack[total - frame_id][2]
                if caller_index >= 0:
                    name = dbg.frame_stack[caller_index][0]
                else:
                    name = '<البرنامج>'
            frames.append({
                'id': frame_id,
                'name': name,
                'source': source,
                'line': line or 1,
                'column': 1,
            })
        self.reply(request, {'stackFrames': frames,
                             'totalFrames': len(frames)})
        return True

    def on_scopes(self, request, args):
        frame_id = args.get('frameId', 0)
        self.reply(request, {'scopes': [
            {'name': 'المتغيرات المحلية',
             'variablesReference': LOCAL_REF_BASE + frame_id,
             'expensive': False},
            {'name': 'عالمي (المستخدم)',
             'variablesReference': GLOBAL_REF,
             'expensive': False},
        ]})
        return True

    def on_variables(self, request, args):
        reference = args.get('variablesReference', 0)
        pairs = []
        if self.debugger is None:
            self.reply(request, {'variables': []})
            return True
        if reference == GLOBAL_REF:
            pairs = self.debugger.global_variables()
        elif reference >= LOCAL_REF_BASE:
            frame_id = reference - LOCAL_REF_BASE
            env = self._env_for_frame(frame_id)
            if env is not None:
                pairs = self.debugger.variables_in_scope(env)
        self.reply(request, {'variables': [
            {'name': name, 'value': value, 'variablesReference': 0}
            for name, value in pairs]})
        return True

    def _env_for_frame(self, frame_id):
        dbg = self.debugger
        total = len(dbg.frame_stack)
        if frame_id == 0:
            return dbg._current_env
        # الإطار ١ = مستدعي الإطار الأعمق — بيئته بيئة دخوله
        caller_index = total - 1 - frame_id
        if caller_index >= 0:
            return dbg.frame_stack[caller_index][1]
        return dbg.interp.globals

    def on_continue(self, request, _args):
        self.reply(request, {'allThreadsContinued': True})
        self.frontend.resume_with((RESUME_CONTINUE,))
        return True

    def on_next(self, request, _args):
        self.reply(request, {})
        self.frontend.resume_with((RESUME_NEXT,))
        return True

    def on_stepIn(self, request, _args):
        self.reply(request, {})
        self.frontend.resume_with((RESUME_STEP,))
        return True

    def on_stepOut(self, request, _args):
        self.reply(request, {})
        self.frontend.resume_with((RESUME_FINISH,))
        return True

    def on_disconnect(self, request, _args):
        self.reply(request, {})
        if self.debugger is not None:
            self.debugger._quit = True
        self.frontend.resume_with(('إنهاء',))
        return False             # أغلق العملية بعد الرد

    # ---------- التنفيذ والتحكم ----------

    def on_paused(self, state):
        """يستدعى من الواجهة عند كل توقف — يرفع حدث stopped."""
        reason = _STOP_EVENT_REASONS.get(state.get('reason') or 'step',
                                         'step')
        self.event('stopped', {'reason': reason, 'threadId': THREAD_ID,
                               'allThreadsStopped': True})

    def _run_program(self):
        """خيط التنفيذ: يشغل البرنامج تحت المنقّح ويحوّل المخرجات."""
        self._real_stdout = sys.stdout
        self._real_stderr = sys.stderr
        sys.stdout = _OutputCollector(self, 'stdout')
        sys.stderr = _OutputCollector(self, 'stderr')
        exit_code = 0
        try:
            interpreter = Interpreter(
                script_dir=os.path.dirname(
                    os.path.abspath(self.debugger.filename)))
            self.debugger.attach(interpreter)
            interpreter.run(self.tree)
        except DebugQuit:
            exit_code = 0           # قطع بطلب المستخدم لا خطأ
        except ArabiError as exc:
            self.send_output('stderr', str(exc) + '\n')
            exit_code = 1
        except RecursionError:
            self.send_output('stderr', 'خطأ تشغيلي: تعاود عميق جدًا — '
                             'تحقق من شرط التوقف في دالتك\n')
            exit_code = 1
        finally:
            sys.stdout = self._real_stdout
            sys.stderr = self._real_stderr
        self.event('exited', {'exitCode': exit_code})
        self.event('terminated', {})
        self.exit_code = exit_code


def main():
    """نقطة دخول المهايئ: عربي --منقح-بروتوكول"""
    DebugAdapter().run()


if __name__ == '__main__':
    main()
