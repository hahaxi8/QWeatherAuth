#!/usr/bin/env python3
"""控制台数据提取的自检用例。

外层结构取自真实抓取结果（控制台 v2/rest 接口），字段含义已与控制台页面文案核对：
    /v2/rest/user      -> subDomain=API Host, uniqueCode=开发者 ID
    /v2/rest/app       -> uniqueCode=项目 ID
    /v2/rest/app/{code}-> keyList[type=3]=API KEY（带明文 key）
                          keyList[type=7]=JWT（publicId 即 kid，sha256 为公钥指纹）

运行（项目根目录）：
    python -m unittest discover tests
"""

from __future__ import annotations

import os
import socket
import struct
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import qweather_console as qconsole  # noqa: E402


class TestChooseProject(unittest.TestCase):
    def setUp(self) -> None:
        self.apps = [
            {"uniqueCode": "AAAAAAAAAA", "name": "测试项目"},
            {"uniqueCode": "38TNW4F93B", "name": "和风天气数据接口"},
        ]

    def test_default_is_first(self) -> None:
        self.assertEqual(qconsole.choose_project(self.apps)["uniqueCode"], "AAAAAAAAAA")

    def test_match_by_code(self) -> None:
        self.assertEqual(
            qconsole.choose_project(self.apps, "38tnw4f93b")["name"], "和风天气数据接口"
        )

    def test_match_by_name(self) -> None:
        self.assertEqual(
            qconsole.choose_project(self.apps, "和风")["uniqueCode"], "38TNW4F93B"
        )

    def test_empty_apps_raises(self) -> None:
        with self.assertRaises(qconsole.ConsoleError):
            qconsole.choose_project([])
        with self.assertRaises(qconsole.ConsoleError):
            qconsole.choose_project(None)


