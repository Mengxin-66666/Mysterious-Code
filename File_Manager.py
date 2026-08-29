'''Python Terminal File Manager

一个使用 Python 编写的简单终端文件管理器。
目前项目处于 Alpha / Early Development 阶段。

⚠️ 当前状态

这个项目目前仍处于早期开发阶段，代码中存在一些已知 Bug 和未完成的功能。
目前不建议将它用于重要文件的管理操作。
尤其是以下功能目前可能存在问题：

- 文件移动
- 文件复制
- 文件重命名
- 文件夹大小计算
- 权限异常处理
- 不同终端环境下的显示
- Windows / Linux / Termux 兼容性
- 部分路径处理

如果你发现新的 Bug，欢迎提交 Issue。

✨ 当前功能

目前已经实现：

- 📁 浏览文件夹
- 📃 浏览文件
- 📂 进入文件夹
- 🔙 返回上一级目录
- 🏠 返回启动目录
- 🔎 跳转到指定目录
- 📄 创建文件
- 📁 创建文件夹
- 🗑️ 删除文件
- 🗑️ 删除文件夹
- ✏️ 重命名
- 📦 移动文件/文件夹
- 📋 复制文件/文件夹
- ℹ️ 查看文件属性
- 📖 UTF-8 文本文件预览
- 🖥️ 调用系统默认程序打开文件[不稳定]
- 🌏 中英文混合字符显示宽度处理
- 📱 部分 Termux 支持

🚧 开发计划

未来可能加入：

- [ ] 修复现有 Bug
- [ ] 更完善的异常处理
- [ ] 文件搜索
- [ ] 文件排序
- [ ] 分页显示
- [ ] 更完善的编码检测
- [ ] 更完善的 Windows 支持
- [ ] 更完善的 Termux 支持
- [ ] 批量文件操作
- [ ] 文件编辑
- [ ] 压缩/解压
- [ ] 更完善的终端 UI

▶️ 运行

需要Python3。
直接运行：
python file_manager.py
或者：
python3 file_manager.py
本项目目前没有第三方 Python 依赖，主要使用 Python 标准库。

⚠️ 使用注意

由于项目目前处于 Alpha 阶段：
请不要使用本程序对重要数据进行删除、移动或复制操作。
建议先在测试目录中进行测试。

🤝 贡献

如果你发现 Bug，可以提交 Issue。
如果你愿意修复 Bug，也欢迎提交 Pull Request。
目前项目处于早期阶段，因此欢迎任何关于代码结构、功能设计和用户体验的建议。

📄 License

本项目使用 MIT License。'''


#检查导入的库是否存在
import importlib.util
#必要库
import os
import sys
import stat
import time
import shutil
import platform
import subprocess
import unicodedata
from pathlib import Path
from datetime import datetime




def clear_nums_screen(n):
	'''清理指定行数日志'''
	for _ in range(n):
		sys.stdout.write("\033[F")  # 光标上移一行
		sys.stdout.write("\033[2K") # 清除该行
	
	sys.stdout.flush()



def clear_screen():
	"""清空控制台显示（跨平台）"""
	os.system('cls' if os.name == 'nt' else 'clear')

def is_int_convertible(value):
	"""检测数据是否可转换为 int"""
	try:
		int(value)
		return True
	except (ValueError, TypeError):
		return False

def columns_lines():
	"""检测终端控制台可显示的字符行数和列数"""
	size = shutil.get_terminal_size()
	#size.columns-->列数
	#size.lines-->行数
	return size.columns, size.lines


def display_width(s):
	"""检测字符串实际占用的显示长度"""
	width = 0

	for ch in s:
		kind = unicodedata.east_asian_width(ch)

		if kind in ("W", "F"):
			width += 2
		else:
			width += 1

	return width



