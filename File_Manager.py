#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
终端文件管理器 (Vim 风格滑动导航)
================================
依赖：Python 3.8+ 标准库（curses / pathlib / shutil）。
Windows 需额外安装：pip install windows-curses

启动：
    python File_Manager.py [起始目录]

按 ? 或 F1 查看完整操作说明。
"""

from __future__ import annotations

import curses
import datetime
import mimetypes
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# 颜色对编号
# ---------------------------------------------------------------------------
C_DEFAULT = 0
C_INDEX = 1
C_DIR = 2
C_FILE = 3
C_SELECTED = 4
C_CURSOR = 5
C_TITLE = 6
C_STATUS = 7
C_WARN = 8
C_EXEC = 9
C_LINK = 10
C_HIDDEN = 11
C_BORDER_ACTIVE = 12
C_BORDER_IDLE = 13
C_HELP = 14
C_HL_KW = 15
C_HL_STR = 16
C_HL_CMT = 17
C_HL_NUM = 18
C_HEX = 19
C_ASCII = 20

# 文本编辑器加载上限，超出则拒绝并提示改用十六进制 / 预览
TEXT_MAX_BYTES = 8 * 1024 * 1024
TEXT_MAX_LINES = 200_000
# 十六进制编辑器内存上限
HEX_MAX_BYTES = 16 * 1024 * 1024


def init_colors() -> None:
    """初始化 curses 调色板。终端不支持颜色时全部退回默认。"""
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    def pair(n, fg, bg_=bg):
        try:
            curses.init_pair(n, fg, bg_)
        except curses.error:
            pass

    pair(C_INDEX, curses.COLOR_YELLOW)
    pair(C_DIR, curses.COLOR_CYAN)
    pair(C_FILE, curses.COLOR_WHITE)
    pair(C_SELECTED, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    pair(C_CURSOR, curses.COLOR_BLACK, curses.COLOR_CYAN)
    pair(C_TITLE, curses.COLOR_BLACK, curses.COLOR_BLUE)
    pair(C_STATUS, curses.COLOR_BLACK, curses.COLOR_GREEN)
    pair(C_WARN, curses.COLOR_WHITE, curses.COLOR_RED)
    pair(C_EXEC, curses.COLOR_GREEN)
    pair(C_LINK, curses.COLOR_MAGENTA)
    pair(C_HIDDEN, curses.COLOR_BLUE)
    pair(C_BORDER_ACTIVE, curses.COLOR_GREEN)
    pair(C_BORDER_IDLE, curses.COLOR_WHITE)
    pair(C_HELP, curses.COLOR_CYAN)
    pair(C_HL_KW, curses.COLOR_MAGENTA)
    pair(C_HL_STR, curses.COLOR_GREEN)
    pair(C_HL_CMT, curses.COLOR_BLUE)
    pair(C_HL_NUM, curses.COLOR_YELLOW)
    pair(C_HEX, curses.COLOR_YELLOW)
    pair(C_ASCII, curses.COLOR_GREEN)


def color(n: int) -> int:
    try:
        return curses.color_pair(n)
    except curses.error:
        return 0


def safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    """写入一行，吞掉越界、宽字符、控制符引起的 curses.error。"""
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x >= w or x < 0:
            return
        cleaned = "".join(
            ch if (ch == " " or (ch.isprintable() and ch != "\t")) else " "
            for ch in text
        )
        room = w - x - 1
        if room <= 0:
            return
        win.addstr(y, x, cleaned[:room], attr)
    except curses.error:
        pass


def sanitize_line(text: str) -> str:
    """去掉会导致 curses 崩溃的控制字符。"""
    return "".join(ch if ch.isprintable() or ch == " " else "·" for ch in text.replace("\t", "    "))


def human_size(n: int) -> str:
    units = ["B", "K", "M", "G", "T"]
    f = float(max(0, n))
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.0f}{u}" if u == "B" else f"{f:.1f}{u}"
        f /= 1024
    return f"{n}B"


def resolve_user_path(raw: str, base: Optional[Path] = None) -> Path:
    """把用户输入的路径展开为绝对路径。支持 ~、$HOME、相对路径。"""
    raw = (raw or "").strip().strip("\"'")
    if not raw:
        return (base or Path.cwd()).resolve()
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not p.is_absolute():
        p = (base or Path.cwd()) / p
    try:
        return p.resolve()
    except OSError:
        return p.absolute()


def looks_binary(data: bytes) -> bool:
    """用 NUL 和控制字符粗判二进制，避免把图片/可执行文件当文本打开。"""
    if not data:
        return False
    sample = data[: 8192]
    if b"\x00" in sample:
        return True
    # 允许常见空白，其余控制符过多则视为二进制
    ctrl = sum(1 for b in sample if b < 32 and b not in (9, 10, 13))
    return ctrl / max(1, len(sample)) > 0.30


def file_kind(p: Path) -> str:
    try:
        if p.is_symlink():
            return "链接"
        if p.is_dir():
            return "文件夹"
        if p.is_file():
            mode = p.stat().st_mode
            if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                return "可执行"
            return "文件"
        if stat.S_ISFIFO(p.lstat().st_mode):
            return "管道"
        if stat.S_ISSOCK(p.lstat().st_mode):
            return "套接字"
        if stat.S_ISCHR(p.lstat().st_mode) or stat.S_ISBLK(p.lstat().st_mode):
            return "设备"
    except OSError:
        return "未知"
    return "其他"


def open_with_system(path: Path) -> str:
    """调用系统默认程序打开。失败只返回错误信息，不抛异常。"""
    try:
        if not path.exists():
            return f"无法打开：路径不存在 {path}"
        if sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(path)])
        elif sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return f"已用系统程序打开 {path.name}"
    except Exception as exc:
        return f"系统打开失败: {exc}"


# ---------------------------------------------------------------------------
# 语法高亮（内置编辑器用）
# ---------------------------------------------------------------------------
LANG_KEYWORDS = {
    ".py": {
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "False", "finally", "for",
        "from", "global", "if", "import", "in", "is", "lambda", "None",
        "nonlocal", "not", "or", "pass", "raise", "return", "True", "try",
        "while", "with", "yield",
    },
    ".js": {
        "break", "case", "catch", "class", "const", "continue", "debugger",
        "default", "delete", "do", "else", "export", "extends", "false",
        "finally", "for", "function", "if", "import", "in", "instanceof",
        "let", "new", "null", "return", "super", "switch", "this", "throw",
        "true", "try", "typeof", "var", "void", "while", "with", "yield",
        "async", "await",
    },
    ".c": {
        "auto", "break", "case", "char", "const", "continue", "default", "do",
        "double", "else", "enum", "extern", "float", "for", "goto", "if",
        "int", "long", "register", "return", "short", "signed", "sizeof",
        "static", "struct", "switch", "typedef", "union", "unsigned", "void",
        "volatile", "while",
    },
}
LANG_KEYWORDS[".h"] = LANG_KEYWORDS[".c"]
LANG_KEYWORDS[".cpp"] = LANG_KEYWORDS[".c"] | {
    "class", "namespace", "template", "public", "private", "protected", "new", "delete", "this",
}
LANG_KEYWORDS[".hpp"] = LANG_KEYWORDS[".cpp"]
LANG_KEYWORDS[".java"] = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "class",
    "const", "continue", "default", "do", "double", "else", "enum", "extends",
    "final", "finally", "float", "for", "goto", "if", "implements", "import",
    "instanceof", "int", "interface", "long", "native", "new", "package",
    "private", "protected", "public", "return", "short", "static", "strictfp",
    "super", "switch", "synchronized", "this", "throw", "throws", "transient",
    "try", "void", "volatile", "while", "true", "false", "null",
}
LANG_KEYWORDS[".ts"] = LANG_KEYWORDS[".js"] | {
    "interface", "type", "implements", "public", "private", "protected", "readonly",
}


def tokenize_line(line: str, ext: str) -> List[Tuple[int, str]]:
    """把一行拆成 (颜色编号, 文本) 片段。"""
    if not line:
        return [(C_FILE, "")]
    stripped = line.lstrip()
    if ext in {".py"} and stripped.startswith("#"):
        return [(C_HL_CMT, line)]
    if ext in {".js", ".ts", ".c", ".h", ".cpp", ".hpp", ".java", ".css"} and stripped.startswith("//"):
        return [(C_HL_CMT, line)]
    if ext in {".html", ".xml"} and stripped.startswith("<!--"):
        return [(C_HL_CMT, line)]

    kws = LANG_KEYWORDS.get(ext, set())
    out: List[Tuple[int, str]] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch in "'\"":
            quote = ch
            j = i + 1
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if line[j] == quote:
                    j += 1
                    break
                j += 1
            out.append((C_HL_STR, line[i:j]))
            i = j
            continue
        if ch == "#" and ext == ".py":
            out.append((C_HL_CMT, line[i:]))
            break
        if ch == "/" and i + 1 < n and line[i + 1] == "/" and ext in {
            ".js", ".ts", ".c", ".h", ".cpp", ".java", ".css",
        }:
            out.append((C_HL_CMT, line[i:]))
            break
        if ch.isdigit():
            j = i + 1
            while j < n and (line[j].isdigit() or line[j] in ".xXaAbBcCdDeEfF"):
                j += 1
            out.append((C_HL_NUM, line[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            out.append((C_HL_KW if word in kws else C_FILE, word))
            i = j
            continue
        out.append((C_FILE, ch))
        i += 1
    return out


# ---------------------------------------------------------------------------
# 面板
# ---------------------------------------------------------------------------
class Pane:
    """单个目录窗格。"""

    SORT_NAME, SORT_SIZE, SORT_MTIME, SORT_TYPE = 0, 1, 2, 3

    def __init__(self, path: Path) -> None:
        try:
            self.path = path.resolve()
        except OSError:
            self.path = path.absolute()
        self.cursor = 0
        self.offset = 0
        self.marked: set = set()
        self.show_hidden = False
        self.sort_mode = self.SORT_NAME
        self.filter_text = ""
        self.entries: List[Path] = []
        self.error = ""
        self.refresh()

    def refresh(self) -> None:
        self.error = ""
        try:
            if not self.path.exists():
                self.error = "目录不存在，已回到上级"
                parent = self.path.parent
                if parent == self.path:
                    self.entries = []
                    return
                self.path = parent
                self.refresh()
                return
            items = list(self.path.iterdir())
        except PermissionError:
            self.error = "权限不足，无法列出目录"
            self.entries = []
            return
        except FileNotFoundError:
            self.error = "目录不存在，已回到上级"
            if self.path.parent != self.path:
                self.path = self.path.parent
                self.refresh()
            return
        except OSError as exc:
            self.error = f"无法读取目录: {exc}"
            self.entries = []
            return

        if not self.show_hidden:
            items = [p for p in items if not p.name.startswith(".")]
        if self.filter_text:
            q = self.filter_text.lower()
            items = [p for p in items if q in p.name.lower()]

        def key(p: Path):
            try:
                is_dir = 0 if p.is_dir() and not p.is_symlink() else 1
            except OSError:
                is_dir = 1
            try:
                st = p.lstat()
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                size, mtime = 0, 0
            name = p.name.lower()
            if self.sort_mode == self.SORT_SIZE:
                return (is_dir, size, name)
            if self.sort_mode == self.SORT_MTIME:
                return (is_dir, -mtime, name)
            if self.sort_mode == self.SORT_TYPE:
                return (is_dir, p.suffix.lower(), name)
            return (is_dir, name)

        try:
            items.sort(key=key)
        except Exception:
            items.sort(key=lambda p: p.name.lower())
        self.entries = items
        if self.cursor >= len(self.entries):
            self.cursor = max(0, len(self.entries) - 1)
        if self.cursor < 0:
            self.cursor = 0
        self.marked = {m for m in self.marked if Path(m).parent == self.path}

    def current(self) -> Optional[Path]:
        if 0 <= self.cursor < len(self.entries):
            return self.entries[self.cursor]
        return None

    def move(self, delta: int) -> None:
        if not self.entries:
            self.cursor = 0
            return
        self.cursor = max(0, min(len(self.entries) - 1, self.cursor + delta))

    def ensure_visible(self, height: int) -> None:
        if height <= 0:
            return
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + height:
            self.offset = self.cursor - height + 1
        max_off = max(0, len(self.entries) - height)
        self.offset = max(0, min(self.offset, max_off))

    def chdir(self, new_path: Path) -> str:
        """切换目录，返回状态信息（失败不抛）。"""
        try:
            new_path = resolve_user_path(str(new_path), self.path)
        except Exception as exc:
            self.error = f"路径无效: {exc}"
            return self.error
        try:
            if not new_path.exists():
                self.error = f"路径不存在: {new_path}"
                return self.error
            if new_path.is_file():
                self.error = ""
                # 调用方若传入文件，跳到所在目录并定位该文件
                parent = new_path.parent
                name = new_path.name
                self.path = parent
                self.cursor = 0
                self.offset = 0
                self.filter_text = ""
                self.refresh()
                for i, p in enumerate(self.entries):
                    if p.name == name:
                        self.cursor = i
                        break
                return f"已定位文件 {name}"
            if not new_path.is_dir():
                self.error = f"不是目录: {new_path}"
                return self.error
        except OSError as exc:
            self.error = f"无法进入: {exc}"
            return self.error
        old = self.path
        self.path = new_path
        self.cursor = 0
        self.offset = 0
        self.filter_text = ""
        self.refresh()
        if old.parent == self.path:
            for i, p in enumerate(self.entries):
                if p == old:
                    self.cursor = i
                    break
        return str(self.path)


# ---------------------------------------------------------------------------
# 底部输入
# ---------------------------------------------------------------------------
def prompt(stdscr, title: str, default: str = "") -> Optional[str]:
    """底部输入一行。Esc 取消，返回 None。可处理宽字符与功能键。"""
    h, w = stdscr.getmaxyx()
    buf = list(default)
    pos = len(buf)
    curses.curs_set(1)
    try:
        while True:
            h, w = stdscr.getmaxyx()
            line = "".join(buf)
            shown = f"{title}: {line}"
            try:
                stdscr.attron(color(C_STATUS))
                stdscr.addstr(h - 1, 0, " " * max(0, w - 1))
                safe_addstr(stdscr, h - 1, 0, shown, color(C_STATUS))
                stdscr.attroff(color(C_STATUS))
            except curses.error:
                pass
            curx = min(w - 2, max(0, len(title) + 2 + pos))
            try:
                stdscr.move(h - 1, curx)
            except curses.error:
                pass
            stdscr.refresh()
            try:
                ch = stdscr.get_wch()
            except curses.error:
                continue
            if ch in ("\x1b",):
                return None
            if ch in ("\n", "\r"):
                return "".join(buf)
            if ch in ("\x7f", "\b", curses.KEY_BACKSPACE):
                if pos > 0:
                    del buf[pos - 1]
                    pos -= 1
                continue
            if ch == curses.KEY_LEFT:
                pos = max(0, pos - 1)
                continue
            if ch == curses.KEY_RIGHT:
                pos = min(len(buf), pos + 1)
                continue
            if ch == curses.KEY_HOME:
                pos = 0
                continue
            if ch == curses.KEY_END:
                pos = len(buf)
                continue
            if ch == curses.KEY_DC and pos < len(buf):
                del buf[pos]
                continue
            if ch == curses.KEY_RESIZE:
                continue
            if isinstance(ch, str) and ch.isprintable():
                buf.insert(pos, ch)
                pos += 1
    finally:
        curses.curs_set(0)


def confirm(stdscr, msg: str) -> bool:
    ans = prompt(stdscr, f"{msg} [y/N]", "")
    return bool(ans) and ans.lower() in {"y", "yes", "是"}


def message(stdscr, msg: str, warn: bool = False) -> None:
    h, w = stdscr.getmaxyx()
    attr = color(C_WARN if warn else C_STATUS)
    try:
        stdscr.attron(attr)
        stdscr.addstr(h - 1, 0, " " * max(0, w - 1))
        stdscr.attroff(attr)
    except curses.error:
        pass
    safe_addstr(stdscr, h - 1, 0, msg, attr)
    stdscr.refresh()


# ---------------------------------------------------------------------------
# 内置类 Vim 文本编辑器（大文件分页）
# ---------------------------------------------------------------------------
EDITOR_HELP = """\
内置文本编辑器帮助（q / Esc 返回）
================================
模式
  Esc           回到 Normal
  i / a         光标前 / 后插入
  I / A         行首 / 行尾插入
  o / O         下方 / 上方新开一行

