#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyVim — 单文件 Python 实现的类 Vim 终端编辑器

用法:
    python3 pyvim.py [文件]
    python3 pyvim.py --help

命令行:
    --syntax FILE.json   启动时加载外部语法高亮配置
    --no-color           关闭高亮
    --help / -h          打印命令行帮助

编辑器内:
    :help                打开内置帮助
    :syntax load PATH    加载外部高亮配置
    :syntax reset        恢复内置高亮
    :syntax off / on     关闭 / 打开高亮
"""

from __future__ import annotations

import argparse
import copy
import curses
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 内置语法高亮配置
# 规则说明（与外部 JSON 文件格式相同）:
#   extensions : 文件后缀列表
#   keywords   : 关键字列表
#   types      : 类型名列表（可选）
#   builtins   : 内置函数/常量（可选）
#   comment    : 行注释起始符，如 "#" 或 "//"
#   block_comment : [开始, 结束]，如 ["/*", "*/"]
#   strings    : 字符串定界符列表，如 ["\"", "'", "`"]
#   numbers    : 是否高亮数字
#   extras     : 额外正则 -> 样式名
# 样式名: keyword, type, builtin, comment, string, number, extra
# ---------------------------------------------------------------------------

BUILTIN_SYNTAX: Dict[str, Dict[str, Any]] = {
    "python": {
        "extensions": [".py", ".pyw", ".pyi"],
        "keywords": [
            "False", "None", "True", "and", "as", "assert", "async", "await",
            "break", "class", "continue", "def", "del", "elif", "else", "except",
            "finally", "for", "from", "global", "if", "import", "in", "is",
            "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
            "while", "with", "yield", "match", "case",
        ],
        "types": [
            "int", "float", "str", "bytes", "bool", "list", "dict", "set",
            "tuple", "object", "type", "Exception",
        ],
        "builtins": [
            "print", "len", "range", "enumerate", "zip", "map", "filter",
            "open", "input", "isinstance", "super", "property", "staticmethod",
            "classmethod", "self", "cls",
        ],
        "comment": "#",
        "strings": ['"', "'"],
        "numbers": True,
        "extras": {r"@\w+": "extra", r"\bself\b": "builtin"},
    },
    "javascript": {
        "extensions": [".js", ".mjs", ".cjs", ".jsx"],
        "keywords": [
            "break", "case", "catch", "class", "const", "continue", "debugger",
            "default", "delete", "do", "else", "export", "extends", "finally",
            "for", "function", "if", "import", "in", "instanceof", "let", "new",
            "return", "super", "switch", "this", "throw", "try", "typeof",
            "var", "void", "while", "with", "yield", "async", "await", "of",
        ],
        "types": ["undefined", "null", "true", "false", "NaN", "Infinity"],
        "builtins": [
            "console", "window", "document", "Array", "Object", "String",
            "Number", "Math", "JSON", "Promise", "Map", "Set",
        ],
        "comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"', "'", "`"],
        "numbers": True,
    },
    "typescript": {
        "extensions": [".ts", ".tsx"],
        "keywords": [
            "break", "case", "catch", "class", "const", "continue", "debugger",
            "default", "delete", "do", "else", "export", "extends", "finally",
            "for", "function", "if", "import", "in", "instanceof", "let", "new",
            "return", "super", "switch", "this", "throw", "try", "typeof",
            "var", "void", "while", "with", "yield", "async", "await", "of",
            "interface", "type", "enum", "implements", "public", "private",
            "protected", "readonly", "abstract", "as", "from",
        ],
        "types": [
            "string", "number", "boolean", "any", "unknown", "never", "void",
            "undefined", "null", "true", "false",
        ],
        "comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"', "'", "`"],
        "numbers": True,
    },
    "c": {
        "extensions": [".c", ".h"],
        "keywords": [
            "auto", "break", "case", "const", "continue", "default", "do",
            "else", "enum", "extern", "for", "goto", "if", "inline", "register",
            "restrict", "return", "sizeof", "static", "struct", "switch",
            "typedef", "union", "volatile", "while",
        ],
        "types": [
            "void", "char", "short", "int", "long", "float", "double",
            "signed", "unsigned", "size_t", "ssize_t", "bool",
        ],
        "comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"'],
        "numbers": True,
        "extras": {r"#\s*\w+": "extra"},
    },
    "cpp": {
        "extensions": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"],
        "keywords": [
            "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand",
            "bitor", "break", "case", "catch", "class", "compl", "concept",
            "const", "consteval", "constexpr", "constinit", "const_cast",
            "continue", "co_await", "co_return", "co_yield", "decltype",
            "default", "delete", "do", "dynamic_cast", "else", "enum",
            "explicit", "export", "extern", "false", "for", "friend", "goto",
            "if", "inline", "mutable", "namespace", "new", "noexcept", "not",
            "not_eq", "nullptr", "operator", "or", "or_eq", "private",
            "protected", "public", "register", "reinterpret_cast", "requires",
            "return", "sizeof", "static", "static_assert", "static_cast",
            "struct", "switch", "template", "this", "thread_local", "throw",
            "true", "try", "typedef", "typeid", "typename", "union", "using",
            "virtual", "volatile", "while", "xor", "xor_eq",
        ],
        "types": [
            "void", "bool", "char", "char8_t", "char16_t", "char32_t", "wchar_t",
            "short", "int", "long", "float", "double", "signed", "unsigned",
            "size_t", "string", "vector", "map", "set", "optional",
        ],
        "comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"'],
        "numbers": True,
        "extras": {r"#\s*\w+": "extra"},
    },
    "java": {
        "extensions": [".java"],
        "keywords": [
            "abstract", "assert", "break", "case", "catch", "class", "const",
            "continue", "default", "do", "else", "enum", "extends", "final",
            "finally", "for", "goto", "if", "implements", "import",
            "instanceof", "interface", "native", "new", "package", "private",
            "protected", "public", "return", "static", "strictfp", "super",
            "switch", "synchronized", "this", "throw", "throws", "transient",
            "try", "void", "volatile", "while",
        ],
        "types": [
            "boolean", "byte", "char", "double", "float", "int", "long",
            "short", "String", "Object", "true", "false", "null",
        ],
        "comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"'],
        "numbers": True,
    },
    "go": {
        "extensions": [".go"],
        "keywords": [
            "break", "case", "chan", "const", "continue", "default", "defer",
            "else", "fallthrough", "for", "func", "go", "goto", "if", "import",
            "interface", "map", "package", "range", "return", "select",
            "struct", "switch", "type", "var",
        ],
        "types": [
            "bool", "byte", "complex64", "complex128", "error", "float32",
            "float64", "int", "int8", "int16", "int32", "int64", "rune",
            "string", "uint", "uint8", "uint16", "uint32", "uint64", "uintptr",
            "true", "false", "nil", "iota",
        ],
        "comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"', "`"],
        "numbers": True,
    },
    "rust": {
        "extensions": [".rs"],
        "keywords": [
            "as", "async", "await", "break", "const", "continue", "crate",
            "dyn", "else", "enum", "extern", "false", "fn", "for", "if",
            "impl", "in", "let", "loop", "match", "mod", "move", "mut", "pub",
            "ref", "return", "self", "Self", "static", "struct", "super",
            "trait", "true", "type", "unsafe", "use", "where", "while",
        ],
        "types": [
            "i8", "i16", "i32", "i64", "i128", "isize", "u8", "u16", "u32",
            "u64", "u128", "usize", "f32", "f64", "bool", "char", "str",
            "String", "Vec", "Option", "Result",
        ],
        "comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"'],
        "numbers": True,
    },
    "html": {
        "extensions": [".html", ".htm"],
        "keywords": [],
        "comment": None,
        "block_comment": ["<!--", "-->"],
        "strings": ['"', "'"],
        "numbers": False,
        "extras": {
            r"</?[A-Za-z][\w:-]*": "keyword",
            r"\b[A-Za-z_:][\w:-]*(?==)": "type",
        },
    },
    "css": {
        "extensions": [".css"],
        "keywords": [
            "important", "from", "to", "and", "or", "not", "only",
        ],
        "comment": None,
        "block_comment": ["/*", "*/"],
        "strings": ['"', "'"],
        "numbers": True,
        "extras": {
            r"#[0-9A-Fa-f]{3,8}\b": "number",
            r"@[\w-]+": "extra",
            r"[\w-]+(?=\s*:)": "type",
        },
    },
    "json": {
        "extensions": [".json"],
        "keywords": ["true", "false", "null"],
        "strings": ['"'],
        "numbers": True,
    },
    "markdown": {
        "extensions": [".md", ".markdown"],
        "keywords": [],
        "comment": None,
        "strings": [],
        "numbers": False,
        "extras": {
            r"^#{1,6}\s.*": "keyword",
            r"`[^`]+`": "string",
            r"\*\*[^*]+\*\*": "builtin",
            r"\*[^*]+\*": "type",
            r"^\s*[-*+]\s": "extra",
        },
    },
    "shell": {
        "extensions": [".sh", ".bash", ".zsh"],
        "keywords": [
            "if", "then", "else", "elif", "fi", "for", "while", "do", "done",
            "case", "esac", "in", "function", "return", "break", "continue",
            "local", "export", "readonly", "shift", "source", "alias",
        ],
        "builtins": [
            "echo", "printf", "read", "cd", "pwd", "ls", "test", "exit",
            "set", "unset", "trap", "eval",
        ],
        "comment": "#",
        "strings": ['"', "'"],
        "numbers": True,
        "extras": {r"\$\{?\w+\}?": "extra"},
    },
    "ruby": {
        "extensions": [".rb"],
        "keywords": [
            "BEGIN", "END", "alias", "and", "begin", "break", "case", "class",
            "def", "defined?", "do", "else", "elsif", "end", "ensure", "false",
            "for", "if", "in", "module", "next", "nil", "not", "or", "redo",
            "rescue", "retry", "return", "self", "super", "then", "true",
            "undef", "unless", "until", "when", "while", "yield",
        ],
        "comment": "#",
        "strings": ['"', "'"],
        "numbers": True,
    },
    "sql": {
        "extensions": [".sql"],
        "keywords": [
            "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES", "UPDATE",
            "SET", "DELETE", "CREATE", "TABLE", "DROP", "ALTER", "INDEX",
            "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON", "AND", "OR",
            "NOT", "NULL", "AS", "ORDER", "BY", "GROUP", "HAVING", "LIMIT",
            "DISTINCT", "UNION", "ALL", "PRIMARY", "KEY", "FOREIGN",
            "REFERENCES", "DEFAULT", "CONSTRAINT",
        ],
        "types": [
            "INT", "INTEGER", "VARCHAR", "CHAR", "TEXT", "DATE", "DATETIME",
            "BOOLEAN", "FLOAT", "DOUBLE", "DECIMAL", "BLOB",
        ],
        "comment": "--",
        "block_comment": ["/*", "*/"],
        "strings": ["'", '"'],
        "numbers": True,
    },
    "plain": {
        "extensions": [],
        "keywords": [],
        "strings": [],
        "numbers": False,
    },
}

# 帮助文本（编辑器内 :help / F1）
HELP_TEXT = """\
PyVim 帮助                                    :q 关闭帮助

