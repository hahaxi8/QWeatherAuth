#!/usr/bin/env python3
"""qweather_core 的自检用例（标准库 unittest，无需额外依赖）。

运行（在项目根目录）：
    python -m unittest discover tests
    python tests/test_qweather_core.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

# 源码在 src/、测试在 tests/：把 src 加入模块搜索路径
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cryptography.hazmat.primitives import serialization  # noqa: E402

import qweather_core as core  # noqa: E402


class TempDataMixin(unittest.TestCase):
    """把凭据目录指向临时目录，避免碰真实凭据。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_env = os.environ.get(core.DATA_DIR_ENV)
        os.environ[core.DATA_DIR_ENV] = self._tmp.name
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop(core.DATA_DIR_ENV, None)
        else:
            os.environ[core.DATA_DIR_ENV] = self._old_env
        self._tmp.cleanup()


class TestJwt(TempDataMixin):
    def test_jwt_matches_official_spec_and_verifies(self) -> None:
        private_path, public_path = core.generate_keypair()
        token = core.create_jwt("ABCDE12345", "Q12345ABCD", "ABCDE23456", 900)

        self.assertEqual(len(token.split(".")), 3, "JWT 必须是 header.payload.signature")
        decoded = core.decode_jwt(token)
        self.assertEqual(decoded["header"], {"alg": "EdDSA", "kid": "ABCDE12345"})
        payload = decoded["payload"]
        self.assertEqual(
            sorted(payload), ["exp", "iat", "iss", "sub"],
            "官方要求只放 iss/sub/iat/exp，不得混入 typ/aud/nbf",
        )
        self.assertEqual(payload["iss"], "Q12345ABCD")
        self.assertEqual(payload["sub"], "ABCDE23456")
        # iat 应比当前时间早 30 秒，exp 比 iat 晚 lifetime
        self.assertEqual(payload["exp"] - payload["iat"], 900 + core.JWT_IAT_BACKOFF)

        # 用公钥验签，确认签名确实由该私钥产生且使用 Base64URL
        public_key = serialization.load_pem_public_key(public_path.read_bytes())
        header_b64, payload_b64, signature_b64 = token.split(".")
        signature = base64.urlsafe_b64decode(signature_b64 + "=" * (-len(signature_b64) % 4))
        public_key.verify(signature, f"{header_b64}.{payload_b64}".encode("ascii"))

        # 私钥文件在 POSIX 下应为 600
        if os.name != "nt":
            self.assertEqual(private_path.stat().st_mode & 0o777, 0o600)

    def test_jwt_rejects_bad_inputs(self) -> None:
        core.generate_keypair()
        with self.assertRaises(ValueError):
            core.create_jwt("", "Q1", "P1")
        with self.assertRaises(ValueError):
            core.create_jwt("kid", "", "P1")
        with self.assertRaises(ValueError):
            core.create_jwt("kid", "Q1", "")
        with self.assertRaises(ValueError):
            core.create_jwt("kid", "Q1", "P1", core.JWT_MAX_LIFETIME + 1)

    def test_jwt_without_key_is_explicit(self) -> None:
        with self.assertRaises(FileNotFoundError):
            core.create_jwt("kid", "Q1", "P1")


class TestKeypairResolution(TempDataMixin):
    def test_prefers_active_key_json(self) -> None:
        first_private, _ = core.generate_keypair()
        second_private, second_public = core.generate_keypair()
        self.assertNotEqual(first_private, second_private)
        private_path, public_path = core.active_keypair()
        self.assertEqual(private_path, second_private)
        self.assertEqual(public_path, second_public)

    def test_reads_legacy_fixed_name(self) -> None:
        """旧版 CLI 生成的 ed25519-private.pem 仍必须被识别。"""
        legacy_private = self.data_dir / "ed25519-private.pem"
        legacy_public = self.data_dir / "ed25519-public.pem"
        private_key = core.Ed25519PrivateKey.generate()
        legacy_private.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        legacy_public.write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        private_path, public_path = core.active_keypair()
        self.assertEqual(private_path, legacy_private)
        self.assertEqual(public_path, legacy_public)

    def test_fingerprint_is_sha256_of_public_key(self) -> None:
        _, public_path = core.generate_keypair()
        fingerprint = core.public_key_fingerprint(public_path.read_bytes())
        self.assertEqual(len(fingerprint), 64)
        int(fingerprint, 16)  # 必须是合法十六进制

    def test_fingerprint_candidates_cover_console_conventions(self) -> None:
        """控制台的 SHA256 口径未写死，四种常见口径都要能算出来并对得上。"""
        import hashlib

        _, public_path = core.generate_keypair()
        raw = public_path.read_bytes()
        prints = core.public_key_fingerprints(raw)
        self.assertEqual(set(prints), {"der", "pem", "pem_body", "pem_file"})
        self.assertEqual(prints["pem_file"], hashlib.sha256(raw).hexdigest())
        stripped = raw.decode("utf-8").strip()
        self.assertEqual(prints["pem"], hashlib.sha256(stripped.encode("utf-8")).hexdigest())
        # 界面展示口径：按控制台文档描述（去首尾空白后的 PEM 文本）
        self.assertEqual(core.public_key_fingerprint(raw), prints["pem"])
        # 控制台若使用 DER 口径，也必须能被识别为一致
        self.assertNotEqual(prints["der"], prints["pem"])


