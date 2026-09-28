# -*- coding: utf-8 -*-
"""أخطاء لغة عربي — رسائل عربية واضحة مع رقم السطر والعمود."""


class ArabiError(Exception):
    """الخطأ الأساسي في اللغة.

    line رقم السطر (من ١) وcol عمود الموضع المذنب (من ١) — العمود
    اختياري ولا يظهر في الرسالة إن لم يتوفر (توافق خلفي كامل).
    """

    label = 'خطأ'

    def __init__(self, message, line=None, col=None):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(str(self))

    def __str__(self):
        text = self.label
        if self.line:
            text += f' في السطر {self.line}'
            if self.col:
                text += f'، العمود {self.col}'
        text += f': {self.message}'
        return text


class LexerError(ArabiError):
    """خطأ أثناء تحليل الرموز اللفظية."""
    label = 'خطأ لفظي'


class ParseError(ArabiError):
    """خطأ في بنية الجمل (النحو)."""
    label = 'خطأ نحوي'


class ArabiRuntimeError(ArabiError):
    """خطأ يحدث أثناء تنفيذ البرنامج."""
    label = 'خطأ تشغيلي'


class ArabiUserError(ArabiRuntimeError):
    """خطأ رفعته لغة عربي عبر كائن من صنف يرث الصنف المدمج 'استثناء'.

    يحمل instance الكائن الأصلي ليُربط بـ 'باستثناء' فيكتلة جرب.
    """

    label = 'خطأ'

    def __init__(self, instance, line=None, col=None):
        self.instance = instance
        cls_name = instance.cls.name
        msg = instance.fields.get('رسالة', '')
        msg = msg if isinstance(msg, str) else str(msg)
        text = f'{cls_name}: {msg}' if msg else cls_name
        super().__init__(text, line, col)
