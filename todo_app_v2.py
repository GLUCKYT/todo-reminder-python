"""
每日待办提醒小助手 - 便利贴风格版本
功能：今日任务清单、任务计时、完成总结、历史复盘
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime, timedelta
import sqlite3
import threading
import time
import os
import sys

if sys.platform == 'win32':
    from win10toast import ToastNotifier

# 数据库路径
DB_PATH = os.path.join(os.path.expanduser('~'), 'todo_reminder_v2.db')


class Database:
    """数据库操作类"""

    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 待办任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                task_date TEXT NOT NULL,
                estimated_duration INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                status INTEGER DEFAULT 0,
                repeat_type INTEGER DEFAULT 0,
                repeat_template_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                notified INTEGER DEFAULT 0
            )
        ''')

        # 检查并添加新字段（用于旧数据库升级）
        try:
            cursor.execute("SELECT repeat_type FROM todos LIMIT 1")
        except sqlite3.OperationalError:
            # 字段不存在，添加新字段
            cursor.execute("ALTER TABLE todos ADD COLUMN repeat_type INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE todos ADD COLUMN repeat_template_id INTEGER")

        # 重复任务模板表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS repeat_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                estimated_duration INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                repeat_type INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 任务执行记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                todo_id INTEGER,
                start_time DATETIME,
                end_time DATETIME,
                duration INTEGER DEFAULT 0,
                summary TEXT,
                FOREIGN KEY (todo_id) REFERENCES todos(id)
            )
        ''')

        # 任务完成历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS completed_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                task_date TEXT NOT NULL,
                completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_duration INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                summary TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def get_today_todos(self):
        """获取今天的待办任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT * FROM todos WHERE task_date = ? ORDER BY priority DESC, id', (today,))
        todos = cursor.fetchall()
        conn.close()
        return todos

    def add_todo(self, title, description='', task_date='', estimated_duration=0, priority=0, repeat_type=0):
        """添加待办任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 如果是重复任务，先创建模板
        template_id = None
        if repeat_type > 0:
            cursor.execute('''
                INSERT INTO repeat_templates (title, description, estimated_duration, priority, repeat_type)
                VALUES (?, ?, ?, ?, ?)
            ''', (title, description, estimated_duration, priority, repeat_type))
            template_id = cursor.lastrowid
            conn.commit()

        cursor.execute('''
            INSERT INTO todos (title, description, task_date, estimated_duration, priority, repeat_type, repeat_template_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, task_date, estimated_duration, priority, repeat_type, template_id))
        conn.commit()
        todo_id = cursor.lastrowid
        conn.close()
        return todo_id

    def update_todo(self, todo_id, title, description='', estimated_duration=0, priority=0, repeat_type=0):
        """更新待办任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 获取原任务信息
        cursor.execute('SELECT repeat_template_id FROM todos WHERE id=?', (todo_id,))
        result = cursor.fetchone()
        old_template_id = result[0] if result else None

        # 如果重复类型改变，需要更新或创建模板
        template_id = old_template_id
        if repeat_type > 0:
            if old_template_id:
                # 更新现有模板
                cursor.execute('''
                    UPDATE repeat_templates
                    SET title=?, description=?, estimated_duration=?, priority=?, repeat_type=?
                    WHERE id=?
                ''', (title, description, estimated_duration, priority, repeat_type, old_template_id))
            else:
                # 创建新模板
                cursor.execute('''
                    INSERT INTO repeat_templates (title, description, estimated_duration, priority, repeat_type)
                    VALUES (?, ?, ?, ?, ?)
                ''', (title, description, estimated_duration, priority, repeat_type))
                template_id = cursor.lastrowid
        elif old_template_id and repeat_type == 0:
            # 从重复任务改为一次性任务，删除模板
            cursor.execute('DELETE FROM repeat_templates WHERE id=?', (old_template_id,))
            template_id = None

        cursor.execute('''
            UPDATE todos
            SET title=?, description=?, estimated_duration=?, priority=?, repeat_type=?, repeat_template_id=?
            WHERE id=?
        ''', (title, description, estimated_duration, priority, repeat_type, template_id, todo_id))
        conn.commit()
        conn.close()

    def delete_todo(self, todo_id):
        """删除待办任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 获取任务的repeat_template_id
        cursor.execute('SELECT repeat_template_id FROM todos WHERE id=?', (todo_id,))
        result = cursor.fetchone()
        template_id = result[0] if result else None

        # 删除任务会话记录
        cursor.execute('DELETE FROM task_sessions WHERE todo_id=?', (todo_id,))
        # 删除任务
        cursor.execute('DELETE FROM todos WHERE id=?', (todo_id,))

        # 如果是重复任务,询问是否删除模板
        if template_id:
            # 检查是否还有其他关联的任务
            cursor.execute('SELECT COUNT(*) FROM todos WHERE repeat_template_id=?', (template_id,))
            other_tasks = cursor.fetchone()[0]

            # 如果没有其他任务使用这个模板,删除模板
            if other_tasks == 0:
                cursor.execute('DELETE FROM repeat_templates WHERE id=?', (template_id,))

        conn.commit()
        conn.close()

    def start_task_session(self, todo_id):
        """开始任务计时"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO task_sessions (todo_id, start_time)
            VALUES (?, ?)
        ''', (todo_id, start_time))
        conn.commit()
        session_id = cursor.lastrowid
        conn.close()
        return session_id

    def stop_task_session(self, session_id, summary=''):
        """停止任务计时"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 获取开始时间
        cursor.execute('SELECT todo_id, start_time FROM task_sessions WHERE id=?', (session_id,))
        result = cursor.fetchone()
        if result:
            todo_id, start_time_str = result
            start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
            end_time_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            duration = int((end_time_dt - start_time).total_seconds())

            cursor.execute('''
                UPDATE task_sessions
                SET end_time=?, duration=?, summary=?
                WHERE id=?
            ''', (end_time, duration, summary, session_id))

            # 更新任务状态
            cursor.execute('UPDATE todos SET status=1 WHERE id=?', (todo_id,))
            conn.commit()

        conn.close()

    def get_active_session(self, todo_id):
        """获取活动的计时会话"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, start_time FROM task_sessions
            WHERE todo_id=? AND end_time IS NULL
            ORDER BY start_time DESC LIMIT 1
        ''', (todo_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def get_task_total_duration(self, todo_id):
        """获取任务总时长"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(duration) FROM task_sessions WHERE todo_id=? AND duration IS NOT NULL', (todo_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] or 0 if result[0] else 0

    def complete_task(self, todo_id, summary=''):
        """完成任务并保存到历史"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 获取任务信息
        cursor.execute('SELECT * FROM todos WHERE id=?', (todo_id,))
        todo = cursor.fetchone()

        if todo:
            todo_id, title, description, task_date, estimated_duration, priority, status, created_at, notified = todo
            total_duration = self.get_task_total_duration(todo_id)
            completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 保存到完成历史
            cursor.execute('''
                INSERT INTO completed_tasks (title, description, task_date, completed_at, total_duration, priority, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (title, description, task_date, completed_at, total_duration, priority, summary))

            # 删除原任务和相关记录
            cursor.execute('DELETE FROM task_sessions WHERE todo_id=?', (todo_id,))
            cursor.execute('DELETE FROM todos WHERE id=?', (todo_id,))
            conn.commit()

        conn.close()

    def get_completed_tasks(self, days=30):
        """获取已完成任务历史"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT * FROM completed_tasks
            WHERE task_date >= ?
            ORDER BY completed_at DESC
        ''', (since_date,))
        tasks = cursor.fetchall()
        conn.close()
        return tasks

    def get_statistics(self, days=7):
        """获取统计数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 完成的任务数
        cursor.execute('SELECT COUNT(*) FROM completed_tasks WHERE task_date >= ?', (since_date,))
        total_completed = cursor.fetchone()[0]

        # 总工作时长
        cursor.execute('SELECT SUM(total_duration) FROM completed_tasks WHERE task_date >= ?', (since_date,))
        total_duration = cursor.fetchone()[0] or 0

        # 按优先级统计
        cursor.execute('''
            SELECT priority, COUNT(*), SUM(total_duration)
            FROM completed_tasks
            WHERE task_date >= ?
            GROUP BY priority
        ''', (since_date,))
        priority_stats = cursor.fetchall()

        # 每日完成统计
        cursor.execute('''
            SELECT task_date, COUNT(*), SUM(total_duration)
            FROM completed_tasks
            WHERE task_date >= ?
            GROUP BY task_date
            ORDER BY task_date DESC
        ''', (since_date,))
        daily_stats = cursor.fetchall()

        conn.close()

        return {
            'total_completed': total_completed,
            'total_duration': total_duration,
            'priority_stats': priority_stats,
            'daily_stats': daily_stats
        }

    def generate_repeat_tasks(self, target_date):
        """为指定日期生成重复任务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        target_dt = datetime.strptime(target_date, '%Y-%m-%d')
        weekday = target_dt.weekday()  # 0=周一, 6=周日

        # 检查是否为工作日 (周一到周五)
        is_weekday = weekday < 5

        # 获取所有重复任务模板
        cursor.execute('SELECT * FROM repeat_templates')
        templates = cursor.fetchall()

        for template in templates:
            template_id, title, description, estimated_duration, priority, repeat_type, created_at = template

            # 检查今天是否已有该模板的任务
            cursor.execute('''
                SELECT COUNT(*) FROM todos
                WHERE task_date=? AND repeat_template_id=?
            ''', (target_date, template_id))
            exists = cursor.fetchone()[0] > 0

            if exists:
                continue  # 已存在，跳过

            # 根据重复类型决定是否生成
            should_create = False
            if repeat_type == 1:  # 每日重复
                should_create = True
            elif repeat_type == 2:  # 工作日重复
                should_create = is_weekday

            if should_create:
                cursor.execute('''
                    INSERT INTO todos (title, description, task_date, estimated_duration, priority, repeat_type, repeat_template_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (title, description, target_date, estimated_duration, priority, repeat_type, template_id))

        conn.commit()
        conn.close()


class TaskTimer:
    """任务计时器"""

    def __init__(self, parent, todo_id, task_title, on_complete):
        self.parent = parent
        self.todo_id = todo_id
        self.task_title = task_title
        self.on_complete = on_complete
        self.start_time = None
        self.is_running = False
        self.is_paused = False
        self.paused_duration = 0
        self.session_id = None

    def start(self):
        """开始计时"""
        if not self.is_running:
            self.start_time = datetime.now()
            self.is_running = True
            self.is_paused = False
            self.paused_duration = 0
            self.session_id = self.parent.db.start_task_session(self.todo_id)
            return True
        return False

    def pause(self):
        """暂停计时"""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.pause_start = datetime.now()
            return True
        return False

    def resume(self):
        """恢复计时"""
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.paused_duration += (datetime.now() - self.pause_start).total_seconds()
            return True
        return False

    def stop(self, summary=''):
        """停止计时"""
        if self.is_running and self.session_id:
            self.parent.db.stop_task_session(self.session_id, summary)
            self.is_running = False
            return True
        return False

    def get_elapsed_time(self):
        """获取已用时间"""
        if self.is_running and not self.is_paused:
            elapsed = (datetime.now() - self.start_time).total_seconds() - self.paused_duration
            return int(elapsed)
        elif self.is_running and self.is_paused:
            elapsed = (self.pause_start - self.start_time).total_seconds() - self.paused_duration
            return int(elapsed)
        return 0


class TodoApp:
    """每日待办提醒小助手主界面"""

    def __init__(self, root):
        self.root = root
        self.root.title("📝 每日待办小助手")
        self.root.geometry("650x500")  # 增加宽度从520到600
        self.root.configure(bg='#F9F9F9')  # Win11浅色背景
        self.root.attributes('-topmost', True)

        # Win11风格圆角窗口（仅Windows）
        try:
            if sys.platform == 'win32':
                from ctypes import windll
                windll.user32.SetWindowPos(root.winfo_id(), -1, 0, 0, 0, 0, 0x0001 | 0x0002)
        except:
            pass

        # 初始化数据库
        self.db = Database(DB_PATH)

        # 初始化通知系统
        self.notifier = None
        if sys.platform == 'win32':
            try:
                self.notifier = ToastNotifier()
            except:
                print("警告：通知系统初始化失败")

        # 当前活动的计时器
        self.active_timer = None
        self.timer_update_job = None

        # 保存主窗口状态
        self.main_window_visible = True

        # 生成今日重复任务
        self.generate_today_repeat_tasks()

        # 创建界面
        self.create_widgets()

        # 加载今日任务
        self.load_today_todos()

    def create_widgets(self):
        """创建界面组件"""
        # 顶部标题栏 - Win11浅色风格
        header_frame = tk.Frame(self.root, bg='#FFFFFF', height=70)
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        header_frame.pack_propagate(False)

        title_label = tk.Label(header_frame, text="今日待办", font=('Segoe UI Variable', 18, 'bold'),
                               bg='#FFFFFF', fg='#000000')
        title_label.pack(side=tk.LEFT, pady=20, padx=25)

        # 日期显示
        today_date = datetime.now().strftime('%Y-%m-%d')
        weekday_dict = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
        weekday = weekday_dict[datetime.now().weekday()]
        date_text = f"{today_date} {weekday}"

        date_label = tk.Label(header_frame, text=date_text, font=('Segoe UI Variable', 11),
                              bg='#FFFFFF', fg='#888888')
        date_label.pack(side=tk.RIGHT, padx=25)

        # 计时器显示区域 - Win11浅色卡片
        self.timer_frame = tk.Frame(self.root, bg='#FFFFFF', height=100)
        self.timer_frame.pack(fill=tk.X, padx=15, pady=(15, 0))
        self.timer_frame.pack_propagate(False)

        self.timer_label = tk.Label(self.timer_frame, text="00:00:00", font=('Segoe UI', 36, 'bold'),
                                    bg='#FFFFFF', fg='#0078D4')
        self.timer_label.pack(expand=True)

        self.timer_task_label = tk.Label(self.timer_frame, text="选择任务开始计时", font=('Segoe UI Variable', 11),
                                         bg='#FFFFFF', fg='#888888')
        self.timer_task_label.pack(pady=(0, 5))

        # 计时器按钮 - Win11浅色风格
        timer_btn_frame = tk.Frame(self.root, bg='#F9F9F9')
        timer_btn_frame.pack(fill=tk.X, padx=15, pady=(12, 0))

        self.start_btn = tk.Button(timer_btn_frame, text="开始", font=('Segoe UI Variable', 11),
                                  bg='#0078D4', fg='white', relief=tk.FLAT, cursor='hand2',
                                  command=self.start_task, padx=20, pady=10, activebackground='#005A9E')
        self.start_btn.pack(side=tk.LEFT, padx=3)

        self.pause_btn = tk.Button(timer_btn_frame, text="暂停", font=('Segoe UI Variable', 11),
                                  bg='#0078D4', fg='white', relief=tk.FLAT, cursor='hand2',
                                  command=self.pause_task, padx=20, pady=10, state=tk.DISABLED, activebackground='#005A9E')
        self.pause_btn.pack(side=tk.LEFT, padx=3)

        self.complete_btn = tk.Button(timer_btn_frame, text="完成", font=('Segoe UI Variable', 11),
                                     bg='#0078D4', fg='white', relief=tk.FLAT, cursor='hand2',
                                     command=self.complete_task, padx=20, pady=10, state=tk.DISABLED, activebackground='#005A9E')
        self.complete_btn.pack(side=tk.LEFT, padx=3)

        tk.Button(timer_btn_frame, text="历史复盘", font=('Microsoft YaHei UI', 11),
                 bg='#E0E0E0', fg='#000000', relief=tk.FLAT, cursor='hand2',
                 command=self.show_history, padx=20, pady=10, activebackground='#D0D0D0').pack(side=tk.RIGHT, padx=3)

        tk.Button(timer_btn_frame, text="精简模式", font=('Microsoft YaHei UI', 11),
                 bg='#E0E0E0', fg='#000000', relief=tk.FLAT, cursor='hand2',
                 command=self.show_mini_window, padx=20, pady=10, activebackground='#D0D0D0').pack(side=tk.RIGHT, padx=3)

        tk.Button(timer_btn_frame, text="新建任务", font=('Microsoft YaHei UI', 11),
                 bg='#E0E0E0', fg='#000000', relief=tk.FLAT, cursor='hand2',
                 command=self.show_add_dialog, padx=20, pady=10, activebackground='#D0D0D0').pack(side=tk.RIGHT, padx=3)

        # 任务列表区域 - Win11浅色卡片风格
        list_frame = tk.Frame(self.root, bg='#F9F9F9')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(15, 10))

        # 创建滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 创建任务列表
        self.todo_listbox = tk.Listbox(list_frame, font=('Segoe UI Variable', 11),
                                       bg='#FFFFFF', fg='#000000', selectmode=tk.SINGLE,
                                       yscrollcommand=scrollbar.set, borderwidth=0,
                                       highlightthickness=0, selectbackground='#0078D4',
                                       selectforeground='#FFFFFF')
        self.todo_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.todo_listbox.yview)

        # 绑定选择事件
        self.todo_listbox.bind('<<ListboxSelect>>', self.on_select)

        # 底部按钮栏 - Win11浅色风格
        button_frame = tk.Frame(self.root, bg='#F9F9F9')
        button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))

        tk.Button(button_frame, text="编辑", font=('Segoe UI Variable', 10),
                 bg='#E0E0E0', fg='#000000', relief=tk.FLAT, cursor='hand2',
                 command=self.edit_selected, padx=20, pady=8, activebackground='#D0D0D0').pack(side=tk.LEFT, padx=3)

        tk.Button(button_frame, text="删除", font=('Segoe UI Variable', 10),
                 bg='#E0E0E0', fg='#000000', relief=tk.FLAT, cursor='hand2',
                 command=self.delete_selected, padx=20, pady=8, activebackground='#D0D0D0').pack(side=tk.LEFT, padx=3)

    def load_today_todos(self):
        """加载今日任务"""
        self.todos = self.db.get_today_todos()
        self.update_todo_list()

    def generate_today_repeat_tasks(self):
        """启动时生成今日重复任务"""
        today = datetime.now().strftime('%Y-%m-%d')
        self.db.generate_repeat_tasks(today)

    def update_todo_list(self):
        """更新任务列表显示"""
        self.todo_listbox.delete(0, tk.END)

        for todo in self.todos:
            todo_id, title, description, task_date, estimated_duration, priority, status, created_at, notified, repeat_type, repeat_template_id = todo[:11]

            # 获取已用时长
            total_duration = self.db.get_task_total_duration(todo_id)
            duration_text = self.format_duration(total_duration)

            # 优先级标识
            priority_icon = ['📌', '⭐', '🔥'][priority]

            # 状态标识
            if status == 1:
                status_icon = '✅'
            else:
                status_icon = '⬜'

            # 重复标识
            repeat_icon = ''
            if repeat_type == 1:
                repeat_icon = '🔄'
            elif repeat_type == 2:
                repeat_icon = '💼'

            # 显示文本
            display_text = f"{status_icon} {priority_icon} {title}"
            if repeat_icon:
                display_text += f" {repeat_icon}"
            if total_duration > 0:
                display_text += f" | ⏱️ {duration_text}"

            self.todo_listbox.insert(tk.END, display_text)

    def format_duration(self, seconds):
        """格式化时长显示"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}小时{minutes}分"
        elif minutes > 0:
            return f"{minutes}分钟"
        else:
            return f"{secs}秒"

    def format_timer(self, seconds):
        """格式化计时器显示"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def format_duration_simple(self, seconds):
        """简化格式化时长显示（用于任务列表）"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}h{minutes}m"
        elif minutes > 0:
            return f"{minutes}m{secs}s"
        else:
            return f"{secs}s"

    def on_select(self, event):
        """选择任务时的处理"""
        pass

    def get_selected_id(self):
        """获取选中的任务ID"""
        selection = self.todo_listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(self.todos):
            return None
        return self.todos[index][0]

    def start_task(self):
        """开始任务"""
        todo_id = self.get_selected_id()
        if not todo_id:
            messagebox.showinfo("提示", "请先选择一个任务")
            return

        # 如果有正在运行的任务，先停止
        if self.active_timer and self.active_timer.is_running:
            if not messagebox.askyesno("确认", "当前有任务正在进行，是否切换？"):
                return
            self.stop_timer_internal()

        # 获取任务标题
        todo = next((t for t in self.todos if t[0] == todo_id), None)
        if todo:
            task_title = todo[1]
            self.active_timer = TaskTimer(self, todo_id, task_title, None)
            self.active_timer.start()

            # 更新界面
            self.timer_task_label.config(text=f"正在进行: {task_title}")
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL, text="⏸️ 暂停")
            self.complete_btn.config(state=tk.NORMAL)

            # 开始更新计时器
            self.update_timer_display()

    def pause_task(self):
        """暂停/恢复任务"""
        if not self.active_timer:
            return

        if self.active_timer.is_paused:
            # 恢复
            self.active_timer.resume()
            self.pause_btn.config(text="⏸️ 暂停")
            self.update_timer_display()
        else:
            # 暂停
            self.active_timer.pause()
            self.pause_btn.config(text="▶️ 继续")
            if self.timer_update_job:
                self.root.after_cancel(self.timer_update_job)
                self.timer_update_job = None

    def complete_task(self):
        """完成任务"""
        if not self.active_timer:
            messagebox.showinfo("提示", "没有正在进行的任务")
            return

        # 停止计时器
        self.stop_timer_internal()

        # 弹出总结对话框
        self.show_summary_dialog()

    def stop_timer_internal(self):
        """内部停止计时器"""
        if self.active_timer and self.active_timer.is_running:
            if self.timer_update_job:
                self.root.after_cancel(self.timer_update_job)
                self.timer_update_job = None

            self.active_timer.stop()
            self.active_timer = None

            # 重置界面
            self.timer_label.config(text="⏱️ 00:00:00")
            self.timer_task_label.config(text="暂无任务")
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.DISABLED, text="⏸️ 暂停")
            self.complete_btn.config(state=tk.DISABLED)

    def update_timer_display(self):
        """更新计时器显示"""
        if self.active_timer and self.active_timer.is_running and not self.active_timer.is_paused:
            elapsed = self.active_timer.get_elapsed_time()
            self.timer_label.config(text=f"⏱️ {self.format_timer(elapsed)}")
            self.timer_update_job = self.root.after(1000, self.update_timer_display)

    def show_summary_dialog(self):
        """显示任务总结对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("任务总结")
        dialog.geometry("520x450")
        dialog.configure(bg='#F3F3F3')
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 260
        y = (dialog.winfo_screenheight() // 2) - 225
        dialog.geometry(f'520x450+{x}+{y}')

        # 创建内容容器
        content_frame = tk.Frame(dialog, bg='white')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(content_frame, text="✨ 任务完成！记录一下收获吧", font=('Microsoft YaHei UI', 14, 'bold'),
                bg='white', fg='#0078D4').pack(pady=(0, 15))

        tk.Label(content_frame, text="本次任务总结：", font=('Microsoft YaHei UI', 11, 'bold'),
                bg='white', fg='#333333').pack(anchor=tk.W)

        summary_text = tk.Text(content_frame, font=('Microsoft YaHei UI', 10), bg='#F5F5F5',
                              height=10, relief=tk.FLAT, highlightthickness=1, highlightbackground='#E0E0E0')
        summary_text.pack(fill=tk.BOTH, expand=True, pady=(10, 10))

        # 添加提示
        tips = "💡 提示：可以记录遇到的问题、解决方案、收获心得等"
        tk.Label(content_frame, text=tips, font=('Microsoft YaHei UI', 9),
                bg='white', fg='#999999').pack(anchor=tk.W)

        button_frame = tk.Frame(content_frame, bg='white')
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))

        def save_summary():
            summary = summary_text.get("1.0", tk.END).strip()
            todo_id = self.get_selected_id()

            if todo_id:
                self.db.complete_task(todo_id, summary)
                self.load_today_todos()

                # 发送完成通知
                if self.notifier:
                    try:
                        self.notifier.show_toast(
                            title="🎉 任务完成",
                            msg="太棒了！又完成了一项任务",
                            duration=5
                        )
                    except:
                        pass

            dialog.destroy()

        tk.Button(button_frame, text="跳过", font=('Microsoft YaHei UI', 10),
                 bg='#E0E0E0', fg='#333333', relief=tk.FLAT, cursor='hand2',
                 command=lambda: [save_summary(), dialog.destroy()], padx=25, pady=10,
                 activebackground='#D0D0D0').pack(side=tk.RIGHT, padx=5)

        tk.Button(button_frame, text="保存总结", font=('Microsoft YaHei UI', 10, 'bold'),
                 bg='#0078D4', fg='white', relief=tk.FLAT, cursor='hand2',
                 command=save_summary, padx=30, pady=10, activebackground='#005A9E').pack(side=tk.RIGHT)

    def show_add_dialog(self, todo_id=None):
        """显示添加/编辑对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑任务" if todo_id else "新建任务")
        dialog.geometry("480x600")
        dialog.configure(bg='#F3F3F3')
        dialog.transient(self.root)
        dialog.grab_set()

        # 居中显示
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'480x600+{x}+{y}')

        # 创建内容容器
        content_frame = tk.Frame(dialog, bg='white')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 标题
        tk.Label(content_frame, text="任务标题 *", font=('Microsoft YaHei UI', 10, 'bold'),
                bg='white', fg='#333333').pack(anchor=tk.W, pady=(0, 5))

        title_entry = tk.Entry(content_frame, font=('Microsoft YaHei UI', 11), bg='#F5F5F5',
                               relief=tk.FLAT, highlightthickness=1, highlightbackground='#E0E0E0')
        title_entry.pack(fill=tk.X, pady=(0, 15))

        # 描述
        tk.Label(content_frame, text="任务描述", font=('Microsoft YaHei UI', 10, 'bold'),
                bg='white', fg='#333333').pack(anchor=tk.W)

        desc_text = tk.Text(content_frame, font=('Microsoft YaHei UI', 10), bg='#F5F5F5',
                           height=3, relief=tk.FLAT, highlightthickness=1, highlightbackground='#E0E0E0')
        desc_text.pack(fill=tk.X, pady=(5, 15))

        # 日期和预估时长
        info_frame = tk.Frame(content_frame, bg='white')
        info_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(info_frame, text="日期", font=('Microsoft YaHei UI', 10, 'bold'),
                bg='white', fg='#333333').pack(side=tk.LEFT)
        date_entry = tk.Entry(info_frame, font=('Microsoft YaHei UI', 10), bg='#F5F5F5',
                              relief=tk.FLAT, highlightthickness=1, highlightbackground='#E0E0E0', width=15)
        date_entry.pack(side=tk.LEFT, padx=(5, 20))
        date_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))

        tk.Label(info_frame, text="预估时长(分钟)", font=('Microsoft YaHei UI', 10, 'bold'),
                bg='white', fg='#333333').pack(side=tk.LEFT)
        duration_entry = tk.Entry(info_frame, font=('Microsoft YaHei UI', 10), bg='#F5F5F5',
                                 relief=tk.FLAT, highlightthickness=1, highlightbackground='#E0E0E0', width=10)
        duration_entry.pack(side=tk.LEFT, padx=5)

        # 优先级
        tk.Label(content_frame, text="优先级", font=('Microsoft YaHei UI', 10, 'bold'),
                bg='white', fg='#333333').pack(anchor=tk.W, pady=(10, 5))

        priority_var = tk.IntVar(value=0)
        priority_frame = tk.Frame(content_frame, bg='white')
        priority_frame.pack(anchor=tk.W)

        for i, text in enumerate(['📌 普通', '⭐ 重要', '🔥 紧急']):
            tk.Radiobutton(priority_frame, text=text, variable=priority_var, value=i,
                          font=('Microsoft YaHei UI', 10), bg='white', cursor='hand2',
                          activebackground='#F5F5F5').pack(side=tk.LEFT, padx=10)

        # 重复类型
        tk.Label(content_frame, text="重复设置（像闹钟一样自动创建）", font=('Microsoft YaHei UI', 10, 'bold'),
                bg='white', fg='#333333').pack(anchor=tk.W, pady=(15, 5))

        repeat_var = tk.IntVar(value=0)
        repeat_frame = tk.Frame(content_frame, bg='white')
        repeat_frame.pack(anchor=tk.W)

        repeat_options = [
            (0, '📅 一次性（仅当天）'),
            (1, '🔄 每日重复（每天自动创建）'),
            (2, '💼 工作日重复（周一到周五）')
        ]

        for i, (value, text) in enumerate(repeat_options):
            tk.Radiobutton(repeat_frame, text=text, variable=repeat_var, value=value,
                          font=('Microsoft YaHei UI', 10), bg='white', cursor='hand2',
                          activebackground='#F5F5F5').pack(anchor=tk.W, pady=3)

        # 如果是编辑，填充数据
        if todo_id:
            for todo in self.todos:
                if todo[0] == todo_id:
                    title_entry.insert(0, todo[1])
                    desc_text.insert(tk.END, todo[2] or '')
                    date_entry.delete(0, tk.END)
                    date_entry.insert(0, todo[3] or '')
                    duration_entry.delete(0, tk.END)
                    # 将秒转换为分钟显示
                    duration_minutes = (todo[4] or 0) // 60
                    duration_entry.insert(0, str(duration_minutes))
                    priority_var.set(todo[5])
                    # 读取重复类型 (新增字段在第9位)
                    if len(todo) > 9:
                        repeat_var.set(todo[9] or 0)
                    break

        # 按钮 - Win11风格
        button_frame = tk.Frame(dialog, bg='white')
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 20))

        def save():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("警告", "请输入标题！")
                return

            description = desc_text.get("1.0", tk.END).strip()
            task_date = date_entry.get().strip()
            try:
                estimated_duration = int(duration_entry.get().strip() or 0) * 60  # 转换为秒
            except:
                estimated_duration = 0
            priority = priority_var.get()
            repeat_type = repeat_var.get()

            if todo_id:
                # 更新
                self.db.update_todo(todo_id, title, description, estimated_duration, priority, repeat_type)
            else:
                # 新增
                self.db.add_todo(title, description, task_date, estimated_duration, priority, repeat_type)

            self.load_today_todos()
            dialog.destroy()

        tk.Button(button_frame, text="取消", font=('Microsoft YaHei UI', 10),
                 bg='#E0E0E0', fg='#333333', relief=tk.FLAT, cursor='hand2',
                 command=dialog.destroy, padx=25, pady=10, activebackground='#D0D0D0').pack(side=tk.RIGHT, padx=5)

        tk.Button(button_frame, text="保存", font=('Microsoft YaHei UI', 10, 'bold'),
                 bg='#0078D4', fg='white', relief=tk.FLAT, cursor='hand2',
                 command=save, padx=30, pady=10, activebackground='#005A9E').pack(side=tk.RIGHT)

    def edit_selected(self):
        """编辑选中的任务"""
        todo_id = self.get_selected_id()
        if todo_id:
            # 检查是否有活动的计时器
            if self.active_timer and self.active_timer.todo_id == todo_id:
                messagebox.showwarning("警告", "任务正在进行中，无法编辑")
                return
            self.show_add_dialog(todo_id)
        else:
            messagebox.showinfo("提示", "请先选择一个任务")

    def delete_selected(self):
        """删除选中的任务"""
        todo_id = self.get_selected_id()
        if todo_id:
            # 检查是否有活动的计时器
            if self.active_timer and self.active_timer.todo_id == todo_id:
                messagebox.showwarning("警告", "任务正在进行中，无法删除")
                return

            if messagebox.askyesno("确认", "确定要删除这个任务吗？"):
                self.db.delete_todo(todo_id)
                self.load_today_todos()
        else:
            messagebox.showinfo("提示", "请先选择一个任务")

    def show_history(self):
        """显示历史记录和复盘界面"""
        history_window = tk.Toplevel(self.root)
        history_window.title("📊 历史复盘")
        history_window.geometry("800x600")
        history_window.configure(bg='#f5f5f5')
        history_window.transient(self.root)

        # 顶部统计卡片
        stats_frame = tk.Frame(history_window, bg='#f5f5f5')
        stats_frame.pack(fill=tk.X, padx=20, pady=20)

        # 获取统计数据
        stats = self.db.get_statistics(days=7)

        # 统计卡片
        cards = [
            ("近7天完成", f"{stats['total_completed']} 个", "#4CAF50"),
            ("总工作时长", self.format_duration(stats['total_duration']), "#2196F3"),
            ("平均每天", f"{stats['total_completed'] // 7 if stats['total_completed'] > 0 else 0} 个", "#FF9800")
        ]

        for i, (title, value, color) in enumerate(cards):
            card = tk.Frame(stats_frame, bg='white', highlightbackground=color, highlightthickness=2)
            card.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)

            tk.Label(card, text=title, font=('Microsoft YaHei UI', 10), bg='white', fg='#666').pack(pady=(15, 5))
            tk.Label(card, text=value, font=('Microsoft YaHei UI', 24, 'bold'), bg='white', fg=color).pack(pady=(0, 15))

        # Tab控件
        notebook = ttk.Notebook(history_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        # 已完成任务Tab
        completed_frame = tk.Frame(notebook, bg='white')
        notebook.add(completed_frame, text="✅ 已完成任务")

        # 创建任务列表
        scrollbar1 = ttk.Scrollbar(completed_frame)
        scrollbar1.pack(side=tk.RIGHT, fill=tk.Y)

        completed_listbox = tk.Listbox(completed_frame, font=('Microsoft YaHei UI', 11),
                                       bg='white', fg='#333', selectmode=tk.SINGLE,
                                       yscrollcommand=scrollbar1.set, borderwidth=0)
        completed_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar1.config(command=completed_listbox.yview)

        # 加载已完成任务
        completed_tasks = self.db.get_completed_tasks(days=30)
        for task in completed_tasks:
            task_id, title, description, task_date, completed_at, total_duration, priority, summary = task
            priority_icon = ['📌', '⭐', '🔥'][priority]
            display_text = f"{priority_icon} {title} | ⏱️ {self.format_duration(total_duration)} | 📅 {task_date}"
            completed_listbox.insert(tk.END, display_text)

        # 双击查看详情
        def show_task_detail(event):
            selection = completed_listbox.curselection()
            if selection:
                index = selection[0]
                if index < len(completed_tasks):
                    task = completed_tasks[index]
                    self.show_task_detail_dialog(task)

        completed_listbox.bind('<Double-Button-1>', show_task_detail)

        # 每日统计Tab
        daily_frame = tk.Frame(notebook, bg='white')
        notebook.add(daily_frame, text="📈 每日统计")

        scrollbar2 = ttk.Scrollbar(daily_frame)
        scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)

        daily_listbox = tk.Listbox(daily_frame, font=('Microsoft YaHei UI', 11),
                                   bg='white', fg='#333', selectmode=tk.SINGLE,
                                   yscrollcommand=scrollbar2.set, borderwidth=0)
        daily_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar2.config(command=daily_listbox.yview)

        # 加载每日统计
        for date, count, duration in stats['daily_stats']:
            display_text = f"📅 {date} | ✅ 完成 {count} 个任务 | ⏱️ 用时 {self.format_duration(duration)}"
            daily_listbox.insert(tk.END, display_text)

    def show_task_detail_dialog(self, task):
        """显示任务详情对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📝 任务详情")
        dialog.geometry("500x400")
        dialog.configure(bg='white')
        dialog.transient(self.root)
        dialog.grab_set()

        task_id, title, description, task_date, completed_at, total_duration, priority, summary = task

        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 250
        y = (dialog.winfo_screenheight() // 2) - 200
        dialog.geometry(f'500x400+{x}+{y}')

        # 内容
        content_frame = tk.Frame(dialog, bg='white')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(content_frame, text=title, font=('Microsoft YaHei UI', 16, 'bold'),
                bg='white', fg='#333').pack(anchor=tk.W, pady=(0, 10))

        info_text = f"📅 完成日期: {task_date}\n⏱️ 用时: {self.format_duration(total_duration)}"
        tk.Label(content_frame, text=info_text, font=('Microsoft YaHei UI', 10),
                bg='white', fg='#666').pack(anchor=tk.W, pady=(0, 15))

        if description:
            tk.Label(content_frame, text="📄 任务描述", font=('Microsoft YaHei UI', 11, 'bold'),
                    bg='white').pack(anchor=tk.W, pady=(5, 5))
            tk.Label(content_frame, text=description, font=('Microsoft YaHei UI', 10),
                    bg='white', fg='#333', wraplength=450, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 10))

        if summary:
            tk.Label(content_frame, text="💡 任务总结", font=('Microsoft YaHei UI', 11, 'bold'),
                    bg='white').pack(anchor=tk.W, pady=(5, 5))
            summary_text_widget = tk.Text(content_frame, font=('Microsoft YaHei UI', 10),
                                         bg='#f8f9fa', height=8, wrap=tk.WORD)
            summary_text_widget.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            summary_text_widget.insert(tk.END, summary)
            summary_text_widget.config(state=tk.DISABLED)

        tk.Button(content_frame, text="关闭", font=('Microsoft YaHei UI', 10),
                 bg='#9E9E9E', fg='white', relief=tk.FLAT, cursor='hand2',
                 command=dialog.destroy, padx=20, pady=8).pack(side=tk.RIGHT)

    def show_mini_window(self):
        """显示精简模式迷你窗口"""
        # 隐藏主窗口
        self.root.withdraw()
        self.main_window_visible = False

        # 根据任务数量计算窗口高度
        task_count = len(self.todos)
        # 每个任务约40像素高，基础高度350（头部+计时器+按钮）
        min_height = 280
        task_height = task_count * 40
        window_height = min_height + task_height
        # 限制最大高度为屏幕高度的80%
        max_height = int(self.root.winfo_screenheight() * 0.8)
        window_height = min(window_height, max_height)

        mini_window = tk.Toplevel(self.root)
        mini_window.title("今日任务")
        mini_window.geometry(f"450x{window_height}")
        mini_window.configure(bg='#F9F9F9')
        mini_window.attributes('-topmost', True)

        # 保存置顶状态
        mini_window.is_topmost = True

        # 当窗口关闭时恢复主窗口
        def on_mini_window_close():
            self.root.deiconify()  # 显示主窗口
            self.main_window_visible = True
            mini_window.destroy()

        mini_window.protocol("WM_DELETE_WINDOW", on_mini_window_close)

        # 创建精简界面
        # 去掉头部空白区域

        # 计时器显示（直接作为顶部）
        timer_frame = tk.Frame(mini_window, bg='#FFFFFF', height=90)
        timer_frame.pack(fill=tk.X, padx=0, pady=(0, 0))
        timer_frame.pack_propagate(False)

        mini_timer_label = tk.Label(timer_frame, text="00:00:00", font=('Microsoft YaHei UI', 36, 'bold'),
                                   bg='#FFFFFF', fg='#000000')
        mini_timer_label.pack(expand=True)

        # 控制按钮（居中显示）
        control_frame = tk.Frame(mini_window, bg='#F9F9F9')
        control_frame.pack(fill=tk.X, padx=15, pady=10)

        # 创建按钮容器实现居中
        button_container = tk.Frame(control_frame, bg='#F9F9F9')
        button_container.pack(expand=True)

        # 创建圆角按钮辅助函数
        def create_rounded_rectangle(canvas, x1, y1, x2, y2, r=8, **kwargs):
            """绘制圆角矩形（兼容所有Python版本）"""
            points = [x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y1+r, x2, y2-r,
                     x2, y2-r, x2, y2, x2-r, y2, x2-r, y2, x1+r, y2, x1+r, y2, x1, y2, x1, y2-r,
                     x1, y2-r, x1, y1+r, x1, y1+r, x1, y1]
            return canvas.create_polygon(points, **kwargs, smooth=True)

        def create_rounded_button(parent, text, command, bg_color='#0078D4', hover_color='#005A9E'):
            """创建圆角按钮"""
            button_frame = tk.Frame(parent, bg='#F9F9F9')
            button_frame.pack(side=tk.LEFT, padx=5)

            # 使用Canvas绘制圆角矩形
            canvas = tk.Canvas(button_frame, width=100, height=40, bg='#F9F9F9',
                             highlightthickness=0, bd=0)
            canvas.pack()

            # 绘制圆角矩形
            r = 8  # 圆角半径
            create_rounded_rectangle(canvas, 2, 2, 98, 38, r=r, fill=bg_color, outline=bg_color)

            # 添加文字
            text_id = canvas.create_text(50, 20, text=text, fill='white',
                                        font=('Microsoft YaHei UI', 11, 'bold'))

            # 鼠标悬停效果
            def on_enter(event):
                canvas.delete("all")
                create_rounded_rectangle(canvas, 2, 2, 98, 38, r=r, fill=hover_color, outline=hover_color)
                canvas.create_text(50, 20, text=text, fill='white',
                                  font=('Microsoft YaHei UI', 11, 'bold'))

            def on_leave(event):
                canvas.delete("all")
                create_rounded_rectangle(canvas, 2, 2, 98, 38, r=r, fill=bg_color, outline=bg_color)
                canvas.create_text(50, 20, text=text, fill='white',
                                  font=('Microsoft YaHei UI', 11, 'bold'))

            def on_click(event):
                command()

            canvas.bind('<Enter>', on_enter)
            canvas.bind('<Leave>', on_leave)
            canvas.bind('<Button-1>', on_click)

            return button_frame

        # 创建三个圆角按钮
        create_rounded_button(button_container, "开始",
                            lambda: self.start_task_from_mini(mini_window),
                            '#0078D4', '#005A9E')
        create_rounded_button(button_container, "暂停",
                            lambda: self.pause_task_from_mini(mini_window),
                            '#0078D4', '#005A9E')
        create_rounded_button(button_container, "完成",
                            lambda: self.complete_task_from_mini(mini_window),
                            '#0078D4', '#005A9E')

        # 任务列表（无滚动条）
        list_frame = tk.Frame(mini_window, bg='#F9F9F9')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(10, 5))

        # 任务列表（无滚动条，Win11圆角风格，字体增大到14号）
        mini_listbox = tk.Listbox(list_frame, font=('Microsoft YaHei UI', 14),
                                 bg='#FFFFFF', fg='#000000', selectmode=tk.SINGLE,
                                 borderwidth=0, highlightthickness=0,
                                 selectbackground='#0078D4', selectforeground='#FFFFFF',
                                 relief=tk.FLAT)
        mini_listbox.pack(fill=tk.BOTH, expand=True)

        # 填充任务
        for todo in self.todos:
            todo_id, title, description, task_date, estimated_duration, priority, status, created_at, notified, repeat_type, repeat_template_id = todo[:11]
            # 获取实际已用时长
            total_duration = self.db.get_task_total_duration(todo_id)

            priority_icon = ['📌', '⭐', '🔥'][priority]
            status_icon = '✅' if status == 1 else '⬜'

            # 显示时长：已进行时长/总时长
            elapsed_text = self.format_duration_simple(total_duration)

            if estimated_duration > 0:
                total_text = self.format_duration_simple(estimated_duration)
                display_text = f"{status_icon} {priority_icon} {title} | ⏱️ {elapsed_text}/{total_text}"
            else:
                display_text = f"{status_icon} {priority_icon} {title} | ⏱️ {elapsed_text}"

            mini_listbox.insert(tk.END, display_text)

        # 保存引用
        mini_window.mini_listbox = mini_listbox
        mini_window.mini_timer_label = mini_timer_label

        # 右下角小按钮区域
        bottom_right_frame = tk.Frame(mini_window, bg='#F9F9F9')
        bottom_right_frame.pack(side=tk.RIGHT, padx=15, pady=10)

        # 置顶切换按钮（小尺寸，Win11圆角风格）
        def toggle_topmost():
            if mini_window.is_topmost:
                mini_window.attributes('-topmost', False)
                mini_window.is_topmost = False
                topmost_btn.config(text="置顶", bg='#F3F3F3', fg='#666666')
            else:
                mini_window.attributes('-topmost', True)
                mini_window.is_topmost = True
                topmost_btn.config(text="已置顶", bg='#E8F3FD', fg='#0078D4')

        topmost_btn = tk.Button(bottom_right_frame, text="已置顶",
                               font=('Segoe UI Variable', 9),
                               bg='#E8F3FD', fg='#0078D4',
                               relief=tk.FLAT, cursor='hand2', borderwidth=0,
                               command=toggle_topmost, padx=8, pady=4,
                               activebackground='#D0E7FF')
        topmost_btn.pack(side=tk.LEFT, padx=3)

        # 返回主界面按钮（小尺寸，Win11圆角风格）
        back_btn = tk.Button(bottom_right_frame, text="返回",
                            font=('Segoe UI Variable', 9),
                            bg='#F3F3F3', fg='#666666',
                            relief=tk.FLAT, cursor='hand2', borderwidth=0,
                            command=on_mini_window_close, padx=8, pady=4,
                            activebackground='#E0E0E0')
        back_btn.pack(side=tk.LEFT, padx=3)

        # 定时更新计时器和任务列表
        def update_mini_timer():
            if hasattr(self, 'active_timer') and self.active_timer and self.active_timer.is_running:
                # 更新计时器显示
                elapsed = self.active_timer.get_elapsed_time()
                mini_timer_label.config(text=self.format_timer(elapsed))

                # 更新任务列表中正在进行的任务的时间显示
                if hasattr(mini_window, 'mini_listbox'):
                    try:
                        # 找到当前正在进行的任务在列表中的位置
                        current_todo_id = self.active_timer.todo_id
                        for idx, todo in enumerate(self.todos):
                            if todo[0] == current_todo_id:
                                # 获取该任务的总时长（之前已用时长 + 当前会话时长）
                                todo_id, title, description, task_date, estimated_duration, priority, status, created_at, notified, repeat_type, repeat_template_id = todo[:11]
                                # 获取之前记录的已用时长
                                previous_duration = self.db.get_task_total_duration(todo_id)
                                # 加上当前会话的时长（注意：get_task_total_duration不包括当前未保存的会话）
                                total_elapsed = previous_duration + elapsed

                                priority_icon = ['📌', '⭐', '🔥'][priority]
                                status_icon = '✅' if status == 1 else '⬜'

                                # 更新显示文本
                                elapsed_text = self.format_duration_simple(total_elapsed)
                                if estimated_duration > 0:
                                    total_text = self.format_duration_simple(estimated_duration)
                                    display_text = f"{status_icon} {priority_icon} {title} | ⏱️ {elapsed_text}/{total_text}"
                                else:
                                    display_text = f"{status_icon} {priority_icon} {title} | ⏱️ {elapsed_text}"

                                # 更新列表中的这一项
                                mini_window.mini_listbox.delete(idx)
                                mini_window.mini_listbox.insert(idx, display_text)
                                break
                    except:
                        pass

            try:
                if mini_window.winfo_exists():
                    mini_window.after(1000, update_mini_timer)
            except:
                pass

        update_mini_timer()

    def start_task_from_mini(self, mini_window):
        """从迷你窗口开始任务"""
        # 从迷你窗口获取选中的任务ID
        selection = mini_window.mini_listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个任务")
            return

        index = selection[0]
        if index >= len(self.todos):
            return

        todo_id = self.todos[index][0]

        # 如果有正在运行的任务，先停止
        if self.active_timer and self.active_timer.is_running:
            if not messagebox.askyesno("确认", "当前有任务正在进行，是否切换？"):
                return
            self.stop_timer_internal()

        # 获取任务标题
        todo = next((t for t in self.todos if t[0] == todo_id), None)
        if todo:
            task_title = todo[1]
            self.active_timer = TaskTimer(self, todo_id, task_title, None)
            self.active_timer.start()

            # 更新迷你窗口界面
            mini_window.mini_timer_label.config(text=f"⏱️ 00:00:00")

    def pause_task_from_mini(self, mini_window):
        """从迷你窗口暂停任务"""
        self.pause_task()

    def complete_task_from_mini(self, mini_window):
        """从迷你窗口完成任务"""
        if not self.active_timer:
            messagebox.showinfo("提示", "没有正在进行的任务")
            return

        # 停止计时器
        if self.timer_update_job:
            self.root.after_cancel(self.timer_update_job)
            self.timer_update_job = None

        self.active_timer.stop()
        todo_id = self.active_timer.todo_id  # 保存todo_id,因为后面会清空
        self.active_timer = None

        # 重置迷你窗口界面
        mini_window.mini_timer_label.config(text="⏱️ 00:00:00")

        # 弹出总结对话框（依附于迷你窗口而不是主窗口）
        self.show_summary_dialog_for_mini(mini_window, todo_id)

    def show_summary_dialog_for_mini(self, parent_window, todo_id):
        """显示任务总结对话框（精简模式专用）"""
        dialog = tk.Toplevel(parent_window)
        dialog.title("任务总结")
        dialog.geometry("520x450")
        dialog.configure(bg='#F3F3F3')
        dialog.transient(parent_window)  # 依附于迷你窗口而不是主窗口
        dialog.grab_set()  # 模态对话框

        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 260
        y = (dialog.winfo_screenheight() // 2) - 225
        dialog.geometry(f'520x450+{x}+{y}')

        # 创建内容容器
        content_frame = tk.Frame(dialog, bg='white')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(content_frame, text="✨ 任务完成！记录一下收获吧", font=('Microsoft YaHei UI', 14, 'bold'),
                bg='white', fg='#0078D4').pack(pady=(0, 15))

        tk.Label(content_frame, text="本次任务总结：", font=('Microsoft YaHei UI', 11, 'bold'),
                bg='white', fg='#333333').pack(anchor=tk.W)

        summary_text = tk.Text(content_frame, font=('Microsoft YaHei UI', 10), bg='#F5F5F5',
                              height=10, relief=tk.FLAT, highlightthickness=1, highlightbackground='#E0E0E0')
        summary_text.pack(fill=tk.BOTH, expand=True, pady=(10, 10))

        # 添加提示
        tips = "💡 提示：可以记录遇到的问题、解决方案、收获心得等"
        tk.Label(content_frame, text=tips, font=('Microsoft YaHei UI', 9),
                bg='white', fg='#999999').pack(anchor=tk.W)

        button_frame = tk.Frame(content_frame, bg='white')
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))

        def save_summary():
            summary = summary_text.get("1.0", tk.END).strip()

            if todo_id:
                self.db.complete_task(todo_id, summary)
                self.load_today_todos()

                # 刷新迷你窗口的任务列表
                if hasattr(parent_window, 'mini_listbox'):
                    parent_window.mini_listbox.delete(0, tk.END)
                    for todo in self.todos:
                        t_id, title, description, task_date, estimated_duration, priority, status, created_at, notified, repeat_type, repeat_template_id = todo[:11]
                        total_duration = self.db.get_task_total_duration(t_id)

                        priority_icon = ['📌', '⭐', '🔥'][priority]
                        status_icon = '✅' if status == 1 else '⬜'

                        # 显示时长：已进行时长/总时长
                        elapsed_text = self.format_duration_simple(total_duration)

                        if estimated_duration > 0:
                            total_text = self.format_duration_simple(estimated_duration)
                            display_text = f"{status_icon} {priority_icon} {title} | ⏱️ {elapsed_text}/{total_text}"
                        else:
                            display_text = f"{status_icon} {priority_icon} {title} | ⏱️ {elapsed_text}"

                        parent_window.mini_listbox.insert(tk.END, display_text)

                # 发送完成通知
                if self.notifier:
                    try:
                        self.notifier.show_toast(
                            title="🎉 任务完成",
                            msg="太棒了！又完成了一项任务",
                            duration=5
                        )
                    except:
                        pass

            dialog.destroy()

        tk.Button(button_frame, text="跳过", font=('Microsoft YaHei UI', 10),
                 bg='#E0E0E0', fg='#333333', relief=tk.FLAT, cursor='hand2',
                 command=lambda: [save_summary(), dialog.destroy()], padx=25, pady=10,
                 activebackground='#D0D0D0').pack(side=tk.RIGHT, padx=5)

        tk.Button(button_frame, text="保存总结", font=('Microsoft YaHei UI', 10, 'bold'),
                 bg='#0078D4', fg='white', relief=tk.FLAT, cursor='hand2',
                 command=save_summary, padx=30, pady=10, activebackground='#005A9E').pack(side=tk.RIGHT)


def main():
    """主函数"""
    root = tk.Tk()
    app = TodoApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