class TestConfigCompat(TempDataMixin):
    def test_salvages_legacy_non_json_config(self) -> None:
        """真实故障场景：config.json 被写成 `developer_id:Qxxx` 一行，旧版直接崩溃。"""
        config_file = self.data_dir / "config.json"
        config_file.write_text("developer_id:Q123456789n", encoding="utf-8")

        config = core.load_config()
        self.assertEqual(config["developer_id"], "Q123456789n")
        # 抢救后应重写为合法 JSON，并留下备份
        rewritten = json.loads(config_file.read_text(encoding="utf-8"))
        self.assertEqual(rewritten["developer_id"], "Q123456789n")
        self.assertTrue((self.data_dir / "config.json.bak").is_file())
        # 关键：不能抛异常
        self.assertEqual(config["latitude"], core.DEFAULTS["latitude"])

    def test_missing_config_returns_defaults(self) -> None:
        config = core.load_config()
        self.assertEqual(config["api_host"], "")
        self.assertEqual(config["auth_mode"], "jwt")

    def test_save_load_roundtrip_keeps_known_keys_only(self) -> None:
        core.save_config({"api_host": "abc.qweatherapi.com", "latitude": "39.92", "noise": 1})
        config = core.load_config()
        self.assertEqual(config["api_host"], "abc.qweatherapi.com")
        self.assertEqual(config["latitude"], "39.92")
        self.assertNotIn("noise", config)