def slice_by_display_width(s, start, end):
	"""截取字符串实际长度"""
	result = []
	width = 0

	for ch in s:
		ch_width = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1

		ch_start = width
		ch_end = width + ch_width

		if ch_end > start and ch_start < end:
			result.append(ch)

		width = ch_end

		if width >= end:
			break

	return "".join(result)

import unicodedata

#-------------------------------------------------------------------------



def substr_width(s, start, length):
	"""
	按显示宽度截取字符串

	参数:
		s:
			原字符串

		start:
			正数:
				从左侧开始，第 start 个显示位置（从1开始）
			负数:
				从右侧开始，-1表示最后一个显示位置

		length:
			正数:
				向右截取 length 个显示宽度
			负数:
				向左截取 abs(length) 个显示宽度

	返回:
		截取后的字符串
	"""

	def char_width(ch):
		return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1

	# 保存每个字符对应的显示位置
	chars = []
	pos = 0

	for ch in s:
		w = char_width(ch)
		chars.append((ch, pos, pos + w))
		pos += w

	total_width = pos

	# 计算起始显示位置
	if start > 0:
		start_pos = start - 1
	else:
		start_pos = total_width + start

	# 计算结束位置
	if length > 0:
		end_pos = start_pos + length
	else:
		end_pos = start_pos + 1
		start_pos = end_pos + length

	# 根据显示范围提取字符
	result = []

	for ch, ch_start, ch_end in chars:
		if ch_end > start_pos and ch_start < end_pos:
			result.append(ch)

	return "".join(result)
#-------------------------------------------------------------------------

class ErrorManager:
	'''清理并刷新终端指定部分'''
	def __init__(self):
		self.lines = 0


	def show(self, *msgs):

		for msg in msgs:
			print(msg)
			self.lines += msg.count("\n") + 1
			


	def clear(self):

		if self.lines:
	
			clear_nums_screen(self.lines + 1)
	
			self.lines = 0




class DefaultOpener:
	"""跨平台调用系统默认打开方式"""

	@staticmethod
	def is_termux():
		"""检测是否运行在Termux"""
		return (
			"TERMUX_VERSION" in os.environ
			or os.path.exists("/data/data/com.termux")
		)

	@staticmethod
	def open(target):
		target = str(target)

		# Termux
		if DefaultOpener.is_termux():
			DefaultOpener._open_termux(target)
			return

		system = platform.system()

		if system == "Windows":
			os.startfile(target)

		elif system == "Darwin":
			subprocess.run(["open", target], check=True)

		elif system == "Linux":
			subprocess.run(["xdg-open", target], check=True)

		else:
			raise RuntimeError(f"不支持系统: {system}")

	@staticmethod
	def _open_termux(target):
		"""
		Termux调用Android Intent
		"""

		# URL
		if target.startswith(("http://", "https://")):
			cmd = ["termux-open-url", target]

		else:
			cmd = ["termux-open", target]

		try:
			subprocess.run(
				cmd,
				check=True
			)

		except FileNotFoundError:
			raise RuntimeError(
				"未找到termux-open，请安装Termux:API插件并启用"
			)

	@staticmethod
	def open_file(filepath):
		path = Path(filepath)

		if not path.exists():
			raise FileNotFoundError(filepath)

		DefaultOpener.open(path)

	@staticmethod
	def open_url(url):
		DefaultOpener.open(url)


