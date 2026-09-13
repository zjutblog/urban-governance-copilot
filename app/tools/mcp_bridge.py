"""MCP 桥接层：把 D:/RDMA_v2 的 MCP server 工具接入本项目的动作体系。

设计：
- copilot 侧作为 MCP **client**，通过 stdio 子进程启动 RDMA_v2 的三个现成 server
 （geotools / gis_data / model_tools），用 RDMA 自己的解释器（ai_env）运行；
- 本项目 pipeline 是同步代码（LangGraph 节点/FastAPI def 端点），MCP client 是异步的，
   故用后台事件循环线程 + run_coroutine_threadsafe 做同步门面；
- 会话懒加载、进程常驻（首次调用时连接，之后复用），失败给出可读错误不崩 pipeline。
- **优先直接导入 RDMA 计算模块**（快），MCP 作为降级后备。

环境变量（均有默认值，可不配）：
- MCP_RDMA_PYTHON : 运行 RDMA server 的解释器（默认 ai_env）
- MCP_RDMA_ROOT   : RDMA_v2 项目根目录
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

from loguru import logger

_RDMA_PYTHON = os.getenv("MCP_RDMA_PYTHON", r"D:\anacanda\envs\ai_env\python.exe")
_RDMA_ROOT = os.getenv("MCP_RDMA_ROOT", r"D:\RDMA_v2")

# server 名 → 启动模块（在 _RDMA_ROOT 下以 -m 方式运行，保证相对导入可用）
MCP_SERVERS: dict[str, dict[str, Any]] = {
    "geotools": {"module": "src.mcp.servers.geotools_server", "desc": "缓冲区/坐标转换/距离/空间关系"},
    "gis_data": {"module": "src.mcp.servers.gis_data_server", "desc": "GIS 数据资源查询"},
    "model_tools": {"module": "src.mcp.servers.model_tools_server", "desc": "GIS 分析模型列表/接口/执行"},
}

_TIMEOUT_SEC = float(os.getenv("MCP_CALL_TIMEOUT", "180"))


class McpBridge:
    """同步门面。每个 server 一条持久会话；线程安全；失败抛 RuntimeError。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._sessions: dict[str, Any] = {}  # server 名 → ClientSession（loop 内使用）
        self._stacks: dict[str, Any] = {}

    # ---- 后台事件循环 ----
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop and self._loop.is_running():
                return self._loop
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, name="mcp-bridge-loop", daemon=True
            )
            self._thread.start()
            return self._loop

    def _run_coro(self, coro, timeout: float = _TIMEOUT_SEC):
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    # ---- 会话管理（协程侧）----
    async def _connect(self, server: str):
        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        info = MCP_SERVERS.get(server)
        if not info:
            raise RuntimeError(f"unknown mcp server '{server}'，可选: {list(MCP_SERVERS)}")
        if not os.path.exists(_RDMA_PYTHON):
            raise RuntimeError(f"RDMA 解释器不存在: {_RDMA_PYTHON}")

        params = StdioServerParameters(
            command=_RDMA_PYTHON,
            args=["-m", info["module"]],
            cwd=_RDMA_ROOT,
        )
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            # 增加初始化超时时间到60秒
            await asyncio.wait_for(session.initialize(), timeout=60)
        except BaseException:
            await stack.aclose()
            raise
        self._sessions[server] = session
        self._stacks[server] = stack
        logger.info(f"mcp connected: {server} ({info['module']})")

    def _get_session(self, server: str):
        """返回已连接会话；未连接则在 loop 内先连接。"""
        if server not in MCP_SERVERS:
            raise RuntimeError(f"unknown mcp server '{server}'，可选: {list(MCP_SERVERS)}")
        if self._sessions.get(server) is None:
            return None
        return self._sessions[server]

    # ---- 对外同步 API ----
    def list_tools(self, server: str) -> list[dict]:
        async def _go():
            if self._get_session(server) is None:
                await self._connect(server)
            res = await self._sessions[server].list_tools()
            return [
                {"name": t.name, "description": t.description}
                for t in getattr(res, "tools", [])
            ]

        return self._run_coro(_go(), timeout=60)

    def call(self, server: str, tool: str, arguments: dict | None = None) -> dict:
        """调用工具，返回 {ok, data|error}。连接失败/工具报错都不抛出到底层节点之外。"""
        
        # 优先：直接导入 RDMA 计算模块（跳过 MCP stdio，快 100x）
        if server == "model_tools" and tool == "run_model":
            direct = _direct_model_call(arguments or {})
            if direct is not None:
                return direct

        async def _go():
            if self._get_session(server) is None:
                await self._connect(server)
            res = await self._sessions[server].call_tool(tool, arguments or {})
            texts = []
            for item in getattr(res, "content", []) or []:
                t = getattr(item, "text", None)
                if t:
                    texts.append(t)
            err = getattr(res, "error", None)
            return {
                "ok": err is None,
                "data": "\n".join(texts),
                "isError": bool(getattr(res, "isError", False)),
            }

        try:
            return self._run_coro(_go())
        except Exception as e:  # noqa: BLE001
            # 连接断了则重置会话，下次重连
            self._sessions.pop(server, None)
            return {"ok": False, "data": "", "error": f"{type(e).__name__}: {e}"}