class TestValidation(unittest.TestCase):
    def test_coordinates_keep_original_precision(self) -> None:
        """不做两位四舍五入：GeoAPI 与开发者示例给的小数位都要原样保留。"""
        self.assertEqual(core.normalize_latitude("22.530761"), "22.530761")
        self.assertEqual(core.normalize_longitude("113.941968"), "113.941968")
        # GeoAPI 实际返回的 5 位小数
        self.assertEqual(core.normalize_latitude("39.90499"), "39.90499")
        # 开发者示例里的 8 位小数
        self.assertEqual(core.normalize_longitude("116.38999939"), "116.38999939")
        # 多余的小数位属于浮点噪声，裁到 8 位
        self.assertEqual(core.normalize_latitude("39.909999851234"), "39.90999985")
        # 多余 0 / 整数形态归一化
        self.assertEqual(core.normalize_longitude("113.940000"), "113.94")
        self.assertEqual(core.normalize_latitude("39.92"), "39.92")
        self.assertEqual(core.normalize_latitude("0"), "0")
        self.assertEqual(core.normalize_longitude("116.0"), "116")

    def test_coordinates_range(self) -> None:
        with self.assertRaises(ValueError):
            core.normalize_latitude("91")
        with self.assertRaises(ValueError):
            core.normalize_longitude("-180.01")
        with self.assertRaises(ValueError):
            core.normalize_latitude("abc")

    def test_lifetime_bounds(self) -> None:
        self.assertEqual(core.normalize_lifetime("900"), 900)
        with self.assertRaises(ValueError):
            core.normalize_lifetime("0")
        with self.assertRaises(ValueError):
            core.normalize_lifetime(str(core.JWT_MAX_LIFETIME + 1))

    def test_forecast_bounds(self) -> None:
        self.assertEqual(core.normalize_int("10", "预报天数", 1, 10), "10")
        with self.assertRaises(ValueError):
            core.normalize_int("11", "预报天数", 1, 10)

    def test_indices_type_rules(self) -> None:
        self.assertEqual(core.normalize_indices_type("0"), "0")
        self.assertEqual(core.normalize_indices_type("3,5"), "3,5")
        with self.assertRaises(ValueError):
            core.normalize_indices_type("0,3")   # 全部不能与具体类型混用
        with self.assertRaises(ValueError):
            core.normalize_indices_type("99")

    def test_indices_days_rules(self) -> None:
        self.assertEqual(core.normalize_indices_days("3d"), "3d")
        with self.assertRaises(ValueError):
            core.normalize_indices_days("7d")

    def test_city_forecast_choices(self) -> None:
        self.assertEqual(
            core.normalize_choice("7d", "城市预报天数", core.CITY_FORECAST_DAYS, "3d"), "7d")
        self.assertEqual(
            core.normalize_choice("", "城市预报小时数", core.CITY_FORECAST_HOURS, "24h"), "24h")
        with self.assertRaises(ValueError):
            core.normalize_choice("5d", "城市预报天数", core.CITY_FORECAST_DAYS, "3d")
        with self.assertRaises(ValueError):
            core.normalize_choice("48h", "城市预报小时数", core.CITY_FORECAST_HOURS, "24h")

    def test_poi_radius_is_kilometres(self) -> None:
        self.assertEqual(core.normalize_radius_km("5"), "5")
        self.assertEqual(core.normalize_radius_km(""), "5")      # 默认 5 公里
        self.assertEqual(core.normalize_radius_km(2.5), "2.5")
        self.assertEqual(core.normalize_radius_km("50"), "50")   # 官方上限
        with self.assertRaises(ValueError):
            core.normalize_radius_km("0")
        with self.assertRaises(ValueError):
            core.normalize_radius_km("51")                       # 不是 5000 米
        with self.assertRaises(ValueError):
            core.normalize_radius_km("abc")

    def test_poi_type_choices(self) -> None:
        allowed = tuple(item[0] for item in core.POI_TYPES)
        self.assertEqual(core.normalize_choice("scenic", "POI 类型", allowed, "scenic"), "scenic")
        self.assertEqual(core.normalize_choice("TSTA", "POI 类型", allowed, "scenic"), "TSTA")
        with self.assertRaises(ValueError):
            core.normalize_choice("050000", "POI 类型", allowed, "scenic")

    def test_country_code(self) -> None:
        self.assertEqual(core.normalize_country("CN"), "cn")
        self.assertEqual(core.normalize_country(""), "")         # 留空=不限国家
        with self.assertRaises(ValueError):
            core.normalize_country("china")

    def test_time_machine_date_rules(self) -> None:
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
        self.assertEqual(core.normalize_time_machine_date(yesterday), yesterday)
        with self.assertRaises(ValueError):
            core.normalize_time_machine_date(date.today().strftime("%Y%m%d"))
        with self.assertRaises(ValueError):
            core.normalize_time_machine_date(
                (date.today() - timedelta(days=core.TIME_MACHINE_MAX_DAYS + 1)).strftime("%Y%m%d")
            )
        with self.assertRaises(ValueError):
            core.normalize_time_machine_date("2026-10-14")


