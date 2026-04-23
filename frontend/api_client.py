"""FastAPI 后端的轻量 HTTP 客户端 (阶段 6 前端使用).

设计要点:
- 仅依赖 ``requests`` (已在 requirements 中), 不引入新依赖.
- 后端地址通过环境变量 ``BACKEND_URL`` 控制, 默认 ``http://localhost:8000``.
- 所有方法返回原生 dict / list, 不做 Pydantic 反序列化, 由前端按 schema 字段读取.
- 网络异常统一抛 ``BackendError``, 由 Streamlit 页面 catch 后做友好提示.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class BackendError(RuntimeError):
    """封装后端 4xx/5xx 与网络异常, 供前端统一展示."""


_DEFAULT_TIMEOUT = float(os.environ.get("BACKEND_TIMEOUT", "120"))


class ApiClient:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None) -> None:
        self.base_url = (base_url or os.environ.get("BACKEND_URL", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT
        self._session = requests.Session()

    # ---- 健康 ----

    def health(self) -> bool:
        try:
            r = self._session.get(f"{self.base_url}/healthz", timeout=5)
            return r.ok and r.json().get("status") == "ok"
        except requests.RequestException:
            return False

    # ---- 会话 / 会诊 ----

    def create_session(self) -> str:
        data = self._post("/api/v1/session", json=None)
        return data["session_id"]

    def consultation(self, session_id: str, case: Dict[str, Any]) -> Dict[str, Any]:
        return self._post(
            "/api/v1/consultation",
            json={"session_id": session_id, "case": case},
        )

    # ---- 历史 / 追溯 ----

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._get("/api/v1/sessions", params={"limit": limit})

    def list_messages(self, session_id: str) -> List[Dict[str, Any]]:
        return self._get(f"/api/v1/session/{session_id}")

    def get_case(self, session_id: str) -> Dict[str, Any]:
        return self._get(f"/api/v1/session/{session_id}/case")

    def delete_session(self, session_id: str) -> None:
        self._call("DELETE", f"/api/v1/session/{session_id}")

    def trace(self, session_id: str, round_: int = 1) -> List[Dict[str, Any]]:
        return self._get(f"/api/v1/session/{session_id}/trace/{round_}")

    # ---- 内部 ----

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._call("GET", path, params=params)

    def _post(self, path: str, json: Optional[Dict[str, Any]]) -> Any:
        return self._call("POST", path, json=json)

    def _call(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        try:
            r = self._session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            raise BackendError(f"无法连接后端 {url}: {e}") from e
        if not r.ok:
            detail: Any
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise BackendError(f"后端 {r.status_code}: {detail}")
        try:
            return r.json()
        except ValueError as e:
            raise BackendError(f"后端响应非 JSON: {r.text[:200]}") from e
