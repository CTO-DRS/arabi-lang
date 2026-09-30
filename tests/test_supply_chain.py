# -*- coding: utf-8 -*-
"""اختبارات سلسلة التوريد (الإصدار 1.29 — المرحلة 7).

يغطي قرارات المواصفة ق٢١ (بصمة الناشر عند النشر)، ق٢٢ (الفهرس يعلن
البصمة والعميل يرفض الخلاف — فشل مغلق)، ق٢٣ (القفل يسجل بصمة الشجرة
وفحص البيئة يكشف العبث بعد التثبيت) — مع توافق الأقفال والفهارس
القديمة.
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from arabi_lang import packages
from arabi_lang.errors import ArabiError
from arabi_lang.registry import RegistryServer


# ================== أدوات مساعدة ==================

def _write(path, content, binary=False):
    mode = 'wb' if binary else 'w'
    with open(path, mode, encoding=None if binary else 'utf-8') as f:
        f.write(content)


def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _make_pkg_dir(base, name='ادوات_نص', version='1.0.0', code=None):
    """يبني مجلد حزمة كامل ببيان — ويعيد مساره."""
    pkg = os.path.join(base, name)
    os.makedirs(pkg, exist_ok=True)
    _write_json(os.path.join(pkg, 'حزمة.json'), {
        'الاسم': name, 'النسخة': version,
        'الوصف': f'حزمة {name}', 'المدخل': f'{name}.عربي',
        'التبعيات': {},
    })
    _write(os.path.join(pkg, f'{name}.عربي'),
           code or f'دالة تحية():\n    أعد "سليمة من {name}"\n')
    return pkg


def _zip_pkg_dir(pkg_dir, zip_path):
    """يؤرشف مجلد حزمة (بيان + كود) في ملف zip."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(pkg_dir)):
            zf.write(os.path.join(pkg_dir, fname), fname)
    return zip_path


# ================== بصمة الشجرة (ق٢٣) ==================