class TestEndpoints(unittest.TestCase):
    """逐个核对官方文档路径，防止把 v1/v7/v2 写混。"""

    def setUp(self) -> None:
        self.config = {
            "api_host": "abcxyz.qweatherapi.com",
            "latitude": "39.92",
            "longitude": "116.41",
            "lang": "zh",
            "local_time": True,
            "location_name": "深圳",
            "location_id": "101280601",
            "forecast_days": "3",
            "forecast_hours": "24",
            "indices_type": "0",
            "indices_days": "1d",
            "time_machine_date": "20261014",
        }

    def url_for(self, key: str) -> str:
        for item, url in core.build_urls(self.config):
            if item.key == key:
                return url
        raise AssertionError(f"端点表缺少 {key}")

    def test_geo_uses_v2(self) -> None:
        url = self.url_for("geo_city_lookup")
        self.assertTrue(url.startswith("https://abcxyz.qweatherapi.com/geo/v2/city/lookup?"), url)
        self.assertIn("location=", url)

    def test_weather_paths_use_v1_and_latlon_in_path(self) -> None:
        self.assertEqual(
            self.url_for("weather_current"),
            "https://abcxyz.qweatherapi.com/weather/v1/current/39.92/116.41"
            "?localTime=true&lang=zh",
        )
        self.assertIn("/weather/v1/daily/39.92/116.41?days=3", self.url_for("weather_daily"))
        self.assertIn("/weather/v1/hourly/39.92/116.41?hours=24", self.url_for("weather_hourly"))

    def test_minutely_stays_v7_and_uses_lon_lat(self) -> None:
        url = self.url_for("minutely_precipitation")
        self.assertIn("/v7/minutely/5m?", url)
        self.assertIn("location=116.41%2C39.92", url, "分钟降水的 location 是“经度,纬度”")

    def test_air_quality_paths(self) -> None:
        self.assertIn("/airquality/v1/current/39.92/116.41", self.url_for("air_current"))
        self.assertIn("/airquality/v1/daily/39.92/116.41", self.url_for("air_daily"))
        self.assertNotIn("days=", self.url_for("air_daily"), "空气质量每日预报没有 days 参数")

    def test_warning_uses_weatheralert_service(self) -> None:
        self.assertIn("/weatheralert/v1/current/39.92/116.41", self.url_for("weather_warning"))

    def test_indices_uses_v7_with_days_in_path(self) -> None:
        url = self.url_for("indices_daily")
        self.assertIn("/v7/indices/1d?", url)
        self.assertIn("type=0", url)
        self.assertIn("location=101280601", url, "填了 LocationID 时优先用 LocationID")

    def test_time_machine_uses_v7_and_location_id(self) -> None:
        url = self.url_for("time_machine")
        self.assertIn("/v7/historical/weather?", url)
        self.assertIn("location=101280601", url)
        self.assertIn("date=20261014", url)

    def test_geo_new_endpoints(self) -> None:
        top = self.url_for("geo_top_city")
        self.assertTrue(top.startswith("https://abcxyz.qweatherapi.com/geo/v2/city/top?"), top)
        self.assertIn("range=cn", top)
        poi = self.url_for("geo_poi_lookup")
        self.assertIn("/geo/v2/poi/lookup?", poi)
        self.assertIn("location=116.41%2C39.92", poi)
        self.assertIn("type=scenic", poi)
        rng = self.url_for("geo_poi_range")
        self.assertIn("/geo/v2/poi/range?", rng)
        self.assertIn("radius=5", rng)          # 单位是公里
        self.assertIn("type=scenic", rng)

    def test_city_v7_endpoints(self) -> None:
        self.assertIn("/v7/weather/now?location=101280601", self.url_for("weather_city_now_v7"))
        self.assertIn("/v7/weather/3d?location=101280601", self.url_for("weather_city_daily_v7"))
        self.assertIn("/v7/weather/24h?location=101280601", self.url_for("weather_city_hourly_v7"))

    def test_city_v7_marked_deprecated(self) -> None:
        for key in ("weather_city_now_v7", "weather_city_daily_v7", "weather_city_hourly_v7"):
            self.assertTrue(core.ENDPOINTS_BY_KEY[key].deprecated, key)
        for key in ("weather_current", "geo_city_lookup", "geo_top_city", "geo_poi_lookup"):
            self.assertFalse(core.ENDPOINTS_BY_KEY[key].deprecated, key)

    def test_endpoint_table_covers_documented_apis(self) -> None:
        groups = {item.group for item in core.ENDPOINTS}
        self.assertEqual(groups, {"GeoAPI", "天气预报", "分钟预报", "空气质量", "预警",
                                  "天气指数", "时光机"})
        self.assertEqual(len(core.ENDPOINTS), 16)

    def test_missing_host_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            core.build_url("", core.ENDPOINTS[0], core.build_request_context(self.config))

    def test_host_normalisation_accepts_full_url(self) -> None:
        self.assertEqual(core.normalize_host("https://abc.qweatherapi.com/"), "abc.qweatherapi.com")
        self.assertEqual(core.normalize_host(" abc.qweatherapi.com "), "abc.qweatherapi.com")

    def test_all_endpoints_have_unique_keys_and_doc_urls(self) -> None:
        keys = [item.key for item in core.ENDPOINTS]
        self.assertEqual(len(keys), len(set(keys)))
        for item in core.ENDPOINTS:
            self.assertTrue(item.doc_url.startswith("https://dev.qweather.com/"), item.key)


