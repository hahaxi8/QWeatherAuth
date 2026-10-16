#!/usr/bin/env python3
"""ConsoleSession：登录态复用、页内 fetch、凭据接口调用。"""

from __future__ import annotations

import base64
import json
import subprocess
import time
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

from .constants import *
from .constants import _WRITE_JS
from .errors import ConsoleError, PublicKeyInUseError, describe_failure, raise_for_failure
from .errors import ConsoleError
from .cdp import Cdp
from .browser import *
from .payloads import *

__all__ = ["ConsoleSession"]
class ConsoleSession:
    """打开浏览器 → 等用户登录 → 读取页面数据。"""

    def __init__(self, port: Optional[int] = None, headless: bool = False) -> None:
        self.port = port or free_port()
        self.headless = headless
        self.process: Optional[subprocess.Popen] = None
        self.cdp: Optional[Cdp] = None

    # -- 生命周期 ---------------------------------------------------------
    def start(self, url: str = CONSOLE_SETTING) -> None:
        browser = find_browser()
        profile = profile_dir()
        args = [
            str(browser),
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate,msEdgeSplitScreen",
        ]
        if self.headless:
            args.append("--headless=new")
        args.append(url)
        self.process = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # 立刻记录端口，避免后续只能靠"扫描进程"来找（不写的话丢了就找不回来）
        write_state(self.port, self.process.pid)

        deadline = time.time() + 40
        target: Dict[str, Any] = {}
        while time.time() < deadline:
            try:
                targets = http_get_json(f"http://127.0.0.1:{self.port}/json/list")
                pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
                if pages:
                    # 优先选择已经打开目标站点的标签页，否则用第一个
                    target = next(
                        (p for p in pages if "qweather" in str(p.get("url", "")).lower()),
                        pages[0],
                    )
                    break
            except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
                pass
            time.sleep(0.5)
        if not target:
            other = find_profile_browser_port()
            if other and other != self.port:
                raise ConsoleError(
                    f"已有一个本工具的浏览器在运行（调试端口 {other}），新窗口起不来调试端口。"
                    "请先关掉那个浏览器窗口，再点一次按钮。"
                )
            raise ConsoleError("浏览器调试端口没有就绪，可能被安全软件拦截")

        self.cdp = Cdp(target["webSocketDebuggerUrl"])
        self.cdp.send("Page.enable")
        self.cdp.send("Runtime.enable")
        self.cdp.send("Network.enable")
        # 命令行的地址可能开在别的标签页，这里显式导航，确保我们操作的是目标页面
        self.cdp.send("Page.navigate", {"url": url})
        time.sleep(2.0)
        write_state(self.port, self.process.pid if self.process else 0)

    @classmethod
    def attach_existing(cls, scan: bool = True) -> Optional["ConsoleSession"]:
        """只在"已经有可用的调试端口"时连接。

        不会启动浏览器，也不会等待登录——用于界面启动后静默获取控制台参数。
        """
        candidates: List[int] = []
        state_port = int(read_state().get("port") or 0)
        if state_port:
            candidates.append(state_port)
        devtools_port = devtools_port_from_profile()
        if devtools_port and devtools_port not in candidates:
            candidates.append(devtools_port)
        if scan:
            scanned = find_profile_browser_port()
            if scanned and scanned not in candidates:
                candidates.append(scanned)
        for port in candidates:
            if not port_alive(port):
                continue
            session = cls()
            try:
                session.attach(port)
            except ConsoleError:
                session.close()
                continue
            return session
        return None

    @classmethod
    def connect(cls) -> "ConsoleSession":
        """优先复用上次打开的浏览器（里面可能已经是登录态），否则新开一个。

        依次尝试：状态文件 → 浏览器自己写的 DevToolsActivePort → 新开浏览器。
        返回的会话如果还没登录，调用方负责等用户登录。
        """
        candidates: List[int] = []
        state_port = int(read_state().get("port") or 0)
        if state_port:
            candidates.append(state_port)
        for extra in (devtools_port_from_profile(), find_profile_browser_port()):
            if extra and extra not in candidates:
                candidates.append(extra)

        for port in candidates:
            if not port_alive(port):
                continue
            session = cls(port=port)
            try:
                session.attach(port)
                write_state(port, 0)
                return session
            except Exception:  # noqa: BLE001 - 这个端口不可用就试下一个/新开浏览器
                try:
                    if session.cdp:
                        session.cdp.close()
                except OSError:
                    pass
                continue

        session = cls()
        session.start(CONSOLE_SETTING)
        return session

    def attach(self, port: int, url_hint: str = "qweather") -> None:
        """连接到一个已经在运行、且开着调试端口的浏览器（复用已登录会话）。"""
        self.port = port
        try:
            targets = http_get_json(f"http://127.0.0.1:{port}/json/list")
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
            raise ConsoleError(f"调试端口 {port} 没有响应：{exc}") from exc
        pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        if not pages:
            raise ConsoleError("该调试端口下没有可用的页面")
        target = next(
            (p for p in pages if url_hint in str(p.get("url", "")).lower()), pages[0]
        )
        self.cdp = Cdp(target["webSocketDebuggerUrl"])
        self.cdp.send("Page.enable")
        self.cdp.send("Runtime.enable")
        self.cdp.send("Network.enable")

    def close(self) -> None:
        if self.cdp:
            try:
                self.cdp.close()
            except OSError:
                pass
            self.cdp = None
        if self.process and self.process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                **hidden_process_kwargs(),
            )
        self.process = None

    # -- 页面操作 ---------------------------------------------------------
    def current_url(self) -> str:
        assert self.cdp
        return str(self.cdp.evaluate("location.href", await_promise=False) or "")

    def body_text(self) -> str:
        assert self.cdp
        return str(self.cdp.evaluate("document.body ? document.body.innerText : ''",
                                     await_promise=False) or "")

    def html(self) -> str:
        assert self.cdp
        return str(self.cdp.evaluate(
            "document.documentElement ? document.documentElement.outerHTML : ''",
            await_promise=False) or "")

    def navigate(self, url: str, settle: float = 4.0) -> None:
        assert self.cdp
        self.cdp.send("Page.navigate", {"url": url})
        time.sleep(settle)

    def fetch_json(self, path: str, timeout: float = 45.0, retries: int = 1) -> Any:
        """在页面里用 fetch 调控制台自己的接口（自带登录态，无需自己处理 Cookie）。

        控制台后端偶尔很慢（实测单次可达约 10 秒），所以超时给得宽，并允许重试一次。
        """
        assert self.cdp
        expression = (
            "fetch(%s, {credentials: 'include', headers: {'Accept': 'application/json'}})"
            ".then(r => r.text().then(t => ({status: r.status, body: t})))"
            ".catch(e => ({status: -1, body: String(e)}))" % json.dumps(path)
        )
        attempt = 0
        while True:
            attempt += 1
            try:
                result = self.cdp.evaluate(expression, timeout=timeout)
                break
            except ConsoleError as exc:
                if attempt > retries or "超时" not in str(exc):
                    raise
        if not isinstance(result, dict):
            raise ConsoleError(f"接口 {path} 返回异常")
        status = int(result.get("status", -1))
        body = str(result.get("body", ""))
        if status != 200:
            raise ConsoleError(f"接口 {path} 返回 HTTP {status}：{body[:200]}")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise ConsoleError(f"接口 {path} 返回的不是 JSON：{body[:200]}") from None

    def fetch_api(self, path: str, timeout: float = 45.0) -> Any:
        payload = self.fetch_json(path, timeout=timeout)
        if not isinstance(payload, dict):
            raise ConsoleError(f"接口 {path} 结构异常")
        if str(payload.get("success", "")).lower() not in ("true", "1"):
            raise_for_failure("GET", path, payload, str(payload),
                              describe_console_code(payload.get("code")))
        return payload.get("data")

    def request(self, method: str, path: str, body: Optional[str] = None,
                content_type: str = "application/json", timeout: float = 60.0) -> Dict[str, Any]:
        """在页面内发起写请求：自带登录态，并按需附带 XSRF 头。

        实测控制台不强制 XSRF，但带上更稳妥（与前端 axios 行为一致）。
        """
        assert self.cdp
        expression = _WRITE_JS % (
            json.dumps(path),
            json.dumps(method.upper()),
            json.dumps(content_type),
            json.dumps(body or ""),
        )
        result = self.cdp.evaluate(expression, timeout=timeout)
        if not isinstance(result, dict):
            raise ConsoleError(f"{method} {path} 返回异常")
        status = int(result.get("status", -1))
        text = str(result.get("body", ""))
        if status != 200:
            raise ConsoleError(f"{method} {path} 返回 HTTP {status}：{text[:200]}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise ConsoleError(f"{method} {path} 返回的不是 JSON：{text[:200]}") from None
        if isinstance(payload, dict) and str(payload.get("success", "")).lower() not in ("true", "1"):
            raise_for_failure(method, path, payload, text,
                              describe_console_code(payload.get("code")))
        return payload

    def write_json(self, method: str, path: str, payload: Dict[str, Any],
                   timeout: float = 60.0) -> Dict[str, Any]:
        return self.request(method, path, json.dumps(payload, ensure_ascii=False),
                            "application/json", timeout)

    def credential_name_available(self, project: str, name: str) -> bool:
        """凭据名是否可用（控制台占用时返回非空）。"""
        data = self.fetch_api(
            API_APP_KEY_CHECK_NAME.format(project=project, name=urllib.parse.quote(name))
        )
        return not data

    def credential_detail(self, project: str, public_id: str) -> Dict[str, Any]:
        data = self.fetch_api(API_APP_KEY_ITEM.format(project=project, public_id=public_id))
        return data if isinstance(data, dict) else {}

    def create_jwt_credential(self, project: str, name: str, public_key_pem: str,
                              template: Optional[Dict[str, Any]] = None,
                              allow_console_data: bool = True) -> Dict[str, Any]:
        """用给定公钥创建 JWT 凭据，并（可选）打开"访问控制台数据"权限。

        控制台的创建接口不带控制台数据权限，所以创建成功后再用编辑接口补设一次。
        """
        payload = build_jwt_credential_payload(name, public_key_pem, template)
        result = self.write_json("PUT", API_APP_KEY_CREATE.format(project=project), payload)
        data = result.get("data")
        if not isinstance(data, dict) or not data.get("publicId"):
            raise ConsoleError(f"控制台没有返回凭据 ID：{str(result)[:200]}")
        public_id = str(data["publicId"])

        console_enabled = False
        if allow_console_data:
            try:
                detail = self.credential_detail(project, public_id)
                update = build_credential_update_payload(
                    detail, console_api_limit_value=DEFAULT_CONSOLE_API_LIMIT_VALUE
                )
                self.write_json(
                    "POST",
                    API_APP_KEY_UPDATE.format(project=project, public_id=public_id),
                    update,
                )
                console_enabled = True
            except ConsoleError:
                console_enabled = False  # 凭据已创建成功，权限补设失败不影响主流程
        created = dict(data)
        created["console_api_enabled"] = console_enabled
        return created

    def create_api_key_credential(self, project: str, name: str,
                                  template: Optional[Dict[str, Any]] = None,
                                  allow_console_data: bool = True) -> Dict[str, Any]:
        """新建 API KEY 凭据，并取回明文密钥。

        API KEY 不需要公钥，所以请求体里没有 algorithm/publicKey；
        创建响应不一定带明文密钥，拿不到就回读一次凭据详情。
        """
        payload = build_api_key_credential_payload(name, template)
        result = self.write_json("PUT", API_APP_KEY_CREATE.format(project=project), payload)
        data = result.get("data")
        if not isinstance(data, dict) or not data.get("publicId"):
            raise ConsoleError(f"控制台没有返回凭据 ID：{str(result)[:200]}")
        public_id = str(data["publicId"])

        detail: Dict[str, Any] = {}
        api_key = str(data.get("key") or data.get("secretKey") or "")
        try:
            detail = self.credential_detail(project, public_id)
            if not api_key:
                api_key = str(detail.get("key") or "")
        except ConsoleError:
            detail = {}

        console_enabled = False
        if allow_console_data:
            try:
                if not detail:
                    detail = self.credential_detail(project, public_id)
                update = build_credential_update_payload(
                    detail, console_api_limit_value=DEFAULT_CONSOLE_API_LIMIT_VALUE
                )
                self.write_json(
                    "POST",
                    API_APP_KEY_UPDATE.format(project=project, public_id=public_id),
                    update,
                )
                console_enabled = True
            except ConsoleError:
                console_enabled = False  # 凭据已创建成功，权限补设失败不影响主流程

        created = dict(data)
        created["key"] = api_key
        created["console_api_enabled"] = console_enabled
        return created

    def ensure_logged_in(self, timeout: float = 600.0, on_tick=None) -> None:
        """已登录就直接返回；否则把浏览器切到控制台并等用户登录。"""
        if self.is_logged_in():
            try:
                self.fetch_api(API_USER, timeout=45)
                return  # 会话仍然有效
            except ConsoleError:
                pass
        try:
            self.navigate(CONSOLE_HOME, settle=2.0)
        except ConsoleError:
            pass
        if not self.wait_for_login(timeout=timeout, on_tick=on_tick):
            raise ConsoleError("等待登录超时，请重新点击登录按钮")

    def is_logged_in(self) -> bool:
        url = self.current_url()
        if LOGIN_HOST in url:
            return False
        return "console.qweather.com" in url

    def wait_for_login(self, timeout: float = 600.0, on_tick=None) -> bool:
        """等用户在浏览器里完成登录（扫码/密码随他）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.is_logged_in():
                    text = self.body_text()
                    if "登录" not in text[:200]:
                        return True
            except ConsoleError:
                # 页面跳转或标签切换可能让连接失效，重连一次继续等
                try:
                    self._reconnect()
                except ConsoleError:
                    pass
            if on_tick:
                on_tick(deadline - time.time())
            time.sleep(2.0)
        return False

    def _reconnect(self) -> None:
        """重新连到当前打开的 qweather 页面。"""
        targets = http_get_json(f"http://127.0.0.1:{self.port}/json/list")
        pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        if not pages:
            raise ConsoleError("找不到可用的页面")
        target = next(
            (p for p in pages if "qweather" in str(p.get("url", "")).lower()), pages[0]
        )
        if self.cdp:
            try:
                self.cdp.close()
            except OSError:
                pass
        self.cdp = Cdp(target["webSocketDebuggerUrl"])
        self.cdp.send("Runtime.enable")
        self.cdp.send("Network.enable")

    # -- 网络响应采集 -----------------------------------------------------
    def collect_json_responses(self, wait: float = 3.0) -> List[Dict[str, Any]]:
        """把这一段时间内的 JSON 接口响应抓下来，用于分析数据结构。"""
        assert self.cdp
        self.cdp.drain_events(wait)
        found: List[Dict[str, Any]] = []
        for event in self.cdp.events:
            if event.get("method") != "Network.responseReceived":
                continue
            params = event.get("params", {})
            response = params.get("response", {})
            url = str(response.get("url", ""))
            mime = str(response.get("mimeType", ""))
            if "json" not in mime and "/api/" not in url:
                continue
            request_id = params.get("requestId")
            try:
                body = self.cdp.send("Network.getResponseBody", {"requestId": request_id})
            except ConsoleError:
                continue
            text = body.get("body", "")
            if body.get("base64Encoded"):
                try:
                    text = base64.b64decode(text).decode("utf-8", "replace")
                except (ValueError, OSError):
                    continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            found.append({"url": url, "status": response.get("status"), "json": parsed,
                          "text": text[:4000]})
        self.cdp.events = [
            event for event in self.cdp.events
            if event.get("method") != "Network.responseReceived"
        ]
        return found
