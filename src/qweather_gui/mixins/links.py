#!/usr/bin/env python3
"""③ 链接生成区域与结果输出。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from tkinter import filedialog, messagebox

import qweather_core as core
import qweather_console as qconsole
from ..constants import *

__all__ = ["LinksSectionMixin"]
class LinksSectionMixin:
    """③ 链接生成区域与结果输出。"""

    def _build_links_section(self) -> None:
        frame = ttk.LabelFrame(self.body, text=" ③ 一键生成所有接口链接 ", padding=(14, 12))
        frame.pack(fill="x", padx=18, pady=(0, 6))

        self.auth_mode_var = tk.StringVar(value="jwt")
        self.include_curl_var = tk.BooleanVar(value=True)
        self.days_var = tk.StringVar(value="3")
        self.hours_var = tk.StringVar(value="24")
        self.indices_type_var = tk.StringVar(value="0")
        self.indices_days_var = tk.StringVar(value="1d")
        self.tm_date_var = tk.StringVar(value=core.default_time_machine_date())
        self.city_days_var = tk.StringVar(value="3d")
        self.city_hours_var = tk.StringVar(value="24h")
        self.poi_type_var = tk.StringVar(value="scenic 景点")
        self.poi_radius_var = tk.StringVar(value="5")
        self.geo_range_var = tk.StringVar(value="cn")

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="生成链接使用：").pack(side="left")
        ttk.Radiobutton(row, text="JWT（推荐）", value="jwt",
                        variable=self.auth_mode_var).pack(side="left", padx=(4, 10))
        ttk.Radiobutton(row, text="API KEY", value="api_key",
                        variable=self.auth_mode_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(row, text="同时输出可直接执行的 curl 命令",
                        variable=self.include_curl_var).pack(side="left")
        ttk.Label(row, text="覆盖：" + "、".join(sorted({e.group for e in core.ENDPOINTS})),
                  style="Hint.TLabel").pack(side="left", padx=(16, 0))

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", pady=(0, 8))
        ttk.Label(row2, text="预报天数").pack(side="left")
        self._entry(row2, self.days_var, width=5).pack(side="left", padx=(6, 14))
        ttk.Label(row2, text="逐小时数").pack(side="left")
        self._entry(row2, self.hours_var, width=6).pack(side="left", padx=(6, 14))
        ttk.Label(row2, text="指数类型").pack(side="left")
        ttk.Combobox(row2, textvariable=self.indices_type_var, width=16, state="readonly",
                     values=[f"{code} {name}" for code, name in core.INDICES_TYPES]).pack(
            side="left", padx=(6, 14)
        )
        ttk.Label(row2, text="指数天数").pack(side="left")
        ttk.Combobox(row2, textvariable=self.indices_days_var, width=5, state="readonly",
                     values=["1d", "3d"]).pack(side="left", padx=(6, 14))
        ttk.Label(row2, text="时光机日期").pack(side="left")
        self._entry(row2, self.tm_date_var, width=11).pack(side="left", padx=(6, 0))

        row2b = ttk.Frame(frame)
        row2b.pack(fill="x", pady=(0, 8))
        ttk.Label(row2b, text="城市预报天数").pack(side="left")
        ttk.Combobox(row2b, textvariable=self.city_days_var, width=5, state="readonly",
                     values=list(core.CITY_FORECAST_DAYS)).pack(side="left", padx=(6, 14))
        ttk.Label(row2b, text="城市小时数").pack(side="left")
        ttk.Combobox(row2b, textvariable=self.city_hours_var, width=6, state="readonly",
                     values=list(core.CITY_FORECAST_HOURS)).pack(side="left", padx=(6, 14))
        ttk.Label(row2b, text="POI 类型").pack(side="left")
        ttk.Combobox(row2b, textvariable=self.poi_type_var, width=11, state="readonly",
                     values=[f"{code} {name}" for code, name in core.POI_TYPES]).pack(
            side="left", padx=(6, 14)
        )
        ttk.Label(row2b, text="POI 半径(km)").pack(side="left")
        self._entry(row2b, self.poi_radius_var, width=5).pack(side="left", padx=(6, 14))
        ttk.Label(row2b, text="热门城市国家").pack(side="left")
        self._entry(row2b, self.geo_range_var, width=5).pack(side="left", padx=(6, 0))

        row3 = ttk.Frame(frame)
        row3.pack(fill="x")
        ttk.Button(row3, text="一键生成所有链接", style="Accent.TButton",
                   command=self._on_generate_all_links).pack(side="left")
        ttk.Button(row3, text="复制全部", command=self._on_copy).pack(side="left", padx=(10, 0))
        ttk.Button(row3, text="导出为 .sh 脚本", command=self._on_export).pack(side="left", padx=(10, 0))
    def _build_output_section(self) -> None:
        frame = ttk.LabelFrame(self.body, text=" 生成结果 ", padding=(10, 8))
        frame.pack(fill="x", padx=18, pady=(0, 10))
        frame.columnconfigure(0, weight=1)

        # 长 URL 自动换行显示，不再需要横向滚动条
        self.result_text = tk.Text(frame, height=16, wrap="word", font=("Consolas", 9),
                                   bg="#ffffff", relief="solid", borderwidth=1)
        self.result_text.grid(row=0, column=0, sticky="nsew")
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=self.result_text.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        self.result_text.configure(yscrollcommand=scroll_y.set)
    def _selected_indices_type(self) -> str:
        return (self.indices_type_var.get() or "0").split(" ", 1)[0].strip() or "0"
    def _selected_poi_type(self) -> str:
        return (self.poi_type_var.get() or "scenic").split(" ", 1)[0].strip() or "scenic"
    def _on_generate_all_links(self) -> None:
        try:
            config = self._collect_config()
            record, lifetime = self._current_auth()
            core.save_auth(record)
            if record.get("mode") == "jwt":
                core.secure_write(core.jwt_path(), str(record.get("value", "")).replace("Bearer ", "") + "\n")
            core.save_config(config)
            self.config_data = config

            text = core.render_links_text(
                config,
                record,
                include_curl=bool(self.include_curl_var.get()),
                token_lifetime=lifetime if record.get("mode") == "jwt" else 0,
            )
            self._set_result(text)
            mode_name = "JWT" if record.get("mode") == "jwt" else "API KEY"
            self._set_status(
                f"已生成 {len(core.ENDPOINTS)} 个接口链接（认证方式：{mode_name}），"
                f"配置已保存到 {core.config_path().name}"
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
    def _on_copy(self) -> None:
        value = self.result_text.get("1.0", "end").strip()
        if not value:
            self._set_status("没有可复制的内容，请先点击“一键生成所有链接”")
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update_idletasks()
        self._set_status("已复制全部内容到剪贴板")
    def _on_export(self) -> None:
        try:
            config = self._collect_config()
            record, _ = self._current_auth(allow_api_key_fallback=True)
            default = core.links_path()
            path = filedialog.asksaveasfilename(
                title="导出接口脚本",
                defaultextension=".sh",
                initialdir=str(default.parent),
                initialfile=default.name,
                filetypes=[("Shell 脚本", "*.sh"), ("所有文件", "*.*")],
            )
            if not path:
                self._set_status("已取消导出")
                return
            core.secure_write(Path(path), core.render_shell_script(config, record))
            self._set_status(f"已导出脚本：{path}")
            messagebox.showinfo(APP_TITLE, f"已导出：\n{path}")
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
