# -*- coding: utf-8 -*-
"""أخطاء لغة عربي — رسائل عربية واضحة مع رقم السطر."""


class ArabiError(Exception):
    """الخطأ الأساسي في اللغة."""

    label = 'خطأ'

    def __init__(self, message, line=None):
        self.message = message
        self.line = line
        super().__init__(str(self))

    def __str__(self):
        text = self.label
        if self.line:
            text += f' في السطر {self.line}'
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
