#!/usr/bin/env python3
"""① API Host 与位置区域。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import webbrowser

import qweather_core as core
import qweather_console as qconsole

__all__ = ["HostSectionMixin"]
class HostSectionMixin:
    """① API Host 与位置区域。"""

    def _build_host_section(self) -> None:
        frame = ttk.LabelFrame(self.body, text=" API Host 与位置（控制台-设置中查看，两个认证方式共用） ",
                               padding=(14, 12))
        frame.pack(fill="x", padx=18, pady=(8, 6))
        frame.columnconfigure(1, weight=1)

        self.host_var = tk.StringVar()
        ttk.Label(frame, text="API Host").grid(row=0, column=0, sticky="w", pady=5)
        self._entry(frame, self.host_var, width=48).grid(
            row=0, column=1, sticky="ew", padx=(10, 10), pady=5
        )
        host_buttons = ttk.Frame(frame)
        host_buttons.grid(row=0, column=2, sticky="e", pady=5)
        self.console_button = ttk.Button(
            host_buttons, text="打开控制台设置", style="Accent.TButton",
            command=self._on_open_console,
        )
        self.console_button.pack(side="left")
        ttk.Button(host_buttons, text="在系统浏览器打开",
                   command=lambda: webbrowser.open(CONSOLE_URL)).pack(side="left", padx=(8, 0))

        self.lat_var = tk.StringVar()
        self.lon_var = tk.StringVar()
        self.lang_var = tk.StringVar()
        # localTime 与"填完自动查询"都是常开行为，不再放勾选框到界面上
        self.local_time_var = tk.BooleanVar(value=True)
        row = ttk.Frame(frame)
        row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(row, text="纬度").pack(side="left")
        self._entry(row, self.lat_var, width=11).pack(side="left", padx=(8, 16))
        ttk.Label(row, text="经度").pack(side="left")
        self._entry(row, self.lon_var, width=11).pack(side="left", padx=(8, 16))
        ttk.Label(row, text="语言").pack(side="left")
        ttk.Combobox(row, textvariable=self.lang_var, values=core.LANGUAGES, width=8,
                     state="readonly").pack(side="left", padx=(8, 16))
        ttk.Label(row, text="（经纬度原样保留精度，最多 8 位小数；请求附带 localTime=true）",
                  style="Hint.TLabel").pack(side="left")

        self.city_var = tk.StringVar()
        self.location_id_var = tk.StringVar()
        self.location_label_var = tk.StringVar()
        row2 = ttk.Frame(frame)
        row2.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(row2, text="查询地名").pack(side="left")
        self.city_entry = self._entry(row2, self.city_var, width=18)
        self.city_entry.pack(side="left", padx=(8, 12))
        ttk.Label(row2, text="LocationID").pack(side="left")
        self.location_id_entry = self._entry(row2, self.location_id_var, width=18)
        self.location_id_entry.pack(side="left", padx=(8, 10))
        # 手动改 LocationID 时，之前的“已选地点”描述就失效了，清掉免得误导
        self.location_id_entry.bind("<KeyRelease>", lambda _event: self._clear_place_text())
        self.lookup_button = ttk.Button(row2, text="立即查询", command=self._on_lookup_location)
        self.lookup_button.pack(side="left", padx=(0, 12))
        # 凭据管理入口放在这里（主窗口只保留这一个）
        self.manage_button = ttk.Button(
            row2, text="凭据管理…", style="Accent.TButton",
            command=self._on_manage_credentials,
        )
        self.manage_button.pack(side="left")

        ttk.Label(
            frame,
            textvariable=self.location_label_var,
            style="Hint.TLabel",
            wraplength=900,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 2))

        # 输入防抖 + 失焦/回车立即查询
        self.city_var.trace_add("write", self._on_city_changed)
        self.city_entry.bind("<FocusOut>", lambda _event: self._lookup_now_if_ready())
        self.city_entry.bind("<Return>", lambda _event: self._lookup_now_if_ready())
