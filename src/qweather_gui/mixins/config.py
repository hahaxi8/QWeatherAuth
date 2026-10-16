#!/usr/bin/env python3
"""界面字段与配置文件之间的读写。"""

from __future__ import annotations


import qweather_core as core
import qweather_console as qconsole
from ..constants import *

__all__ = ["ConfigMixin"]
class ConfigMixin:
    """界面字段与配置文件之间的读写。"""

    def _load_config_into_ui(self) -> None:
        data = self.config_data
        self.host_var.set(str(data.get("api_host", "")))
        self.lat_var.set(str(data.get("latitude", core.DEFAULTS["latitude"])))
        self.lon_var.set(str(data.get("longitude", core.DEFAULTS["longitude"])))
        self.lang_var.set(str(data.get("lang", core.DEFAULTS["lang"])))
        # localTime 常开（界面上没有开关），配置里始终写 true
        self.local_time_var.set(True)
        self.city_var.set(str(data.get("location_name", core.DEFAULTS["location_name"])))
        self.location_id_var.set(str(data.get("location_id", "")))
        self._place_text = str(data.get("location_label", "")).strip()
        self._render_location_hint()
        self.kid_var.set(str(data.get("credential_id", "")))
        self.iss_var.set(str(data.get("developer_id", "")))
        self.sub_var.set(str(data.get("project_id", "")))
        self.lifetime_var.set(str(data.get("jwt_lifetime", 900)))
        self.auth_mode_var.set(str(data.get("auth_mode", "jwt")))
        self.days_var.set(str(data.get("forecast_days", 3)))
        self.hours_var.set(str(data.get("forecast_hours", 24)))
        self.indices_days_var.set(str(data.get("indices_days", "1d")))
        self.city_days_var.set(str(data.get("city_forecast_days", "3d")))
        self.city_hours_var.set(str(data.get("city_forecast_hours", "24h")))
        self.poi_radius_var.set(str(data.get("poi_radius_km", "5")))
        self.geo_range_var.set(str(data.get("geo_range", "cn")))
        poi_code = str(data.get("poi_type", "scenic"))
        for code, name in core.POI_TYPES:
            if code == poi_code:
                self.poi_type_var.set(f"{code} {name}")
                break
        else:
            self.poi_type_var.set("scenic 景点")
        self.tm_date_var.set(str(data.get("time_machine_date", "")) or core.default_time_machine_date())
        type_code = str(data.get("indices_type", "0"))
        for code, name in core.INDICES_TYPES:
            if code == type_code:
                self.indices_type_var.set(f"{code} {name}")
                break
        else:
            self.indices_type_var.set("0 全部（推荐）")
        # 已保存的 API KEY 回填到输入框（掩码显示），省得每次重新粘贴
        saved_auth = core.load_auth()
        if str(saved_auth.get("mode", "")).lower() == "api_key" and saved_auth.get("value"):
            self.api_key_var.set(str(saved_auth["value"]))
        # 回填不算"用户修改"：记录当前城市名后再打开自动查询开关
        self._last_lookup_city = self.city_var.get().strip()
        if not self.location_id_var.get().strip():
            # 配置里已有城市名但缺 LocationID：启动后自动补查一次
            self._last_lookup_city = ""
            self._city_after_id = self.after(CITY_LOOKUP_DELAY_MS, self._auto_lookup_location)
        self._city_watch_enabled = True
    def _collect_config(self) -> dict:
        return {
            "api_host": core.normalize_host(self.host_var.get()),
            "latitude": self.lat_var.get().strip(),
            "longitude": self.lon_var.get().strip(),
            "lang": self.lang_var.get().strip() or "zh",
            "local_time": bool(self.local_time_var.get()),
            "location_name": self.city_var.get().strip(),
            "location_label": self._place_text,
            "location_id": self.location_id_var.get().strip(),
            "auth_mode": self.auth_mode_var.get(),
            "credential_id": self.kid_var.get().strip(),
            "developer_id": self.iss_var.get().strip(),
            "project_id": self.sub_var.get().strip(),
            "jwt_lifetime": self.lifetime_var.get().strip(),
            "forecast_days": self.days_var.get().strip(),
            "forecast_hours": self.hours_var.get().strip(),
            "indices_type": self._selected_indices_type(),
            "indices_days": self.indices_days_var.get().strip(),
            "time_machine_date": self.tm_date_var.get().strip(),
            "city_forecast_days": self.city_days_var.get().strip() or "3d",
            "city_forecast_hours": self.city_hours_var.get().strip() or "24h",
            "poi_type": self._selected_poi_type(),
            "poi_radius_km": self.poi_radius_var.get().strip() or "5",
            "geo_range": self.geo_range_var.get().strip(),
        }
    def _persist_config(self) -> None:
        try:
            self.config_data = self._collect_config()
            core.save_config(self.config_data)
        except Exception as exc:  # noqa: BLE001 - 保存失败不影响本次生成
            self._set_status(f"配置保存失败：{exc}")
    def _activate_project_key(self) -> None:
        """签发 JWT 前切到该项目对应的密钥（多项目时各自的公钥不同）。"""
        project = self.sub_var.get().strip()
        if not project:
            return
        name = core.key_for_project(project)
        if not name:
            return
        pair = core.keypair_by_name(name)
        if not pair:
            return
        try:
            core.activate_keypair(*pair)
            self._refresh_key_info()
        except OSError:
            pass

    def _current_auth(self, allow_api_key_fallback: bool = False):
        """按界面选择生成认证记录，返回 (record, lifetime)。"""
        mode = self.auth_mode_var.get()
        api_key = self.api_key_var.get().strip()
        jwt_error: Exception | None = None
        if mode == "jwt":
            try:
                lifetime = core.normalize_lifetime(self.lifetime_var.get())
                self._activate_project_key()
                token = core.create_jwt(
                    self.kid_var.get(), self.iss_var.get(), self.sub_var.get(), lifetime
                )
                return core.build_auth_record("jwt", token=token, lifetime=lifetime), lifetime
            except Exception as exc:  # noqa: BLE001
                jwt_error = exc
                if not (allow_api_key_fallback and api_key):
                    raise
        if not api_key:
            if jwt_error is not None:
                raise jwt_error
            raise ValueError("请先填写 API KEY，或改用 JWT 认证方式")
        return core.build_auth_record("api_key", api_key=api_key), 0