class TestTreeFingerprint(unittest.TestCase):
    """بصمة الشجرة: حتمية، حساسة لأي تغيير، مستثنية الكاش."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-بصمة-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_deterministic_for_same_content(self):
        a = _make_pkg_dir(self.tmp, 'حزمة_أ')
        self.assertEqual(packages._tree_fingerprint(a),
                         packages._tree_fingerprint(a))

    def test_content_change_changes_fingerprint(self):
        pkg = _make_pkg_dir(self.tmp, 'حزمة_أ')
        before = packages._tree_fingerprint(pkg)
        path = os.path.join(pkg, 'حزمة_أ.عربي')
        _write(path, _read_file(path) + '\n# سطر زائد\n')
        self.assertNotEqual(packages._tree_fingerprint(pkg), before)

    def test_added_and_removed_files_change_fingerprint(self):
        pkg = _make_pkg_dir(self.tmp, 'حزمة_أ')
        before = packages._tree_fingerprint(pkg)
        extra = os.path.join(pkg, 'إضافي.عربي')
        _write(extra, 'دالة صفر():\n    أعد 0\n')
        with_added = packages._tree_fingerprint(pkg)
        self.assertNotEqual(with_added, before)
        os.remove(extra)
        self.assertEqual(packages._tree_fingerprint(pkg), before)

    def test_bytecode_cache_is_excluded(self):
        pkg = _make_pkg_dir(self.tmp, 'حزمة_أ')
        before = packages._tree_fingerprint(pkg)
        cache = os.path.join(pkg, '__بايت__')
        os.makedirs(cache)
        _write(os.path.join(cache, 'x.رمز'),
               'بايتات كاش عشوائية'.encode('utf-8'), binary=True)
        self.assertEqual(packages._tree_fingerprint(pkg), before)

    def test_single_file_mode_is_file_hash(self):
        path = os.path.join(self.tmp, 'مفيد.عربي')
        _write(path, 'دالة سلام():\n    أعد "أهلا"\n')
        expected = hashlib.sha256(
            open(path, 'rb').read()).hexdigest()
        self.assertEqual(packages._tree_fingerprint(path), expected)


def _read_file(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


# ================== القفل يسجل بصمة الشجرة (ق٢٣) ==================

class TestLockRecordsFingerprint(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-قفل-')
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)
        self.src = _make_pkg_dir(self.tmp, 'ادوات_نص')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_lock_records_tree_fingerprint(self):
        packages.install(self.src, self.project)
        lock = packages.read_lock(self.project)
        self.assertIn('بصمة_الشجرة', lock['ادوات_نص'])

    def test_recorded_fingerprint_matches_recompute(self):
        packages.install(self.src, self.project)
        lock = packages.read_lock(self.project)
        declared = lock['ادوات_نص']['بصمة_الشجرة']
        installed = os.path.join(self.project, 'حزم', 'ادوات_نص')
        self.assertEqual(declared, packages._tree_fingerprint(installed))
        self.assertEqual(len(declared), 64)

    def test_single_file_install_records_fingerprint(self):
        # ملف .عربي مفرد يُغلّف ببيان ويُثبت مجلدًا — البصمة شجرة المجلد
        single = os.path.join(self.tmp, 'مفيد.عربي')
        _write(single, 'دالة سلام():\n    أعد "أهلا"\n')
        packages.install(single, self.project)
        lock = packages.read_lock(self.project)
        installed = os.path.join(self.project, 'حزم', 'مفيد')
        self.assertTrue(os.path.isdir(installed))
        self.assertEqual(lock['مفيد']['بصمة_الشجرة'],
                         packages._tree_fingerprint(installed))


# ================== التحقق من بصمة الفهرس وقت التثبيت (ق٢٢) ==================

class TestIndexFingerprintVerification(unittest.TestCase):
    """الفهرس المحلي يعلن بصمة الأرشيف — العميل يرفض الخلاف فورًا."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-تحقق-')
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)
        self.pkg_dir = _make_pkg_dir(self.tmp, 'ادوات_نص', '1.4.0')
        self.zip_path = _zip_pkg_dir(
            self.pkg_dir, os.path.join(self.tmp, 'ادوات_نص.zip'))
        self.fingerprint = packages._sha256_file(self.zip_path)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write_index(self, fingerprint_value):
        entry = {'المصدر': self.zip_path, 'النسخة': '1.4.0',
                 'الوصف': 'أدوات'}
        if fingerprint_value is not None:
            entry['البصمة'] = fingerprint_value
        index_path = os.path.join(self.tmp, 'الفهرس.json')
        _write_json(index_path, {'ادوات_نص': entry})
        return index_path

    def test_matching_fingerprint_installs(self):
        index = self._write_index(self.fingerprint)
        msgs = packages.install('ادوات_نص', self.project, index)
        kinds = [k for _, k in msgs]
        self.assertEqual(kinds, ['ثُبتت'])
        # الشفافية: رسالة التثبيت تذكر أن البصمة طابقت
        self.assertIn('بصمة الفهرس مطابقة', msgs[0][0])
        self.assertTrue(os.path.isfile(os.path.join(
            self.project, 'حزم', 'ادوات_نص', 'ادوات_نص.عربي')))

    def test_tampered_archive_refused_fail_closed(self):
        # البصمة معلنة للأصل، ثم أُعيد بناء الأرشيف بمحتوى مغاير
        index = self._write_index(self.fingerprint)
        _write(os.path.join(self.pkg_dir, 'ادوات_نص.عربي'),
               'دالة تحية():\n    أعد "مُعبثة"\n')
        _zip_pkg_dir(self.pkg_dir, self.zip_path)
        with self.assertRaises(ArabiError) as ctx:
            packages.install('ادوات_نص', self.project, index)
        self.assertIn('بصمة', str(ctx.exception))
        self.assertIn('المعلن', str(ctx.exception))
        # فشل مغلق: لا شيء ثبت إطلاقًا
        self.assertFalse(os.path.isdir(
            os.path.join(self.project, 'حزم', 'ادوات_نص')))

    def test_malformed_fingerprint_refused(self):
        index = self._write_index('abc123')
        with self.assertRaises(ArabiError) as ctx:
            packages.install('ادوات_نص', self.project, index)
        self.assertIn('غير سليمة', str(ctx.exception))

    def test_non_string_fingerprint_refused(self):
        index = self._write_index(12345)
        with self.assertRaises(ArabiError) as ctx:
            packages.install('ادوات_نص', self.project, index)
        self.assertIn('بصمة', str(ctx.exception))

    def test_uppercase_fingerprint_normalized(self):
        index = self._write_index(self.fingerprint.upper())
        msgs = packages.install('ادوات_نص', self.project, index)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])

    def test_index_without_fingerprint_installs(self):
        # فهرس بروتوكول قديم — التثبيت يتم (بلا إعلان لا تحقق)
        index = self._write_index(None)
        msgs = packages.install('ادوات_نص', self.project, index)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])
        self.assertNotIn('بصمة الفهرس مطابقة', msgs[0][0])


# ================== التحذير للشبكة بلا بصمة (ق٢٢) ==================