class TestRendering(TempDataMixin):
    def test_links_text_covers_all_endpoints_and_warns_about_location_id(self) -> None:
        config = {
            "api_host": "abc.qweatherapi.com",
            "latitude": "22.53",
            "longitude": "113.94",
            "lang": "zh",
            "local_time": True,
            "location_name": "深圳",
            "location_id": "",
            "forecast_days": "3",
            "forecast_hours": "24",
            "indices_type": "0",
            "indices_days": "1d",
            "time_machine_date": (date.today() - timedelta(days=1)).strftime("%Y%m%d"),
        }
        auth = core.build_auth_record("jwt", token="a.b.c", lifetime=900)
        text = core.render_links_text(config, auth, include_curl=True, token_lifetime=900)

        for item in core.ENDPOINTS:
            self.assertIn(item.name, text)
        self.assertEqual(text.count("curl --compressed"), len(core.ENDPOINTS))
        self.assertIn("缺少 LocationID", text, "时光机缺 LocationID 时必须给出警告")
        self.assertIn("Authorization: Bearer a.b.c", text)

    def test_shell_script_is_executable_shaped(self) -> None:
        config = {
            "api_host": "abc.qweatherapi.com",
            "latitude": "22.53",
            "longitude": "113.94",
            "lang": "zh",
            "local_time": True,
            "time_machine_date": (date.today() - timedelta(days=1)).strftime("%Y%m%d"),
        }
        auth = core.build_auth_record("api_key", api_key="KEY123")
        script = core.render_shell_script(config, auth)
        self.assertTrue(script.startswith("#!/bin/sh"))
        self.assertIn("X-QW-Api-Key: KEY123", script)
        # 脚本里 curl 只定义一次（封装成 request 函数），每个接口调用一次
        self.assertEqual(script.count("curl --compressed"), 1)
        self.assertEqual(script.count('request "https://'), len(core.ENDPOINTS))

    def test_generate_keypair_survives_same_second_calls(self) -> None:
        first_private, _ = core.generate_keypair()
        second_private, _ = core.generate_keypair()
        self.assertNotEqual(first_private, second_private)
        self.assertTrue(first_private.is_file() and second_private.is_file())

    def test_auth_record_schema_roundtrip(self) -> None:
        record = core.build_auth_record("jwt", token="x.y.z", lifetime=900)
        self.assertEqual(record["header"], "Authorization")
        self.assertEqual(record["value"], "Bearer x.y.z")
        self.assertEqual(record["expires_in"], 900)
        self.assertIn("expires_at", record)
        core.save_auth(record)
        self.assertEqual(core.load_auth()["value"], "Bearer x.y.z")

        with self.assertRaises(ValueError):
            core.build_auth_record("api_key", api_key="")
        with self.assertRaises(ValueError):
            core.build_auth_record("unknown")


class TestAuthCompat(TempDataMixin):
    """旧版 GUI 只写 request_command，升级后必须仍能读出请求头。"""

    def write_auth(self, payload: dict) -> None:
        path = core.auth_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_migrates_legacy_api_key_command(self) -> None:
        self.write_auth(
            {
                "mode": "api_key",
                "request_command": 'curl --compressed -H "X-QW-Api-Key: KEY123" "https://h/x"',
            }
        )
        record = core.load_auth()
        self.assertEqual(record["header"], "X-QW-Api-Key")
        self.assertEqual(record["value"], "KEY123")
        self.assertEqual(core.auth_header_line(record), "X-QW-Api-Key: KEY123")

    def test_migrates_legacy_bearer_command(self) -> None:
        self.write_auth(
            {
                "mode": "jwt",
                "request_command": 'curl --compressed -H "Authorization: Bearer a.b.c" "https://h/x"',
            }
        )
        self.assertEqual(core.auth_header_line(core.load_auth()), "Authorization: Bearer a.b.c")

    def test_new_schema_is_untouched(self) -> None:
        record = core.build_auth_record("api_key", api_key="NEWKEY")
        core.save_auth(record)
        loaded = core.load_auth()
        self.assertEqual(loaded["value"], "NEWKEY")
        self.assertEqual(loaded["created_at"], record["created_at"])

    def test_unparsable_legacy_auth_is_silent(self) -> None:
        self.write_auth({"mode": "api_key", "request_command": "curl https://h/x"})
        self.assertEqual(core.auth_header_line(core.load_auth()), "")


