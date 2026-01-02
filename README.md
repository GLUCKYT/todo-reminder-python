# 待办提醒 (Todo Reminder)

<div align="center">

**一款简洁优雅的待办事项提醒应用**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/yourusername/todo-reminder-python/releases)
[![Python](https://img.shields.io/badge/python-3.7+-green.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

</div>

## ✨ 特性

- 📋 **任务管理** - 轻松创建、编辑、删除待办任务
- ⏱️ **计时功能** - 实时计时任务耗时，提高时间管理效率
- 🔔 **系统通知** - Windows 10/11 原生 Toast 通知提醒
- 📊 **历史复盘** - 查看任务历史记录和耗时统计
- 🔄 **重复任务** - 支持每日/工作日自动重复创建任务
- 🎯 **精简模式** - 专注当前任务的小窗口，减少干扰
- 🎨 **Win11 风格** - 采用 Windows 11 设计语言，圆润优雅
- 📈 **优先级管理** - 高/中/低优先级标识
- 💾 **数据持久化** - SQLite 数据库本地存储

## 📸 界面预览

### 主界面
- 完整的任务管理功能
- 实时计时器显示
- 历史复盘和精简模式入口
- 新建任务快捷按钮

### 精简模式
- 专注当前任务的小窗口
- 自适应窗口高度
- 可选置顶显示
- 圆润的 Win11 风格按钮

## 🚀 快速开始

### 方式一：使用可执行文件（推荐）

1. 下载最新版本的 `待办提醒.exe`
2. 双击运行即可使用
3. 无需安装 Python 环境

### 方式二：从源码运行

1. **克隆仓库**
   ```bash
   git clone https://github.com/yourusername/todo-reminder-python.git
   cd todo-reminder-python
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **运行应用**
   ```bash
   python todo_app_v2.py
   ```

## 📖 使用说明

### 主界面功能

1. **新建任务**
   - 点击"新建任务"按钮
   - 填写任务标题、预计时长、优先级
   - 可选择重复类型（一次性/每日/工作日）

2. **开始任务**
   - 在任务列表中选择任务
   - 点击"开始"按钮启动计时
   - 实时显示已进行时长

3. **完成任务**
   - 点击"完成"按钮结束计时
   - 填写任务总结（可选）
   - 查看本次任务耗时统计

4. **历史复盘**
   - 点击"历史复盘"按钮
   - 查看所有已完成任务
   - 按日期分组显示

5. **精简模式**
   - 点击"精简模式"按钮
   - 主界面隐藏，显示小窗口
   - 专注于当前任务

### 精简模式功能

- **开始/完成任务** - 直接在精简窗口操作
- **置顶切换** - 点击右下角按钮控制窗口置顶
- **返回主界面** - 点击"返回"按钮恢复主窗口
- **自适应高度** - 根据任务数量自动调整窗口大小

### 优先级设置

- 🔴 **高优先级** - 紧急重要任务
- 🟡 **中优先级** - 普通任务
- 🟢 **低优先级** - 可延后处理

### 重复任务

- **每日** - 每天自动创建新任务
- **工作日** - 仅在周一至周五创建任务
- **一次性** - 不重复，完成任务即结束

## 🛠️ 开发

### 打包成 EXE

使用提供的批处理文件：

```bash
打包EXE.bat
```

或手动执行：

```bash
pyinstaller 待办提醒.spec
```

生成的 EXE 文件位于 `dist/待办提醒.exe`

### 技术栈

- **Python** 3.7+
- **Tkinter** - GUI 框架
- **SQLite** - 数据库
- **win10toast** - Windows 通知
- **PyInstaller** - 打包工具

## 📁 项目结构

```
todo-reminder-python/
├── todo_app_v2.py          # 主程序文件
├── 待办提醒.spec            # PyInstaller 配置
├── requirements.txt         # Python 依赖
├── README.md               # 项目文档
├── 打包EXE.bat              # 打包脚本
└── 运行新版应用.bat         # 运行脚本
```

## 💾 数据存储

应用使用 SQLite 数据库存储数据，位置：

- Windows: `~/todo_reminder_v2.db`

数据库包含以下表：
- `todos` - 待办任务
- `task_sessions` - 任务会话记录
- `repeat_templates` - 重复任务模板

## 🔧 系统要求

- **操作系统**: Windows 10/11
- **内存**: 最低 2GB RAM
- **磁盘空间**: 约 50MB

## 🐛 常见问题

### 通知不显示

确保 Windows 通知权限已开启：
1. 设置 → 系统 → 通知和操作
2. 允许应用访问通知

### 任务删除后重新出现

这是因为重复任务模板未删除。v1.0.0 已修复此问题：
- 删除重复任务时会自动清理模板
- 确保任务不再自动生成

## 📝 版本历史

### v1.0.0 (2026-01-02)

**新功能**
- ✨ 首个稳定版本发布
- 🎨 Win11 风格界面设计
- ⏱️ 实时计时功能
- 🔄 重复任务支持
- 📊 历史复盘功能
- 🎯 精简模式

**修复**
- 🐛 修复精简模式下任务选择错误
- 🐛 修复任务时间显示为 0 的问题
- 🐛 修复完成按钮导致应用卡死
- 🐛 修复删除重复任务后重新出现的问题
- 🐛 修复主界面按钮显示问题

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 👨‍💻 作者

Your Name

## 🙏 致谢

感谢所有为此项目做出贡献的开发者！

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐️ Star！**

</div>