_bridge: McpBridge | None = None
_bridge_lock = threading.Lock()


def _direct_model_call(arguments: dict) -> dict | None:
    """直接调用 RDMA 计算模块（绕过 MCP stdio，快 100x）。"""
    import json as _json
    model_name = arguments.get("model_name", "")
    params = arguments.get("parameters", {})
    name_lower = model_name.lower()

    try:
        # 添加 RDMA_v2 到 sys.path
        if _RDMA_ROOT not in __import__("sys").path:
            __import__("sys").path.insert(0, _RDMA_ROOT)

        if "storm" in name_lower or "flood" in name_lower or "swmm" in name_lower or "runoff" in name_lower:
            from src.compute.swmm import run_swmm_simulation
            result = run_swmm_simulation(
                duration_hours=params.get("simulation_duration", 24),
                time_step_minutes=params.get("time_step", 5),
                infiltration_model=params.get("infiltration_model", 0),
                return_period=params.get("return_period", 10),
            )
            return {"ok": True, "data": _json.dumps(result, ensure_ascii=False)}

        elif "living" in name_lower or "accessibility" in name_lower or "15-min" in name_lower:
            from src.compute.living_area import run_living_area_analysis
            result = run_living_area_analysis(
                routing_mode=params.get("Routing", params.get("routing_mode", 2)),
                contour_threshold=params.get("Contour", params.get("contour_threshold", 15)),
                contour_type=params.get("Contour_Type", params.get("contour_type", "minutes")),
            )
            return {"ok": True, "data": _json.dumps(result, ensure_ascii=False)}

        elif "traffic" in name_lower or "transport" in name_lower:
            from src.compute.traffic import run_traffic_prediction
            result = run_traffic_prediction(
                prediction_horizon_minutes=params.get("prediction_horizon", 60),
                time_interval_minutes=params.get("time_interval", 5),
                include_weather=params.get("include_weather", 1),
            )
            return {"ok": True, "data": _json.dumps(result, ensure_ascii=False)}

    except Exception as e:
        logger.warning(f"direct model call failed: {e}, falling back to MCP")
        return None

    return None


def get_mcp_bridge() -> McpBridge:
    global _bridge
    with _bridge_lock:
        if _bridge is None:
            _bridge = McpBridge()
        return _bridge


def call_mcp_tool(server: str, tool: str, arguments: dict | None = None) -> dict:
    """模块级便捷入口（供 workflow 动作处理器使用）。"""
    return get_mcp_bridge().call(server, tool, arguments)