═══════════════════════════════════════════════════════════
  模式
═══════════════════════════════════════════════════════════
  NORMAL   普通模式（启动默认）  按 Esc 随时回到此模式
  INSERT   插入模式              i a o O I A s
  VISUAL   可视选区              v
  COMMAND  命令行                :

═══════════════════════════════════════════════════════════
  普通模式 — 移动
═══════════════════════════════════════════════════════════
  h j k l        左 下 上 右
  0  ^           行首 / 第一个非空白
  $              行尾
  w  b           下一个 / 上一个单词
  gg  G          文件头 / 文件尾
  {n}G           跳到第 n 行
  Ctrl-u / Ctrl-d  半页上 / 下
  Ctrl-b / Ctrl-f  整页上 / 下
  H  M  L        屏幕顶 / 中 / 底

═══════════════════════════════════════════════════════════
  普通模式 — 编辑
═══════════════════════════════════════════════════════════
  i  a           光标前 / 后插入
  I  A           行首 / 行尾插入
  o  O           下方 / 上方新开一行并插入
  s              删除当前字符并插入
  x              删除光标处字符
  X              删除光标前字符
  dd             删除整行
  D              删除到行尾
  yy             复制整行
  yw             复制单词
  p  P           光标后 / 前粘贴
  r{c}           替换当前字符为 c
  u              撤销
  Ctrl-r         重做
  J              合并下一行

═══════════════════════════════════════════════════════════
  可视模式
═══════════════════════════════════════════════════════════
  v              进入 / 退出可视
  h j k l        扩展选区
  d / x          删除选区
  y              复制选区
  Esc            取消选区

═══════════════════════════════════════════════════════════
  查找
═══════════════════════════════════════════════════════════
  /pattern       向下查找
  ?pattern       向上查找
  n  N           下一个 / 上一个匹配
  *              查找光标下的单词

═══════════════════════════════════════════════════════════
  命令行  (先按 :)
═══════════════════════════════════════════════════════════
  :w [file]      保存（可另存为）
  :q             退出（有未保存改动会拒绝）
  :q!            强制退出
  :wq  :x        保存并退出
  :e file        打开文件
  :help          本帮助
  :set nu        显示行号
  :set nonu      隐藏行号
  :syntax on     打开高亮
  :syntax off    关闭高亮
  :syntax reset  恢复内置高亮配置
  :syntax load PATH
                 加载外部 JSON 高亮配置（可与内置合并）
  :syntax list   列出当前已加载的语言
  :set ft=LANG   强制指定文件类型，如 :set ft=python

═══════════════════════════════════════════════════════════
  外部高亮配置文件格式 (JSON)
