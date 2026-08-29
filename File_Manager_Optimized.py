"""Python Terminal File Manager

一个使用 Python 编写的简单终端文件管理器。
优化版本 - 改进代码结构、错误处理和性能。

功能列表：
- 📁 浏览文件夹和文件
- 📂 进入/返回文件夹
- 🏠 返回启动目录
- 🔎 跳转到指定目录
- 📄 创建文件/文件夹
- 🗑️ 删除文件/文件夹
- ✏️ 重命名文件/文件夹
- 📦 移动文件/文件夹
- 📋 复制文件/文件夹
- ℹ️ 查看文件属性
- 📖 UTF-8 文本文件预览
- 🖥️ 调用系统默认程序打开文件
- 🌏 中英文混合字符显示宽度处理
"""

import importlib.util
import os
import sys
import stat
import logging
import platform
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple, Union

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.ERROR,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 常量定义 ====================
class Color:
    """ANSI 颜色代码常量"""
    PATH_BG = '\033[48;2;30;30;30m'
    FOLDER_FG = '\033[38;2;255;255;0m'
    FILE_FG = '\033[38;2;135;215;255m'
    MENU_BG = '\033[48;2;95;135;255m'
    MENU_FG = '\033[38;2;95;255;255m'
    OPERATION_BG = '\033[48;2;0;0;255m'
    OPERATION_FG = '\033[38;2;255;225;255m'
    ERROR_FG = '\033[38;2;255;0;0m'
    INFO_FG = '\033[38;2;0;255;255m'
    ELLIPSIS_FG = '\033[38;2;0;175;0m'
    RESET = '\033[0m'

class MenuText:
    """菜单文本常量"""
    OPEN = '打开-->1'
    DELETE = '删除-->2'
    RENAME = '重命名-->3'
    MOVE = '移动-->4'
    COPY = '复制-->5'
    PROPERTIES = '属性-->6'
    BACK = '返回-->r'
    
    SELECT = '选中-->输入对应的数字+s'
    OPEN_NUM = '打开-->输入对应的数字'
    JUMP = '跳转至指定目录-->j'
    HOME = '回到首页目录-->js'
    PARENT = '返回上一级目录-->r'
    QUIT = '退出-->q'
    NEW = '新建-->n'
    SELECT_DIR = '选中当前目录--y'
    CANCEL = '取消-->q'
    
    MOVE_STATUS = '当前操作状态>>>移动'
    COPY_STATUS = '当前操作状态>>>复制'

# ==================== 工具函数 ====================

def clear_screen() -> None:
    """清空控制台显示（跨平台）"""
    os.system('cls' if os.name == 'nt' else 'clear')

def clear_line_up(n: int) -> None:
    """清理指定行数日志"""
    for _ in range(n):
        sys.stdout.write("\033[F")
        sys.stdout.write("\033[2K")
    sys.stdout.flush()

def is_int_convertible(value: str) -> bool:
    """检测数据是否可转换为 int"""
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False

def get_terminal_size() -> Tuple[int, int]:
    """获取终端宽度和高度"""
    import shutil
    size = shutil.get_terminal_size()
    return size.columns, size.lines

def get_display_width(s: str) -> int:
    """检测字符串实际占用的显示长度"""
    width = 0
    for ch in s:
        kind = unicodedata.east_asian_width(ch)
        width += 2 if kind in ("W", "F") else 1
    return width

def truncate_by_display_width(s: str, max_width: int) -> str:
    """按显示宽度截取字符串"""
    width = 0
    result = []
    
    for ch in s:
        ch_width = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + ch_width > max_width:
            break
        result.append(ch)
        width += ch_width
    
    return "".join(result)

def substr_by_display_width(s: str, start: int, length: int) -> str:
    """按显示宽度截取字符串
    
    Args:
        s: 原字符串
        start: 正数从左侧开始，负数从右侧开始
        length: 正数向右截取，负数向左截取
    
    Returns:
        截取后的字符串
    """
    def char_width(ch):
        return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    
    chars = []
    pos = 0
    
    for ch in s:
        w = char_width(ch)
        chars.append((ch, pos, pos + w))
        pos += w
    
    total_width = pos
    start_pos = start - 1 if start > 0 else total_width + start
    
    if length > 0:
        end_pos = start_pos + length
    else:
        end_pos = start_pos + 1
        start_pos = end_pos + length
    
    result = []
    for ch, ch_start, ch_end in chars:
        if ch_end > start_pos and ch_start < end_pos:
            result.append(ch)
    
    return "".join(result)