class TestNetworkWithoutFingerprintWarns(unittest.TestCase):
    """محتوى يعبر الشبكة من فهرس بلا إعلان بصمة → تحذير صادق."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-شبكة-')
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        pkg_dir = _make_pkg_dir(self.tmp, 'بعيدة', '2.0.0')
        srv = RegistryServer(os.path.join(self.tmp, 'مخزن'), port=0,
                             no_web=True).start()
        self.addCleanup(srv.stop)
        self.base = srv.base_url()
        packages.publish(pkg_dir, self.base + '/الفهرس.json')

    def test_legacy_index_warns_on_network_source(self):
        # فهرس مكتوب يدويًا بلا حقل البصمة ومصدره رابط شبكي
        url = (self.base + '/تحميل/'
               + urllib.parse.quote('بعيدة/2.0.0', safe='/.'))
        index_path = os.path.join(self.tmp, 'فهرس_قديم.json')
        _write_json(index_path, {
            'بعيدة': {'المصدر': url, 'النسخة': '2.0.0',
                      'الوصف': 'بلا إعلان'},
        })
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            msgs = packages.install('بعيدة', self.project, index_path)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])
        out = stderr.getvalue()
        self.assertIn('تحذير', out)
        self.assertIn('بصمة', out)

    def test_declaring_index_no_warning(self):
        # الفهرس الرسمي للخادم يعلن البصمة — لا تحذير، والتحقق يمر
        index_url = self.base + '/الفهرس.json'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            msgs = packages.install('بعيدة', self.project, index_url)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])
        self.assertIn('بصمة الفهرس مطابقة', msgs[0][0])
        self.assertEqual(stderr.getvalue(), '')


# ================== بصمة الناشر عند النشر (ق٢١) ==================

class TestPublisherAttestation(unittest.TestCase):
    """النشر يرسل بصمة المحتوى بترويسة — الخادم يتحقق ويخزنها."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-ناشر-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.pkg_dir = _make_pkg_dir(self.tmp, 'منشورة', '1.0.0')
        srv = RegistryServer(os.path.join(self.tmp, 'مخزن'), port=0,
                             no_web=True).start()
        self.addCleanup(srv.stop)
        self.base = srv.base_url()
        self.server = srv

    def _raw_publish(self, name, version, blob, fingerprint=None):
        """نشر خام — لمحاكاة عملاء قدماء أو طلبات معدلة."""
        path = urllib.parse.quote(f'/نشر/{name}/{version}', safe='/.')
        headers = {'Content-Type': 'application/zip'}
        if fingerprint is not None:
            headers['X-Arabi-Fingerprint'] = fingerprint
        req = urllib.request.Request(self.base + path, data=blob,
                                     headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8')
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, {'raw': body}

    def test_publish_declares_publisher_fingerprint(self):
        blob, name, version, _ = packages._build_package_zip(self.pkg_dir)
        expected = hashlib.sha256(blob).hexdigest()
        message = packages.publish(self.pkg_dir, self.base
                                   + '/الفهرس.json')
        # رسالة النشر تعرض البصمة الموثقة من الناشر
        self.assertIn(expected, message)
        # والفهرس يعلنها
        index = packages.load_index(self.base + '/الفهرس.json')
        self.assertEqual(index['منشورة'].get('البصمة'), expected)

    def test_wrong_declared_fingerprint_rejected(self):
        blob, name, version, _ = packages._build_package_zip(self.pkg_dir)
        status, payload = self._raw_publish(
            'منشورة', '1.0.0', blob, fingerprint='0' * 64)
        self.assertEqual(status, 400)
        self.assertIn('بصمة الناشر', payload.get('الخطأ', ''))

    def test_malformed_fingerprint_header_rejected(self):
        blob, name, version, _ = packages._build_package_zip(self.pkg_dir)
        status, payload = self._raw_publish(
            'منشورة', '1.0.0', blob, fingerprint='not-a-hex-value')
        self.assertEqual(status, 400)
        self.assertIn('sha256', payload.get('الخطأ', ''))

    def test_legacy_client_without_header_still_works(self):
        # عميل بروتوكول قديم بلا ترويسة — الخادم يحسب البصمة كما كان
        blob, name, version, _ = packages._build_package_zip(self.pkg_dir)
        status, payload = self._raw_publish('منشورة', '1.0.0', blob)
        self.assertEqual(status, 201)
        self.assertEqual(payload.get('الحالة'), 'نُشرت')
        expected = hashlib.sha256(blob).hexdigest()
        index = packages.load_index(self.base + '/الفهرس.json')
        self.assertEqual(index['منشورة'].get('البصمة'), expected)


# ================== فحص البيئة يكشف العبث بعد التثبيت (ق٢٣) ==================

class TestVerifyDetectsPostInstallTampering(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-فحص-')
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)
        self.src = _make_pkg_dir(self.tmp, 'ادوات_نص')
        packages.install(self.src, self.project)
        self.installed = os.path.join(self.project, 'حزم', 'ادوات_نص',
                                      'ادوات_نص.عربي')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_clean_environment_passes(self):
        self.assertEqual(packages.verify(self.project), [])

    def test_modified_file_flagged(self):
        _write(self.installed, _read_file(self.installed) + '\n# عبث\n')
        issues = packages.verify(self.project)
        self.assertTrue(issues)
        self.assertIn('تعدلت بعد التثبيت', issues[0])
        self.assertIn('ادوات_نص', issues[0])

    def test_added_file_flagged(self):
        _write(os.path.join(self.project, 'حزم', 'ادوات_نص',
                            'غريب.عربي'), 'دالة غ():\n    أعد 1\n')
        issues = packages.verify(self.project)
        self.assertTrue(any('تعدلت بعد التثبيت' in i for i in issues))

    def test_removed_file_flagged(self):
        os.remove(self.installed)
        issues = packages.verify(self.project)
        self.assertTrue(any('تعدلت بعد التثبيت' in i for i in issues))

    def test_reinstall_restores_integrity(self):
        _write(self.installed, _read_file(self.installed) + '\n# عبث\n')
        self.assertTrue(packages.verify(self.project))
        packages.remove('ادوات_نص', self.project)
        packages.install(self.src, self.project)
        self.assertEqual(packages.verify(self.project), [])


# ================== توافق الأقفال القديمة ==================

class TestOldLockCompatibility(unittest.TestCase):
    """قفل بروتوكول أقدم من 1.29 (بلا بصمات) يُفحص بلا إنذارات كاذبة."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-قديم-')
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)
        self.src = _make_pkg_dir(self.tmp, 'ادوات_نص')
        packages.install(self.src, self.project)
        self.lock_path = os.path.join(self.project, 'قفل.json')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _strip_fingerprints(self):
        with open(self.lock_path, encoding='utf-8') as f:
            lock = json.load(f)
        for entry in lock['الحزم'].values():
            entry.pop('بصمة_الشجرة', None)
        _write_json(self.lock_path, lock)

    def test_old_lock_no_false_positive(self):
        self._strip_fingerprints()
        self.assertEqual(packages.verify(self.project), [])

    def test_corrupt_fingerprint_flagged(self):
        with open(self.lock_path, encoding='utf-8') as f:
            lock = json.load(f)
        lock['الحزم']['ادوات_نص']['بصمة_الشجرة'] = '0' * 64
        _write_json(self.lock_path, lock)
        issues = packages.verify(self.project)
        self.assertTrue(any('تعدلت بعد التثبيت' in i for i in issues))


# ================== الدورة الكاملة ==================

class TestEndToEndSupplyChain(unittest.TestCase):
    """نشر → تثبيت موثق → فحص سليم → عبث → كشف → تحديث يصلح."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='عربي-دورة-')
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        pkg_dir = _make_pkg_dir(self.tmp, 'دورة', '1.0.0')
        srv = RegistryServer(os.path.join(self.tmp, 'مخزن'), port=0,
                             no_web=True).start()
        self.addCleanup(srv.stop)
        self.index_url = srv.base_url() + '/الفهرس.json'
        packages.publish(pkg_dir, self.index_url)

    def test_full_cycle(self):
        # 1) تثبيت موثق من الفهرس
        msgs = packages.install('دورة', self.project, self.index_url)
        self.assertIn('بصمة الفهرس مطابقة', msgs[0][0])
        # 2) البيئة سليمة
        self.assertEqual(packages.verify(self.project), [])
        # 3) عبث بملف مثبت — الفحص يكشف
        target = os.path.join(self.project, 'حزم', 'دورة', 'دورة.عربي')
        _write(target, _read_file(target) + '\n# دخيل\n')
        self.assertTrue(packages.verify(self.project))
        # 4) تحديث يعيد التثبيت من السجل — والبصمة تُتصادق من جديد
        messages = packages.update('دورة', self.project, self.index_url)
        self.assertTrue(any(k == 'ثُبتت' for _, k in messages))
        self.assertEqual(packages.verify(self.project), [])


if __name__ == '__main__':
    unittest.main()