class DocumentShow:
	'''显示文件和文件夹'''
	def __init__(self):
		'''加载需要的变量'''
		self.wenjianjia = {}
		self.wenjian = {}
		#1正常操作显示
		#2移动文件时显示
		self.Function = 1
		self.move_true = None
	def texts_os(self):
		"""刷新界面"""
		clear_screen()  # 刷新前先清屏
		self.wenjianjia.clear()
		self.wenjian.clear()
		self.now_path()
		
		
	def now_path(self):
		'''显示当前目录'''
		self.pathss = Path.cwd()
		aaa = f'当前目录 --> {self.pathss}'
		if display_width(aaa) < columns_lines()[0]:
			print(f'\033[48;2;30;30;30m{aaa}\033[0m\n')
		else:
			print(f'\033[48;2;30;30;30m{aaa[0:9]}...{substr_width(aaa, -0, -columns_lines()[0]+15)}\033[0m\n')
		self.verify_Permissions()
	def verify_Permissions(self):
		try:
			os.scandir(self.pathss)
		except FileNotFoundError:
			print('没有该文件或目录')
			caozuo()
		except PermissionError:
			print('权限被拒绝')
			caozuo()
		else:
			self.show_folder_document()
		
	def show_folder_document(self):
		'''显示文件夹和文件'''
		nums = 1
		#------------------------------------------------------
		wenjian_temporary = []
		with os.scandir(self.pathss) as entries:
			for entry in entries:
				if entry.is_dir():
					self.wenjianjia[nums] = entry.name
					nums += 1
				elif entry.is_file():
					wenjian_temporary.append(entry.name)
		for document in wenjian_temporary:
			self.wenjian[nums] = document
			nums += 1
		#------------------------------------------------------
		for nums, folders in self.wenjianjia.items():
			aaa = f'<{nums}>: {folders}'
			if display_width(aaa)+2 < columns_lines()[0]:
				print(f'📁 \033[38;2;255;255;0m<{nums}>:\033[0m {folders}')
			else:
				print(f'📁 \033[38;2;255;255;0m{aaa[0:len(str(nums))+4]}\033[0m{slice_by_display_width(aaa, len(str(nums))+4, columns_lines()[0]-6)}\033[38;2;0;175;0m...\033[0m')
		for nums, document in self.wenjian.items():
			aaa = f'<{nums}>: {document}'
			if display_width(aaa)+2 < columns_lines()[0]:
				print(f'📃 \033[38;2;135;215;255m<{nums}>:\033[0m {document}')
			else:
				print(f'📃 \033[38;2;135;215;255m{aaa[0:len(str(nums))+4]}\033[0m{slice_by_display_width(aaa, len(str(nums))+4, columns_lines()[0]-6)}\033[38;2;0;175;0m...\033[0m')
		caozuo()

