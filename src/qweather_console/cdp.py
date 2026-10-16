#!/usr/bin/env python3
"""CDP 客户端：WebSocket 帧收发与 Runtime.evaluate。"""

from __future__ import annotations

import base64
import json
import random
import socket
import struct
import time
from typing import Any, Dict, List, Optional

from .errors import ConsoleError

__all__ = ["WebSocketClient", "Cdp"]
class WebSocketClient:
    OPCODE_TEXT = 0x1
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        if not url.startswith("ws://"):
            raise ConsoleError(f"只支持 ws:// 调试地址：{url}")
        rest = url[len("ws://"):]
        host_port, _, path = rest.partition("/")
        host, _, port_text = host_port.partition(":")
        port = int(port_text or 80)
        self.timeout = timeout
        try:
            self.sock = socket.create_connection((host, port), timeout=timeout)
        except (socket.timeout, TimeoutError) as exc:
            raise ConsoleError(f"连接浏览器调试端口 {host}:{port} 超时") from exc
        except OSError as exc:
            raise ConsoleError(f"无法连接浏览器调试端口 {host}:{port}：{exc}") from exc
        self.sock.settimeout(timeout)
        key = base64.b64encode(bytes(random.getrandbits(8) for _ in range(16))).decode()
        request = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        header = b""
        try:
            while b"\r\n\r\n" not in header:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConsoleError("调试端口在握手阶段关闭了连接")
                header += chunk
        except (socket.timeout, TimeoutError) as exc:
            raise ConsoleError("浏览器调试端口握手超时，可能被安全软件拦截") from exc
        except OSError as exc:
            raise ConsoleError(f"浏览器调试端口握手失败：{exc}") from exc
        status_line = header.split(b"\r\n", 1)[0].decode("latin-1")
        if "101" not in status_line:
            raise ConsoleError(f"WebSocket 握手失败：{status_line}")
        # 握手响应后面可能已经跟了帧数据，全部进缓冲区
        self._raw = header.split(b"\r\n\r\n", 1)[1]

    # -- 底层收发 ---------------------------------------------------------
    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = bytes(random.getrandbits(8) for _ in range(4))
        length = len(payload)
        header = bytes([0x80 | opcode])
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _pump(self) -> None:
        """把 socket 上可用的字节追加进缓冲区（超时不算错误）。"""
        try:
            chunk = self.sock.recv(65536)
        except socket.timeout:
            return
        if not chunk:
            raise ConsoleError("浏览器调试连接已断开")
        self._raw += chunk

    def _try_parse(self):
        """尝试从缓冲区解析出一条完整帧；数据不足返回 None（不消费任何字节）。"""
        buffer = self._raw
        if len(buffer) < 2:
            return None
        first, second = buffer[0], buffer[1]
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        offset = 2
        if length == 126:
            if len(buffer) < 4:
                return None
            length = struct.unpack(">H", buffer[2:4])[0]
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                return None
            length = struct.unpack(">Q", buffer[2:10])[0]
            offset = 10
        mask_key = b""
        if masked:
            if len(buffer) < offset + 4:
                return None
            mask_key = buffer[offset:offset + 4]
            offset += 4
        if len(buffer) < offset + length:
            return None
        payload = buffer[offset:offset + length]
        self._raw = buffer[offset + length:]
        if masked:
            payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
        return fin, opcode, payload

    def send_text(self, text: str) -> None:
        self._send_frame(self.OPCODE_TEXT, text.encode("utf-8"))

    def recv_message(self, timeout: Optional[float] = None) -> Optional[str]:
        """读取一条完整文本消息；控制帧自动处理，连接关闭返回 None。

        解析基于缓冲区，读取超时不会丢掉已收到的半帧数据——
        否则超时一次就会让整条 WebSocket 流错位。
        """
        deadline = time.time() + (self.timeout if timeout is None else timeout)
        fragments: List[bytes] = []
        while True:
            parsed = self._try_parse()
            if parsed is None:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise ConsoleError("读取调试消息超时")
                self.sock.settimeout(min(remaining, 5.0))
                self._pump()
                continue
            fin, opcode, payload = parsed
            if opcode == self.OPCODE_CLOSE:
                return None
            if opcode == self.OPCODE_PING:
                self._send_frame(self.OPCODE_PONG, payload)
                continue
            if opcode == self.OPCODE_PONG:
                continue
            fragments.append(payload)
            if fin:
                return b"".join(fragments).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self._send_frame(self.OPCODE_CLOSE, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class Cdp:
    def __init__(self, ws_url: str, timeout: float = 30.0) -> None:
        self.ws = WebSocketClient(ws_url, timeout=timeout)
        self._next_id = 0
        self.events: List[Dict[str, Any]] = []

    def send(self, method: str, params: Optional[Dict[str, Any]] = None,
             timeout: float = 30.0) -> Dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        try:
            self.ws.send_text(json.dumps(
                {"id": message_id, "method": method, "params": params or {}}, ensure_ascii=False
            ))
        except OSError as exc:
            raise ConsoleError(f"向浏览器发送 {method} 失败：{exc}") from exc

        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise ConsoleError(
                    f"等待浏览器响应 {method} 超时（{timeout:.0f} 秒无响应）："
                    "浏览器可能已关闭、页面被挂起或控制台接口响应过慢，请重试"
                )
            try:
                raw = self.ws.recv_message(timeout=remaining)
            except ConsoleError as exc:
                text = str(exc)
                # 带上步骤名，便于定位（否则只看到“读取调试消息超时”不知道卡在哪）
                raise ConsoleError(text if method in text else f"{method}：{text}") from exc
            except (socket.timeout, TimeoutError) as exc:
                raise ConsoleError(
                    f"等待浏览器响应 {method} 超时（{timeout:.0f} 秒）：网络或控制台响应过慢，请重试"
                ) from exc
            except OSError as exc:
                raise ConsoleError(f"读取浏览器响应 {method} 失败：{exc}") from exc
            if raw is None:
                raise ConsoleError("浏览器调试连接已关闭")
            message = json.loads(raw)
            if message.get("id") == message_id:
                if "error" in message:
                    raise ConsoleError(f"{method} 失败：{message['error']}")
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)

    def evaluate(self, expression: str, await_promise: bool = True,
                 timeout: float = 30.0) -> Any:
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "userGesture": True,
            },
            timeout=timeout,
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            raise ConsoleError(f"页面脚本执行出错：{detail.get('text', detail)}")
        return result.get("result", {}).get("value")

    def drain_events(self, seconds: float = 0.0) -> None:
        """把待处理的事件收进 self.events（不阻塞等待新事件）。

        读取超时由 recv_message 内部处理且不会丢半帧，不会让流错位。
        """
        deadline = time.time() + seconds
        while True:
            remaining = deadline - time.time()
            try:
                raw = self.ws.recv_message(timeout=max(0.05, remaining))
            except ConsoleError:
                break
            except (socket.timeout, TimeoutError, OSError):
                break
            if raw is None:
                break
            message = json.loads(raw)
            if "method" in message:
                self.events.append(message)

    def close(self) -> None:
        self.ws.close()
