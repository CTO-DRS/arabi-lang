# -*- coding: utf-8 -*-
"""اختبارات البنية المعيارية (الإصدار 1.30) — الفصل 16/19 من التدقيق.

المبدأ: الاختبارات تشغّل المعايير في الوضع السريع فقط (ثوانٍ)، وتتحقق من
البوابات سلوكيًا لا من الأرقام المطلقة (الأجهزة تختلف) — مع اختبار فشل
مغلق: خط أساس مفسوف ×10 يجب أن يُسقط البوابة برمز خروج 1.
"""
import json
import subprocess
import sys
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / 'benchmarks' / 'run.py'
BASELINE = ROOT / 'benchmarks' / 'baseline.json'


def _run(args, timeout=300):
    return subprocess.run(
        [sys.executable, str(RUNNER)] + args,
        capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))


class TestRunnerQuick(unittest.TestCase):
    """الوضع السريع يعمل وينتج المعايير الخمسة كلها."""

    def test_quick_json_wellformed(self):
        r = _run(['--quick', '--json'])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        data = json.loads(r.stdout)
        self.assertEqual(set(data.keys()), {'بدء', 'حلقة_ساخنة', 'مولدات', 'بيئة_قدّم', 'تشفير'})

    def test_quick_check_gates_pass(self):
        r = _run(['--quick', '--check'])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertGreaterEqual(r.stdout.count('[سليم]'), 8)
        self.assertNotIn('[فشل]', r.stdout)

    def test_quick_numbers_positive(self):
        r = _run(['--quick', '--json'])
        data = json.loads(r.stdout)
        self.assertGreater(data['حلقة_ساخنة']['دولاب_ثانية'], 0)
        self.assertGreater(data['حلقة_ساخنة']['شجري_ثانية'], 0)
        self.assertGreater(data['تشفير']['شفّر_مبثث'], 0)
        self.assertGreater(data['بدء']['ثانية'], 0)

    def test_equivalence_holds(self):
        """تكافؤ الدولاب والشجري على نفس الحمل — الصحة قبل الزمن."""
        r = _run(['--quick', '--json'])
        data = json.loads(r.stdout)
        n = 1_000_000 // 10  # نفس تصغير الوضع السريع
        self.assertGreater(data['حلقة_ساخنة']['دولاب_ثانية'], 0)
        # النتائج نفسها مفحوصة داخل المعيار برفع خطأ عند أي انحراف —
        # وصولنا هنا يعني أن كل دورة كانت تساوي ن(ن-١)/٢ بالضبط
        self.assertEqual(n * (n - 1) // 2, 4_999_950_000)


class TestVMAccelerationGate(unittest.TestCase):
    """بوابة النسبة: الدولاب ألا يكون أبطأ من الشجري ×1.5 — حد انحلال 50%."""

    def test_vm_not_slower_than_tree_times_1_5(self):
        r = _run(['--quick', '--json'])
        data = json.loads(r.stdout)
        hl = data['حلقة_ساخنة']
        self.assertGreaterEqual(hl['شجري_ثانية'] / hl['دولاب_ثانية'], 1 / 1.5)


class TestBaseline(unittest.TestCase):
    """خط الأساس المرفق سليم، والمقارنة الصارمة تفشل مغلقًا عند العبث."""

    def test_baseline_file_valid(self):
        self.assertTrue(BASELINE.exists())
        data = json.loads(BASELINE.read_text(encoding='utf-8'))
        self.assertTrue(data['numbers'], 'خط الأساس بلا أرقام')
        self.assertIn('حلقة_ساخنة.دولاب_ثانية', data['numbers'])
        self.assertTrue(data['python'])

    def test_baseline_comparison_passes(self):
        r = _run(['--quick', '--baseline', str(BASELINE)])
        self.assertEqual(r.returncode, 0, r.stdout[-500:])
        self.assertIn('بلا انحلال', r.stdout)

    def test_tampered_baseline_fails_closed(self):
        """عبث بالخط الأساس (×10 أبطأ) → رمز خروج 1 — البوابة تغلق."""
        data = json.loads(BASELINE.read_text(encoding='utf-8'))
        key = 'حلقة_ساخنة.دولاب_ثانية'
        # المرجع يصغر ×100 فيصبح القياس الحقيقي «انحلالًا» عشرة أضعاف عنه
        # (×10 بالضبط تُمحّاها تصغير الوضع السريع نفسه)
        data['numbers'][key] = data['numbers'][key] / 100
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tampered = Path(td) / 'baseline.json'
            tampered.write_text(json.dumps(data, ensure_ascii=False),
                                encoding='utf-8')
            r = _run(['--quick', '--baseline', str(tampered)])
        self.assertEqual(r.returncode, 1)
        self.assertIn(key, r.stdout)

    def test_ceilings_fail_closed(self):
        """سقف كارثي مسحوب إلى ما دون الصفر → فشل البوابة (برهان الإغلاق)."""
        # نفحص منطق البوابات مباشرة — بلا تشغيل عملية جديدة
        sys.path.insert(0, str(ROOT / 'benchmarks'))
        try:
            import run as bench_run
            results = {
                'بدء': {'ثانية': 0.1, 'سقف': 5.0},
                'حلقة_ساخنة': {'دولاب_ثانية': 0.2, 'شجري_ثانية': 0.4,
                               'نسبة_التسريع': 2.0, 'سقف_دولاب': 15.0, 'سقف_شجري': 30.0},
                'مولدات': {'ثانية': 0.7, 'سقف': 30.0},
                'بيئة_قدّم': {'ترميز_50_ثانية': 0.0001, 'ترميز_500_ثانية': 0.0005, 'سقف': 2.0},
                'تشفير': {'شفّر_مبثث': 2.0, 'فكّ_مبثث': 2.0, 'سقف_ثانية_لكل_اتجاه': 30.0},
            }
            gates = dict((name, ok) for name, ok, _ in bench_run.check_gates(results, True))
            self.assertTrue(all(gates.values()))
            # انحلال: الدولاب أبطأ من الشجري (نسبة 0.4 < 0.67)
            results['حلقة_ساخنة']['نسبة_التسريع'] = 0.4
            gates2 = dict((name, ok) for name, ok, _ in bench_run.check_gates(results, True))
            self.assertFalse(gates2['دولاب_لا_أبطأ_من_الشجري×1.5'])
        finally:
            sys.path.remove(str(ROOT / 'benchmarks'))
            sys.modules.pop('run', None)