class operate:
	'''处理选择的文件夹或文件'''
	def __init__(self):
		'''加载需要的变量'''
		self.path = Path.cwd()
		self.path_old = None
		
	def folders(self, nums):
		'''处理文件夹'''
		clear_screen()
		print(f'已选中文件夹:\n{columns_lines()[0] * "-"}')
		print(f'{user_your.wenjianjia[nums]}\n')
		print(columns_lines()[0] * "-")
		colors = '\033[48;2;95;135;255m\033[38;2;95;255;255m'
		choose = ['打开-->1', 
				'删除-->2',
				'重命名-->3',
				'移动-->4',
				'复制-->5',
				'属性-->6',
				'返回-->r']
		for choose_num in choose:
			print(f'{colors}{choose_num}{(columns_lines()[0]-display_width(choose_num)-1) * " "}|\033[0m')
		error = ErrorManager()
		while True:
			enters = input('输入对应选项:')
			error.clear()
			if is_int_convertible(enters):
				num = int(enters)
				if num == 1:
					self.open_choose(self.path / user_your.wenjianjia[nums])
					user_your.texts_os()
					return
				elif num == 2:
					self.judgment_choose_2(self.path / user_your.wenjianjia[nums])
					return
				elif num == 3:
					self.judgment_choose_3(self.path / user_your.wenjianjia[nums])
					return
				elif num == 4:
					self.judgment_choose_4(self.path, user_your.wenjianjia[nums])
					return
				elif num == 5:
					self.judgment_choose_5(self.path, user_your.wenjianjia[nums])
					return
				elif num == 6:
					self.judgment_choose_6(self.path, user_your.wenjianjia[nums])
					return
				else:
					error.show('❌没有该选项! 请重新输入')
			elif enters.lower() == 'r':
				user_your.texts_os()
				return
			else:
				error.show('❌没有该选项! 请重新输入')
	
	def document(self, nums):
		'''处理文件'''
		clear_screen()
		print(f'已选中文件:\n{columns_lines()[0] * "-"}')
		print(f'{user_your.wenjian[nums]}\n')
		print(columns_lines()[0] * "-")
		colors = '\033[48;2;95;135;255m\033[38;2;95;255;255m'
		choose = ['打开-->1', 
				'删除-->2',
				'重命名-->3',
				'移动-->4',
				'复制-->5',
				'属性-->6',
				'返回-->r']
		for choose_num in choose:
			print(f'{colors}{choose_num}{(columns_lines()[0]-display_width(choose_num)-1) * " "}|\033[0m')
		error = ErrorManager()
		while True:
			enters = input('输入对应选项:')
			error.clear()
			if is_int_convertible(enters):
				num = int(enters)
				if num == 1:
					self.judgment_choose_1(self.path / user_your.wenjian[nums])
					return
				elif num == 2:
					self.judgment_choose_2(self.path / user_your.wenjian[nums])
					return
				elif num == 3:
					self.judgment_choose_3(self.path / user_your.wenjian[nums])
					return
				elif num == 4:
					self.judgment_choose_4(self.path, user_your.wenjian[nums])
					return
				elif num == 5:
					self.judgment_choose_5(self.path, user_your.wenjian[nums])
					return
				elif num == 6:
					self.judgment_choose_6(self.path, user_your.wenjian[nums])
					return
				else:
					error.show('❌没有该选项! 请重新输入')
			elif enters.lower() == 'r':
				user_your.texts_os()
				return
			else:
				error.show('❌没有该选项! 请重新输入')
	
	def judgment_choose(self, path_now):
		'''判断是文件还是文件夹
		返回值为True是文件
		返回值为False是文件夹
		返回值为None是没有该路径或其他原因访问失败'''
		#path_now传的是完整路径
		path = Path(path_now)
		if path.is_file():
			return True
		elif path.is_dir():
			return False
		else:
			return None
	
	def new_document_folder(self):
		'''新建文件或文件夹'''
		clear_nums_screen(1)
		error = ErrorManager()
		print('选择新建类型:\n\n文件夹-->1\n文件-->2\n取消-->r\n')
		while True:
			new_now = input('输入对应选项:')
			error.clear()
			if new_now in ('1', '2'):
				while True:
					new_name = input('输入新建名称:')
					error.clear()
					if not (self.path / new_name).exists():
						if new_now == '1':
							Path(self.path / new_name).mkdir(exist_ok=True)
							user_your.texts_os()
							return
						elif new_now == '2':
							Path(self.path / new_name).touch()
							user_your.texts_os()
							return
					else:
						clear_nums_screen(1)
						error.show('❌存在重名文件或文件夹!\n是否继续新建?')
						error.show('新建-->y\n取消-->n\n')
						while True:
							now_choose = input('输入新建名称:')
							error.clear()
							if now_choose.lower() == 'y':
								break
							elif now_choose.lower() == 'n':
								user_your.texts_os()
								return
							else:
								error.show('❌没有该选项! 请重新输入')
								error.show('❌存在重名文件或文件夹!\n是否继续新建?')
								error.show('新建-->y\n取消-->n\n')
					
					
					
			elif new_now.lower() == 'r':
				user_your.texts_os()
				return
			else:
				error.show('❌没有该选项! 请重新输入')
	def open_choose(self, path_now):
		'''打开文件或文件夹'''
		#path_now传的是完整路径
		judgment = self.judgment_choose(path_now)
		if judgment == True:
			os.system("cls" if os.name == "nt" else "clear")
			print(f'\n\033[48;2;128;128;128m当前目录 --> {self.path}\033[0m')
			print(f'正在读取文件: {os.path.basename(path_now)}\n\033[38;2;0;255;255m{columns_lines()[0] * "-"}\033[0m')
			try:
				content = Path(path_now).read_text(encoding="utf-8")
				print(content)
			except UnicodeDecodeError:
				print('❌该文件不是纯文本文件\n或编码不是 UTF-8\n无法直接显示')
			except Exception as e:
				print(f'❌读取失败:{e}')
			print(f'\033[38;2;0;255;255m{columns_lines()[0] * "-"}\033[0m')
			print('由于时间和本人技术原因，暂时不提供编辑功能!')
			print('若需要编辑文件，请选择使用系统默认方式去打开它!')
			input('\n按回车键返回菜单...')  # 暂停，方便查看内容
		elif judgment == False:
			os.chdir(str(path_now))
		else:
			return False
	
	def delete_choose(self, path_now):
		'''删除文件或文件夹'''
		#path_now传的是完整路径
		judgment = self.judgment_choose(path_now)
		if judgment == True:
			Path(path_now).unlink()
		elif judgment == False:
			shutil.rmtree(path_now)
		else:
			return False
	
	def name_choose(self, path_now, new_name):
		'''命名文件或文件夹'''
		#path_now传的是完整路径
		#new_name传的是新的名称
		judgment = self.judgment_choose(path_now)
		if judgment == True or judgment == False:
			Path(path_now).rename(new_name)
		else:
			return False
	
	def move_choose(self, path_old, path_now):
		'''移动文件或文件夹'''
		#path_nold传的是选择的文件或文件夹路径
		#path_now传的是确定移动到的路径
		judgment = self.judgment_choose(path_old)
		if judgment == True or judgment == False:
			shutil.move(str(path_old), str(path_now))
		else:
			return False
		
	def copy_choose(self, path_old, path_now):
		'''复制文件或文件夹'''
		#path_nold传的是选择的文件或文件夹路径
		#path_now传的是确定复制到的路径
		judgment = self.judgment_choose(path_old)
		if judgment == True:
			shutil.copy2(path_old, path_now)
		elif judgment == False:
			shutil.copytree(path_old, path_now)
		else:
			return False
		
	def property_choose(self, path_now):
		'''查看文件或文件夹的属性'''
		#path_now传的是完整路径
		judgment = self.judgment_choose(path_now)
		if judgment == True:
			pass
		elif judgment == False:
			pass
		else:
			return False
		
	def judgment_choose_1(self, path_now):
		'''选择功能1'''
		clear_nums_screen(1)
		judgment = self.judgment_choose(path_now)
		if judgment == True:
			error = ErrorManager()
			print(f'你想用什么方式去打开{os.path.basename(path_now)}?\n\n系统默认方式[实验性功能]-->1\n当前的脚本--2\n取消-->r\n')
			while True:
				open_now = input('输入对应选项:')
				error.clear()
				if open_now == '1':
					DefaultOpener.open_file(str(path_now))
					user_your.texts_os()
					return
				elif open_now == '2':
					self.open_choose(path_now)
					user_your.texts_os()
					return
				elif open_now.lower() == 'r':
					user_your.texts_os()
					return
				else:
					error.show('❌没有该选项! 请重新输入')
		elif judgment == False:
			self.open_choose(path_now)
			user_your.texts_os()
		else:
			return False
		
	
	def judgment_choose_2(self, path_now):
		'''选择功能2'''
		colors = '\033[38;2;255;0;0m'
		shan = '删除后将无法恢复!'
		print(f'{colors}{shan}\033[0m')
		print(f'确认删除?\n确认-->y\n取消-->n')
		while True:
			confirm_delete = input('输入对应字符:')
			if confirm_delete.lower() == 'y':
				self.delete_choose(path_now)
				user_your.texts_os()
				return
			elif confirm_delete.lower() == 'n':
				user_your.texts_os()
				return
			else:
				clear_nums_screen(numss)
				numss = 2
				print('❌没有该选项! 请重新输入')
	
	def judgment_choose_3(self, path_now):
		'''选择功能3'''
		clear_nums_screen(1)
		error = ErrorManager()
		error.show('是否继续重命名?\n重命名-->y\n取消-->n')
		while True:
			xuan = input('输入对应选项:')
			error.clear()
			if xuan.lower() == 'y':
				new_name = input('重命名:')
				target = self.path / new_name
				if not target.exists():
					self.name_choose(path_now, new_name)
					user_your.texts_os()
					return
				else:
					clear_nums_screen(1)
					while True:
						error.show('存在重名文件或文件夹')
						error.show('是否继续重命名?\n重命名-->y\n取消-->n')
						xuan = input('输入对应选项:')
						error.clear()
						if xuan.lower() == 'y':
							error.show('是否继续重命名?\n重命名-->y\n取消-->n')
							break
						elif xuan.lower() == 'n':
							user_your.texts_os()
							return
						else:
							error.show('❌没有该选项! 请重新输入')
			elif xuan.lower() == 'n':
				user_your.texts_os()
				return
			else:
				error.show('❌没有该选项! 请重新输入')
				error.show('是否继续重命名?\n重命名-->y\n取消-->n')

	
	def judgment_choose_4(self, path_now, name):
		'''选择功能4'''
		clear_nums_screen(1)
		error = ErrorManager()
		user_your.Function = 2
		path_old = path_now
		while True:
			user_your.texts_os()
			directory = Path(user_your.move_true)
			# 要检查的文件或文件夹名称
			target = directory / name
			if directory == path_old:
				user_your.texts_os()
				return
			elif target.exists():
				error.show("存在同名文件或文件夹\n是否重命名来移动它?\n重命名-->y\n取消-->n")
				while True:
					xuan = input('输入对应选项:')
					error.clear()
					if xuan.lower() == 'y':
						new_name = input('输入新名称:')
						error.clear()
						target = directory / new_name
						if not target.exists():
							Path(path_old / name).rename(new_name)
							user_your.Function = 1
							src = path_old / new_name
							dst = directory
							self.move_choose(src, dst)
							user_your.texts_os()
							return
						else:
							clear_nums_screen(1)
							error.show("存在同名文件或文件夹\n是否重命名来移动它?\n重命名-->y\n取消-->n")
					elif xuan.lower() == 'n':
						user_your.texts_os()
						return
					else:
						error.show('❌没有该选项! 请重新输入')
						error.show("存在同名文件或文件夹\n是否重命名来移动它?\n重命名-->y\n取消-->n")
			else:
				user_your.Function = 1
				src = path_old / name
				dst = directory
				self.move_choose(src, dst)
				user_your.texts_os()
				return
		
	def judgment_choose_5(self, path_now, name):
		'''选择功能5'''
		clear_nums_screen(1)
		error = ErrorManager()
		user_your.Function = 3
		path_old = path_now
		user_your.texts_os()
		error.show(f'是否复制该文件夹{name}至{user_your.move_true}')
		error.show('复制-->y\n取消-->n')
		while True:
			xuan = input('输入对应选项:')
			error.clear()
			if xuan.lower() == 'y':
				dst_folder = Path(user_your.move_true)
				target = dst_folder / name
				if not target.exists():
					user_your.Function = 1
					src_folder = path_old / name
					self.copy_choose(src_folder, target)
					user_your.texts_os()
					return
				else:
					error.show("存在同名文件夹\n是否重命名来复制它?\n重命名-->y\n取消-->n")
					while True:
						xuan = input('输入对应选项:')
						if xuan.lower() == 'y':
							new_name = input('输入新名称:')
							target = dst_folder / new_name
							if not target.exists():
								user_your.Function = 1
								src_folder = path_old / name
								target = dst_folder / new_name
								self.copy_choose(src_folder, target)
								user_your.texts_os()
								return
						elif xuan.lower() == 'n':
							user_your.texts_os()
							return
						else:
							error.show('❌没有该选项! 请重新输入')
							error.show("存在同名文件夹\n是否重命名来复制它?\n重命名-->y\n取消-->n")
			elif xuan.lower() == 'n':
				user_your.texts_os()
				return
			else:
				error.show('❌没有该选项! 请重新输入')
				error.show(f'是否复制该文件夹{name}至{user_your.move_true}')
				error.show('复制-->y\n取消-->n')
	
	def judgment_choose_6(self, path_now, name):
		'''选择功能6'''
		judgment = self.judgment_choose(path_now / name)
		colos = "\033[38;2;0;255;255m"
		clear_nums_screen(1)
		print(columns_lines()[0] * "-")
		print(f'{colos}名称\033[0m {name}\n')
		print(f'{colos}目录\033[0m {path_now}\n')
		if judgment == True:
			print(f'{colos}类型\033[0m 文件\n\n')
		elif judgment == False:
			print(f'{colos}类型\033[0m 文件夹\n\n')
		else:
			print(f'{colos}类型\033[0m 未知\n\n')
		num = None
		if judgment == True:
			size = Path(path_now / name)
			num = size.stat().st_size
			units = ["B", "KB", "MB", "GB", "TB"]
			for unit in units:
				if num < 1024:
					clear_nums_screen(1)
					print(f"{colos}大小\033[0m {num:.2f}{unit}")
					break
				num /= 1024
			else:
				clear_nums_screen(1)
				print(f"{colos}大小\033[0m {num:.2f}PB")
		elif judgment == False:
			size = path_now / name
			num = 0
			units = ["B", "KB", "MB", "GB", "TB"]
			for f in size.rglob("*"):
				if f.is_file():
					num += f.stat().st_size
					num_s = num
					for unit in units:
						if num_s < 1024:
							clear_nums_screen(1)
							print(f"{colos}大小\033[0m {num_s:.2f}{unit}")
							break
						num_s /= 1024
					else:
						clear_nums_screen(1)
						print(f"{colos}大小\033[0m {num_s:.2f}PB")
		file = Path(self.path / name)
		mtime = file.stat().st_mtime
		time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
		print(f'\n{colos}修改时间\033[0m {time_str}\n')
		mode = os.stat(path_now / name).st_mode
		print(f'{colos}权限\033[0m {stat.filemode(mode)}\n')
		print(columns_lines()[0] * "-")
		input('\n按回车键返回菜单...')
		user_your.texts_os()
	