# ==================== 错误管理 ====================

class ErrorManager:
    """终端错误和信息管理"""
    
    def __init__(self):
        self.lines = 0
    
    def show(self, *msgs: str) -> None:
        """显示消息"""
        for msg in msgs:
            print(msg)
            self.lines += msg.count("\n") + 1
    
    def clear(self) -> None:
        """清空显示的消息"""
        if self.lines:
            clear_line_up(self.lines + 1)
            self.lines = 0

# ==================== 文件操作类 ====================

class DefaultOpener:
    """跨平台调用系统默认打开方式"""
    
    @staticmethod
    def is_termux() -> bool:
        """检测是否运行在Termux"""
        return (
            "TERMUX_VERSION" in os.environ
            or os.path.exists("/data/data/com.termux")
        )
    
    @staticmethod
    def open(target: Union[str, Path]) -> None:
        """打开文件或URL"""
        target = str(target)
        
        if DefaultOpener.is_termux():
            DefaultOpener._open_termux(target)
            return
        
        system = platform.system()
        
        try:
            if system == "Windows":
                os.startfile(target)
            elif system == "Darwin":
                subprocess.run(["open", target], check=True)
            elif system == "Linux":
                subprocess.run(["xdg-open", target], check=True)
            else:
                raise RuntimeError(f"不支持系统: {system}")
        except Exception as e:
            logger.error(f"打开文件失败: {e}")
            raise
    
    @staticmethod
    def _open_termux(target: str) -> None:
        """Termux调用Android Intent"""
        cmd = (
            ["termux-open-url", target]
            if target.startswith(("http://", "https://"))
            else ["termux-open", target]
        )
        
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            raise RuntimeError(
                "未找到termux-open，请安装Termux:API插件并启用"
            )
    
    @staticmethod
    def open_file(filepath: Union[str, Path]) -> None:
        """打开文件"""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")
        DefaultOpener.open(path)

# ==================== 主要文件管理类 ====================

