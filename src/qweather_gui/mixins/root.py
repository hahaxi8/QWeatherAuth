#!/usr/bin/env python3
"""窗口骨架：滚动区、样式、状态栏、通用对话框、关闭。"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox

import qweather_core as core
import qweather_console as qconsole
from ..theme import apply_window_icon, enable_dpi_awareness
from ..constants import *

__all__ = ["RootMixin"]
class RootMixin:
    """窗口骨架：滚动区、样式、状态栏、通用对话框、关闭。"""

    def __init__(self) -> None:
        enable_dpi_awareness()
        super().__init__()
        self.config_data = core.load_config()
        # 自动查询 LocationID 的状态（必须在建界面之前初始化）
        self._lookup_seq = 0
        self._city_after_id = None
        self._last_lookup_city = ""
        self._city_watch_enabled = False
        self._place_text = ""
        # 后台线程只往队列里放结果，Tk 变量一律在主线程访问
        self._lookup_queue: "queue.Queue" = queue.Queue()
        self._console_queue: "queue.Queue" = queue.Queue()
        self._console_busy = False
        self._picker_state = None         # 「凭据管理」单窗口的状态
        # 启动后静默读取控制台参数（不点按钮、不主动开浏览器）
        self._console_auto_after_id = None
        self._console_auto_done = False
        self._console_auto_running = False
        self._console_auto_attempt = 0
        self._poll_after_id = None
        self._closing = False
        self.auto_lookup_var = tk.BooleanVar(value=True)
        self.title(APP_TITLE)
        # 窗口/任务栏图标与 exe 文件图标保持一致
        self.icon_source = apply_window_icon(self)
        # 自适应屏幕高度，避免在小屏笔记本上超出桌面
        height = min(960, max(700, self.winfo_screenheight() - 90))
        self.geometry(f"1000x{height}")
        self.minsize(900, 700)
        self.configure(bg="#f3f5f7")
        self._configure_style()
        # 状态栏先占住底部，剩下的空间给可滚动主体
        self._build_status_bar()
        self._build_scroll_area()
        self._build_header()
        self._build_host_section()
        self._build_api_key_section()
        self._build_jwt_section()
        self._build_links_section()
        self._build_output_section()
        self._load_config_into_ui()
        self._refresh_key_info()
        self._start_lookup_poller()
        self._start_console_auto_fetch()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    def _build_scroll_area(self) -> None:
        """主体放进可滚动区域，右侧放一条可拖动的竖向滚动条。"""
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, highlightthickness=0, bg="#f3f5f7")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.vbar = ttk.Scrollbar(outer, orient="vertical")
        self.vbar.pack(side="right", fill="y")

        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.vbar.configure(command=self.canvas.yview)

        self.body = ttk.Frame(self.canvas)
        self._body_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind_all("<MouseWheel>", self._on_mouse_wheel, add="+")
    def _on_body_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._body_window, width=event.width)
    def _canvas_scrollable(self) -> bool:
        box = self.canvas.bbox("all")
        return bool(box) and (box[3] - box[1]) > self.canvas.winfo_height()
    def _on_mouse_wheel(self, event) -> None:
        """滚轮滚动主体；结果框、列表、下拉框自己会滚，不抢。"""
        target = self.winfo_containing(event.x_root, event.y_root)
        if target is not None and target.winfo_toplevel() is not self:
            return
        while target is not None and target is not self:
            if isinstance(target, (tk.Text, tk.Listbox, ttk.Combobox)):
                return
            target = getattr(target, "master", None)
        if self._canvas_scrollable():
            self.canvas.yview_scroll(-1 if getattr(event, "delta", 0) > 0 else 1, "units")
    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        for name in ("Microsoft YaHei UI", "Microsoft YaHei"):
            style.configure("Title.TLabel", font=(name, 18, "bold"))
            style.configure("Hint.TLabel", font=(name, 9), foreground="#52606d")
            style.configure("TLabel", font=(name, 10))
            style.configure("TLabelframe.Label", font=(name, 10, "bold"))
            style.configure("TButton", font=(name, 10), padding=(10, 6))
            style.configure("Accent.TButton", font=(name, 10, "bold"), padding=(10, 7))
            style.configure("Status.TLabel", font=(name, 9), foreground="#0b5cad")
            break
    def _build_header(self) -> None:
        header = ttk.Frame(self.body, padding=(18, 10, 18, 0))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="先填 API Host，再选一种认证方式；最后“一键生成所有链接”即可拿到全部接口的 URL/curl。",
            style="Hint.TLabel",
        ).pack(anchor="w")
    def _entry(self, parent: tk.Widget, variable: tk.Variable, width: int = 24,
               secret: bool = False) -> ttk.Entry:
        return ttk.Entry(parent, textvariable=variable, width=width,
                         show="*" if secret else "")
    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="就绪")
        bar = ttk.Frame(self, padding=(18, 0, 18, 10))
        bar.pack(side="bottom", fill="x")
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")
    def _set_status(self, message: str) -> None:
        self.status_var.set(message)
    def _show_error(self, exc: Exception) -> None:
        self._set_status(f"失败：{exc}")
        messagebox.showerror(APP_TITLE, str(exc))
    def _set_result(self, text: str) -> None:
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
    def _raise_dialog(self, dialog: tk.Toplevel) -> None:
        """把弹出的对话框提到最前面。

        主窗口不在前台时（例如使用者刚在浏览器里登录完），新开的小窗口容易落在后面，
        这里临时置顶并抢一次焦点，随后恢复普通层级。
        """
        try:
            dialog.lift()
            dialog.attributes("-topmost", True)
            dialog.after(400, lambda: self._unpin_dialog(dialog))
            dialog.focus_force()
        except tk.TclError:
            pass
    @staticmethod
    def _unpin_dialog(dialog: tk.Toplevel) -> None:
        try:
            dialog.attributes("-topmost", False)
        except tk.TclError:
            pass
    def _refresh_key_info(self) -> None:
        try:
            private_path, public_path = core.active_keypair()
        except FileNotFoundError:
            self.key_info_var.set("当前密钥：未生成（点击“一键生成公私钥”，并把公钥上传到控制台）")
            return
        fingerprint = ""
        try:
            if public_path.is_file():
                fingerprint = core.public_key_fingerprint(public_path.read_bytes())
        except OSError:
            fingerprint = ""
        text = f"当前私钥：{private_path.name}　公钥：{public_path.name}"
        if fingerprint:
            text += (
                f"\n公钥 SHA256：{fingerprint}"
                "（按控制台口径：去首尾空白后的 PEM 文本；也可与“登录控制台并自动填写”的核对结果对照）"
            )
        self.key_info_var.set(text)
    def _on_close(self) -> None:
        self._closing = True
        for after_id in (self._poll_after_id, self._city_after_id, self._console_auto_after_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        self._poll_after_id = None
        self._city_after_id = None
        self._console_auto_after_id = None
        self._persist_config()
        self.destroy()