移动
  h j k l       左 下 上 右
  0 / $ / ^     行首 / 行尾 / 第一个非空
  gg / G        文件头 / 文件尾
  w / b         下一词 / 上一词
  Ctrl-d / u    半页
  Ctrl-f / b    整页下 / 上（分页）
  PgDn / PgUp   整页
  :数字         跳到指定行，如 :120

分页（行数很多时自动按屏幕高度分页）
  标题栏显示  行 当前/总行  页 当前/总页
  只渲染当前页，避免大文件卡死界面

编辑
  x             删除字符
  dd / yy / p   删行 / 复制行 / 粘贴
  u / Ctrl-r    撤销 / 重做

查找
  /pattern      查找   n / N 下一个 / 上一个

命令
  :w  :q  :q!  :wq  :e  :help
  :n / :N       下一页 / 上一页

二进制文件请改用十六进制编辑器（文件管理器按 x）。
""".splitlines()


class Editor:
    """极简 modal 文本编辑器。大文件只渲染当前页。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: List[str] = [""]
        self.y = 0
        self.x = 0
        self.row_off = 0
        self.col_off = 0
        self.mode = "NORMAL"
        self.dirty = False
        self.cmd = ""
        self.status = ""
        self.yank = ""
        self.undo: List[Tuple[List[str], int, int]] = []
        self.redo: List[Tuple[List[str], int, int]] = []
        self.last_find = ""
        self.pending = ""
        self.ext = path.suffix.lower()
        self.truncated = False
        self.error = self._load()

    def snapshot(self) -> None:
        # 大文件不保存完整快照，避免内存暴涨
        if len(self.lines) > 20_000:
            self.undo.append(([], self.y, self.x))  # 占位，撤销不可用
            self.status = "文件过大，撤销已禁用"
            return
        self.undo.append(([ln[:] for ln in self.lines], self.y, self.x))
        if len(self.undo) > 60:
            self.undo.pop(0)
        self.redo.clear()

    def _load(self) -> str:
        try:
            if not self.path.exists():
                return f"无法打开：文件不存在 {self.path}"
            if self.path.is_dir():
                return f"无法打开：这是目录 {self.path}"
            st = self.path.stat()
            if not stat.S_ISREG(st.st_mode):
                return f"无法打开：不是普通文件 ({file_kind(self.path)})"
            if st.st_size > TEXT_MAX_BYTES:
                return (
                    f"无法用文本编辑器打开：文件 {human_size(st.st_size)} 超过 "
                    f"{human_size(TEXT_MAX_BYTES)}，请改用十六进制编辑器 (x)"
                )
            data = self.path.read_bytes()
        except PermissionError:
            return "无法打开：权限不足"
        except OSError as exc:
            return f"无法打开: {exc}"
        except Exception as exc:
            return f"无法打开: {exc}"

        if looks_binary(data):
            return (
                f"无法用文本编辑器打开：{self.path.name} 像是二进制文件，"
                "请按 x 用十六进制编辑器，或按 s 用系统程序打开"
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("gb18030")
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
                self.status = "编码不完全是 UTF-8，已替换非法字节"
        raw_lines = text.splitlines()
        if len(raw_lines) > TEXT_MAX_LINES:
            self.lines = raw_lines[:TEXT_MAX_LINES]
            self.truncated = True
            self.dirty = False
            return ""
        self.lines = raw_lines or [""]
        self.dirty = False
        return ""

    def save(self) -> str:
        if self.truncated:
            return "文件被截断加载，拒绝保存以免丢数据。请用十六进制编辑器"
        try:
            text = "\n".join(self.lines)
            if not text.endswith("\n"):
                text += "\n"
            self.path.write_text(text, encoding="utf-8")
            self.dirty = False
            return f"已写入 {self.path}"
        except Exception as exc:
            return f"保存失败: {exc}"

    def clamp(self) -> None:
        if not self.lines:
            self.lines = [""]
        self.y = max(0, min(self.y, len(self.lines) - 1))
        self.x = max(0, min(self.x, len(self.lines[self.y])))

    def page_height(self, term_h: int) -> int:
        return max(1, term_h - 2)

    def page_info(self, term_h: int) -> Tuple[int, int, int]:
        """返回 (当前页 1-based, 总页, 页高)。"""
        ph = self.page_height(term_h)
        total = max(1, (len(self.lines) + ph - 1) // ph)
        cur = self.y // ph + 1
        return cur, total, ph

    def goto_page(self, page: int, term_h: int) -> None:
        ph = self.page_height(term_h)
        total = max(1, (len(self.lines) + ph - 1) // ph)
        page = max(1, min(total, page))
        self.y = (page - 1) * ph
        self.x = 0

    def run(self, stdscr) -> None:
        if self.error:
            message(stdscr, self.error, warn=True)
            try:
                stdscr.get_wch()
            except curses.error:
                pass
            return
        if self.truncated:
            self.status = f"行数过多，仅加载前 {TEXT_MAX_LINES} 行（只读）"
        curses.curs_set(1)
        showing_help = False
        help_off = 0
        try:
            while True:
                h, w = stdscr.getmaxyx()
                if showing_help:
                    help_off = self._draw_help(stdscr, help_off)
                    try:
                        ch = stdscr.get_wch()
                    except curses.error:
                        continue
                    if ch in ("q", "\x1b"):
                        showing_help = False
                    elif ch in ("j", curses.KEY_DOWN):
                        help_off += 1
                    elif ch in ("k", curses.KEY_UP):
                        help_off = max(0, help_off - 1)
                    continue
                self._draw(stdscr)
                try:
                    key = stdscr.get_wch()
                except curses.error:
                    continue
                if key == curses.KEY_RESIZE:
                    continue
                if self.mode == "INSERT":
                    self._insert_key(key)
                elif self.mode == "COMMAND":
                    action = self._command_key(key, h)
                    if action == "quit":
                        break
                    if action == "help":
                        showing_help = True
                elif self.mode == "SEARCH":
                    self._search_key(key)
                else:
                    action = self._normal_key(key, h)
                    if action == "quit":
                        if self.dirty:
                            self.status = "有未保存修改，使用 :q! 强制退出或 :wq 保存"
                            continue
                        break
                    if action == "help":
                        showing_help = True
        except Exception as exc:
            message(stdscr, f"编辑器异常已退出: {exc}", warn=True)
            try:
                stdscr.get_wch()
            except curses.error:
                pass
        finally:
            curses.curs_set(0)

    def _draw_help(self, stdscr, off: int) -> int:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        off = max(0, min(off, max(0, len(EDITOR_HELP) - h + 1)))
        for i in range(h - 1):
            li = off + i
            if li < len(EDITOR_HELP):
                safe_addstr(stdscr, i, 0, EDITOR_HELP[li], color(C_HELP))
        safe_addstr(stdscr, h - 1, 0, "j/k 滑动  q 返回编辑器", color(C_STATUS))
        stdscr.refresh()
        return off

    def _draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        text_h = max(1, h - 2)
        self.clamp()
        # 按页对齐：光标所在页的第一行作为 row_off
        page, pages, ph = self.page_info(h)
        page_start = (page - 1) * ph
        self.row_off = page_start
        if self.x < self.col_off:
            self.col_off = self.x
        vis_w = max(8, w - 8)
        if self.x >= self.col_off + vis_w:
            self.col_off = self.x - vis_w + 1

        gutter_w = max(4, len(str(len(self.lines)))) + 1
        for i in range(text_h):
            li = self.row_off + i
            if li >= len(self.lines):
                break
            raw = sanitize_line(self.lines[li])
            visible = raw[self.col_off :]
            gutter = f"{li + 1:>{gutter_w - 1}} "
            safe_addstr(stdscr, i, 0, gutter[:w], color(C_INDEX))
            col = min(gutter_w, w - 1)
            for cpair, chunk in tokenize_line(visible, self.ext):
                if col >= w - 1:
                    break
                piece = chunk[: max(0, w - 1 - col)]
                safe_addstr(stdscr, i, col, piece, color(cpair))
                col += len(piece)

        flag = "+" if self.dirty else " "
        cut = " 截断" if self.truncated else ""
        title = (
            f" {self.path.name} [{self.mode}]{flag}{cut}  "
            f"行 {self.y + 1}/{len(self.lines)}  "
            f"页 {page}/{pages}  列 {self.x + 1}  :help "
        )
        safe_addstr(stdscr, h - 2, 0, title.ljust(max(0, w - 1)), color(C_TITLE))
        bar = self.status
        if self.mode == "COMMAND":
            bar = ":" + self.cmd
        elif self.mode == "SEARCH":
            bar = "/" + self.cmd
        safe_addstr(stdscr, h - 1, 0, (bar or "").ljust(max(0, w - 1)), color(C_STATUS))
        cx = min(w - 2, gutter_w + max(0, self.x - self.col_off))
        cy = self.y - self.row_off
        if 0 <= cy < text_h:
            try:
                stdscr.move(cy, cx)
            except curses.error:
                pass
        stdscr.refresh()

    def _insert_key(self, key) -> None:
        if key == "\x1b":
            self.mode = "NORMAL"
            self.x = max(0, self.x - 1)
            return
        if self.truncated:
            self.status = "截断加载，禁止编辑"
            return
        if key in ("\n", "\r"):
            self.snapshot()
            line = self.lines[self.y]
            self.lines[self.y] = line[: self.x]
            self.lines.insert(self.y + 1, line[self.x :])
            self.y += 1
            self.x = 0
            self.dirty = True
            return
        if key in ("\x7f", "\b", curses.KEY_BACKSPACE):
            self.snapshot()
            if self.x > 0:
                line = self.lines[self.y]
                self.lines[self.y] = line[: self.x - 1] + line[self.x :]
                self.x -= 1
            elif self.y > 0:
                prev = self.lines[self.y - 1]
                self.x = len(prev)
                self.lines[self.y - 1] = prev + self.lines[self.y]
                del self.lines[self.y]
                self.y -= 1
            self.dirty = True
            return
        if isinstance(key, str) and key.isprintable():
            self.snapshot()
            line = self.lines[self.y]
            self.lines[self.y] = line[: self.x] + key + line[self.x :]
            self.x += 1
            self.dirty = True
            return
        if key == curses.KEY_LEFT:
            self.x = max(0, self.x - 1)
        elif key == curses.KEY_RIGHT:
            self.x = min(len(self.lines[self.y]), self.x + 1)
        elif key == curses.KEY_UP:
            self.y = max(0, self.y - 1)
        elif key == curses.KEY_DOWN:
            self.y = min(len(self.lines) - 1, self.y + 1)

    def _command_key(self, key, term_h: int) -> str:
        if key == "\x1b":
            self.mode = "NORMAL"
            self.cmd = ""
            return ""
        if key in ("\x7f", "\b", curses.KEY_BACKSPACE):
            self.cmd = self.cmd[:-1]
            return ""
        if key not in ("\n", "\r"):
            if isinstance(key, str) and key.isprintable():
                self.cmd += key
            return ""
        c = self.cmd.strip()
        self.cmd = ""
        self.mode = "NORMAL"
        if c in {"q", "quit"}:
            return "quit"
        if c in {"q!", "quit!"}:
            self.dirty = False
            return "quit"
        if c in {"w", "write"}:
            self.status = self.save()
        elif c in {"wq", "x"}:
            self.status = self.save()
            if not self.dirty:
                return "quit"
        elif c == "e":
            self.error = self._load()
            self.status = self.error or "已重新加载"
            if self.error:
                return "quit"
        elif c == "help":
            return "help"
        elif c in {"n", "pn"}:
            page, pages, _ = self.page_info(term_h)
            self.goto_page(page + 1, term_h)
            self.status = f"第 {min(page + 1, pages)} 页"
        elif c in {"N", "pp"}:
            page, _, _ = self.page_info(term_h)
            self.goto_page(page - 1, term_h)
            self.status = f"第 {max(1, page - 1)} 页"
        elif c.isdigit():
            self.y = max(0, min(len(self.lines) - 1, int(c) - 1))
            self.status = f"跳到第 {self.y + 1} 行"
        else:
            self.status = f"未知命令 :{c}"
        return ""

    def _search_key(self, key) -> None:
        if key == "\x1b":
            self.mode = "NORMAL"
            self.cmd = ""
            return
        if key in ("\x7f", "\b", curses.KEY_BACKSPACE):
            self.cmd = self.cmd[:-1]
            return
        if key not in ("\n", "\r"):
            if isinstance(key, str) and key.isprintable():
                self.cmd += key
            return
        self.last_find = self.cmd
        self.cmd = ""
        self.mode = "NORMAL"
        self._find(1)

    def _find(self, direction: int) -> None:
        if not self.last_find:
            self.status = "没有上次查找"
            return
        n = len(self.lines)
        start = self.y + (1 if direction > 0 else -1)
        for step in range(n):
            i = (start + step * direction) % n
            if self.last_find in self.lines[i]:
                self.y = i
                self.x = self.lines[i].find(self.last_find)
                self.status = f"找到: {self.last_find}"
                return
        self.status = f"未找到: {self.last_find}"

    def _normal_key(self, key, term_h: int) -> str:
        self.status = ""
        ph = self.page_height(term_h)
        if self.pending:
            combo = self.pending + (key if isinstance(key, str) else "")
            self.pending = ""
            if combo == "gg":
                self.y = 0
                self.x = 0
                return ""
            if combo == "dd":
                if self.truncated:
                    self.status = "截断加载，禁止编辑"
                    return ""
                self.snapshot()
                self.yank = self.lines[self.y]
                if len(self.lines) == 1:
                    self.lines = [""]
                else:
                    del self.lines[self.y]
                    if self.y >= len(self.lines):
                        self.y = len(self.lines) - 1
                self.dirty = True
                return ""
            if combo == "yy":
                self.yank = self.lines[self.y]
                self.status = "已复制一行"
                return ""

        if key == "g":
            self.pending = "g"
            return ""
        if key == "d":
            self.pending = "d"
            return ""
        if key == "y":
            self.pending = "y"
            return ""
        if key == "q":
            return "quit"
        if key == "?":
            return "help"
        if key == "i":
            self.mode = "INSERT"
        elif key == "a":
            self.mode = "INSERT"
            self.x = min(len(self.lines[self.y]), self.x + 1)
        elif key == "I":
            self.mode = "INSERT"
            self.x = 0
        elif key == "A":
            self.mode = "INSERT"
            self.x = len(self.lines[self.y])
        elif key == "o":
            if self.truncated:
                self.status = "截断加载，禁止编辑"
                return ""
            self.snapshot()
            self.lines.insert(self.y + 1, "")
            self.y += 1
            self.x = 0
            self.mode = "INSERT"
            self.dirty = True
        elif key == "O":
            if self.truncated:
                self.status = "截断加载，禁止编辑"
                return ""
            self.snapshot()
            self.lines.insert(self.y, "")
            self.x = 0
            self.mode = "INSERT"
            self.dirty = True
        elif key in ("h", curses.KEY_LEFT):
            self.x = max(0, self.x - 1)
        elif key in ("l", curses.KEY_RIGHT):
            self.x = min(len(self.lines[self.y]), self.x + 1)
        elif key in ("j", curses.KEY_DOWN):
            self.y = min(len(self.lines) - 1, self.y + 1)
        elif key in ("k", curses.KEY_UP):
            self.y = max(0, self.y - 1)
        elif key == "0":
            self.x = 0
        elif key == "$":
            self.x = len(self.lines[self.y])
        elif key == "^":
            s = self.lines[self.y]
            self.x = len(s) - len(s.lstrip()) if s.strip() else 0
        elif key == "G":
            self.y = len(self.lines) - 1
        elif key == "x":
            if self.truncated:
                return ""
            self.snapshot()
            line = self.lines[self.y]
            if self.x < len(line):
                self.lines[self.y] = line[: self.x] + line[self.x + 1 :]
                self.dirty = True
        elif key == "p":
            if self.yank and not self.truncated:
                self.snapshot()
                self.lines.insert(self.y + 1, self.yank)
                self.y += 1
                self.dirty = True
        elif key == "P":
            if self.yank and not self.truncated:
                self.snapshot()
                self.lines.insert(self.y, self.yank)
                self.dirty = True
        elif key == "u":
            if self.undo and self.undo[-1][0]:
                self.redo.append(([ln[:] for ln in self.lines], self.y, self.x))
                self.lines, self.y, self.x = self.undo.pop()
                self.dirty = True
            else:
                self.status = "无法撤销"
        elif key == "\x12":
            if self.redo:
                self.undo.append(([ln[:] for ln in self.lines], self.y, self.x))
                self.lines, self.y, self.x = self.redo.pop()
                self.dirty = True
        elif key == "\x04":
            self.y = min(len(self.lines) - 1, self.y + max(1, ph // 2))
        elif key == "\x15":
            self.y = max(0, self.y - max(1, ph // 2))
        elif key in ("\x06", curses.KEY_NPAGE):  # Ctrl-f
            self.y = min(len(self.lines) - 1, self.y + ph)
        elif key in ("\x02", curses.KEY_PPAGE):  # Ctrl-b
            self.y = max(0, self.y - ph)
        elif key == "/":
            self.mode = "SEARCH"
            self.cmd = ""
        elif key == "n":
            self._find(1)
        elif key == "N":
            self._find(-1)
        elif key == ":":
            self.mode = "COMMAND"
            self.cmd = ""
        elif key == "w":
            line = self.lines[self.y]
            i = self.x
            while i < len(line) and line[i].isalnum():
                i += 1
            while i < len(line) and not line[i].isalnum():
                i += 1
            self.x = min(len(line), i)
        elif key == "b":
            line = self.lines[self.y]
            i = max(0, self.x - 1)
            while i > 0 and not line[i].isalnum():
                i -= 1
            while i > 0 and line[i - 1].isalnum():
                i -= 1
            self.x = i
        return ""


# ---------------------------------------------------------------------------
# 十六进制 / 二进制编辑器
# ---------------------------------------------------------------------------
HEX_HELP = """\
十六进制 / 二进制编辑器（q / Esc 返回帮助后回编辑器）
================================================
视图
  Tab / t       在 HEX（十六进制）和 BIN（二进制位）之间切换
  每行默认 16 字节：偏移 | 数据 | ASCII

移动
  h j k l / 方向键     按字节移动
  gg / G               文件头 / 尾
  Ctrl-f / Ctrl-b      整页
  :偏移                跳到字节偏移，支持 1024 或 0x1A0

编辑
  0-9 a-f              HEX 视图下直接改当前半字节
  0/1                  BIN 视图下改当前比特
  x                    把当前字节置 0
  i                    在当前偏移插入 1 个 0x00
  X / Del              删除当前字节
  可打印字符            ASCII 区可直接覆盖（先按 A 进入 ASCII 编辑）
  A                    切换是否用键盘直接写 ASCII

查找
  /                    查找：可输入 hello 或 hex:6c6c6f

命令
  :w  :q  :q!  :wq  :help
  :goto N              跳转偏移

注意
  大于 16MB 的文件只只读打开前 16MB，禁止保存。
""".splitlines()


class HexEditor:
    """十六进制 + 二进制位视图，可就地改字节。"""

    COLS = 16

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = bytearray()
        self.offset = 0
        self.row_off = 0
        self.dirty = False
        self.mode = "HEX"  # HEX / BIN
        self.ascii_edit = False
        self.nibble = 0  # HEX 下 0=高半字节 1=低半字节
        self.bit = 7      # BIN 下当前比特 7..0
        self.cmd_mode = ""  # "" / ":" / "/"
        self.cmd = ""
        self.status = ""
        self.truncated = False
        self.pending = ""
        self.error = self._load()

    def _load(self) -> str:
        try:
            if not self.path.exists():
                return f"无法打开：文件不存在 {self.path}"
            if self.path.is_dir():
                return f"无法打开：这是目录 {self.path}"
            st = self.path.stat()
            if not stat.S_ISREG(st.st_mode):
                return f"无法打开：不是普通文件 ({file_kind(self.path)})"
            size = st.st_size
            with open(self.path, "rb") as fh:
                if size > HEX_MAX_BYTES:
                    self.data = bytearray(fh.read(HEX_MAX_BYTES))
                    self.truncated = True
                else:
                    self.data = bytearray(fh.read())
            if self.truncated:
                self.status = f"文件 {human_size(size)}，仅加载前 {human_size(HEX_MAX_BYTES)}（只读）"
            return ""
        except PermissionError:
            return "无法打开：权限不足"
        except OSError as exc:
            return f"无法打开: {exc}"
        except Exception as exc:
            return f"无法打开: {exc}"

    def save(self) -> str:
        if self.truncated:
            return "文件被截断加载，拒绝保存以免丢数据"
        try:
            with open(self.path, "wb") as fh:
                fh.write(self.data)
            self.dirty = False
            return f"已写入 {len(self.data)} 字节 → {self.path}"
        except Exception as exc:
            return f"保存失败: {exc}"

    def run(self, stdscr) -> None:
        if self.error:
            message(stdscr, self.error, warn=True)
            try:
                stdscr.get_wch()
            except curses.error:
                pass
            return
        showing_help = False
        help_off = 0
        curses.curs_set(0)
        try:
            while True:
                if showing_help:
                    help_off = self._draw_help(stdscr, help_off)
                    try:
                        ch = stdscr.get_wch()
                    except curses.error:
                        continue
                    if ch in ("q", "\x1b"):
                        showing_help = False
                    elif ch in ("j", curses.KEY_DOWN):
                        help_off += 1
                    elif ch in ("k", curses.KEY_UP):
                        help_off = max(0, help_off - 1)
                    continue
                self._draw(stdscr)
                try:
                    key = stdscr.get_wch()
                except curses.error:
                    continue
                if key == curses.KEY_RESIZE:
                    continue
                if self.cmd_mode:
                    action = self._cmd_key(key)
                    if action == "quit":
                        break
                    if action == "help":
                        showing_help = True
                    continue
                action = self._key(key, stdscr)
                if action == "quit":
                    if self.dirty:
                        self.status = "有未保存修改，:w 保存  :q! 丢弃"
                        continue
                    break
                if action == "help":
                    showing_help = True
        except Exception as exc:
            message(stdscr, f"十六进制编辑器异常已退出: {exc}", warn=True)
            try:
                stdscr.get_wch()
            except curses.error:
                pass

    def _draw_help(self, stdscr, off: int) -> int:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        off = max(0, min(off, max(0, len(HEX_HELP) - h + 1)))
        for i in range(h - 1):
            li = off + i
            if li < len(HEX_HELP):
                safe_addstr(stdscr, i, 0, HEX_HELP[li], color(C_HELP))
        safe_addstr(stdscr, h - 1, 0, "j/k 滑动  q 返回", color(C_STATUS))
        stdscr.refresh()
        return off

    def _rows_on_screen(self, h: int) -> int:
        return max(1, h - 2)

    def _draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        rows = self._rows_on_screen(h)
        max_off = max(0, (max(1, len(self.data)) - 1) // self.COLS)
        cur_row = self.offset // self.COLS
        if cur_row < self.row_off:
            self.row_off = cur_row
        if cur_row >= self.row_off + rows:
            self.row_off = cur_row - rows + 1
        self.row_off = max(0, min(self.row_off, max(0, max_off - rows + 1)))

        for i in range(rows):
            base = (self.row_off + i) * self.COLS
            if base > len(self.data) and not self.data and i > 0:
                break
            if base >= len(self.data) and self.data:
                break
            chunk = bytes(self.data[base : base + self.COLS])
            addr = f"{base:08X}  "
            safe_addstr(stdscr, i, 0, addr, color(C_INDEX))
            col = 10
            if self.mode == "BIN":
                # 每字节 8 位 + 空格，空间不够就少画几列
                for bi, byte in enumerate(chunk):
                    bits = f"{byte:08b}"
                    for bit_i, bit_ch in enumerate(bits):
                        on = (
                            base + bi == self.offset
                            and (7 - bit_i) == self.bit
                        )
                        attr = color(C_CURSOR) if on else color(C_HEX)
                        if col < w - 1:
                            safe_addstr(stdscr, i, col, bit_ch, attr)
                        col += 1
                    if col < w - 1:
                        safe_addstr(stdscr, i, col, " ", 0)
                    col += 1
            else:
                for bi in range(self.COLS):
                    if bi == 8 and col < w - 1:
                        safe_addstr(stdscr, i, col, " ", 0)
                        col += 1
                    if bi < len(chunk):
                        hx = f"{chunk[bi]:02X}"
                        on = base + bi == self.offset
                        attr = color(C_CURSOR) if on else color(C_HEX)
                        if col + 2 < w:
                            if on and self.nibble == 0:
                                safe_addstr(stdscr, i, col, hx[0], color(C_CURSOR) | curses.A_UNDERLINE)
                                safe_addstr(stdscr, i, col + 1, hx[1], attr)
                            elif on and self.nibble == 1:
                                safe_addstr(stdscr, i, col, hx[0], attr)
                                safe_addstr(stdscr, i, col + 1, hx[1], color(C_CURSOR) | curses.A_UNDERLINE)
                            else:
                                safe_addstr(stdscr, i, col, hx, attr)
                    else:
                        if col + 2 < w:
                            safe_addstr(stdscr, i, col, "  ", 0)
                    col += 3
            # ASCII
            col = max(col + 1, 10 + self.COLS * 3 + 4)
            if col < w - 2:
                ascii_s = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                for ai, ch in enumerate(ascii_s):
                    on = base + ai == self.offset
                    attr = color(C_CURSOR) if on else color(C_ASCII)
                    if col + ai < w - 1:
                        safe_addstr(stdscr, i, col + ai, ch, attr)

        flag = "+" if self.dirty else " "
        cut = " 截断只读" if self.truncated else ""
        ascii_f = " ASCII写" if self.ascii_edit else ""
        total = len(self.data)
        title = (
            f" HEX {self.path.name} [{self.mode}]{flag}{cut}{ascii_f}  "
            f"off 0x{self.offset:X} ({self.offset}/{total})  ?帮助 "
        )
        safe_addstr(stdscr, h - 2, 0, title.ljust(max(0, w - 1)), color(C_TITLE))
        bar = self.status
        if self.cmd_mode == ":":
            bar = ":" + self.cmd
        elif self.cmd_mode == "/":
            bar = "/" + self.cmd
        safe_addstr(stdscr, h - 1, 0, (bar or "").ljust(max(0, w - 1)), color(C_STATUS))
        stdscr.refresh()

    def _ensure_byte(self) -> None:
        if not self.data:
            self.data.append(0)
            self.offset = 0
        self.offset = max(0, min(self.offset, max(0, len(self.data) - 1)))

    def _key(self, key, stdscr) -> str:
        self.status = ""
        self._ensure_byte()
        if self.pending:
            combo = self.pending + (key if isinstance(key, str) else "")
            self.pending = ""
            if combo == "gg":
                self.offset = 0
                return ""
        if key == "g":
            self.pending = "g"
            return ""
        if key in ("q",):
            return "quit"
        if key in ("?",):
            return "help"
        if key in ("\t", "t"):
            self.mode = "BIN" if self.mode == "HEX" else "HEX"
            self.status = f"视图: {self.mode}"
            return ""
        if key == "A":
            self.ascii_edit = not self.ascii_edit
            self.status = "ASCII 直接写入 ON" if self.ascii_edit else "ASCII 直接写入 OFF"
            return ""
        if key == ":":
            self.cmd_mode = ":"
            self.cmd = ""
            return ""
        if key == "/":
            self.cmd_mode = "/"
            self.cmd = ""
            return ""
        if key in ("h", curses.KEY_LEFT):
            if self.mode == "BIN":
                if self.bit < 7:
                    self.bit += 1
                else:
                    self.bit = 0
                    self.offset = max(0, self.offset - 1)
            else:
                if self.nibble == 1:
                    self.nibble = 0
                else:
                    self.nibble = 1
                    self.offset = max(0, self.offset - 1)
            return ""
        if key in ("l", curses.KEY_RIGHT):
            if self.mode == "BIN":
                if self.bit > 0:
                    self.bit -= 1
                else:
                    self.bit = 7
                    self.offset = min(max(0, len(self.data) - 1), self.offset + 1)
            else:
                if self.nibble == 0:
                    self.nibble = 1
                else:
                    self.nibble = 0
                    self.offset = min(max(0, len(self.data) - 1), self.offset + 1)
            return ""
        if key in ("j", curses.KEY_DOWN):
            self.offset = min(max(0, len(self.data) - 1), self.offset + self.COLS)
            return ""
        if key in ("k", curses.KEY_UP):
            self.offset = max(0, self.offset - self.COLS)
            return ""
        if key == "G":
            self.offset = max(0, len(self.data) - 1)
            return ""
        if key in ("\x06", curses.KEY_NPAGE):
            h = stdscr.getmaxyx()[0]
            self.offset = min(max(0, len(self.data) - 1), self.offset + self.COLS * self._rows_on_screen(h))
            return ""
        if key in ("\x02", curses.KEY_PPAGE):
            h = stdscr.getmaxyx()[0]
            self.offset = max(0, self.offset - self.COLS * self._rows_on_screen(h))
            return ""
        if self.truncated:
            self.status = "截断只读，禁止修改"
            return ""
        if key == "x":
            self.data[self.offset] = 0
            self.dirty = True
            return ""
        if key in ("X", curses.KEY_DC):
            if self.data:
                del self.data[self.offset]
                if not self.data:
                    self.data.append(0)
                self._ensure_byte()
                self.dirty = True
            return ""
        if key == "i":
            self.data.insert(self.offset, 0)
            self.dirty = True
            self.status = "已插入 0x00"
            return ""
        # ASCII 覆盖
        if self.ascii_edit and isinstance(key, str) and key.isprintable() and len(key) == 1:
            self.data[self.offset] = ord(key) & 0xFF
            self.offset = min(len(self.data) - 1, self.offset + 1)
            self.dirty = True
            return ""
        if self.mode == "HEX" and isinstance(key, str) and key.lower() in "0123456789abcdef":
            val = int(key, 16)
            cur = self.data[self.offset]
            if self.nibble == 0:
                self.data[self.offset] = (val << 4) | (cur & 0x0F)
                self.nibble = 1
            else:
                self.data[self.offset] = (cur & 0xF0) | val
                self.nibble = 0
                self.offset = min(len(self.data) - 1, self.offset + 1)
            self.dirty = True
            return ""
        if self.mode == "BIN" and isinstance(key, str) and key in "01":
            cur = self.data[self.offset]
            mask = 1 << self.bit
            if key == "1":
                cur |= mask
            else:
                cur &= ~mask
            self.data[self.offset] = cur
            if self.bit > 0:
                self.bit -= 1
            else:
                self.bit = 7
                self.offset = min(len(self.data) - 1, self.offset + 1)
            self.dirty = True
            return ""
        return ""

    def _cmd_key(self, key) -> str:
        if key == "\x1b":
            self.cmd_mode = ""
            self.cmd = ""
            return ""
        if key in ("\x7f", "\b", curses.KEY_BACKSPACE):
            self.cmd = self.cmd[:-1]
            return ""
        if key not in ("\n", "\r"):
            if isinstance(key, str) and key.isprintable():
                self.cmd += key
            return ""
        mode = self.cmd_mode
        c = self.cmd.strip()
        self.cmd_mode = ""
        self.cmd = ""
        if mode == "/":
            self._search(c)
            return ""
        if c in {"q", "quit"}:
            return "quit"
        if c in {"q!", "quit!"}:
            self.dirty = False
            return "quit"
        if c in {"w", "write"}:
            self.status = self.save()
        elif c in {"wq", "x"}:
            self.status = self.save()
            if not self.dirty:
                return "quit"
        elif c == "help":
            return "help"
        elif c.startswith("goto"):
            self._goto(c[4:].strip())
        elif c:
            self._goto(c)
        return ""

    def _goto(self, raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        try:
            off = int(raw, 16) if raw.lower().startswith("0x") else int(raw, 0) if raw[:2] in ("0x", "0X") else int(raw)
        except ValueError:
            try:
                off = int(raw, 16)
            except ValueError:
                self.status = f"无效偏移: {raw}"
                return
        self.offset = max(0, min(max(0, len(self.data) - 1), off))
        self.status = f"跳到 0x{self.offset:X}"

    def _search(self, raw: str) -> None:
        if not raw:
            return
        needle: bytes
        if raw.lower().startswith("hex:"):
            hx = raw[4:].replace(" ", "")
            try:
                needle = bytes.fromhex(hx)
            except ValueError:
                self.status = "hex: 格式错误，应为 hex:6c6c6f"
                return
        else:
            needle = raw.encode("utf-8", errors="replace")
        start = self.offset + 1
        blob = bytes(self.data)
        idx = blob.find(needle, start)
        if idx < 0:
            idx = blob.find(needle, 0)
        if idx < 0:
            self.status = f"未找到 {raw}"
            return
        self.offset = idx
        self.status = f"找到 @ 0x{idx:X}"


# ---------------------------------------------------------------------------
# 帮助全文
# ---------------------------------------------------------------------------
HELP_TEXT = """\
文件管理器完整帮助（j/k 滑动，q / Esc / ? 返回）
================================================
一、启动
  python File_Manager.py
  python File_Manager.py /某个/目录

二、滑动浏览（和 vim 一样）
  j / ↓             下移一行
  k / ↑             上移一行
  h / ← / Backspace 回到上级目录
  l / →             进入文件夹；文件则弹出打开菜单
  gg                跳到列表顶部（先按 g 再按 g）
  G                 跳到列表底部
  Ctrl-d / Ctrl-u   半页下 / 上
  PgDn / PgUp       整页下 / 上
  数字 + Enter      按左侧黄色编号打开（文件夹和文件共用连续编号）
  Esc               取消正在输入的编号 / 退出视觉多选

三、按完整路径跳转
  f                 弹出输入框，输入绝对或相对路径后回车
                    例:  /etc   ~/Downloads   ../src   $HOME/bin
                    若输入的是文件，会跳到其所在目录并定位该文件
  ~                 跳到当前用户主目录
  :cd PATH          命令行跳转，PATH 规则同上
  :cd               不带参数则跳到主目录

四、窗口
  w                 单窗口 ↔ 双窗口
  Tab               双窗时切换活动窗口（绿框是正在滑动的那一侧）
  [ / ]             强制激活左窗 / 右窗
  :1  :2            命令行激活左 / 右，并自动打开双窗
  :pane 1  :pane 2
  :dual  :single
  t                 把另一窗切到与当前窗相同的目录

五、打开文件（失败只会在底栏提示，不会闪退）
  Enter / l / o     打开菜单
      s             系统默认程序（xdg-open / open / start）
      e             内置类 vim 文本编辑器
      v             只读预览（自动分页）
      x             十六进制编辑器
      b             二进制位视图（同一编辑器切到 BIN）
  x                 直接用十六进制编辑器打开当前文件
  e                 直接用内置文本编辑器打开
  文本编辑器遇到下列情况会拒绝打开并提示原因：
      · 二进制（含 NUL / 控制符过多）
      · 大于 8MB
      · 不是普通文件（目录、管道、设备）
      · 没权限 / 文件消失
  行数很多时文本编辑器按「一屏一页」显示，标题栏有「页 x/y」

六、选中与文件操作
  Space             标记 / 取消标记当前项
  v                 视觉多选：再按 j/k 扩展选区
  a                 全选 / 取消全选
  d                 删除当前项或全部标记项（会确认）
  r                 重命名
  c                 复制（双窗默认复制到另一侧，单窗询问目标目录）
  m                 移动（同上）
  y                 放入内部剪贴板
  P                 把剪贴板复制到当前目录（大写 P）
  n / N             新建文件 / 新建文件夹
  z                 chmod，输入八进制如 755
  i 或 p            查看属性（类型、大小、权限、时间、MIME）

七、列表显示
  .                 显示 / 隐藏点文件
  s                 排序循环：名称 → 大小 → 时间 → 类型
  /                 按文件名过滤，清空过滤词即取消
  R 或 Ctrl-l       刷新
  编号是黄色，文件夹青色加粗，可执行绿色，链接紫色，隐藏文件蓝色
  当前行整行反色，已标记项黄底

八、书签
  m 后不能当书签（m 是移动）。用命令：
  :mark a           把当前目录记到书签 a（单字母）
  :to a             跳到书签 a
  :marks            列出全部书签
  'a                快捷跳到书签 a（先按 ' 再按字母）

九、命令行 :  （先按冒号）
  :q / :quit        退出管理器
  :help             本页
  :cd PATH          路径跳转
  :e FILE           内置文本编辑器
  :hex FILE         十六进制编辑器
  :bin FILE         二进制位视图
  :sys FILE         系统打开
  :chmod 755
  :mkdir NAME
  :touch NAME
  :mark a  :to a  :marks

十、内置文本编辑器（e）
  Esc 回 Normal；i 插入；:w 保存；:q 退出；:q! 丢弃
  :120 跳到第 120 行；Ctrl-f / Ctrl-b 翻页
  ? 编辑器内帮助
  截断加载的超大文本禁止保存，以免覆盖丢数据

十一、十六进制 / 二进制编辑器（x / b）
  Tab 切换 HEX ↔ BIN
  0-9 a-f 改十六进制；0/1 改比特
  A 开启后可直接键入 ASCII 覆盖字节
  i 插入 0x00；X 删除字节；:w 保存
  /hello 或 /hex:6c6c6f 查找
  :0x1A0 或 :1024 跳转偏移
  大于 16MB 只读打开前 16MB

十二、其它提示
  所有打开 / 复制 / 删除失败都只写底栏，不抛到终端
  终端过小会提示「终端太小」
  Windows 需 pip install windows-curses
""".splitlines()


# ---------------------------------------------------------------------------
# 主管理器
# ---------------------------------------------------------------------------
class FileManager:
    def __init__(self, start: Path) -> None:
        self.left = Pane(start)
        self.right = Pane(start)
        self.dual = False
        self.active = 0
        self.pending_digits = ""
        self.pending_g = False
        self.pending_quote = False  # 'a 书签跳转
        self.visual = False
        self.visual_anchor = 0
        self.clipboard: List[Path] = []
        self.bookmarks = {}  # letter -> Path
        self.status = "按 ? 查看完整帮助   f 路径跳转   x 十六进制   w 双窗"
        self.last_key = ""

    @property
    def pane(self) -> Pane:
        return self.right if (self.dual and self.active == 1) else self.left

    @property
    def other(self) -> Pane:
        return self.left if self.pane is self.right else self.right

    def run(self, stdscr) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        try:
            stdscr.notimeout(False)
        except curses.error:
            pass
        init_colors()
        while True:
            try:
                self._draw(stdscr)
            except Exception as exc:
                try:
                    message(stdscr, f"绘制出错: {exc}", warn=True)
                except Exception:
                    pass
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue
            try:
                if self._handle(stdscr, key) == "quit":
                    break
            except Exception as exc:
                self.status = f"操作失败: {exc}"

    def _draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        if h < 6 or w < 20:
            safe_addstr(stdscr, 0, 0, "终端太小，请放大")
            stdscr.refresh()
            return
        mode = "双窗口" if self.dual else "单窗口"
        act = "右" if (self.dual and self.active == 1) else "左"
        head = f" FM  {mode} 活动:{act}  标记:{len(self.pane.marked)}  {self.pane.path} "
        safe_addstr(stdscr, 0, 0, head.ljust(max(0, w - 1)), color(C_TITLE) | curses.A_BOLD)

        body_h = h - 2
        if self.dual:
            mid = max(10, w // 2)
            self._draw_pane(stdscr, self.left, 1, 0, body_h, mid, active=(self.active == 0))
            self._draw_pane(stdscr, self.right, 1, mid, body_h, max(1, w - mid), active=(self.active == 1))
        else:
            self._draw_pane(stdscr, self.left, 1, 0, body_h, w, active=True)

        buf = f" 编号:{self.pending_digits}" if self.pending_digits else ""
        vis = " [VISUAL]" if self.visual else ""
        markp = " ['+字母跳书签]" if self.pending_quote else ""
        bar = f"{vis}{markp}{buf} {self.status}"
        safe_addstr(stdscr, h - 1, 0, bar.ljust(max(0, w - 1)), color(C_STATUS))
        stdscr.refresh()

    def _draw_pane(self, stdscr, pane: Pane, top: int, left: int, height: int, width: int, active: bool) -> None:
        if height < 3 or width < 4:
            return
        inner_h = max(1, height - 2)
        inner_w = max(1, width - 2)
        pane.ensure_visible(inner_h)
        bcol = color(C_BORDER_ACTIVE if active else C_BORDER_IDLE)
        try:
            for x in range(width):
                ch = "+" if x in (0, width - 1) else "-"
                stdscr.addch(top, left + x, ch, bcol)
                if top + height - 1 < stdscr.getmaxyx()[0]:
                    stdscr.addch(top + height - 1, left + x, ch, bcol)
            for y in range(1, height - 1):
                stdscr.addch(top + y, left, "|", bcol)
                if width > 1:
                    stdscr.addch(top + y, left + width - 1, "|", bcol)
        except curses.error:
            pass

        sort_name = ["名称", "大小", "时间", "类型"][pane.sort_mode]
        hid = "·隐" if pane.show_hidden else ""
        filt = f" /{pane.filter_text}" if pane.filter_text else ""
        cap = f" {pane.path.name or str(pane.path)}  {sort_name}{hid}{filt} "
        if pane.error:
            cap = f" !{pane.error} "
        safe_addstr(stdscr, top, left + 1, cap[:inner_w], bcol | curses.A_BOLD)

        n = len(pane.entries)
        idx_w = max(2, len(str(max(n, 1))))
        for row in range(inner_h):
            i = pane.offset + row
            y = top + 1 + row
            x = left + 1
            if i >= n:
                continue
            p = pane.entries[i]
            marked = str(p) in pane.marked
            is_cur = i == pane.cursor and active
            idx = f"{i + 1:>{idx_w}} "
            name = sanitize_line(p.name)
            extra = ""
            try:
                if p.is_symlink():
                    extra = "@"
                elif p.is_dir():
                    extra = "/"
            except OSError:
                extra = "?"
            meta = ""
            try:
                st = p.lstat()
                if p.is_dir() and not p.is_symlink():
                    meta = "<DIR>"
                else:
                    meta = human_size(st.st_size)
            except OSError:
                meta = "?"
            room = inner_w - idx_w - 1 - len(meta) - 1
            shown = (name + extra)[: max(1, room)]
            line_rest = shown.ljust(max(1, room)) + " " + meta
            if is_cur:
                attr_idx = color(C_CURSOR) | curses.A_BOLD
                attr_name = color(C_CURSOR) | curses.A_BOLD
            elif marked:
                attr_idx = color(C_SELECTED)
                attr_name = color(C_SELECTED)
            else:
                attr_idx = color(C_INDEX) | curses.A_BOLD
                attr_name = self._name_attr(p)
            safe_addstr(stdscr, y, x, idx[:inner_w], attr_idx)
            if inner_w > len(idx):
                safe_addstr(stdscr, y, x + len(idx), line_rest[: inner_w - len(idx)], attr_name)

    def _name_attr(self, p: Path) -> int:
        try:
            if p.name.startswith("."):
                return color(C_HIDDEN)
            if p.is_symlink():
                return color(C_LINK)
            if p.is_dir():
                return color(C_DIR) | curses.A_BOLD
            mode = p.stat().st_mode
            if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) and p.is_file():
                return color(C_EXEC)
        except OSError:
            return color(C_FILE)
        return color(C_FILE)

    def _handle(self, stdscr, key) -> str:
        if key == curses.KEY_RESIZE:
            return ""

        if self.pending_quote:
            self.pending_quote = False
            if isinstance(key, str) and key.isalnum() and len(key) == 1:
                self._goto_mark(key)
            else:
                self.status = "书签已取消"
            return ""

        if isinstance(key, str) and key.isdigit():
            self.pending_digits += key
            self.status = f"输入编号 {self.pending_digits} ，回车打开，Esc 取消"
            return ""

        if key == "\x1b":
            self.pending_digits = ""
            self.pending_g = False
            self.pending_quote = False
            self.visual = False
            self.status = "已取消"
            return ""

        if self.pending_g:
            self.pending_g = False
            if key == "g":
                self.pane.cursor = 0
                return ""

        if key in ("\n", "\r"):
            if self.pending_digits:
                try:
                    num = int(self.pending_digits)
                except ValueError:
                    num = -1
                self._open_index(stdscr, num)
                self.pending_digits = ""
                return ""
            return self._activate(stdscr)

        self.pending_digits = ""

        if key in ("q", "Q"):
            return "quit"
        if key in ("?", curses.KEY_F1):
            self._help(stdscr)
            return ""
        if key == ":":
            return self._colon(stdscr)
        if key == "f":
            self._goto_path(stdscr)
        elif key == "~":
            self.status = self.pane.chdir(Path.home())
        elif key == "'":
            self.pending_quote = True
            self.status = "再按书签字母跳转，如 'a"
        elif key in ("j", curses.KEY_DOWN):
            self._move(1)
        elif key in ("k", curses.KEY_UP):
            self._move(-1)
        elif key in ("h", curses.KEY_LEFT, curses.KEY_BACKSPACE, "\x7f", "\b"):
            self.status = self.pane.chdir(self.pane.path.parent)
        elif key in ("l", curses.KEY_RIGHT):
            return self._activate(stdscr)
        elif key == "G":
            self.pane.cursor = max(0, len(self.pane.entries) - 1)
        elif key == "g":
            self.pending_g = True
            self.status = "再按 g 回到顶部"
        elif key == "\x04":
            self._move(max(1, (stdscr.getmaxyx()[0] - 4) // 2))
        elif key == "\x15":
            self._move(-max(1, (stdscr.getmaxyx()[0] - 4) // 2))
        elif key == curses.KEY_NPAGE:
            self._move(max(1, stdscr.getmaxyx()[0] - 4))
        elif key == curses.KEY_PPAGE:
            self._move(-max(1, stdscr.getmaxyx()[0] - 4))
        elif key in ("\t",):
            if self.dual:
                self.active = 1 - self.active
                self.status = "活动窗口: " + ("右" if self.active == 1 else "左")
        elif key == "[" and self.dual:
            self.active = 0
            self.status = "活动窗口: 左"
        elif key == "]" and self.dual:
            self.active = 1
            self.status = "活动窗口: 右"
        elif key == "w":
            self.dual = not self.dual
            if not self.dual:
                self.active = 0
            self.status = "双窗口" if self.dual else "单窗口"
        elif key == "t" and self.dual:
            self.status = self.other.chdir(self.pane.path)
            self.status = "已同步另一窗口目录"
        elif key == " ":
            self._toggle_mark()
        elif key == "v":
            self.visual = not self.visual
            self.visual_anchor = self.pane.cursor
            self.status = "视觉多选 ON" if self.visual else "视觉多选 OFF"
        elif key == "a":
            if len(self.pane.marked) == len(self.pane.entries) and self.pane.entries:
                self.pane.marked.clear()
                self.status = "已取消全选"
            else:
                self.pane.marked = {str(p) for p in self.pane.entries}
                self.status = f"已全选 {len(self.pane.marked)} 项"
        elif key == "o":
            self._open_menu(stdscr)
        elif key == "e":
            self._open_text(stdscr, self.pane.current())
        elif key == "x":
            self._open_hex(stdscr, self.pane.current(), binary=False)
        elif key == "b":
            # 浏览模式 b = 二进制编辑器（书签用 ' 和 :mark）
            self._open_hex(stdscr, self.pane.current(), binary=True)
        elif key == "d":
            self._delete(stdscr)
        elif key == "r":
            self._rename(stdscr)
        elif key == "c":
            self._copy(stdscr)
        elif key == "m":
            self._move_files(stdscr)
        elif key in ("i", "p"):
            self._props(stdscr)
        elif key == "n":
            self._new(stdscr, folder=False)
        elif key == "N":
            self._new(stdscr, folder=True)
        elif key == "y":
            targets = self._targets()
            self.clipboard = targets
            self.status = f"已复制 {len(targets)} 项到内部剪贴板"
        elif key == "P":
            self._paste(stdscr)
        elif key == "z":
            self._chmod(stdscr)
        elif key == ".":
            self.pane.show_hidden = not self.pane.show_hidden
            self.pane.refresh()
            self.status = "显示隐藏" if self.pane.show_hidden else "隐藏点文件"
        elif key == "s":
            self.pane.sort_mode = (self.pane.sort_mode + 1) % 4
            self.pane.refresh()
            self.status = "排序: " + ["名称", "大小", "时间", "类型"][self.pane.sort_mode]
        elif key == "/":
            q = prompt(stdscr, "过滤", self.pane.filter_text)
            if q is not None:
                self.pane.filter_text = q
                self.pane.refresh()
                self.status = f"过滤 '{q}'" if q else "已清除过滤"
        elif key in ("R", "\x0c"):
            self.pane.refresh()
            if self.dual:
                self.other.refresh()
            self.status = "已刷新"
        return ""

    def _move(self, delta: int) -> None:
        self.pane.move(delta)
        if self.visual and self.pane.entries:
            lo, hi = sorted((self.visual_anchor, self.pane.cursor))
            hi = min(hi, len(self.pane.entries) - 1)
            lo = max(0, lo)
            self.pane.marked = {str(self.pane.entries[i]) for i in range(lo, hi + 1)}

    def _toggle_mark(self) -> None:
        cur = self.pane.current()
        if not cur:
            return
        s = str(cur)
        if s in self.pane.marked:
            self.pane.marked.discard(s)
        else:
            self.pane.marked.add(s)
        self.status = f"标记 {len(self.pane.marked)} 项"

    def _targets(self) -> List[Path]:
        if self.pane.marked:
            return [Path(s) for s in sorted(self.pane.marked)]
        cur = self.pane.current()
        return [cur] if cur else []

    def _open_index(self, stdscr, num: int) -> None:
        i = num - 1
        if i < 0 or i >= len(self.pane.entries):
            self.status = f"没有编号 {num}"
            return
        self.pane.cursor = i
        self._activate(stdscr)

    def _goto_path(self, stdscr) -> None:
        raw = prompt(stdscr, "跳转到路径", str(self.pane.path))
        if raw is None:
            self.status = "取消跳转"
            return
        self.status = self.pane.chdir(Path(raw))

    def _goto_mark(self, letter: str) -> None:
        dest = self.bookmarks.get(letter)
        if not dest:
            self.status = f"没有书签 '{letter}'，先用 :mark {letter}"
            return
        self.status = self.pane.chdir(dest)

    def _activate(self, stdscr) -> str:
        cur = self.pane.current()
        if not cur:
            self.status = "空目录"
            return ""
        try:
            if cur.is_symlink():
                try:
                    target = cur.resolve()
                except OSError as exc:
                    self.status = f"无法解析链接: {exc}"
                    return ""
                if target.is_dir():
                    self.status = self.pane.chdir(target)
                    return ""
            elif cur.is_dir():
                self.status = self.pane.chdir(cur)
                return ""
        except OSError as exc:
            self.status = f"无法进入: {exc}"
            return ""
        self._open_menu(stdscr)
        return ""

    def _open_menu(self, stdscr) -> None:
        cur = self.pane.current()
        if not cur:
            return
        try:
            if cur.is_dir() and not cur.is_symlink():
                self.status = self.pane.chdir(cur)
                return
        except OSError as exc:
            self.status = f"无法打开: {exc}"
            return
        choice = prompt(
            stdscr,
            f"打开 {cur.name}  [s]系统 [e]文本 [v]预览 [x]十六进制 [b]二进制",
            "e",
        )
        if choice is None:
            self.status = "取消打开"
            return
        choice = choice.strip().lower()
        if choice in {"s", "sys", "system", "系统"}:
            self.status = open_with_system(cur)
        elif choice in {"v", "view", "预览"}:
            self._preview(stdscr, cur)
        elif choice in {"x", "hex"}:
            self._open_hex(stdscr, cur, binary=False)
        elif choice in {"b", "bin", "binary"}:
            self._open_hex(stdscr, cur, binary=True)
        else:
            self._open_text(stdscr, cur)

    def _open_text(self, stdscr, path: Optional[Path]) -> None:
        if path is None:
            self.status = "没有选中文件"
            return
        try:
            if path.is_dir():
                self.status = "这是目录，不能用文本编辑器打开"
                return
        except OSError as exc:
            self.status = f"无法打开: {exc}"
            return
        try:
            Editor(path).run(stdscr)
        except Exception as exc:
            self.status = f"无法打开文本编辑器: {exc}"
            return
        self.pane.refresh()
        if not self.status.startswith("无法"):
            self.status = f"已关闭编辑器 {path.name}"

    def _open_hex(self, stdscr, path: Optional[Path], binary: bool) -> None:
        if path is None:
            self.status = "没有选中文件"
            return
        try:
            if path.is_dir():
                self.status = "这是目录，不能用十六进制编辑器打开"
                return
        except OSError as exc:
            self.status = f"无法打开: {exc}"
            return
        try:
            ed = HexEditor(path)
            if binary:
                ed.mode = "BIN"
            ed.run(stdscr)
        except Exception as exc:
            self.status = f"无法打开十六进制编辑器: {exc}"
            return
        self.pane.refresh()
        self.status = f"已关闭十六进制编辑器 {path.name}"

    def _preview(self, stdscr, path: Path) -> None:
        try:
            if path.is_dir():
                self.status = "目录请直接进入，不必预览"
                return
            st = path.stat()
            if not stat.S_ISREG(st.st_mode):
                self.status = f"无法预览：{file_kind(path)}"
                return
            with open(path, "rb") as fh:
                data = fh.read(min(st.st_size, 2 * 1024 * 1024))
        except Exception as exc:
            self.status = f"无法预览: {exc}"
            return
        if looks_binary(data):
            self.status = "这是二进制文件，请按 x 用十六进制查看"
            return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        lines = text.splitlines() or [""]
        off = 0
        while True:
            h, w = stdscr.getmaxyx()
            stdscr.erase()
            pages = max(1, (len(lines) + max(1, h - 2) - 1) // max(1, h - 2))
            page = off // max(1, h - 2) + 1
            safe_addstr(stdscr, 0, 0, f" 预览 {path.name}  页 {page}/{pages}  q退出 j/k滑动 ", color(C_TITLE))
            for i in range(1, h - 1):
                li = off + i - 1
                if li < len(lines):
                    safe_addstr(stdscr, i, 0, sanitize_line(lines[li]))
            safe_addstr(stdscr, h - 1, 0, f"{off + 1}/{len(lines)}", color(C_STATUS))
            stdscr.refresh()
            try:
                k = stdscr.get_wch()
            except curses.error:
                continue
            if k in ("q", "\x1b"):
                break
            if k in ("j", curses.KEY_DOWN):
                off = min(max(0, len(lines) - 1), off + 1)
            elif k in ("k", curses.KEY_UP):
                off = max(0, off - 1)
            elif k in (curses.KEY_NPAGE, "\x06"):
                off = min(max(0, len(lines) - 1), off + h - 2)
            elif k in (curses.KEY_PPAGE, "\x02"):
                off = max(0, off - (h - 2))
            elif k == "G":
                off = max(0, len(lines) - (h - 2))
            elif k == "g":
                off = 0

    def _delete(self, stdscr) -> None:
        items = self._targets()
        if not items:
            self.status = "没有可删除项"
            return
        names = ", ".join(p.name for p in items[:5])
        extra = f" 等{len(items)}项" if len(items) > 5 else ""
        if not confirm(stdscr, f"删除 {names}{extra}?"):
            self.status = "取消删除"
            return
        ok, fail = 0, 0
        last_err = ""
        for p in items:
            try:
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                ok += 1
            except Exception as exc:
                fail += 1
                last_err = str(exc)
        self.pane.marked.clear()
        self.pane.refresh()
        self.status = f"删除成功 {ok} 失败 {fail}" + (f" ({last_err})" if last_err else "")

    def _rename(self, stdscr) -> None:
        cur = self.pane.current()
        if not cur:
            self.status = "没有选中项"
            return
        new = prompt(stdscr, "新名称", cur.name)
        if not new or new == cur.name:
            self.status = "取消重命名"
            return
        if "/" in new or "\\" in new:
            self.status = "名称里不要包含路径分隔符，移动请用 m"
            return
        dest = cur.with_name(new)
        try:
            cur.rename(dest)
            self.pane.refresh()
            self.status = f"已重命名为 {new}"
        except Exception as exc:
            self.status = f"重命名失败: {exc}"

    def _copy(self, stdscr) -> None:
        items = self._targets()
        if not items:
            self.status = "没有可复制项"
            return
        if self.dual:
            dest_dir = self.other.path
        else:
            raw = prompt(stdscr, "复制到目录", str(self.pane.path))
            if raw is None:
                self.status = "取消复制"
                return
            dest_dir = resolve_user_path(raw, self.pane.path)
        self._copy_to(dest_dir, items)
        self.pane.refresh()
        if self.dual:
            self.other.refresh()

    def _copy_to(self, dest_dir: Path, items: Sequence[Path]) -> None:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.status = f"无法创建目标目录: {exc}"
            return
        ok = 0
        for p in items:
            target = dest_dir / p.name
            try:
                if target.resolve() == p.resolve():
                    continue
            except OSError:
                pass
            try:
                if p.is_dir() and not p.is_symlink():
                    shutil.copytree(p, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(p, target)
                ok += 1
            except Exception as exc:
                self.status = f"复制失败 {p.name}: {exc}"
                return
        self.status = f"已复制 {ok} 项到 {dest_dir}"

    def _move_files(self, stdscr) -> None:
        items = self._targets()
        if not items:
            self.status = "没有可移动项"
            return
        if self.dual:
            dest_dir = self.other.path
        else:
            raw = prompt(stdscr, "移动到目录", str(self.pane.path))
            if raw is None:
                self.status = "取消移动"
                return
            dest_dir = resolve_user_path(raw, self.pane.path)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.status = f"无法创建目标目录: {exc}"
            return
        ok = 0
        for p in items:
            try:
                shutil.move(str(p), str(dest_dir / p.name))
                ok += 1
            except Exception as exc:
                self.status = f"移动失败 {p.name}: {exc}"
                self.pane.refresh()
                return
        self.pane.marked.clear()
        self.pane.refresh()
        if self.dual:
            self.other.refresh()
        self.status = f"已移动 {ok} 项到 {dest_dir}"

    def _paste(self, stdscr) -> None:
        if not self.clipboard:
            self.status = "剪贴板为空，先用 y 复制"
            return
        self._copy_to(self.pane.path, self.clipboard)
        self.pane.refresh()

    def _new(self, stdscr, folder: bool) -> None:
        name = prompt(stdscr, "文件夹名" if folder else "文件名", "")
        if not name:
            self.status = "取消新建"
            return
        dest = self.pane.path / name
        try:
            if folder:
                dest.mkdir(parents=True, exist_ok=False)
            else:
                dest.touch(exist_ok=False)
            self.pane.refresh()
            self.status = f"已创建 {name}"
        except Exception as exc:
            self.status = f"创建失败: {exc}"

    def _chmod(self, stdscr) -> None:
        items = self._targets()
        if not items:
            self.status = "没有选中项"
            return
        raw = prompt(stdscr, "权限(八进制 如 755)", "644")
        if raw is None:
            return
        try:
            mode = int(raw, 8)
        except ValueError:
            self.status = "权限格式错误，请输入 644 / 755 这种八进制"
            return
        ok, fail = 0, 0
        for p in items:
            try:
                os.chmod(p, mode)
                ok += 1
            except Exception:
                fail += 1
        self.status = f"已修改权限 {ok} 项" + (f"，失败 {fail}" if fail else "")

    def _props(self, stdscr) -> None:
        cur = self.pane.current()
        if not cur:
            self.status = "没有选中项"
            return
        try:
            st = cur.lstat()
        except OSError as exc:
            self.status = f"无法读取属性: {exc}"
            return
        lines = [
            f"名称: {cur.name}",
            f"路径: {cur}",
            f"类型: {file_kind(cur)}",
            f"大小: {st.st_size} ({human_size(st.st_size)})",
            f"权限: {stat.filemode(st.st_mode)} ({oct(st.st_mode & 0o777)})",
            f"UID/GID: {st.st_uid}/{st.st_gid}",
            f"修改: {datetime.datetime.fromtimestamp(st.st_mtime)}",
            f"访问: {datetime.datetime.fromtimestamp(st.st_atime)}",
            f"inode: {st.st_ino}",
        ]
        if cur.is_symlink():
            try:
                lines.append(f"指向: {os.readlink(cur)}")
            except OSError:
                lines.append("指向: <无法读取>")
        mime, _ = mimetypes.guess_type(str(cur))
        if mime:
            lines.append(f"MIME: {mime}")
        try:
            if cur.is_file() and st.st_size <= 8192:
                with open(cur, "rb") as fh:
                    head = fh.read(16)
                lines.append("文件头: " + " ".join(f"{b:02X}" for b in head))
        except OSError:
            pass
        lines.append("")
        lines.append("按任意键返回")
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        for i, ln in enumerate(lines):
            if i >= h:
                break
            safe_addstr(stdscr, i, 0, ln, color(C_HELP))
        stdscr.refresh()
        try:
            stdscr.get_wch()
        except curses.error:
            pass

    def _help(self, stdscr) -> None:
        off = 0
        while True:
            h, w = stdscr.getmaxyx()
            stdscr.erase()
            max_off = max(0, len(HELP_TEXT) - h + 1)
            off = max(0, min(off, max_off))
            for i in range(h - 1):
                li = off + i
                if li < len(HELP_TEXT):
                    safe_addstr(stdscr, i, 0, HELP_TEXT[li], color(C_HELP))
            safe_addstr(stdscr, h - 1, 0, f"j/k 或 PgUp/PgDn 滑动  q 返回  {off + 1}/{len(HELP_TEXT)}", color(C_STATUS))
            stdscr.refresh()
            try:
                k = stdscr.get_wch()
            except curses.error:
                continue
            if k in ("q", "\x1b", "?"):
                break
            if k in ("j", curses.KEY_DOWN):
                off += 1
            elif k in ("k", curses.KEY_UP):
                off -= 1
            elif k in (curses.KEY_NPAGE, "\x06"):
                off += max(1, h - 2)
            elif k in (curses.KEY_PPAGE, "\x02"):
                off -= max(1, h - 2)
            elif k == "G":
                off = max_off
            elif k == "g":
                off = 0

    def _colon(self, stdscr) -> str:
        raw = prompt(stdscr, ":", "")
        if raw is None:
            return ""
        parts = raw.strip().split(maxsplit=1)
        if not parts:
            return ""
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in {"q", "quit", "exit"}:
            return "quit"
        if cmd in {"1", "left", "pane1"}:
            self.dual = True
            self.active = 0
            self.status = "活动窗口: 左"
            return ""
        if cmd in {"2", "right", "pane2"}:
            self.dual = True
            self.active = 1
            self.status = "活动窗口: 右"
            return ""
        if cmd == "pane":
            self.dual = True
            self.active = 1 if arg.strip() in {"2", "right", "r"} else 0
            self.status = "活动窗口: " + ("右" if self.active == 1 else "左")
            return ""
        if cmd in {"dual", "split"}:
            self.dual = True
            self.status = "双窗口"
            return ""
        if cmd in {"single"}:
            self.dual = False
            self.active = 0
            self.status = "单窗口"
            return ""
        if cmd == "help":
            self._help(stdscr)
        elif cmd == "cd":
            dest = resolve_user_path(arg or "~", self.pane.path)
            self.status = self.pane.chdir(dest)
        elif cmd == "e":
            path = resolve_user_path(arg, self.pane.path) if arg else self.pane.current()
            self._open_text(stdscr, path)
        elif cmd in {"hex", "xxd"}:
            path = resolve_user_path(arg, self.pane.path) if arg else self.pane.current()
            self._open_hex(stdscr, path, binary=False)
        elif cmd in {"bin", "binary"}:
            path = resolve_user_path(arg, self.pane.path) if arg else self.pane.current()
            self._open_hex(stdscr, path, binary=True)
        elif cmd == "sys":
            path = resolve_user_path(arg, self.pane.path) if arg else self.pane.current()
            if path:
                self.status = open_with_system(path)
            else:
                self.status = "没有目标文件"
        elif cmd == "mark":
            letter = (arg.strip() or "a")[0]
            self.bookmarks[letter] = self.pane.path
            self.status = f"书签 '{letter}' = {self.pane.path}"
        elif cmd == "to":
            letter = (arg.strip() or "")[:1]
            if letter:
                self._goto_mark(letter)
            else:
                self.status = "用法 :to a"
        elif cmd == "marks":
            if not self.bookmarks:
                self.status = "还没有书签，用 :mark a 添加"
            else:
                self.status = "  ".join(f"{k}:{v}" for k, v in sorted(self.bookmarks.items()))
        elif cmd == "chmod":
            if arg:
                try:
                    mode = int(arg, 8)
                    ok = 0
                    for p in self._targets():
                        try:
                            os.chmod(p, mode)
                            ok += 1
                        except OSError:
                            pass
                    self.status = f"权限已改 {ok} 项"
                except Exception as exc:
                    self.status = f"chmod 失败: {exc}"
            else:
                self._chmod(stdscr)
        elif cmd == "mkdir":
            if not arg:
                self.status = "用法 :mkdir 名称"
            else:
                try:
                    (self.pane.path / arg).mkdir(parents=True, exist_ok=False)
                    self.pane.refresh()
                    self.status = f"已创建目录 {arg}"
                except Exception as exc:
                    self.status = f"创建失败: {exc}"
        elif cmd == "touch":
            if not arg:
                self.status = "用法 :touch 名称"
            else:
                try:
                    (self.pane.path / arg).touch(exist_ok=False)
                    self.pane.refresh()
                    self.status = f"已创建 {arg}"
                except Exception as exc:
                    self.status = f"创建失败: {exc}"
        else:
            # 允许 :/usr/bin 这种直接当路径
            if cmd.startswith("/") or cmd.startswith("~") or cmd.startswith("./") or cmd.startswith("../"):
                dest = resolve_user_path(raw.strip(), self.pane.path)
                self.status = self.pane.chdir(dest)
            else:
                self.status = f"未知命令 :{cmd}  （:help 看说明）"
        return ""


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    start = Path(argv[0]).expanduser() if argv else Path.cwd()
    if not start.exists():
        print(f"路径不存在: {start}", file=sys.stderr)
        return 1
    try:
        if start.is_file():
            start = start.parent
    except OSError:
        pass

    def _wrapped(stdscr):
        try:
            curses.set_escdelay(25)
        except Exception:
            pass
        FileManager(start).run(stdscr)

    try:
        curses.wrapper(_wrapped)
    except KeyboardInterrupt:
        return 0
    except curses.error as exc:
        print(f"终端界面出错: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