class FileManager:
    """文件管理器主类"""
    
    # 操作模式常量
    MODE_NORMAL = 1      # 正常操作
    MODE_MOVE = 2        # 移动文件
    MODE_COPY = 3        # 复制文件
    
    def __init__(self):
        self.folders: Dict[int, str] = {}
        self.files: Dict[int, str] = {}
        self.current_path = Path.cwd()
        self.mode = self.MODE_NORMAL
        self.move_dest = None
        self.operator = FileOperator()
    
    def refresh_display(self) -> None:
        """刷新界面"""
        clear_screen()
        self.folders.clear()
        self.files.clear()
        self._display_current_path()
    
    def _display_current_path(self) -> None:
        """显示当前目录"""
        self.current_path = Path.cwd()
        path_text = f'当前目录 --> {self.current_path}'
        
        cols, _ = get_terminal_size()
        if get_display_width(path_text) < cols:
            print(f'{Color.PATH_BG}{path_text}{Color.RESET}\n')
        else:
            truncated = substr_by_display_width(path_text, -0, -(cols - 15))
            print(f'{Color.PATH_BG}{path_text[0:9]}...{truncated}{Color.RESET}\n')
        
        self._verify_permissions()
    
    def _verify_permissions(self) -> None:
        """验证目录访问权限"""
        try:
            os.scandir(self.current_path)
        except FileNotFoundError:
            print('❌ 没有该文件或目录')
            self._show_menu()
        except PermissionError:
            print('❌ 权限被拒绝')
            self._show_menu()
        else:
            self._list_contents()
    
    def _list_contents(self) -> None:
        """列出目录内容"""
        num = 1
        temp_files = []
        cols, _ = get_terminal_size()
        
        try:
            with os.scandir(self.current_path) as entries:
                for entry in entries:
                    if entry.is_dir():
                        self.folders[num] = entry.name
                        num += 1
                    elif entry.is_file():
                        temp_files.append(entry.name)
        except PermissionError:
            print('❌ 权限不足，无法读取目录内容')
            self._show_menu()
            return
        except Exception as e:
            logger.error(f"列目录失败: {e}")
            print(f'❌ 读取目录失败: {e}')
            self._show_menu()
            return
        
        for file in temp_files:
            self.files[num] = file
            num += 1
        
        # 显示文件夹
        for idx, folder in self.folders.items():
            display_text = f'<{idx}>: {folder}'
            if get_display_width(display_text) + 2 < cols:
                print(f'📁 {Color.FOLDER_FG}<{idx}>:{Color.RESET} {folder}')
            else:
                truncated = truncate_by_display_width(display_text, cols - 10)
                print(f'📁 {Color.FOLDER_FG}{truncated}{Color.RESET}{Color.ELLIPSIS_FG}...{Color.RESET}')
        
        # 显示文件
        for idx, file in self.files.items():
            display_text = f'<{idx}>: {file}'
            if get_display_width(display_text) + 2 < cols:
                print(f'📃 {Color.FILE_FG}<{idx}>:{Color.RESET} {file}')
            else:
                truncated = truncate_by_display_width(display_text, cols - 10)
                print(f'📃 {Color.FILE_FG}{truncated}{Color.RESET}{Color.ELLIPSIS_FG}...{Color.RESET}')
        
        self._show_menu()
    
    def _show_menu(self) -> None:
        """显示菜单和处理用户输入"""
        cols, _ = get_terminal_size()
        print("-" * cols)
        
        if self.mode == self.MODE_NORMAL:
            self._show_normal_menu()
        elif self.mode == self.MODE_MOVE:
            self._show_move_menu()
        elif self.mode == self.MODE_COPY:
            self._show_copy_menu()
        
        self._handle_user_input()
    
    def _show_normal_menu(self) -> None:
        """显示普通菜单"""
        cols, _ = get_terminal_size()
        menu_items = [
            MenuText.SELECT,
            MenuText.OPEN_NUM,
            MenuText.JUMP,
            MenuText.HOME,
            MenuText.PARENT,
            MenuText.NEW,
            MenuText.QUIT
        ]
        self._print_menu_items(menu_items, Color.MENU_BG, Color.MENU_FG, cols)
    
    def _show_move_menu(self) -> None:
        """显示移动文件菜单"""
        cols, _ = get_terminal_size()
        menu_items = [
            MenuText.OPEN_NUM,
            MenuText.JUMP,
            MenuText.HOME,
            MenuText.PARENT
        ]
        self._print_menu_items(menu_items, Color.MENU_BG, Color.MENU_FG, cols)
        
        special_items = [MenuText.MOVE_STATUS, MenuText.SELECT_DIR, MenuText.CANCEL]
        self._print_menu_items(special_items, Color.OPERATION_BG, Color.OPERATION_FG, cols)
    
    def _show_copy_menu(self) -> None:
        """显示复制文件菜单"""
        cols, _ = get_terminal_size()
        menu_items = [
            MenuText.OPEN_NUM,
            MenuText.JUMP,
            MenuText.HOME,
            MenuText.PARENT
        ]
        self._print_menu_items(menu_items, Color.MENU_BG, Color.MENU_FG, cols)
        
        special_items = [MenuText.COPY_STATUS, MenuText.SELECT_DIR, MenuText.CANCEL]
        self._print_menu_items(special_items, Color.OPERATION_BG, Color.OPERATION_FG, cols)
    
    @staticmethod
    def _print_menu_items(items, bg_color, fg_color, cols):
        """打印菜单项"""
        for item in items:
            padding = max(0, cols - get_display_width(item) - 1)
            print(f'{bg_color}{fg_color}{item}{" " * padding}|{Color.RESET}')
        print("-" * cols)
    
    def _handle_user_input(self) -> None:
        """处理用户输入"""
        error = ErrorManager()
        
        while True:
            user_input = input(f'{Color.INFO_FG}\033[1m>>>{Color.RESET}')
            error.clear()
            
            if self._process_input(user_input):
                break
            else:
                error.show('❌ 没有该命令! 请重新输入')
    
    def _process_input(self, user_input: str) -> bool:
        """处理用户输入，返回是否应该退出菜单循环"""
        user_input = user_input.lower().strip()
        
        # 公共命令
        if user_input == 'q':
            if self.mode == self.MODE_NORMAL:
                clear_screen()
                return True
            else:
                self.mode = self.MODE_NORMAL
                self.refresh_display()
                return True
        
        if user_input == 'j':
            path_input = input('请输入完整路径: ')
            try:
                os.chdir(path_input)
                self.refresh_display()
            except FileNotFoundError:
                print('❌ 请检查输入的路径是否正确!')
            return True
        
        if user_input == 'js':
            os.chdir(STARTUP_PATH)
            self.refresh_display()
            return True
        
        if user_input == 'r':
            os.chdir(self.current_path.parent)
            self.refresh_display()
            return True
        
        # 正常模式命令
        if self.mode == self.MODE_NORMAL:
            if user_input == 'n':
                self.operator.create_new_file_or_folder(self.current_path, self)
                return True
            
            if user_input.endswith('s') and is_int_convertible(user_input[:-1]):
                idx = int(user_input[:-1])
                if idx in self.folders:
                    self.operator.show_folder_menu(idx, self)
                    return True
                elif idx in self.files:
                    self.operator.show_file_menu(idx, self)
                    return True
            
            if is_int_convertible(user_input):
                idx = int(user_input)
                if idx in self.folders:
                    os.chdir(self.current_path / self.folders[idx])
                    self.refresh_display()
                    return True
                elif idx in self.files:
                    self.operator.handle_file_open(self.current_path / self.files[idx])
                    self.refresh_display()
                    return True
        
        # 移动/复制模式命令
        elif self.mode in (self.MODE_MOVE, self.MODE_COPY):
            if user_input == 'y':
                self.move_dest = self.current_path
                self.mode = self.MODE_NORMAL
                return True
            
            if is_int_convertible(user_input):
                idx = int(user_input)
                if idx in self.folders:
                    os.chdir(self.current_path / self.folders[idx])
                    self.refresh_display()
                    return True
        
        return False

