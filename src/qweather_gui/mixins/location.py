#!/usr/bin/env python3
"""地名查询：自动查询、结果解析与提示行。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

import qweather_core as core
import qweather_console as qconsole
from ..constants import *

__all__ = ["LocationMixin"]
class LocationMixin:
    """地名查询：自动查询、结果解析与提示行。"""

    def _on_city_changed(self, *_args: object) -> None:
        """城市名变化后延迟查询（防抖），避免每敲一个字就发一次请求。"""
        if not self._city_watch_enabled or not self.auto_lookup_var.get():
            return
        if self._city_after_id is not None:
            self.after_cancel(self._city_after_id)
        self._city_after_id = self.after(CITY_LOOKUP_DELAY_MS, self._auto_lookup_location)
    def _lookup_now_if_ready(self) -> None:
        """失焦/回车时立即查询（跳过防抖等待）。"""
        if self._city_after_id is not None:
            self.after_cancel(self._city_after_id)
            self._city_after_id = None
        if self._city_watch_enabled and self.auto_lookup_var.get():
            self._auto_lookup_location()
    def _auto_lookup_location(self) -> None:
        self._city_after_id = None
        if not self.auto_lookup_var.get():
            return
        city = self.city_var.get().strip()
        if len(city) < CITY_LOOKUP_MIN_CHARS or city == self._last_lookup_city:
            return
        if not core.normalize_host(self.host_var.get()):
            self._set_status("填写 API Host 后可自动查询 LocationID")
            return
        self._start_location_lookup(manual=False)
    def _on_lookup_location(self) -> None:
        city = self.city_var.get().strip()
        if not city:
            self._show_error(ValueError("请先填写城市名，例如 深圳 或 深圳,南山"))
            return
        self._start_location_lookup(manual=True)
    def _start_location_lookup(self, manual: bool) -> None:
        city = self.city_var.get().strip()
        host = core.normalize_host(self.host_var.get())
        if not host:
            if manual:
                self._show_error(ValueError("请先填写 API Host"))
            return
        try:
            record, _ = self._current_auth(allow_api_key_fallback=True)
        except Exception as exc:  # noqa: BLE001
            if manual:
                self._show_error(exc)
            else:
                self._set_status(f"无法自动查询 LocationID：{exc}")
            return

        # 所有需要在后台使用的值都在主线程取好，工作线程不碰 Tk
        header_name = str(record.get("header", ""))
        header_value = str(record.get("value", ""))
        lang = self.lang_var.get().strip() or "zh"

        self._lookup_seq += 1
        sequence = self._lookup_seq
        self._last_lookup_city = city
        self.lookup_button.configure(state="disabled")
        self._set_status(f"正在查询“{city}”的 LocationID…")

        def worker() -> None:
            try:
                results = core.lookup_location_id(host, city, header_name, header_value, lang)
            except Exception as exc:  # noqa: BLE001
                self._lookup_queue.put((sequence, manual, exc, None))
                return
            self._lookup_queue.put((sequence, manual, None, results))

        threading.Thread(target=worker, daemon=True).start()
    def _lookup_failed(self, exc: Exception, sequence: int, manual: bool) -> None:
        if sequence != self._lookup_seq:  # 已有更新的查询，丢弃旧结果
            return
        self.lookup_button.configure(state="normal")
        self._last_lookup_city = ""  # 允许下次重新尝试同一城市
        if manual:
            self._show_error(exc)
        else:
            self._set_status(f"自动查询 LocationID 失败：{exc}")
    def _show_lookup_results(self, results: list, sequence: int, manual: bool) -> None:
        if sequence != self._lookup_seq:
            return
        self.lookup_button.configure(state="normal")
        if not results:
            self._last_lookup_city = ""
            message = ValueError("未查询到匹配的城市，请换一个名称或直接填 LocationID")
            if manual:
                self._show_error(message)
            else:
                self._set_status(str(message))
            return
        if len(results) == 1:
            self._apply_location(results[0])
            return

        dialog = tk.Toplevel(self)
        dialog.title("选择城市")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("560x340")
        ttk.Label(dialog, text="请选择要使用的城市：", padding=(12, 10, 12, 4)).pack(anchor="w")
        listbox = tk.Listbox(dialog, font=("Microsoft YaHei UI", 10))
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        for item in results:
            listbox.insert(
                "end",
                f"{self._place_label(item)}　LocationID={item['id']}"
                f"　经纬度={item['lon']},{item['lat']}",
            )
        listbox.selection_set(0)

        def confirm() -> None:
            selection = listbox.curselection()
            if selection:
                self._apply_location(results[selection[0]])
            dialog.destroy()

        ttk.Button(dialog, text="使用选中城市", command=confirm).pack(pady=(0, 12))
        dialog.wait_window()
    def _apply_location(self, item: dict) -> None:
        """把选中的地点写进界面：LocationID 与经纬度是权威值，查询地名保持用户输入。"""
        self.location_id_var.set(item["id"])
        # 不把选中的地名回写进“查询地名”输入框：那里是 GeoAPI 的查询关键词，
        # 选到区县时（例如 南山区）写进去会让人误以为那是城市名。
        if not self.city_var.get().strip() and item.get("name"):
            self.city_var.set(str(item["name"]))
        if item.get("lat") and item.get("lon"):
            try:
                self.lat_var.set(core.normalize_latitude(item["lat"]))
                self.lon_var.set(core.normalize_longitude(item["lon"]))
            except ValueError:  # 返回异常值时回退为原样字符串
                self.lat_var.set(str(item["lat"]))
                self.lon_var.set(str(item["lon"]))
        self._place_text = self._place_label(item) or str(item.get("name", ""))
        self._render_location_hint()
        # 回填会不会触发查询由这里登记；查询关键词未变，不会重复请求
        self._last_lookup_city = self.city_var.get().strip()
        self._persist_config()
        self._set_status(f"已选用 {self._place_text}：LocationID={item['id']}")
    @staticmethod
    def _place_label(item: dict) -> str:
        """拼出「省 市 区」形式的完整地名，重复的部分只保留一次。"""
        parts: list = []
        for key in ("adm1", "adm2", "name"):
            value = str(item.get(key, "")).strip()
            if value and value not in parts:
                parts.append(value)
        return " ".join(parts)
    def _clear_place_text(self) -> None:
        if self._place_text:
            self._place_text = ""
            self._render_location_hint()
    def _render_location_hint(self) -> None:
        if not self._place_text:
            location_id = self.location_id_var.get().strip()
            if location_id:
                self.location_label_var.set(
                    f"已填 LocationID {location_id}（点“立即查询”可按地名重新选择）。"
                    + self.LOCATION_HINT
                )
            else:
                self.location_label_var.set(self.LOCATION_HINT)
            return
        detail = []
        location_id = self.location_id_var.get().strip()
        latitude = self.lat_var.get().strip()
        longitude = self.lon_var.get().strip()
        if location_id:
            detail.append(f"LocationID {location_id}")
        if latitude and longitude:
            detail.append(f"经纬度 {longitude},{latitude}")
        suffix = f"（{'，'.join(detail)}）" if detail else ""
        self.location_label_var.set(f"已选地点：{self._place_text}{suffix}")
