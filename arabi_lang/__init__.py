# -*- coding: utf-8 -*-
"""لغة عربي — لغة برمجة عربية بالكامل."""

__version__ = '1.23.0'

from .errors import ArabiError, LexerError, ParseError, ArabiRuntimeError
from .lexer import Lexer
from .parser import Parser
from .interpreter import Interpreter

__all__ = [
    'ArabiError', 'LexerError', 'ParseError', 'ArabiRuntimeError',
    'Lexer', 'Parser', 'Interpreter', '__version__',
]