def choose_operate():
	path = Path.cwd()
	error = ErrorManager()
	while True:
		opens = input('\033[38;2;0;255;255m\033[1m>>>\033[0m')
		error.clear()
		if opens.lower() == 'j':
			pathss = input('请输入完整路径:')
			try:
				os.chdir(pathss)
				user_your.texts_os()
			except FileNotFoundError:
				print('\n❌请检查输入的路径是否正确!')
			else:
				return
		elif opens.lower() == 'js':
			#回到首页
			os.chdir(path_start)
			user_your.texts_os()
			return
		elif opens.lower() == 'r':
			# 返回上一级
			os.chdir(path.parent)
			user_your.texts_os()
			return
		elif opens.lower() == 'q':
			if user_your.Function == 1:
				# 退出
				clear_screen()
				return
			elif user_your.Function in (2, 3):
				user_your.Function = 1
				user_your.texts_os()
				return
		elif opens.lower() == 'n':
			if user_your.Function == 1:
				operate().new_document_folder()
				return
			
		elif opens.lower() == 'y' and user_your.Function in (2, 3):
			#选中当前目录
			user_your.move_true = path
			user_your.Function = 1
			return
		elif is_int_convertible(opens):
			nums = int(opens)
			if nums in user_your.wenjianjia:
				# 进入文件夹
				os.chdir(path / user_your.wenjianjia[nums])
				user_your.texts_os()
				return
				
			elif nums in user_your.wenjian:
				if user_your.Function == 1:
					operate().judgment_choose_1(path / user_your.wenjian[nums])
					return
				if user_your.Function in (2, 3):
					error.show('❌该选项不是文件夹! 请重新输入')
			else:
				error.show('❌没有该文件夹或文件! 请重新输入')
		elif user_your.Function == 1 and opens[-1:].lower() == 's' and is_int_convertible(opens[0:-1]):
			nums = int(opens[0:-1])
			if nums in user_your.wenjianjia:
				operate().folders(nums)
			elif nums in user_your.wenjian:
				operate().document(nums)
			return
		else:
			error.show('❌没有该命令! 请重新输入')