# ==================== 文件操作类 ====================

class FileOperator:
    """处理具体的文件操作"""
    
    def show_folder_menu(self, folder_idx: int, manager: FileManager) -> None:
        """显示文件夹菜单"""
        clear_screen()
        folder_name = manager.folders[folder_idx]
        folder_path = manager.current_path / folder_name
        
        print(f'已选中文件夹:\n{"-" * 50}')
        print(f'{folder_name}\n')
        print("-" * 50)
        
        self._show_item_menu()
        self._handle_folder_operation(folder_path, manager)
    
    def show_file_menu(self, file_idx: int, manager: FileManager) -> None:
        """显示文件菜单"""
        clear_screen()
        file_name = manager.files[file_idx]
        file_path = manager.current_path / file_name
        
        print(f'已选中文件:\n{"-" * 50}')
        print(f'{file_name}\n')
        print("-" * 50)
        
        self._show_item_menu()
        self._handle_file_operation(file_path, manager)
    
    @staticmethod
    def _show_item_menu() -> None:
        """显示项目操作菜单"""
        cols, _ = get_terminal_size()
        menu_items = [
            MenuText.OPEN,
            MenuText.DELETE,
            MenuText.RENAME,
            MenuText.MOVE,
            MenuText.COPY,
            MenuText.PROPERTIES,
            MenuText.BACK
        ]
        
        for item in menu_items:
            padding = max(0, cols - get_display_width(item) - 1)
            print(f'{Color.MENU_BG}{Color.MENU_FG}{item}{" " * padding}|{Color.RESET}')
    
    def _handle_folder_operation(self, folder_path: Path, manager: FileManager) -> None:
        """处理文件夹操作"""
        error = ErrorManager()
        
        while True:
            try:
                choice = input('输入对应选项: ').strip()
                error.clear()
                
                if choice == '1':
                    os.chdir(folder_path)
                    manager.refresh_display()
                    return
                elif choice == '2':
                    self.delete_item(folder_path)
                    manager.refresh_display()
                    return
                elif choice == '3':
                    self.rename_item(folder_path, manager)
                    manager.refresh_display()
                    return
                elif choice == '4':
                    self.move_item(folder_path, manager)
                    manager.refresh_display()
                    return
                elif choice == '5':
                    self.copy_item(folder_path, manager)
                    manager.refresh_display()
                    return
                elif choice == '6':
                    self.show_properties(folder_path)
                    manager.refresh_display()
                    return
                elif choice.lower() == 'r':
                    manager.refresh_display()
                    return
                else:
                    error.show('❌ 没有该选项! 请重新输入')
            except KeyboardInterrupt:
                manager.refresh_display()
                return
            except Exception as e:
                logger.error(f"操作失败: {e}")
                error.show(f'❌ 操作失败: {e}')
    
    def _handle_file_operation(self, file_path: Path, manager: FileManager) -> None:
        """处理文件操作"""
        error = ErrorManager()
        
        while True:
            try:
                choice = input('输入对应选项: ').strip()
                error.clear()
                
                if choice == '1':
                    self.handle_file_open(file_path)
                    manager.refresh_display()
                    return
                elif choice == '2':
                    self.delete_item(file_path)
                    manager.refresh_display()
                    return
                elif choice == '3':
                    self.rename_item(file_path, manager)
                    manager.refresh_display()
                    return
                elif choice == '4':
                    self.move_item(file_path, manager)
                    manager.refresh_display()
                    return
                elif choice == '5':
                    self.copy_item(file_path, manager)
                    manager.refresh_display()
                    return
                elif choice == '6':
                    self.show_properties(file_path)
                    manager.refresh_display()
                    return
                elif choice.lower() == 'r':
                    manager.refresh_display()
                    return
                else:
                    error.show('❌ 没有该选项! 请重新输入')
            except KeyboardInterrupt:
                manager.refresh_display()
                return
            except Exception as e:
                logger.error(f"操作失败: {e}")
                error.show(f'❌ 操作失败: {e}')
    
    def handle_file_open(self, file_path: Path) -> None:
        """处理打开文件"""
        clear_screen()
        error = ErrorManager()
        
        print(f'你想用什么方式打开 {file_path.name}?\n\n')
        print(f'系统默认方式[实验性功能]-->1\n当前脚本预览-->2\n取消-->r\n')
        
        while True:
            choice = input('输入对应选项: ').strip()
            error.clear()
            
            if choice == '1':
                try:
                    DefaultOpener.open_file(file_path)
                except Exception as e:
                    print(f'❌ 打开失败: {e}')
                    input('按回车键继续...')
                return
            elif choice == '2':
                self._preview_file(file_path)
                return
            elif choice.lower() == 'r':
                return
            else:
                error.show('❌ 没有该选项! 请重新输入')
    
    @staticmethod
    def _preview_file(file_path: Path) -> None:
        """预览文件内容"""
        clear_screen()
        cols, _ = get_terminal_size()
        
        print(f'\n{Color.PATH_BG}当前目录 --> {file_path.parent}{Color.RESET}')
        print(f'正在读取文件: {file_path.name}\n{Color.INFO_FG}{"-" * cols}{Color.RESET}')
        
        try:
            content = file_path.read_text(encoding='utf-8')
            print(content)
        except UnicodeDecodeError:
            print('❌ 该文件不是纯文本文件\n或编码不是 UTF-8\n无法直接显示')
        except Exception as e:
            print(f'❌ 读取失败: {e}')
        
        print(f'{Color.INFO_FG}{"-" * cols}{Color.RESET}')
        print('由于时间和本人技术原因，暂时不提供编辑功能!')
        print('若需要编辑文件，请选择使用系统默认方式去打开它!')
        input('\n按回车键返回菜单...')
    
    def delete_item(self, item_path: Path) -> None:
        """删除文件或文件夹"""
        error = ErrorManager()
        
        print(f'{Color.ERROR_FG}删除后将无法恢复!{Color.RESET}')
        print('确认删除? 确认-->y 取消-->n')
        
        while True:
            choice = input('输入对应字符: ').strip().lower()
            error.clear()
            
            if choice == 'y':
                try:
                    if item_path.is_file():
                        item_path.unlink()
                    elif item_path.is_dir():
                        import shutil
                        shutil.rmtree(item_path)
                    print('✅ 删除成功')
                except Exception as e:
                    print(f'❌ 删除失败: {e}')
                    logger.error(f"删除失败: {e}")
                return
            elif choice == 'n':
                return
            else:
                error.show('❌ 没有该选项! 请重新输入')
    
    def rename_item(self, item_path: Path, manager: FileManager) -> None:
        """重命名文件或文件夹"""
        error = ErrorManager()
        
        print('是否继续重命名? 重命名-->y 取消-->n')
        
        while True:
            choice = input('输入对应选项: ').strip().lower()
            error.clear()
            
            if choice == 'y':
                new_name = input('输入新名称: ').strip()
                error.clear()
                
                if not new_name:
                    error.show('❌ 名称不能为空!')
                    continue
                
                new_path = item_path.parent / new_name
                
                if new_path.exists():
                    error.show('❌ 已存在同名文件或文件夹!')
                    continue
                
                try:
                    item_path.rename(new_path)
                    print('✅ 重命名成功')
                except Exception as e:
                    print(f'❌ 重命名失败: {e}')
                    logger.error(f"重命名失败: {e}")
                return
            elif choice == 'n':
                return
            else:
                error.show('❌ 没有该选项! 请重新输入')
    
    def move_item(self, item_path: Path, manager: FileManager) -> None:
        """移动文件或文件夹"""
        manager.mode = FileManager.MODE_MOVE
        manager.refresh_display()
    
    def copy_item(self, item_path: Path, manager: FileManager) -> None:
        """复制文件或文件夹"""
        manager.mode = FileManager.MODE_COPY
        manager.refresh_display()
    
    def show_properties(self, item_path: Path) -> None:
        """显示文件或文件夹属性"""
        clear_screen()
        cols, _ = get_terminal_size()
        
        print("-" * cols)
        print(f'{Color.INFO_FG}名称{Color.RESET} {item_path.name}\n')
        print(f'{Color.INFO_FG}目录{Color.RESET} {item_path.parent}\n')
        
        if item_path.is_file():
            print(f'{Color.INFO_FG}类型{Color.RESET} 文件\n')
            size = item_path.stat().st_size
            size_str = self._format_size(size)
            print(f'{Color.INFO_FG}大小{Color.RESET} {size_str}\n')
        elif item_path.is_dir():
            print(f'{Color.INFO_FG}类型{Color.RESET} 文件夹\n')
            size = self._calculate_dir_size(item_path)
            size_str = self._format_size(size)
            print(f'{Color.INFO_FG}大小{Color.RESET} {size_str}\n')
        
        mtime = item_path.stat().st_mtime
        time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f'{Color.INFO_FG}修改时间{Color.RESET} {time_str}\n')
        
        mode = os.stat(item_path).st_mode
        print(f'{Color.INFO_FG}权限{Color.RESET} {stat.filemode(mode)}\n')
        print("-" * cols)
        
        input('\n按回车键返回菜单...')
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f}PB"
    
    @staticmethod
    def _calculate_dir_size(dir_path: Path) -> int:
        """计算文件夹大小"""
        total_size = 0
        try:
            for entry in dir_path.rglob("*"):
                if entry.is_file():
                    try:
                        total_size += entry.stat().st_size
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return total_size
    
    def create_new_file_or_folder(self, current_path: Path, manager: FileManager) -> None:
        """创建新文件或文件夹"""
        clear_screen()
        error = ErrorManager()
        
        print('选择新建类型:\n\n文件夹-->1\n文件-->2\n取消-->r\n')
        
        while True:
            choice = input('输入对应选项: ').strip()
            error.clear()
            
            if choice in ('1', '2'):
                while True:
                    name = input('输入新建名称: ').strip()
                    error.clear()
                    
                    if not name:
                        error.show('❌ 名称不能为空!')
                        continue
                    
                    new_path = current_path / name
                    
                    if not new_path.exists():
                        try:
                            if choice == '1':
                                new_path.mkdir(exist_ok=True)
                                print('✅ 文件夹创建成功')
                            else:
                                new_path.touch()
                                print('✅ 文件创建成功')
                            manager.refresh_display()
                            return
                        except Exception as e:
                            print(f'❌ 创建失败: {e}')
                            logger.error(f"创建失败: {e}")
                            return
                    else:
                        error.show('❌ 已存在同名文件或文件夹!')
                        while True:
                            confirm = input('是否继续新建? 新建-->y 取消-->n: ').strip().lower()
                            error.clear()
                            
                            if confirm == 'y':
                                break
                            elif confirm == 'n':
                                manager.refresh_display()
                                return
                            else:
                                error.show('❌ 没有该选项! 请重新输入')
            elif choice.lower() == 'r':
                manager.refresh_display()
                return
            else:
                error.show('❌ 没有该选项! 请重新输入')

# ==================== 主程序 ====================

STARTUP_PATH = Path.cwd()

def check_dependencies() -> bool:
    """检查必要的库"""
    required_libs = [
        'os', 'sys', 'stat', 'logging', 'platform', 'datetime',
        'subprocess', 'unicodedata', 'pathlib'
    ]
    
    for lib in required_libs:
        if not importlib.util.find_spec(lib):
            print(f'❌ 缺少必要的库: {lib}')
            return False
    return True

def main() -> None:
    """主函数"""
    if not check_dependencies():
        print('缺少必要的库，请安装之后再使用该脚本!')
        return
    
    try:
        manager = FileManager()
        manager.refresh_display()
    except KeyboardInterrupt:
        clear_screen()
        print('程序已退出')
    except Exception as e:
        logger.error(f"程序异常: {e}")
        print(f'程序异常: {e}')

if __name__ == "__main__":
    main()
