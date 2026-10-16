#!/usr/bin/env python3
"""② 认证区域：API KEY 与 JWT 输入、密钥生成。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
import webbrowser
from tkinter import filedialog, messagebox

import qweather_core as core
import qweather_console as qconsole

__all__ = ["AuthSectionMixin"]
class AuthSectionMixin:
    """② 认证区域：API KEY 与 JWT 输入、密钥生成。"""

    def _build_api_key_section(self) -> None:
        frame = ttk.LabelFrame(self.body, text=" ① API KEY 认证 ", padding=(14, 12))
        frame.pack(fill="x", padx=18, pady=(0, 6))
        frame.columnconfigure(1, weight=1)

        self.api_key_var = tk.StringVar()
        ttk.Label(frame, text="API KEY").grid(row=0, column=0, sticky="w", pady=6)
        self._entry(frame, self.api_key_var, width=48, secret=True).grid(
            row=0, column=1, sticky="ew", padx=(10, 10), pady=6
        )
        ttk.Label(
            frame,
            text="请求时使用请求头 X-QW-Api-Key；在下方「凭据管理…」里新建或选用 API KEY 凭据。",
            style="Hint.TLabel",
        ).grid(row=1, column=1, sticky="w", padx=(10, 0))
    def _build_jwt_section(self) -> None:
        frame = ttk.LabelFrame(self.body, text=" ② JWT 认证（官方推荐，需先上传公钥） ", padding=(14, 12))
        frame.pack(fill="x", padx=18, pady=(0, 6))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        self.kid_var = tk.StringVar()
        self.iss_var = tk.StringVar()
        self.sub_var = tk.StringVar()
        self.lifetime_var = tk.StringVar(value="900")

        ttk.Label(frame, text="凭据 ID（kid）").grid(row=0, column=0, sticky="w", pady=5)
        self._entry(frame, self.kid_var, width=26).grid(row=0, column=1, sticky="ew",
                                                        padx=(10, 18), pady=5)
        ttk.Label(frame, text="有效期（秒）").grid(row=0, column=2, sticky="w", pady=5)
        self._entry(frame, self.lifetime_var, width=12).grid(row=0, column=3, sticky="w",
                                                             padx=(10, 0), pady=5)

        ttk.Label(frame, text="开发者 ID（iss）").grid(row=1, column=0, sticky="w", pady=5)
        self._entry(frame, self.iss_var, width=26).grid(row=1, column=1, sticky="ew",
                                                        padx=(10, 18), pady=5)
        ttk.Label(frame, text="项目 ID（sub）").grid(row=1, column=2, sticky="w", pady=5)
        self._entry(frame, self.sub_var, width=26).grid(row=1, column=3, sticky="ew",
                                                        padx=(10, 0), pady=5)

        # 新凭据的命名固定为「jwb+年月日时分秒」（JWT）与「api+年月日时分秒」（API KEY），不需要界面配置
        ttk.Label(
            frame,
            text="新凭据命名：JWT 用 jwb+年月日时分秒（如 jwb20261015172350），API KEY 用 api+年月日时分秒。",
            style="Hint.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        self.key_info_var = tk.StringVar(value="当前密钥：未生成")
        ttk.Label(frame, textvariable=self.key_info_var, style="Hint.TLabel",
                  wraplength=880, justify="left").grid(row=3, column=0, columnspan=4,
                                                       sticky="w", pady=(4, 0))
    def _on_generate_keys(self) -> None:
        try:
            private_path, public_path = core.generate_keypair()
            self._refresh_key_info()
            messagebox.showinfo(
                APP_TITLE,
                "公私钥生成成功（文件名含生成时间，旧密钥不会被覆盖）。\n\n"
                f"私钥：{private_path.name}\n公钥：{public_path.name}\n\n"
                "回到「凭据管理」点「一键生成」，就会用这把新公钥创建 JWT 凭据。",
            )
            self._set_status("已生成新的 Ed25519 密钥对；点「一键生成」会用新公钥创建 JWT 凭据")
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
    def _on_open_key_dir(self) -> None:
        try:
            directory = core.ensure_data_dir()
            if os.name == "nt":
                os.startfile(directory)  # type: ignore[attr-defined]
            else:
                webbrowser.open(directory.as_uri())
            self._set_status(f"已打开：{directory}")
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