class TestExtractAccountData(unittest.TestCase):
    def setUp(self) -> None:
        self.user = {
            "id": 1377285496201216,
            "realName": "hades",
            "email": "s**@1**.com",
            "phone": "136****7692",
            "subDomain": "ku78m4c6nn.re.qweatherapi.com",
            "uniqueCode": "Q010A7B225",
        }
        self.apps = [
            {
                "id": 1377286037266432,
                "uniqueCode": "38TNW4F93B",
                "name": "和风天气数据接口",
                "totalKeys": 2,
            }
        ]
        self.detail = {
            "uniqueCode": "38TNW4F93B",
            "name": "和风天气数据接口",
            "totalKeys": 2,
            "keyList": [
                {"name": "api", "publicId": "TC5BUAGUXF", "type": 3,
                 "key": "0123456789abcdef0123456789abcdef"},
                {"name": "jwb", "publicId": "T7B82R288A", "type": 7,
                 "sha256": "a9f1c801a35d5f5c3c82500019a821b7990b8343c798dfb7503620809ca29d56"},
            ],
        }

    def extract(self):
        return qconsole.extract_account_data(self.user, self.apps, self.detail)

    def test_extracts_host_and_ids(self) -> None:
        data = self.extract()
        self.assertEqual(data["api_host"], "ku78m4c6nn.re.qweatherapi.com")
        self.assertEqual(data["developer_id"], "Q010A7B225")
        self.assertEqual(data["project_id"], "38TNW4F93B")
        self.assertEqual(data["project_name"], "和风天气数据接口")

    def test_extracts_api_key_and_jwt_credential(self) -> None:
        data = self.extract()
        self.assertEqual(data["api_key"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(data["api_key_id"], "TC5BUAGUXF")
        self.assertEqual(data["jwt_credential_id"], "T7B82R288A")
        self.assertEqual(
            data["jwt_public_sha256"],
            "a9f1c801a35d5f5c3c82500019a821b7990b8343c798dfb7503620809ca29d56",
        )

    def test_key_list_is_summarised(self) -> None:
        data = self.extract()
        types = {item["id"]: item["type"] for item in data["credentials"]}
        self.assertEqual(types, {"TC5BUAGUXF": 3, "T7B82R288A": 7})

    def test_jwt_only_project_has_no_api_key(self) -> None:
        self.detail["keyList"] = [item for item in self.detail["keyList"] if item["type"] == 7]
        data = self.extract()
        self.assertEqual(data["api_key"], "")
        self.assertEqual(data["jwt_credential_id"], "T7B82R288A")

    def test_api_key_only_project_has_no_jwt(self) -> None:
        self.detail["keyList"] = [item for item in self.detail["keyList"] if item["type"] == 3]
        data = self.extract()
        self.assertEqual(data["jwt_credential_id"], "")
        self.assertEqual(data["api_key_id"], "TC5BUAGUXF")

    def test_missing_host_raises_readable_error(self) -> None:
        self.user.pop("subDomain")
        with self.assertRaises(qconsole.ConsoleError):
            self.extract()

    def test_missing_developer_id_raises(self) -> None:
        self.user.pop("uniqueCode")
        with self.assertRaises(qconsole.ConsoleError):
            self.extract()

    def test_project_list_is_returned(self) -> None:
        data = self.extract()
        self.assertEqual(data["projects"], [{"id": "38TNW4F93B", "name": "和风天气数据接口"}])


class FakeSock:
    """喂给 WebSocket 客户端的假 socket：按块返回数据，耗尽后抛超时。"""

    def __init__(self, chunks: list) -> None:
        self.chunks = list(chunks)
        self.sent: list = []
        self.timeout = None

    def recv(self, _size: int) -> bytes:
        if not self.chunks:
            raise socket.timeout("timed out")
        return self.chunks.pop(0)

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def settimeout(self, value) -> None:
        self.timeout = value

    def close(self) -> None:
        pass


def ws_frame(payload: bytes, opcode: int = 0x1, fin: bool = True) -> bytes:
    """构造服务端→客户端的帧（不加掩码）。"""
    first = (0x80 if fin else 0x00) | opcode
    length = len(payload)
    if length < 126:
        header = bytes([first, length])
    elif length < 65536:
        header = bytes([first, 126]) + struct.pack(">H", length)
    else:
        header = bytes([first, 127]) + struct.pack(">Q", length)
    return header + payload


def make_client(chunks: list) -> qconsole.WebSocketClient:
    client = object.__new__(qconsole.WebSocketClient)
    client.timeout = 0.2
    client.sock = FakeSock(chunks)
    client._raw = b""
    return client


class TestWebSocketFraming(unittest.TestCase):
    """自写的 WebSocket 解析必须能容忍"读到一半超时"，否则整条流会错位。"""

    def test_parses_complete_frame(self) -> None:
        client = make_client([ws_frame(b'{"id":1}')])
        self.assertEqual(client.recv_message(timeout=0.5), '{"id":1}')

    def test_partial_frame_is_not_consumed(self) -> None:
        frame = ws_frame(b'{"hello":"world"}')
        client = make_client([frame[:6]])
        with self.assertRaises(qconsole.ConsoleError):
            client.recv_message(timeout=0.05)
        # 关键：超时后补齐剩余字节，仍应解析出完整消息（旧实现会在这里丢数据）
        client.sock.chunks.append(frame[6:])
        self.assertEqual(client.recv_message(timeout=0.5), '{"hello":"world"}')

    def test_two_frames_in_one_chunk(self) -> None:
        client = make_client([ws_frame(b"one") + ws_frame(b"two")])
        self.assertEqual(client.recv_message(timeout=0.5), "one")
        self.assertEqual(client.recv_message(timeout=0.5), "two")

    def test_ping_is_answered_and_skipped(self) -> None:
        client = make_client([ws_frame(b"ping-data", opcode=0x9) + ws_frame(b"payload")])
        self.assertEqual(client.recv_message(timeout=0.5), "payload")
        self.assertTrue(client.sock.sent, "收到 ping 必须回 pong")

    def test_close_frame_returns_none(self) -> None:
        client = make_client([ws_frame(b"", opcode=0x8)])
        self.assertIsNone(client.recv_message(timeout=0.5))

    def test_fragmented_text_is_joined(self) -> None:
        client = make_client([ws_frame(b"he", fin=False) + ws_frame(b"llo", fin=True)])
        self.assertEqual(client.recv_message(timeout=0.5), "hello")


class FakeWs:
    """假的 WebSocket：读取总是超时，用于验证错误提示。"""

    def __init__(self) -> None:
        self.sock = FakeSock([])
        self.closed = False

    def send_text(self, _text: str) -> None:
        pass

    def recv_message(self, timeout=None):  # noqa: ANN001
        raise qconsole.ConsoleError("读取调试消息超时")

    def close(self) -> None:
        self.closed = True


class TestCdpErrorMessages(unittest.TestCase):
    """超时必须给出可读、可行动的中文提示，不能把 socket 的 'timed out' 直接抛给用户。"""

    def make_cdp(self) -> qconsole.Cdp:
        cdp = object.__new__(qconsole.Cdp)
        cdp.ws = FakeWs()
        cdp._next_id = 0
        cdp.events = []
        return cdp

    def test_timeout_message_names_the_step(self) -> None:
        cdp = self.make_cdp()
        with self.assertRaises(qconsole.ConsoleError) as ctx:
            cdp.send("Runtime.evaluate", {}, timeout=1)
        message = str(ctx.exception)
        self.assertIn("超时", message)
        self.assertIn("Runtime.evaluate", message)
        self.assertNotEqual(message.strip(), "timed out")

    def test_connection_error_is_wrapped(self) -> None:
        with self.assertRaises(qconsole.ConsoleError) as ctx:
            qconsole.WebSocketClient("ws://127.0.0.1:1/devtools/page/x", timeout=1)
        self.assertIn("调试端口", str(ctx.exception))


class TestCredentialCreation(unittest.TestCase):
    """新建 JWT 凭据：命名规则与请求体必须与控制台前端一致。"""

    def test_default_name_is_prefix_plus_timestamp(self) -> None:
        moment = datetime(2026, 10, 15, 17, 35, 0)
        self.assertEqual(
            qconsole.default_credential_name("jwb", now=moment), "jwb20261015173500"
        )
        self.assertEqual(
            qconsole.default_credential_name("abc", now=moment), "abc20261015173500"
        )

    def test_payload_matches_console_frontend(self) -> None:
        pem = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----"
        payload = qconsole.build_jwt_credential_payload("jwb20261015173500", pem)
        self.assertEqual(payload["name"], "jwb20261015173500")
        self.assertEqual(payload["type"], qconsole.KEY_TYPE_JWT)
        self.assertEqual(payload["algorithm"], "2")  # Ed25519
        self.assertIn("BEGIN PUBLIC KEY", payload["publicKey"])
        self.assertIn("apiLimit", payload)
        self.assertIn("apiLimitValue", payload)

    def test_payload_defaults_to_basic_api_set(self) -> None:
        """没有可沿用的凭据时，必须给出默认 API 组合，绝不能创建出 0 个 API 的凭据。"""
        pem = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----"
        payload = qconsole.build_jwt_credential_payload("jwb1", pem)
        self.assertEqual(payload["apiLimitValue"], qconsole.DEFAULT_API_LIMIT_VALUE)
        self.assertNotEqual(payload["apiLimitValue"].strip(), "")
        self.assertGreaterEqual(len(payload["apiLimitValue"].split(",")), 1)

    def test_payload_reuses_existing_limits(self) -> None:
        pem = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----"
        template = {"apiLimit": 1, "apiLimitValue": "2,3,6,7,1,4,5,8", "type": 7}
        payload = qconsole.build_jwt_credential_payload("jwb1", pem, template)
        self.assertEqual(payload["apiLimitValue"], "2,3,6,7,1,4,5,8")

    def test_payload_rejects_bad_input(self) -> None:
        with self.assertRaises(qconsole.ConsoleError):
            qconsole.build_jwt_credential_payload("", "-----BEGIN PUBLIC KEY-----")
        with self.assertRaises(qconsole.ConsoleError):
            qconsole.build_jwt_credential_payload("jwb1", "not-a-pem")

    def test_console_error_codes_are_explained(self) -> None:
        self.assertIn("已存在", qconsole.describe_console_code("103"))
        # 未知错误码也要把码带出来，便于排查
        self.assertIn("999", qconsole.describe_console_code("999"))
        self.assertEqual(qconsole.describe_console_code(""), "")


    def test_api_code_tables(self) -> None:
        # 免费套餐 = 前 8 个 API；12/13 = 财务汇总 / 请求量统计
        self.assertEqual(qconsole.FREE_API_CODES, tuple("12345678"))
        self.assertEqual(qconsole.DEFAULT_API_LIMIT_VALUE, "1,2,3,4,5,6,7,8")
        self.assertEqual(qconsole.DEFAULT_CONSOLE_API_LIMIT_VALUE, "12,13")

    def test_api_names_are_translated(self) -> None:
        names = qconsole.api_names("2,7,12")
        self.assertEqual(names, ["GeoAPI", "时光机", "财务汇总"])
        self.assertEqual(len(qconsole.api_names(qconsole.DEFAULT_API_LIMIT_VALUE)), 8)

    def test_update_payload_enables_console_data_without_touching_apis(self) -> None:
        detail = {
            "type": 7, "requestLimit": 0, "requestLimitValue": "",
            "apiLimit": 1, "apiLimitValue": "2,3,6,7,1,4,5,8", "consoleApiLimitValue": "",
        }
        payload = qconsole.build_credential_update_payload(
            detail, console_api_limit_value=qconsole.DEFAULT_CONSOLE_API_LIMIT_VALUE
        )
        self.assertEqual(payload["consoleApiLimitValue"], "12,13")
        self.assertEqual(payload["apiLimitValue"], "2,3,6,7,1,4,5,8")  # 原有 API 选择不动
        self.assertEqual(payload["type"], 7)
        self.assertEqual(
            sorted(payload),
            ["apiLimit", "apiLimitValue", "consoleApiLimitValue",
             "requestLimit", "requestLimitValue", "type"],
        )

    def test_update_payload_keeps_values_when_not_overridden(self) -> None:
        detail = {"type": 3, "apiLimit": 1, "apiLimitValue": "1,2",
                  "consoleApiLimitValue": "13", "requestLimit": 1}
        payload = qconsole.build_credential_update_payload(detail)
        self.assertEqual(payload["apiLimitValue"], "1,2")
        self.assertEqual(payload["consoleApiLimitValue"], "13")


    def test_default_name_prefix_depends_on_credential_type(self) -> None:
        """JWT 凭据用 jwb 前缀，API KEY 凭据用 api 前缀。"""
        moment = datetime(2026, 10, 15, 17, 35, 0)
        self.assertEqual(qconsole.CREDENTIAL_NAME_PREFIX, "jwb")
        self.assertEqual(qconsole.CREDENTIAL_NAME_PREFIX_API, "api")
        self.assertEqual(
            qconsole.default_credential_name(now=moment, credential_type=qconsole.KEY_TYPE_JWT),
            "jwb20261015173500",
        )
        self.assertEqual(
            qconsole.default_credential_name(now=moment, credential_type=qconsole.KEY_TYPE_API_KEY),
            "api20261015173500",
        )
        # 不传类型时默认按 JWT
        self.assertEqual(qconsole.default_credential_name(now=moment), "jwb20261015173500")
        # 显式指定前缀时以指定值为准
        self.assertEqual(qconsole.default_credential_name("x", now=moment), "x20261015173500")

    def test_merge_console_codes_keeps_existing(self) -> None:
        self.assertEqual(qconsole.merge_console_codes(""), "12,13")
        self.assertEqual(qconsole.merge_console_codes("13"), "13,12")
        # 已有权限不能被删掉
        self.assertEqual(qconsole.merge_console_codes("12,13"), "12,13")
        self.assertEqual(qconsole.merge_console_codes("12,13,14@PROJ1"), "12,13,14@PROJ1")

    def test_find_matching_credential_compares_sha256(self) -> None:
        """本地公钥指纹与控制台记录的 sha256 一致时，必须判定为"已有"。"""

        class FakeSession:
            def fetch_api(self, path, timeout=45.0):
                if path == qconsole.API_APP_DETAIL.format(code="P1"):
                    return {"keyList": [
                        {"type": qconsole.KEY_TYPE_JWT, "publicId": "OTHER1"},
                        {"type": qconsole.KEY_TYPE_JWT, "publicId": "MATCH1"},
                        {"type": qconsole.KEY_TYPE_API_KEY, "publicId": "APIKEY1"},
                    ]}
                raise AssertionError(path)

            def credential_detail(self, project, public_id):
                if public_id == "MATCH1":
                    return {"name": "api20261015173500", "publicId": "MATCH1",
                            "sha256": "abc123", "apiLimitValue": "1,2,3",
                            "consoleApiLimitValue": "12,13"}
                return {"name": "other", "publicId": public_id, "sha256": "zzz"}

        found = qconsole.find_matching_jwt_credential(FakeSession(), "P1", {"abc123"})
        self.assertIsNotNone(found)
        self.assertEqual(found["public_id"], "MATCH1")
        self.assertEqual(found["name"], "api20261015173500")

    def test_find_matching_credential_returns_none_when_absent(self) -> None:
        class FakeSession:
            def fetch_api(self, path, timeout=45.0):
                return {"keyList": [{"type": qconsole.KEY_TYPE_JWT, "publicId": "X1"}]}

            def credential_detail(self, project, public_id):
                return {"name": "x", "publicId": public_id, "sha256": "nope"}

        self.assertIsNone(qconsole.find_matching_jwt_credential(FakeSession(), "P1", {"abc"}))
        # 没有指纹时不应误判为"已有"
        self.assertIsNone(qconsole.find_matching_jwt_credential(FakeSession(), "P1", set()))


class TestProjectHelpers(unittest.TestCase):
    """项目/凭据列表与创建请求体。"""

    def test_build_project_payload_matches_console(self) -> None:
        payload = qconsole.build_project_payload("天气数据接口")
        self.assertEqual(payload, {"appName": "天气数据接口", "appType": 1})
        with self.assertRaises(qconsole.ConsoleError):
            qconsole.build_project_payload("   ")

    def test_normalize_project(self) -> None:
        item = qconsole.normalize_project({"uniqueCode": "P1", "name": "项目A", "totalKeys": 3})
        self.assertEqual(item, {"id": "P1", "name": "项目A", "key_count": 3})
        self.assertEqual(qconsole.normalize_project(None)["id"], "")

    def test_credential_type_labels(self) -> None:
        self.assertEqual(qconsole.credential_type_label(qconsole.KEY_TYPE_JWT), "JWT")
        self.assertEqual(qconsole.credential_type_label(qconsole.KEY_TYPE_API_KEY), "API KEY")
        self.assertIn("9", qconsole.credential_type_label(9))

    def test_list_projects_and_credentials(self) -> None:
        class FakeSession:
            def fetch_api(self, path, timeout=45.0):
                if path == qconsole.API_APPS:
                    return [{"uniqueCode": "P1", "name": "项目A", "totalKeys": 1}]
                if path == qconsole.API_APP_DETAIL.format(code="P1"):
                    return {"keyList": [
                        {"name": "api", "publicId": "K1", "type": qconsole.KEY_TYPE_API_KEY},
                        {"name": "jwb", "publicId": "K2", "type": qconsole.KEY_TYPE_JWT,
                         "sha256": "deadbeef"},
                    ]}
                raise AssertionError(path)

        session = FakeSession()
        projects = qconsole.list_projects(session)
        self.assertEqual(projects, [{"id": "P1", "name": "项目A", "key_count": 1}])
        credentials = qconsole.list_credentials(session, "P1")
        self.assertEqual([c["type_label"] for c in credentials], ["API KEY", "JWT"])
        self.assertEqual(credentials[1]["sha256"], "deadbeef")


class TestSilentAttach(unittest.TestCase):
    """启动后静默读取控制台参数时用的 attach_existing。"""

    def test_returns_none_and_never_launches_browser(self) -> None:
        # 要替换“会话实际查找的命名空间”，而不是包的再导出
        from qweather_console import session as session_module

        original = (session_module.read_state, session_module.devtools_port_from_profile,
                    session_module.find_profile_browser_port)
        session_module.read_state = lambda: {"port": 1}        # 1 端口不会有调试服务
        session_module.devtools_port_from_profile = lambda: 0
        session_module.find_profile_browser_port = lambda timeout=12.0: 0
        try:
            self.assertIsNone(qconsole.ConsoleSession.attach_existing(scan=True))
            self.assertIsNone(qconsole.ConsoleSession.attach_existing(scan=False))
        finally:
            (session_module.read_state, session_module.devtools_port_from_profile,
             session_module.find_profile_browser_port) = original

    def test_port_alive_is_false_for_closed_port(self) -> None:
        self.assertFalse(qconsole.port_alive(1, timeout=0.5))


class TestApiKeyCredential(unittest.TestCase):
    """API KEY 凭据的自动创建（JWT 之外的第二条路径）。"""

    def test_payload_carries_no_public_key_fields(self) -> None:
        payload = qconsole.build_api_key_credential_payload(
            "api20261015190000", {"apiLimitValue": "1,2,3"}
        )
        self.assertEqual(payload["name"], "api20261015190000")
        self.assertEqual(payload["type"], qconsole.KEY_TYPE_API_KEY)
        self.assertEqual(payload["apiLimitValue"], "1,2,3")
        # 控制台前端只在 JWT 时才补 algorithm / publicKey
        self.assertNotIn("publicKey", payload)
        self.assertNotIn("algorithm", payload)
        with self.assertRaises(qconsole.ConsoleError):
            qconsole.build_api_key_credential_payload("   ")

    def test_create_credential_reads_plain_key_and_enables_console_data(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.calls = []

            def write_json(self, method, path, payload, timeout=60.0):
                self.calls.append((method, path, dict(payload)))
                if method == "PUT":
                    return {"success": True,
                            "data": {"publicId": "NEWAPIKEY", "name": payload["name"]}}
                return {"success": True}

            def credential_detail(self, project, public_id):
                return {"name": "api20261015190000", "publicId": public_id, "key": "secretkey123",
                        "apiLimit": "0", "apiLimitValue": "1,2", "consoleApiLimitValue": ""}

        session = FakeSession()
        created = qconsole.ConsoleSession.create_api_key_credential(
            session, "PROJ1", "api20261015190000"
        )
        self.assertEqual(created["publicId"], "NEWAPIKEY")
        self.assertEqual(created["key"], "secretkey123")
        self.assertTrue(created["console_api_enabled"])
        self.assertEqual([call[0] for call in session.calls], ["PUT", "POST"])
        self.assertNotIn("publicKey", session.calls[0][2])
        self.assertIn("12,13", str(session.calls[1][2].get("consoleApiLimitValue")))

    def test_plain_key_falls_back_to_detail(self) -> None:
        class FakeSession:
            def write_json(self, method, path, payload, timeout=60.0):
                if method == "PUT":
                    return {"success": True, "data": {"publicId": "NEW2", "name": payload["name"]}}
                return {"success": True}

            def credential_detail(self, project, public_id):
                return {"key": "fromdetail", "consoleApiLimitValue": "12,13"}

        created = qconsole.ConsoleSession.create_api_key_credential(
            FakeSession(), "PROJ1", "api20261015190001"
        )
        self.assertEqual(created["key"], "fromdetail")


class TestHiddenProcess(unittest.TestCase):
    """调用 PowerShell 等辅助命令时必须隐藏窗口。"""

    def test_kwargs_hide_window_on_windows(self) -> None:
        kwargs = qconsole.hidden_process_kwargs()
        if os.name != "nt":
            self.assertEqual(kwargs, {})
            return
        self.assertIn("creationflags", kwargs)
        self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)
        startupinfo = kwargs["startupinfo"]
        self.assertTrue(startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(startupinfo.wShowWindow, subprocess.SW_HIDE)

    def test_process_scan_passes_hidden_kwargs(self) -> None:
        """进程扫描用的 PowerShell 调用必须带上隐藏窗口参数。"""
        if os.name != "nt":
            self.skipTest("只有 Windows 才会调用 PowerShell 扫描进程")
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            raise OSError("stop here")

        original = qconsole.subprocess.run
        qconsole.subprocess.run = fake_run
        try:
            qconsole.find_profile_browser_port(timeout=1.0)
        finally:
            qconsole.subprocess.run = original
        self.assertIn("powershell", captured["args"][0].lower())
        self.assertIn("creationflags", captured["kwargs"])
        self.assertTrue(captured["kwargs"]["creationflags"] & subprocess.CREATE_NO_WINDOW)


class TestAccountDataWithoutProject(unittest.TestCase):
    """账号下还没有项目时，抓取不应报错，而是把账号信息带回去。"""

    USER = {"subDomain": "abcxyz.qweatherapi.com", "uniqueCode": "QTEST12345",
            "realName": "tester", "email": "t@example.com", "phone": ""}

    def test_extract_keeps_account_without_project(self) -> None:
        data = qconsole.extract_account_data(self.USER, [], {})
        self.assertEqual(data["api_host"], "abcxyz.qweatherapi.com")
        self.assertEqual(data["developer_id"], "QTEST12345")
        self.assertEqual(data["project_id"], "")
        self.assertEqual(data["projects"], [])
        self.assertEqual(data["api_key"], "")

    def test_collect_skips_detail_when_no_project(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.paths = []

            def fetch_api(self, path, timeout=45.0):
                self.paths.append(path)
                if path == qconsole.API_USER:
                    return TestAccountDataWithoutProject.USER
                if path == qconsole.API_APPS:
                    return []
                raise AssertionError(f"没有项目时不应再请求：{path}")

        session = FakeSession()
        data = qconsole.collect_account_data(session)
        self.assertEqual(data["projects"], [])
        self.assertEqual(session.paths, [qconsole.API_USER, qconsole.API_APPS])

    def test_choose_project_still_raises_for_library_callers(self) -> None:
        with self.assertRaises(qconsole.ConsoleError):
            qconsole.choose_project([])


class TestProvisionCredentials(unittest.TestCase):
    """一键生成：把 JWT 与 API KEY 凭据一次备齐，已有的复用。"""

    PUBLIC_PEM = "-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----"

    def _run(self, keys):
        writes: list = []

        class FakeSession:
            cdp = None

            def ensure_logged_in(self, timeout=600.0, on_tick=None):
                return None

            def fetch_api(self, path, timeout=45.0):
                if path == qconsole.API_APPS:
                    return [{"uniqueCode": "P1", "name": "天气数据接口"}]
                if path == qconsole.API_APP_DETAIL.format(code="P1"):
                    return {"keyList": keys}
                raise AssertionError(f"未预期的接口：{path}")

            def credential_detail(self, project, public_id):
                for item in keys:
                    if item["publicId"] == public_id:
                        return dict(item, apiLimit="0", apiLimitValue="1,2",
                                    consoleApiLimitValue="12,13")
                return {}

            def credential_name_available(self, project, name):
                return True

            def write_json(self, method, path, payload, timeout=60.0):
                writes.append((method, path, dict(payload)))
                return {"success": True, "data": {"publicId": "NEW", "name": payload.get("name", "")}}

            def create_jwt_credential(self, project, name, pem, template=None,
                                      allow_console_data=True):
                writes.append(("PUT", qconsole.API_APP_KEY_CREATE.format(project=project),
                               qconsole.build_jwt_credential_payload(name, pem, template)))
                return {"name": name, "publicId": "NEWJWT", "console_api_enabled": True}

            def create_api_key_credential(self, project, name, template=None,
                                          allow_console_data=True):
                writes.append(("PUT", qconsole.API_APP_KEY_CREATE.format(project=project),
                               qconsole.build_api_key_credential_payload(name, template)))
                return {"name": name, "publicId": "NEWAPI", "key": "brandnew456",
                        "console_api_enabled": True}

            def close(self):
                pass

        original = qconsole.ConsoleSession.connect
        qconsole.ConsoleSession.connect = classmethod(lambda cls: FakeSession())
        try:
            data = qconsole.provision_credentials(
                project_hint="P1", public_key_pem=self.PUBLIC_PEM, fingerprints={"MATCH"}
            )
        finally:
            qconsole.ConsoleSession.connect = original
        return data, writes

    def test_creates_both_when_project_is_empty(self) -> None:
        data, writes = self._run([])
        self.assertFalse(data["jwt"]["reused"])
        self.assertFalse(data["api_key"]["reused"])
        self.assertEqual(data["jwt"]["public_id"], "NEWJWT")
        self.assertEqual(data["api_key"]["api_key"], "brandnew456")
        self.assertEqual(len(writes), 2)
        # JWT 请求体带公钥，API KEY 请求体不带
        self.assertIn("publicKey", writes[0][2])
        self.assertNotIn("publicKey", writes[1][2])
        self.assertTrue(writes[0][2]["name"].startswith("jwb"))
        self.assertTrue(writes[1][2]["name"].startswith("api"))

    def test_reuses_existing_and_creates_nothing(self) -> None:
        keys = [
            {"name": "jwb20261015191705", "publicId": "KJWT", "type": qconsole.KEY_TYPE_JWT,
             "sha256": "MATCH"},
            {"name": "api20261015191649", "publicId": "KAPI", "type": qconsole.KEY_TYPE_API_KEY,
             "key": "existing999"},
        ]
        data, writes = self._run(keys)
        self.assertTrue(data["jwt"]["reused"])
        self.assertEqual(data["jwt"]["public_id"], "KJWT")
        self.assertTrue(data["api_key"]["reused"])
        self.assertEqual(data["api_key"]["api_key"], "existing999")
        self.assertEqual(writes, [], "已有可用的凭据时不应再写控制台")


    def test_api_key_prefix_is_not_taken_from_jwt_prefix(self) -> None:
        """传入 JWT 前缀时，API KEY 凭据仍必须用 api 前缀。"""
        writes: list = []

        class FakeSession:
            cdp = None

            def ensure_logged_in(self, timeout=600.0, on_tick=None):
                return None

            def fetch_api(self, path, timeout=45.0):
                if path == qconsole.API_APPS:
                    return [{"uniqueCode": "P1", "name": "天气数据接口2"}]
                if path == qconsole.API_APP_DETAIL.format(code="P1"):
                    return {"keyList": []}
                raise AssertionError(path)

            def credential_detail(self, project, public_id):
                return {}

            def credential_name_available(self, project, name):
                return True

            def write_json(self, method, path, payload, timeout=60.0):
                writes.append(dict(payload))
                return {"success": True, "data": {"publicId": "NEW", "name": payload["name"]}}

            def create_jwt_credential(self, project, name, pem, template=None,
                                      allow_console_data=True):
                writes.append({"name": name, "publicKey": pem})
                return {"name": name, "publicId": "NEWJWT", "console_api_enabled": True}

            def create_api_key_credential(self, project, name, template=None,
                                          allow_console_data=True):
                writes.append({"name": name})
                return {"name": name, "publicId": "NEWAPI", "key": "k12345678",
                        "console_api_enabled": True}

            def close(self):
                pass

        original = qconsole.ConsoleSession.connect
        qconsole.ConsoleSession.connect = classmethod(lambda cls: FakeSession())
        try:
            qconsole.provision_credentials(
                project_hint="P1", name_prefix="jwb", public_key_pem=self.PUBLIC_PEM,
                fingerprints={"abc"},
            )
        finally:
            qconsole.ConsoleSession.connect = original

        names = [item["name"] for item in writes]
        self.assertEqual(len(names), 2, names)
        self.assertTrue(names[0].startswith("jwb"), names)
        self.assertTrue(names[1].startswith("api"), f"API KEY 凭据名字不对：{names}")


class TestPublicKeyAlreadyUsed(unittest.TestCase):
    """同一个公钥在控制台只能注册一次：收到 code=122 时应换新密钥重试。"""

    PUBLIC_PEM = "-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----"

    def _session_factory(self, calls):
        class FakeSession:
            cdp = None

            def ensure_logged_in(self, timeout=600.0, on_tick=None):
                return None

            def fetch_api(self, path, timeout=45.0):
                if path == qconsole.API_APPS:
                    return [{"uniqueCode": "P2", "name": "天气数据接口2"}]
                if path == qconsole.API_APP_DETAIL.format(code="P2"):
                    return {"keyList": []}
                raise AssertionError(path)

            def credential_detail(self, project, public_id):
                return {}

            def credential_name_available(self, project, name):
                return True

            def create_jwt_credential(self, project, name, pem, template=None,
                                      allow_console_data=True):
                calls.append(pem)
                if len(calls) == 1:
                    raise qconsole.PublicKeyInUseError(
                        "PUT /app/key/app/P2 被控制台拒绝（code=122）：公钥已存在", "122")
                return {"name": name, "publicId": "NEWJWT2", "console_api_enabled": True}

            def create_api_key_credential(self, project, name, template=None,
                                          allow_console_data=True):
                return {"name": name, "publicId": "NEWAPI2", "key": "k2",
                        "console_api_enabled": True}

            def close(self):
                pass

        return FakeSession()

    def test_retries_once_with_a_fresh_key(self) -> None:
        calls: list = []
        provider_calls: list = []
        original = qconsole.ConsoleSession.connect
        qconsole.ConsoleSession.connect = classmethod(lambda cls: self._session_factory(calls))
        try:
            data = qconsole.provision_credentials(
                project_hint="P2",
                public_key_pem=self.PUBLIC_PEM,
                fingerprints={"first"},
                key_provider=lambda: (provider_calls.append(1) or
                                      ("-----BEGIN PUBLIC KEY-----\nsecond\n-----END PUBLIC KEY-----",
                                       {"second"})),
            )
        finally:
            qconsole.ConsoleSession.connect = original

        self.assertEqual(len(calls), 2, f"应重试一次：{calls}")
        self.assertIn("second", calls[1], "重试必须换成新的公钥")
        self.assertEqual(provider_calls, [1], "应通过 key_provider 取一次新密钥")
        self.assertEqual(data["jwt"]["public_id"], "NEWJWT2")

    def test_without_provider_the_error_is_raised(self) -> None:
        calls: list = []
        original = qconsole.ConsoleSession.connect
        qconsole.ConsoleSession.connect = classmethod(lambda cls: self._session_factory(calls))
        try:
            with self.assertRaises(qconsole.PublicKeyInUseError):
                qconsole.provision_credentials(
                    project_hint="P2", public_key_pem=self.PUBLIC_PEM, fingerprints={"first"}
                )
        finally:
            qconsole.ConsoleSession.connect = original
        self.assertEqual(len(calls), 1, "没有 key_provider 时不应重试")


if __name__ == "__main__":
    unittest.main(verbosity=2)