═══════════════════════════════════════════════════════════
  {
    "mylang": {
      "extensions": [".ml"],
      "keywords": ["let", "in", "fun"],
      "types": ["int", "string"],
      "builtins": ["print"],
      "comment": "//",
      "block_comment": ["/*", "*/"],
      "strings": ["\\"", "'"],
      "numbers": true,
      "extras": { "\\\\bTODO\\\\b": "extra" }
    }
  }
  样式名可用: keyword, type, builtin, comment, string, number, extra
  加载后按扩展名自动匹配；也可用 :set ft=mylang 强制指定。

═══════════════════════════════════════════════════════════
  其它按键
═══════════════════════════════════════════════════════════
  F1             打开 / 关闭帮助
  Ctrl-g         显示文件信息
  Esc            取消命令 / 回到普通模式
"""

STYLE_MAP = {
    "keyword": 1,
    "type": 2,
    "builtin": 3,
    "comment": 4,
    "string": 5,
    "number": 6,
    "extra": 7,
    "lineno": 8,
    "status": 9,
    "command": 10,
    "visual": 11,
    "search": 12,
    "message": 13,
}


def ident_re(words: List[str], flags: int = 0) -> Optional[re.Pattern]:
    if not words:
        return None
    # 较长的词优先，避免短词抢匹配
    words = sorted(set(words), key=len, reverse=True)
    body = "|".join(re.escape(w) for w in words)
    return re.compile(r"\b(?:" + body + r")\b", flags)


class Highlighter:
    """基于配置的简易词法高亮（按行，块注释跨行）。"""

    def __init__(self, specs: Dict[str, Dict[str, Any]]):
        self.specs = specs
        self._compiled: Dict[str, Dict[str, Any]] = {}
        self._ext_index: Dict[str, str] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._ext_index.clear()
        self._compiled.clear()
        for name, spec in self.specs.items():
            for ext in spec.get("extensions") or []:
                self._ext_index[ext.lower()] = name

    def merge_external(self, data: Dict[str, Any]) -> List[str]:
        added = []
        if not isinstance(data, dict):
            raise ValueError("配置根节点必须是对象 {lang: spec, ...}")
        for name, spec in data.items():
            if not isinstance(spec, dict):
                continue
            if name in self.specs:
                merged = copy.deepcopy(self.specs[name])
                for k, v in spec.items():
                    if k in ("keywords", "types", "builtins", "extensions", "strings") and isinstance(v, list):
                        merged[k] = list(dict.fromkeys((merged.get(k) or []) + v))
                    elif k == "extras" and isinstance(v, dict):
                        merged.setdefault("extras", {}).update(v)
                    else:
                        merged[k] = v
                self.specs[name] = merged
            else:
                self.specs[name] = spec
            added.append(name)
        self._rebuild_index()
        return added

    def reset(self, builtin: Dict[str, Dict[str, Any]]) -> None:
        self.specs = copy.deepcopy(builtin)
        self._rebuild_index()

    def guess_lang(self, path: Optional[str], forced: Optional[str] = None) -> str:
        if forced and forced in self.specs:
            return forced
        if path:
            _, ext = os.path.splitext(path)
            lang = self._ext_index.get(ext.lower())
            if lang:
                return lang
        return "plain"

    def _compile(self, lang: str) -> Dict[str, Any]:
        if lang in self._compiled:
            return self._compiled[lang]
        spec = self.specs.get(lang) or self.specs["plain"]
        flags = 0
        # SQL 关键字大小写不敏感
        kw_flags = re.IGNORECASE if lang == "sql" else 0
        compiled = {
            "kw": ident_re(spec.get("keywords") or [], kw_flags),
            "ty": ident_re(spec.get("types") or []),
            "bi": ident_re(spec.get("builtins") or []),
            "comment": spec.get("comment"),
            "block": spec.get("block_comment"),
            "strings": spec.get("strings") or [],
            "numbers": bool(spec.get("numbers")),
            "extras": [],
        }
        for pat, style in (spec.get("extras") or {}).items():
            try:
                compiled["extras"].append((re.compile(pat), style))
            except re.error:
                continue
        self._compiled[lang] = compiled
        return compiled

    def highlight_lines(self, lines: List[str], lang: str) -> List[List[Tuple[str, str]]]:
        """返回每行 [(text, style_name), ...]。style_name 空字符串表示普通文本。"""
        c = self._compile(lang)
        out: List[List[Tuple[str, str]]] = []
        in_block = False
        block = c["block"]
        b_open = block[0] if block else None
        b_close = block[1] if block else None

        num_re = re.compile(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b")

        for line in lines:
            spans: List[Tuple[str, str]] = []
            i = 0
            n = len(line)
            while i < n:
                if in_block and b_close:
                    j = line.find(b_close, i)
                    if j == -1:
                        spans.append((line[i:], "comment"))
                        i = n
                        break
                    spans.append((line[i:j + len(b_close)], "comment"))
                    i = j + len(b_close)
                    in_block = False
                    continue

                # 块注释开始
                if b_open:
                    j = line.find(b_open, i)
                else:
                    j = -1
                # 行注释
                cpos = line.find(c["comment"], i) if c["comment"] else -1
                # 字符串
                spos, sdelim = -1, ""
                for d in c["strings"]:
                    p = line.find(d, i)
                    if p != -1 and (spos == -1 or p < spos):
                        spos, sdelim = p, d

                candidates = []
                if j != -1:
                    candidates.append((j, "block"))
                if cpos != -1:
                    candidates.append((cpos, "linec"))
                if spos != -1:
                    candidates.append((spos, "str"))

                if not candidates:
                    spans.extend(self._color_code(line[i:], c, num_re))
                    break

                candidates.sort(key=lambda x: x[0])
                pos, kind = candidates[0]
                if pos > i:
                    spans.extend(self._color_code(line[i:pos], c, num_re))
                if kind == "block":
                    k = line.find(b_close, pos + len(b_open)) if b_close else -1
                    if k == -1:
                        spans.append((line[pos:], "comment"))
                        in_block = True
                        i = n
                    else:
                        spans.append((line[pos:k + len(b_close)], "comment"))
                        i = k + len(b_close)
                elif kind == "linec":
                    spans.append((line[pos:], "comment"))
                    i = n
                else:
                    # 字符串，处理简单转义
                    k = pos + len(sdelim)
                    while k < n:
                        if line[k] == "\\" and k + 1 < n:
                            k += 2
                            continue
                        if line.startswith(sdelim, k):
                            k += len(sdelim)
                            break
                        k += 1
                    spans.append((line[pos:k], "string"))
                    i = k
            out.append(spans if spans else [("", "")])
        return out

    def _color_code(
        self, text: str, c: Dict[str, Any], num_re: re.Pattern
    ) -> List[Tuple[str, str]]:
        if not text:
            return []
        marks: List[Tuple[int, int, str]] = []  # start, end, style

        def add_pat(pat: Optional[re.Pattern], style: str) -> None:
            if not pat:
                return
            for m in pat.finditer(text):
                marks.append((m.start(), m.end(), style))

        add_pat(c["kw"], "keyword")
        add_pat(c["ty"], "type")
        add_pat(c["bi"], "builtin")
        if c["numbers"]:
            add_pat(num_re, "number")
        for pat, style in c["extras"]:
            add_pat(pat, style)

        if not marks:
            return [(text, "")]

        marks.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        # 去掉重叠（保留先出现 / 更长的）
        kept: List[Tuple[int, int, str]] = []
        last = -1
        for s, e, st in marks:
            if s < last:
                continue
            kept.append((s, e, st))
            last = e

        spans: List[Tuple[str, str]] = []
        cur = 0
        for s, e, st in kept:
            if s > cur:
                spans.append((text[cur:s], ""))
            spans.append((text[s:e], st))
            cur = e
        if cur < len(text):
            spans.append((text[cur:], ""))
        return spans


@dataclass
class EditorState:
    lines: List[str] = field(default_factory=lambda: [""])
    cy: int = 0
    cx: int = 0
    toprow: int = 0
    leftcol: int = 0
    mode: str = "NORMAL"  # NORMAL INSERT VISUAL COMMAND SEARCH HELP
    filename: Optional[str] = None
    dirty: bool = False
    message: str = ""
    clipboard: str = ""
    undo: List[Tuple[List[str], int, int]] = field(default_factory=list)
    redo: List[Tuple[List[str], int, int]] = field(default_factory=list)
    visual_anchor: Optional[Tuple[int, int]] = None
    search_pat: str = ""
    search_dir: int = 1
    show_lineno: bool = True
    highlight_on: bool = True
    filetype: Optional[str] = None
    cmd: str = ""
    pending: str = ""
    count: str = ""
    help_top: int = 0


class PyVim:
    def __init__(
        self,
        filename: Optional[str] = None,
        syntax_file: Optional[str] = None,
        color: bool = True,
    ):
        self.hl = Highlighter(copy.deepcopy(BUILTIN_SYNTAX))
        self.st = EditorState(highlight_on=color)
        self._hl_cache_key: Optional[Tuple] = None
        self._hl_cache: List[List[Tuple[str, str]]] = []
        if syntax_file:
            try:
                added = self._load_syntax_file(syntax_file)
                self.st.message = "已加载语法: " + ", ".join(added)
            except Exception as e:
                self.st.message = f"加载语法失败: {e}"
        if filename:
            self._open(filename)

    # ---------- 文件 ----------
    def _snapshot(self) -> None:
        self.st.undo.append((self.st.lines[:], self.st.cy, self.st.cx))
        if len(self.st.undo) > 200:
            self.st.undo.pop(0)
        self.st.redo.clear()

    def _open(self, path: str) -> None:
        path = os.path.expanduser(path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            self.st.lines = text.split("\n")
            if not self.st.lines:
                self.st.lines = [""]
            # 去掉末尾因 split 产生的空问题：保留文件原样
            self.st.filename = path
            self.st.dirty = False
            self.st.cy = self.st.cx = self.st.toprow = self.st.leftcol = 0
            self.st.filetype = None
            self.st.message = f'已打开 "{path}"  {len(self.st.lines)} 行'
            self._invalidate_hl()
        except FileNotFoundError:
            self.st.lines = [""]
            self.st.filename = path
            self.st.dirty = False
            self.st.message = f'新建 "{path}"'
            self._invalidate_hl()
        except OSError as e:
            self.st.message = f"打开失败: {e}"

    def _save(self, path: Optional[str] = None) -> bool:
        target = path or self.st.filename
        if not target:
            self.st.message = "未指定文件名，请用 :w 文件名"
            return False
        target = os.path.expanduser(target)
        try:
            data = "\n".join(self.st.lines)
            with open(target, "w", encoding="utf-8") as f:
                f.write(data)
            self.st.filename = target
            self.st.dirty = False
            self.st.message = f'已写入 "{target}"  {len(self.st.lines)} 行'
            return True
        except OSError as e:
            self.st.message = f"保存失败: {e}"
            return False

    def _load_syntax_file(self, path: str) -> List[str]:
        path = os.path.expanduser(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        added = self.hl.merge_external(data)
        self._invalidate_hl()
        return added

    def _invalidate_hl(self) -> None:
        self._hl_cache_key = None

    # ---------- 光标 / 缓冲 ----------
    def _cur_line(self) -> str:
        if not self.st.lines:
            self.st.lines = [""]
        self.st.cy = max(0, min(self.st.cy, len(self.st.lines) - 1))
        return self.st.lines[self.st.cy]

    def _clamp_x(self, insert: bool = False) -> None:
        line = self._cur_line()
        mx = len(line) if insert else max(0, len(line) - 1) if line else 0
        if not line and not insert:
            mx = 0
        self.st.cx = max(0, min(self.st.cx, mx))

    def _ensure_visible(self, rows: int, cols: int, gutter: int) -> None:
        text_rows = max(1, rows - 2)
        text_cols = max(1, cols - gutter)
        if self.st.cy < self.st.toprow:
            self.st.toprow = self.st.cy
        if self.st.cy >= self.st.toprow + text_rows:
            self.st.toprow = self.st.cy - text_rows + 1
        if self.st.cx < self.st.leftcol:
            self.st.leftcol = self.st.cx
        if self.st.cx >= self.st.leftcol + text_cols:
            self.st.leftcol = self.st.cx - text_cols + 1
        self.st.toprow = max(0, self.st.toprow)
        self.st.leftcol = max(0, self.st.leftcol)

    def _word_forward(self) -> None:
        line = self._cur_line()
        x = self.st.cx
        n = len(line)
        if x >= n - 1 and self.st.cy < len(self.st.lines) - 1:
            self.st.cy += 1
            self.st.cx = 0
            return
        while x < n and (line[x].isalnum() or line[x] == "_"):
            x += 1
        while x < n and not (line[x].isalnum() or line[x] == "_"):
            x += 1
        self.st.cx = min(x, max(0, n - 1)) if n else 0

    def _word_back(self) -> None:
        line = self._cur_line()
        x = self.st.cx
        if x == 0 and self.st.cy > 0:
            self.st.cy -= 1
            self.st.cx = max(0, len(self._cur_line()) - 1)
            return
        x = max(0, x - 1)
        while x > 0 and not (line[x].isalnum() or line[x] == "_"):
            x -= 1
        while x > 0 and (line[x - 1].isalnum() or line[x - 1] == "_"):
            x -= 1
        self.st.cx = x

    def _current_word(self) -> str:
        line = self._cur_line()
        if not line:
            return ""
        x = min(self.st.cx, len(line) - 1)
        a = x
        while a > 0 and (line[a - 1].isalnum() or line[a - 1] == "_"):
            a -= 1
        b = x
        while b < len(line) and (line[b].isalnum() or line[b] == "_"):
            b += 1
        return line[a:b]

    # ---------- 编辑操作 ----------
    def _insert_char(self, ch: str) -> None:
        self._snapshot()
        line = self._cur_line()
        self.st.lines[self.st.cy] = line[: self.st.cx] + ch + line[self.st.cx :]
        self.st.cx += len(ch)
        self.st.dirty = True
        self._invalidate_hl()

    def _insert_newline(self) -> None:
        self._snapshot()
        line = self._cur_line()
        left, right = line[: self.st.cx], line[self.st.cx :]
        self.st.lines[self.st.cy] = left
        self.st.lines.insert(self.st.cy + 1, right)
        self.st.cy += 1
        self.st.cx = 0
        self.st.dirty = True
        self._invalidate_hl()

    def _backspace(self) -> None:
        if self.st.cx == 0 and self.st.cy == 0:
            return
        self._snapshot()
        if self.st.cx > 0:
            line = self._cur_line()
            self.st.lines[self.st.cy] = line[: self.st.cx - 1] + line[self.st.cx :]
            self.st.cx -= 1
        else:
            prev = self.st.lines[self.st.cy - 1]
            cur = self.st.lines[self.st.cy]
            self.st.cx = len(prev)
            self.st.lines[self.st.cy - 1] = prev + cur
            del self.st.lines[self.st.cy]
            self.st.cy -= 1
        self.st.dirty = True
        self._invalidate_hl()

    def _delete_char(self) -> None:
        line = self._cur_line()
        if self.st.cx < len(line):
            self._snapshot()
            self.st.lines[self.st.cy] = line[: self.st.cx] + line[self.st.cx + 1 :]
            self.st.dirty = True
            self._invalidate_hl()
        elif self.st.cy < len(self.st.lines) - 1:
            self._snapshot()
            self.st.lines[self.st.cy] = line + self.st.lines[self.st.cy + 1]
            del self.st.lines[self.st.cy + 1]
            self.st.dirty = True
            self._invalidate_hl()

    def _delete_line(self) -> None:
        self._snapshot()
        self.st.clipboard = self._cur_line() + "\n"
        if len(self.st.lines) == 1:
            self.st.lines = [""]
        else:
            del self.st.lines[self.st.cy]
            if self.st.cy >= len(self.st.lines):
                self.st.cy = len(self.st.lines) - 1
        self.st.cx = 0
        self.st.dirty = True
        self._invalidate_hl()

    def _yank_line(self) -> None:
        self.st.clipboard = self._cur_line() + "\n"
        self.st.message = "已复制 1 行"

    def _paste(self, before: bool) -> None:
        if not self.st.clipboard:
            return
        self._snapshot()
        clip = self.st.clipboard
        if clip.endswith("\n"):
            text = clip[:-1]
            if before:
                self.st.lines.insert(self.st.cy, text)
            else:
                self.st.lines.insert(self.st.cy + 1, text)
                self.st.cy += 1
            self.st.cx = 0
        else:
            line = self._cur_line()
            pos = self.st.cx if before else self.st.cx + 1
            pos = min(pos, len(line))
            self.st.lines[self.st.cy] = line[:pos] + clip + line[pos:]
            self.st.cx = pos + len(clip) - 1
        self.st.dirty = True
        self._invalidate_hl()

    def _undo(self) -> None:
        if not self.st.undo:
            self.st.message = "已是最早状态"
            return
        self.st.redo.append((self.st.lines[:], self.st.cy, self.st.cx))
        lines, y, x = self.st.undo.pop()
        self.st.lines, self.st.cy, self.st.cx = lines, y, x
        self.st.dirty = True
        self._invalidate_hl()

    def _redo(self) -> None:
        if not self.st.redo:
            self.st.message = "已是最新状态"
            return
        self.st.undo.append((self.st.lines[:], self.st.cy, self.st.cx))
        lines, y, x = self.st.redo.pop()
        self.st.lines, self.st.cy, self.st.cx = lines, y, x
        self.st.dirty = True
        self._invalidate_hl()

    def _visual_range(self) -> Tuple[int, int, int, int]:
        assert self.st.visual_anchor is not None
        ay, ax = self.st.visual_anchor
        by, bx = self.st.cy, self.st.cx
        if (ay, ax) <= (by, bx):
            return ay, ax, by, bx
        return by, bx, ay, ax

    def _visual_text(self) -> str:
        y1, x1, y2, x2 = self._visual_range()
        if y1 == y2:
            line = self.st.lines[y1]
            x2c = min(x2 + 1, len(line))
            return line[x1:x2c]
        parts = [self.st.lines[y1][x1:]]
        for y in range(y1 + 1, y2):
            parts.append(self.st.lines[y])
        parts.append(self.st.lines[y2][: min(x2 + 1, len(self.st.lines[y2]))])
        return "\n".join(parts)

    def _delete_visual(self) -> None:
        self._snapshot()
        y1, x1, y2, x2 = self._visual_range()
        self.st.clipboard = self._visual_text()
        if y1 == y2:
            line = self.st.lines[y1]
            x2c = min(x2 + 1, len(line))
            self.st.lines[y1] = line[:x1] + line[x2c:]
        else:
            first = self.st.lines[y1][:x1]
            last = self.st.lines[y2][min(x2 + 1, len(self.st.lines[y2])) :]
            del self.st.lines[y1 : y2 + 1]
            self.st.lines.insert(y1, first + last)
        self.st.cy, self.st.cx = y1, x1
        self.st.dirty = True
        self.st.mode = "NORMAL"
        self.st.visual_anchor = None
        self._invalidate_hl()

    def _search(self, pat: str, direction: int, from_next: bool = True) -> bool:
        if not pat:
            return False
        try:
            rx = re.compile(pat)
        except re.error as e:
            self.st.message = f"无效正则: {e}"
            return False
        n = len(self.st.lines)
        start_y = self.st.cy
        start_x = self.st.cx + (1 if from_next and direction > 0 else 0)
        if direction < 0 and from_next:
            start_x = self.st.cx
        order = range(n) if direction > 0 else range(n - 1, -1, -1)
        # 从当前行扫起再绕一圈
        ys = list(range(start_y, n)) + list(range(0, start_y))
        if direction < 0:
            ys = list(range(start_y, -1, -1)) + list(range(n - 1, start_y, -1))
        first = True
        for y in ys:
            line = self.st.lines[y]
            if direction > 0:
                x0 = start_x if first and y == start_y else 0
                m = rx.search(line, x0)
            else:
                x0 = start_x if first and y == start_y else len(line)
                last = None
                for m in rx.finditer(line):
                    if m.start() < x0:
                        last = m
                    else:
                        break
                m = last
            first = False
            if m:
                self.st.cy = y
                self.st.cx = m.start()
                self.st.message = f"/{pat}" if direction > 0 else f"?{pat}"
                return True
        self.st.message = f"未找到: {pat}"
        return False

    # ---------- 命令 ----------
    def _run_command(self, raw: str) -> bool:
        """返回 True 表示请求退出编辑器。"""
        cmd = raw.strip()
        if not cmd:
            return False

        # 数字当作跳行
        if cmd.isdigit():
            self.st.cy = min(len(self.st.lines) - 1, max(0, int(cmd) - 1))
            self.st.cx = 0
            return False

        parts = cmd.split(None, 1)
        head = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if head in ("q", "quit"):
            if self.st.mode == "HELP":
                self.st.mode = "NORMAL"
                return False
            if self.st.dirty:
                self.st.message = "有未保存修改，使用 :q! 强制退出"
                return False
            return True
        if head in ("q!", "quit!"):
            return True
        if head in ("wq", "x"):
            if self._save(arg or None):
                return True
            return False
        if head == "w" or head == "write":
            self._save(arg or None)
            return False
        if head in ("e", "edit"):
            if not arg:
                self.st.message = "用法: :e 文件名"
            elif self.st.dirty:
                self.st.message = "有未保存修改，先 :w 或丢弃后重开"
            else:
                self._open(arg)
            return False
        if head in ("h", "help"):
            self.st.mode = "HELP"
            self.st.help_top = 0
            return False
        if head == "set":
            self._cmd_set(arg)
            return False
        if head == "syntax":
            self._cmd_syntax(arg)
            return False
        self.st.message = f"未知命令: {cmd}"
        return False

    def _cmd_set(self, arg: str) -> None:
        a = arg.strip()
        if a in ("nu", "number"):
            self.st.show_lineno = True
            self.st.message = "行号: 开"
        elif a in ("nonu", "nonumber"):
            self.st.show_lineno = False
            self.st.message = "行号: 关"
        elif a.startswith("ft=") or a.startswith("filetype="):
            lang = a.split("=", 1)[1].strip()
            if lang in self.hl.specs:
                self.st.filetype = lang
                self._invalidate_hl()
                self.st.message = f"文件类型: {lang}"
            else:
                self.st.message = f"未知类型: {lang}  (见 :syntax list)"
        else:
            self.st.message = "用法: :set nu|nonu  或  :set ft=python"

    def _cmd_syntax(self, arg: str) -> None:
        a = arg.strip()
        if a == "on":
            self.st.highlight_on = True
            self._invalidate_hl()
            self.st.message = "语法高亮: 开"
        elif a == "off":
            self.st.highlight_on = False
            self.st.message = "语法高亮: 关"
        elif a == "reset":
            self.hl.reset(BUILTIN_SYNTAX)
            self.st.filetype = None
            self._invalidate_hl()
            self.st.message = "已恢复内置语法配置"
        elif a == "list":
            names = ", ".join(sorted(self.hl.specs.keys()))
            self.st.message = "语言: " + names
        elif a.startswith("load ") or a.startswith("file "):
            path = a.split(None, 1)[1]
            try:
                added = self._load_syntax_file(path)
                self.st.message = "已加载: " + (", ".join(added) if added else path)
            except Exception as e:
                self.st.message = f"加载失败: {e}"
        else:
            self.st.message = "用法: :syntax on|off|reset|list|load PATH"

    # ---------- 绘制 ----------
    def _init_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()
        # pair: fg, bg  (-1 = default)
        curses.init_pair(1, curses.COLOR_MAGENTA, -1)  # keyword
        curses.init_pair(2, curses.COLOR_CYAN, -1)  # type
        curses.init_pair(3, curses.COLOR_YELLOW, -1)  # builtin
        curses.init_pair(4, curses.COLOR_GREEN, -1)  # comment
        curses.init_pair(5, curses.COLOR_RED, -1)  # string
        curses.init_pair(6, curses.COLOR_BLUE, -1)  # number
        curses.init_pair(7, curses.COLOR_WHITE, -1)  # extra
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_WHITE)  # lineno fallback
        try:
            curses.init_pair(8, 8, -1)  # grey lineno if available
        except curses.error:
            curses.init_pair(8, curses.COLOR_WHITE, -1)
        curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_CYAN)  # status
        curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # visual
        curses.init_pair(12, curses.COLOR_BLACK, curses.COLOR_GREEN)  # search
        curses.init_pair(13, curses.COLOR_YELLOW, -1)

    def _gutter_width(self) -> int:
        if not self.st.show_lineno:
            return 0
        return max(4, len(str(len(self.st.lines))) + 1)

    def _attr(self, style: str) -> int:
        pid = STYLE_MAP.get(style, 0)
        if not pid:
            return curses.A_NORMAL
        extra = curses.A_BOLD if style in ("keyword", "status") else 0
        if style == "comment":
            extra = curses.A_DIM
        return curses.color_pair(pid) | extra

    def _is_visual_pos(self, y: int, x: int) -> bool:
        if self.st.mode != "VISUAL" or self.st.visual_anchor is None:
            return False
        y1, x1, y2, x2 = self._visual_range()
        if y < y1 or y > y2:
            return False
        if y1 == y2:
            return x1 <= x <= x2
        if y == y1:
            return x >= x1
        if y == y2:
            return x <= x2
        return True

    def _get_hl(self) -> List[List[Tuple[str, str]]]:
        lang = self.hl.guess_lang(self.st.filename, self.st.filetype)
        key = (id(self.st.lines), lang, len(self.st.lines), self.st.highlight_on)
        # 用内容哈希更稳妥
        sig = (lang, self.st.highlight_on, hash("\n".join(self.st.lines)))
        if self._hl_cache_key == sig:
            return self._hl_cache
        if not self.st.highlight_on:
            self._hl_cache = [[(ln, "")] for ln in self.st.lines]
        else:
            self._hl_cache = self.hl.highlight_lines(self.st.lines, lang)
        self._hl_cache_key = sig
        return self._hl_cache

    def _draw(self, stdscr) -> None:
        stdscr.erase()
        rows, cols = stdscr.getmaxyx()
        if rows < 3 or cols < 10:
            return

        if self.st.mode == "HELP":
            self._draw_help(stdscr, rows, cols)
            return

        gutter = self._gutter_width()
        self._clamp_x(insert=(self.st.mode == "INSERT"))
        self._ensure_visible(rows, cols, gutter)

        hl_lines = self._get_hl()
        text_rows = rows - 2
        search_rx = None
        if self.st.search_pat:
            try:
                search_rx = re.compile(self.st.search_pat)
            except re.error:
                search_rx = None

        for i in range(text_rows):
            y = self.st.toprow + i
            if y >= len(self.st.lines):
                try:
                    stdscr.addstr(i, 0, "~", self._attr("lineno"))
                except curses.error:
                    pass
                continue
            if gutter:
                num = str(y + 1).rjust(gutter - 1)
                try:
                    stdscr.addstr(i, 0, num + " ", self._attr("lineno"))
                except curses.error:
                    pass

            # 把高亮片段铺到屏幕
            xoff = 0
            spans = hl_lines[y] if y < len(hl_lines) else [(self.st.lines[y], "")]
            # 搜索高亮覆盖：先拼出全行再按列画，便于 visual/search
            built: List[Tuple[str, str]] = []
            for text, style in spans:
                built.append((text, style))
            col = 0
            screen_x = gutter
            for text, style in built:
                for ch in text:
                    if col < self.st.leftcol:
                        col += 1
                        continue
                    if screen_x >= cols:
                        break
                    attr = self._attr(style)
                    if self._is_visual_pos(y, col):
                        attr = self._attr("visual")
                    try:
                        stdscr.addstr(i, screen_x, ch if ch != "\t" else " ", attr)
                    except curses.error:
                        pass
                    screen_x += 1
                    col += 1
            # 搜索匹配再覆盖一层（仅可见列）
            if search_rx:
                line = self.st.lines[y]
                for m in search_rx.finditer(line):
                    for sx in range(m.start(), m.end()):
                        if sx < self.st.leftcol:
                            continue
                        px = gutter + (sx - self.st.leftcol)
                        if 0 <= px < cols:
                            ch = line[sx] if sx < len(line) else " "
                            try:
                                stdscr.addstr(i, px, ch if ch != "\t" else " ", self._attr("search"))
                            except curses.error:
                                pass

        self._draw_status(stdscr, rows, cols, gutter)
        self._draw_cmdline(stdscr, rows, cols)

        # 光标
        vis_y = self.st.cy - self.st.toprow
        vis_x = gutter + (self.st.cx - self.st.leftcol)
        if 0 <= vis_y < text_rows and gutter <= vis_x < cols:
            try:
                stdscr.move(vis_y, vis_x)
            except curses.error:
                pass
        stdscr.refresh()

    def _draw_status(self, stdscr, rows: int, cols: int, gutter: int) -> None:
        lang = self.hl.guess_lang(self.st.filename, self.st.filetype)
        name = self.st.filename or "[未命名]"
        dirty = " [+]" if self.st.dirty else ""
        mode = self.st.mode
        if mode == "INSERT":
            mode_s = "-- INSERT --"
        elif mode == "VISUAL":
            mode_s = "-- VISUAL --"
        elif mode == "COMMAND":
            mode_s = "COMMAND"
        elif mode == "SEARCH":
            mode_s = "SEARCH"
        else:
            mode_s = "NORMAL"
        right = f"{lang}  {self.st.cy + 1},{self.st.cx + 1}  {len(self.st.lines)}L"
        left = f" {mode_s}  {name}{dirty}"
        pad = cols - len(left) - len(right) - 1
        if pad < 1:
            line = (left + " " + right)[: cols - 1]
        else:
            line = left + " " * pad + right
        line = line[: cols - 1].ljust(cols - 1)
        try:
            stdscr.addstr(rows - 2, 0, line, self._attr("status"))
        except curses.error:
            pass

    def _draw_cmdline(self, stdscr, rows: int, cols: int) -> None:
        if self.st.mode == "COMMAND":
            text = ":" + self.st.cmd
        elif self.st.mode == "SEARCH":
            prefix = "/" if self.st.search_dir > 0 else "?"
            text = prefix + self.st.cmd
        elif self.st.pending or self.st.count:
            text = self.st.count + self.st.pending
        else:
            text = self.st.message
        text = text[: cols - 1]
        try:
            stdscr.addstr(rows - 1, 0, text.ljust(cols - 1), self._attr("command"))
        except curses.error:
            pass
        if self.st.mode in ("COMMAND", "SEARCH"):
            try:
                stdscr.move(rows - 1, min(len(text), cols - 1))
            except curses.error:
                pass

    def _draw_help(self, stdscr, rows: int, cols: int) -> None:
        help_lines = HELP_TEXT.split("\n")
        max_top = max(0, len(help_lines) - (rows - 2))
        self.st.help_top = max(0, min(self.st.help_top, max_top))
        for i in range(rows - 2):
            idx = self.st.help_top + i
            if idx >= len(help_lines):
                break
            line = help_lines[idx][: cols - 1]
            attr = curses.A_BOLD if line.startswith("═") or line.startswith("  ") and "模式" in line else curses.A_NORMAL
            if line.startswith("PyVim"):
                attr = self._attr("keyword")
            try:
                stdscr.addstr(i, 0, line.ljust(cols - 1), attr)
            except curses.error:
                pass
        bar = " HELP  j/k 或方向键滚动  :q / Esc / F1 关闭 ".ljust(cols - 1)[: cols - 1]
        try:
            stdscr.addstr(rows - 2, 0, bar, self._attr("status"))
            stdscr.addstr(rows - 1, 0, " " * (cols - 1))
        except curses.error:
            pass
        stdscr.refresh()

    # ---------- 输入 ----------
    def _handle_help_key(self, key: int) -> Optional[bool]:
        if key in (27, curses.KEY_F1, ord("q")):
            self.st.mode = "NORMAL"
        elif key in (ord("j"), curses.KEY_DOWN):
            self.st.help_top += 1
        elif key in (ord("k"), curses.KEY_UP):
            self.st.help_top -= 1
        elif key in (curses.KEY_NPAGE, 6):  # Ctrl-f
            self.st.help_top += 20
        elif key in (curses.KEY_PPAGE, 2):  # Ctrl-b
            self.st.help_top -= 20
        elif key == ord(":"):
            self.st.mode = "COMMAND"
            self.st.cmd = ""
        return None

    def _handle_insert(self, key: int) -> None:
        if key == 27:  # Esc
            self.st.mode = "NORMAL"
            self._clamp_x(False)
            return
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self._backspace()
            return
        if key in (curses.KEY_DC,):
            self._delete_char()
            return
        if key in (curses.KEY_ENTER, 10, 13):
            self._insert_newline()
            return
        if key == curses.KEY_LEFT:
            self.st.cx = max(0, self.st.cx - 1)
            return
        if key == curses.KEY_RIGHT:
            self.st.cx = min(len(self._cur_line()), self.st.cx + 1)
            return
        if key == curses.KEY_UP:
            self.st.cy = max(0, self.st.cy - 1)
            self._clamp_x(True)
            return
        if key == curses.KEY_DOWN:
            self.st.cy = min(len(self.st.lines) - 1, self.st.cy + 1)
            self._clamp_x(True)
            return
        if key == curses.KEY_HOME:
            self.st.cx = 0
            return
        if key == curses.KEY_END:
            self.st.cx = len(self._cur_line())
            return
        if 32 <= key <= 126 or key >= 128:
            try:
                self._insert_char(chr(key))
            except ValueError:
                pass

    def _handle_command_line(self, key: int, kind: str) -> Optional[bool]:
        if key == 27:
            self.st.mode = "NORMAL"
            self.st.cmd = ""
            return None
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if self.st.cmd:
                self.st.cmd = self.st.cmd[:-1]
            else:
                self.st.mode = "NORMAL"
            return None
        if key in (curses.KEY_ENTER, 10, 13):
            text = self.st.cmd
            self.st.cmd = ""
            if kind == "COMMAND":
                self.st.mode = "NORMAL"
                return self._run_command(text)
            else:
                self.st.search_pat = text
                self.st.mode = "NORMAL"
                if text:
                    self._search(text, self.st.search_dir, from_next=False)
            return None
        if 32 <= key <= 126:
            self.st.cmd += chr(key)
        return None

    def _move_vertical(self, delta: int) -> None:
        self.st.cy = max(0, min(len(self.st.lines) - 1, self.st.cy + delta))

    def _handle_normal(self, key: int, rows: int) -> Optional[bool]:
        st = self.st
        # 数字前缀
        if (key >= ord("1") and key <= ord("9")) or (key == ord("0") and st.count):
            st.count += chr(key)
            return None
        count = int(st.count) if st.count else 1
        pending = st.pending

        def clearp() -> None:
            st.pending = ""
            st.count = ""

        if key == 27:
            clearp()
            st.mode = "NORMAL"
            st.visual_anchor = None
            return None
        if key == curses.KEY_F1:
            clearp()
            st.mode = "HELP"
            st.help_top = 0
            return None
        if key == 7:  # Ctrl-g
            clearp()
            name = st.filename or "[未命名]"
            st.message = f'"{name}" {len(st.lines)} 行  {st.cy + 1}:{st.cx + 1}' + (
                " 已修改" if st.dirty else ""
            )
            return None

        # 方向键
        if key == curses.KEY_LEFT:
            key = ord("h")
        elif key == curses.KEY_RIGHT:
            key = ord("l")
        elif key == curses.KEY_UP:
            key = ord("k")
        elif key == curses.KEY_DOWN:
            key = ord("j")

        ch = chr(key) if 32 <= key < 127 else ""

        # dd / yy / gg 等双键
        if pending == "d":
            if ch == "d":
                for _ in range(count):
                    self._delete_line()
            clearp()
            return None
        if pending == "y":
            if ch == "y":
                self._yank_line()
            elif ch == "w":
                word = self._current_word()
                st.clipboard = word
                st.message = f"已复制 {len(word)} 字符"
            clearp()
            return None
        if pending == "g":
            if ch == "g":
                st.cy = 0
                st.cx = 0
            clearp()
            return None
        if pending == "r":
            if 32 <= key <= 126:
                line = self._cur_line()
                if line and st.cx < len(line):
                    self._snapshot()
                    st.lines[st.cy] = line[: st.cx] + chr(key) + line[st.cx + 1 :]
                    st.dirty = True
                    self._invalidate_hl()
            clearp()
            return None

        if ch == "d":
            st.pending = "d"
            return None
        if ch == "y":
            st.pending = "y"
            return None
        if ch == "g":
            st.pending = "g"
            return None
        if ch == "r":
            st.pending = "r"
            return None

        # 移动
        if ch == "h":
            st.cx = max(0, st.cx - count)
        elif ch == "l":
            for _ in range(count):
                line = self._cur_line()
                if st.cx < max(0, len(line) - 1):
                    st.cx += 1
        elif ch == "j":
            self._move_vertical(count)
        elif ch == "k":
            self._move_vertical(-count)
        elif ch == "0":
            st.cx = 0
        elif ch == "^":
            line = self._cur_line()
            i = 0
            while i < len(line) and line[i] in " \t":
                i += 1
            st.cx = i
        elif ch == "$":
            st.cx = max(0, len(self._cur_line()) - 1)
        elif ch == "w":
            for _ in range(count):
                self._word_forward()
        elif ch == "b":
            for _ in range(count):
                self._word_back()
        elif ch == "G":
            if st.count:
                st.cy = min(len(st.lines) - 1, max(0, int(st.count) - 1))
            else:
                st.cy = len(st.lines) - 1
            st.cx = 0
        elif ch == "H":
            st.cy = st.toprow
        elif ch == "L":
            st.cy = min(len(st.lines) - 1, st.toprow + max(0, rows - 3))
        elif ch == "M":
            st.cy = min(len(st.lines) - 1, st.toprow + max(0, rows - 3) // 2)
        elif key in (21,):  # Ctrl-u
            self._move_vertical(-(rows // 2))
        elif key in (4,):  # Ctrl-d
            self._move_vertical(rows // 2)
        elif key in (2, curses.KEY_PPAGE):
            self._move_vertical(-(rows - 2))
        elif key in (6, curses.KEY_NPAGE):
            self._move_vertical(rows - 2)

        # 模式切换 / 编辑
        elif ch == "i":
            st.mode = "INSERT"
        elif ch == "a":
            st.mode = "INSERT"
            line = self._cur_line()
            if line:
                st.cx = min(len(line), st.cx + 1)
        elif ch == "I":
            st.mode = "INSERT"
            line = self._cur_line()
            i = 0
            while i < len(line) and line[i] in " \t":
                i += 1
            st.cx = i
        elif ch == "A":
            st.mode = "INSERT"
            st.cx = len(self._cur_line())
        elif ch == "o":
            self._snapshot()
            st.lines.insert(st.cy + 1, "")
            st.cy += 1
            st.cx = 0
            st.mode = "INSERT"
            st.dirty = True
            self._invalidate_hl()
        elif ch == "O":
            self._snapshot()
            st.lines.insert(st.cy, "")
            st.cx = 0
            st.mode = "INSERT"
            st.dirty = True
            self._invalidate_hl()
        elif ch == "s":
            self._delete_char()
            st.mode = "INSERT"
        elif ch == "x":
            for _ in range(count):
                self._delete_char()
        elif ch == "X":
            for _ in range(count):
                if st.cx > 0:
                    st.cx -= 1
                    self._delete_char()
        elif ch == "D":
            self._snapshot()
            line = self._cur_line()
            st.clipboard = line[st.cx :]
            st.lines[st.cy] = line[: st.cx]
            st.dirty = True
            self._invalidate_hl()
        elif ch == "p":
            self._paste(False)
        elif ch == "P":
            self._paste(True)
        elif ch == "u":
            self._undo()
        elif key == 18:  # Ctrl-r
            self._redo()
        elif ch == "J":
            if st.cy < len(st.lines) - 1:
                self._snapshot()
                a, b = st.lines[st.cy], st.lines[st.cy + 1]
                st.cx = len(a)
                st.lines[st.cy] = a + " " + b if a and b else a + b
                del st.lines[st.cy + 1]
                st.dirty = True
                self._invalidate_hl()
        elif ch == "v":
            st.mode = "VISUAL"
            st.visual_anchor = (st.cy, st.cx)
        elif ch == ":":
            st.mode = "COMMAND"
            st.cmd = ""
        elif ch == "/":
            st.mode = "SEARCH"
            st.search_dir = 1
            st.cmd = ""
        elif ch == "?":
            st.mode = "SEARCH"
            st.search_dir = -1
            st.cmd = ""
        elif ch == "n":
            if st.search_pat:
                self._search(st.search_pat, st.search_dir, True)
        elif ch == "N":
            if st.search_pat:
                self._search(st.search_pat, -st.search_dir, True)
        elif ch == "*":
            w = self._current_word()
            if w:
                st.search_pat = r"\b" + re.escape(w) + r"\b"
                st.search_dir = 1
                self._search(st.search_pat, 1, True)
        else:
            if ch and not pending:
                pass  # 未知键忽略
        clearp()
        return None

    def _handle_visual(self, key: int, rows: int) -> None:
        if key == 27:
            self.st.mode = "NORMAL"
            self.st.visual_anchor = None
            return
        ch = chr(key) if 32 <= key < 127 else ""
        if key == curses.KEY_LEFT:
            ch = "h"
        elif key == curses.KEY_RIGHT:
            ch = "l"
        elif key == curses.KEY_UP:
            ch = "k"
        elif key == curses.KEY_DOWN:
            ch = "j"
        if ch == "h":
            self.st.cx = max(0, self.st.cx - 1)
        elif ch == "l":
            line = self._cur_line()
            if self.st.cx < max(0, len(line) - 1):
                self.st.cx += 1
        elif ch == "j":
            self._move_vertical(1)
        elif ch == "k":
            self._move_vertical(-1)
        elif ch == "0":
            self.st.cx = 0
        elif ch == "$":
            self.st.cx = max(0, len(self._cur_line()) - 1)
        elif ch in ("d", "x"):
            self._delete_visual()
        elif ch == "y":
            self.st.clipboard = self._visual_text()
            self.st.message = "已复制选区"
            self.st.mode = "NORMAL"
            self.st.visual_anchor = None
        elif ch == "v":
            self.st.mode = "NORMAL"
            self.st.visual_anchor = None

    def run(self, stdscr) -> None:
        curses.raw()
        curses.noecho()
        curses.curs_set(1)
        stdscr.keypad(True)
        try:
            self._init_colors()
        except curses.error:
            pass
        if not self.st.message:
            self.st.message = "PyVim  —  :help 查看帮助   F1 打开帮助"

        while True:
            rows, cols = stdscr.getmaxyx()
            self._draw(stdscr)
            try:
                key = stdscr.getch()
            except KeyboardInterrupt:
                key = 3
            if key == curses.KEY_RESIZE:
                continue
            if key == 3:  # Ctrl-c
                if self.st.mode != "NORMAL":
                    self.st.mode = "NORMAL"
                    self.st.cmd = ""
                    continue
                if not self.st.dirty:
                    break
                self.st.message = "有未保存修改，使用 :q! 退出"
                continue

            quit_req: Optional[bool] = None
            mode = self.st.mode
            if mode == "HELP":
                quit_req = self._handle_help_key(key)
            elif mode == "INSERT":
                self._handle_insert(key)
            elif mode == "COMMAND":
                quit_req = self._handle_command_line(key, "COMMAND")
            elif mode == "SEARCH":
                quit_req = self._handle_command_line(key, "SEARCH")
            elif mode == "VISUAL":
                self._handle_visual(key, rows)
            else:
                quit_req = self._handle_normal(key, rows)
            if quit_req:
                break


def print_cli_help() -> None:
    sys.stdout.write(
        """PyVim — 单文件 Python 类 Vim 编辑器

用法:
  python3 pyvim.py [选项] [文件]

选项:
  -h, --help          显示本命令行帮助
  --syntax FILE       启动时加载外部 JSON 语法高亮配置
  --no-color          关闭语法高亮

编辑器内按 :help 或 F1 查看完整快捷键与配置格式。
"""
    )


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--syntax", dest="syntax_file", default=None)
    p.add_argument("--no-color", action="store_true")
    p.add_argument("file", nargs="?", default=None)
    args, unknown = p.parse_known_args(argv)
    if args.help:
        print_cli_help()
        return 0
    if unknown:
        sys.stderr.write("未知参数: " + " ".join(unknown) + "\n")
        print_cli_help()
        return 2
    editor = PyVim(
        filename=args.file,
        syntax_file=args.syntax_file,
        color=not args.no_color,
    )
    try:
        curses.wrapper(editor.run)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