def caozuo():
	"""操作提示"""
	#正常选项
	print(columns_lines()[0] * "-")
	choose_1 = '选中-->输入对应的数字+s'
	choose_2 = '打开-->输入对应的数字'
	choose_3 = '跳转至指定目录-->j'
	choose_4 = '回到首页目录-->js'
	choose_5 = '返回上一级目录-->r'
	choose_6 = '退出-->q'
	choose_7 = '新建-->n'
	#特殊选项
	choose_special_1 = '选中当前目录--y'
	choose_special_2 = '取消-->q'
	if user_your.Function == 1:
		colors = '\033[48;2;0;95;175m\033[38;2;0;215;255m'
		choose_all = [choose_1, choose_2, choose_3, choose_4, choose_5, choose_7, choose_6]
		for choose_i in choose_all:
			print(f'{colors}{choose_i}{(columns_lines()[0]-display_width(choose_i)-1) * " "}|\033[0m')
		print(columns_lines()[0] * "-")
	elif user_your.Function == 2:
		colors = '\033[48;2;0;95;175m\033[38;2;0;215;255m'
		colors_move = '\033[48;2;0;0;255m\033[38;2;255;225;255m'
		choose_all = [choose_2, choose_3, choose_4, choose_5]
		for choose_i in choose_all:
			print(f'{colors}{choose_i}{(columns_lines()[0]-display_width(choose_i)-1) * " "}|\033[0m')
		choose_special = '当前操作状态>>>移动'
		choose_special_all = [choose_special, choose_special_1, choose_special_2]
		for choose_i in choose_special_all:
			print(f'{colors_move}{choose_i}{(columns_lines()[0]-display_width(choose_i)-1) * " "}|\033[0m')
		print(columns_lines()[0] * "-")
	elif user_your.Function == 3:
		colors = '\033[48;2;0;95;175m\033[38;2;0;215;255m'
		colors_move = '\033[48;2;0;0;255m\033[38;2;255;225;255m'
		choose_all = [choose_2, choose_3, choose_4, choose_5]
		for choose_i in choose_all:
			print(f'{colors}{choose_i}{(columns_lines()[0]-display_width(choose_i)-1) * " "}|\033[0m')
		choose_special = '当前操作状态>>>复制'
		choose_special_all = [choose_special, choose_special_1, choose_special_2]
		for choose_i in choose_special_all:
			print(f'{colors_move}{choose_i}{(columns_lines()[0]-display_width(choose_i)-1) * " "}|\033[0m')
		print(columns_lines()[0] * "-")
	choose_operate()


# 工作目录（可根据需要修改）
os.chdir(Path.cwd())
path_start = Path.cwd()
# 启动脚本
if __name__ == "__main__":
	libraries = [
		'os',
		'sys',
		'stat',
		'time',
		'shutil',
		'pathlib',
		'platform',
		'datetime',
		'subprocess',
		'unicodedata'
	]
	start_up = True
	for lib in libraries:
		if not importlib.util.find_spec(lib):
			print(f'Not installed:{lib}')
			start_up = False
	if start_up == True:
		user_your = DocumentShow()
		user_your.texts_os()
	else:
		print('缺少必要的库，请安装之后再使用该脚本!')