class TestProjectLayout(unittest.TestCase):
    """目录约定：凭据目录生成在程序（exe/源码）所在目录，名为 data。"""

    def test_data_dir_name_is_data(self) -> None:
        self.assertEqual(core.DATA_DIR_NAME, "data")

    def test_source_layout_uses_source_dir(self) -> None:
        core_file = Path(core.__file__).resolve()
        self.assertEqual(core.program_dir(), core_file.parent)
        self.assertEqual(core.data_dir(), core.program_dir() / "data")

    def test_frozen_layout_puts_credentials_next_to_exe(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        bin_dir = Path(tmp.name) / "weather" / "bin"
        bin_dir.mkdir(parents=True)
        old_frozen = getattr(sys, "frozen", None)
        old_exe = sys.executable
        old_env = os.environ.pop(core.DATA_DIR_ENV, None)
        try:
            sys.frozen = True  # type: ignore[attr-defined]
            sys.executable = str(bin_dir / "QWeatherAuth.exe")
            # exe 在 bin/ 下时，凭据目录就是 bin/data（与 exe 同目录）
            self.assertEqual(core.program_dir(), bin_dir)
            self.assertEqual(core.data_dir(), bin_dir / "data")
        finally:
            if old_frozen is None:
                del sys.frozen  # type: ignore[attr-defined]
            else:
                sys.frozen = old_frozen  # type: ignore[attr-defined]
            sys.executable = old_exe
            if old_env is not None:
                os.environ[core.DATA_DIR_ENV] = old_env

    def test_env_override_wins(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old = os.environ.get(core.DATA_DIR_ENV)
        try:
            os.environ[core.DATA_DIR_ENV] = tmp.name
            self.assertEqual(core.data_dir(), Path(tmp.name))
        finally:
            if old is None:
                os.environ.pop(core.DATA_DIR_ENV, None)
            else:
                os.environ[core.DATA_DIR_ENV] = old


class TestCli(unittest.TestCase):
    def test_parser_wires_every_command(self) -> None:
        import qweather_auth

        parser = qweather_auth.build_parser()
        for argv in (
            ["keygen"],
            ["api-key", "KEY"],
            ["jwt", "KID"],
            ["links", "--host", "h", "--lat", "1", "--lon", "2"],
        ):
            args = parser.parse_args(argv)
            self.assertTrue(callable(args.func), argv)


class TestKeypairForFingerprint(unittest.TestCase):
    """多项目时本地有多把密钥：应按控制台的公钥指纹找到对应的那一把。"""

    def setUp(self) -> None:
        import os
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("QWEATHER_DATA_DIR")
        os.environ["QWEATHER_DATA_DIR"] = self._tmp.name

    def tearDown(self) -> None:
        import os

        if self._old is None:
            os.environ.pop("QWEATHER_DATA_DIR", None)
        else:
            os.environ["QWEATHER_DATA_DIR"] = self._old
        self._tmp.cleanup()

    def test_finds_the_matching_key_among_several(self) -> None:
        first_private, first_public = core.generate_keypair()
        first_prints = core.public_key_fingerprints(first_public.read_bytes())
        second_private, second_public = core.generate_keypair()   # 成为当前密钥
        second_prints = core.public_key_fingerprints(second_public.read_bytes())

        matched = core.keypair_for_fingerprint(first_prints["pem"])
        self.assertIsNotNone(matched, "应能在多把密钥里找到匹配的那把")
        self.assertEqual(matched[0].name, first_private.name)
        self.assertEqual(core.keypair_for_fingerprint(second_prints["pem"])[0].name,
                         second_private.name)
        self.assertIsNone(core.keypair_for_fingerprint("0" * 64))
        self.assertIsNone(core.keypair_for_fingerprint(""))

    def test_remember_and_restore_project_key(self) -> None:
        private_path, public_path = core.generate_keypair()
        core.remember_project_key("PROJ1", private_path)
        self.assertEqual(core.key_for_project("PROJ1"), private_path.name)
        self.assertEqual(core.key_for_project("PROJ2"), "")
        pair = core.keypair_by_name(core.key_for_project("PROJ1"))
        self.assertIsNotNone(pair)
        core.activate_keypair(*pair)
        self.assertEqual(core.active_keypair()[0].name, private_path.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
