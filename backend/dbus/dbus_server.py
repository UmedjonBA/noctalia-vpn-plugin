"""DBus interface for the VPN backend.

Exposed on the session bus:
  service:     org.noctalia.VpnPlugin
  object path: /org/noctalia/VpnPlugin
  interface:   org.noctalia.VpnPlugin
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from dbus_next import BusType, RequestNameReply, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from backend.service.vpn_service import VpnService

SERVICE_NAME = "org.noctalia.VpnPlugin"
OBJECT_PATH = "/org/noctalia/VpnPlugin"
INTERFACE_NAME = "org.noctalia.VpnPlugin"


def _to_variant(value: Any) -> Variant:
    """Best-effort conversion of a Python value to a DBus Variant."""
    if isinstance(value, bool):
        return Variant("b", value)
    if isinstance(value, int):
        return Variant("x", value)
    if isinstance(value, float):
        return Variant("d", value)
    if isinstance(value, str):
        return Variant("s", value)
    if isinstance(value, list):
        if not value:
            return Variant("as", [])
        if all(isinstance(v, str) for v in value):
            return Variant("as", value)
        if all(isinstance(v, bool) for v in value):
            return Variant("ab", value)
        if all(isinstance(v, int) for v in value):
            return Variant("ax", value)
        # mixed → marshal each element as a variant
        return Variant("av", [_to_variant(v) for v in value])
    if isinstance(value, dict):
        return Variant("a{sv}", {str(k): _to_variant(v) for k, v in value.items()})
    if value is None:
        return Variant("s", "")
    return Variant("s", json.dumps(value))


def _dict_to_a_sv(d: dict) -> dict[str, Variant]:
    return {str(k): _to_variant(v) for k, v in d.items()}


def _variant_dict_to_python(d: dict[str, Variant]) -> dict:
    out: dict[str, Any] = {}
    for k, v in d.items():
        out[k] = v.value if isinstance(v, Variant) else v
    return out


class VpnInterface(ServiceInterface):
    def __init__(self, service: VpnService, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(INTERFACE_NAME)
        self._svc = service
        self._loop = loop
        # Wire state listeners
        service.state.status_listeners.append(self._on_status_change)
        service.state.server_list_listeners.append(self._on_server_list_change)
        service.state.log_listeners.append(self._on_log)
        service.add_traffic_listener(self._on_traffic)

    # ----------------------------------------------------------------- methods

    @method(name="StartProxy")
    async def StartProxy(self, server_id: "s", mode: "s", proxy_mode: "s") -> "b":  # type: ignore[name-defined]  # noqa: F821
        return await self._svc.start_proxy(server_id, mode, proxy_mode)

    @method(name="StopProxy")
    async def StopProxy(self) -> "b":  # noqa: F821
        return await self._svc.stop_proxy()

    @method(name="GetStatus")
    async def GetStatus(self) -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(self._svc.get_status())

    @method(name="GetServers")
    async def GetServers(self) -> "aa{sv}":  # noqa: F821
        servers = await self._svc.list_servers()
        return [_dict_to_a_sv(s) for s in servers]

    @method(name="AddServer")
    async def AddServer(self, server: "a{sv}") -> "s":  # noqa: F821
        return await self._svc.add_server(_variant_dict_to_python(server))

    @method(name="RemoveServer")
    async def RemoveServer(self, server_id: "s") -> "b":  # noqa: F821
        return await self._svc.remove_server(server_id)

    @method(name="UpdateServer")
    async def UpdateServer(self, server: "a{sv}") -> "b":  # noqa: F821
        try:
            return await self._svc.update_server(_variant_dict_to_python(server))
        except ValueError:
            return False

    @method(name="SwitchServer")
    async def SwitchServer(self, server_id: "s") -> "b":  # noqa: F821
        return await self._svc.switch_server(server_id)

    @method(name="SetMode")
    async def SetMode(self, mode: "s") -> "b":  # noqa: F821
        return await self._svc.set_mode(mode)

    @method(name="SetProxyMode")
    async def SetProxyMode(self, proxy_mode: "s") -> "b":  # noqa: F821
        return await self._svc.set_proxy_mode(proxy_mode)

    @method(name="PingServer")
    async def PingServer(self, server_id: "s") -> "i":  # noqa: F821
        return await self._svc.ping(server_id)

    @method(name="GetLogs")
    async def GetLogs(self) -> "as":  # noqa: F821
        return await self._svc.get_logs()

    @method(name="GetHealth")
    async def GetHealth(self) -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(self._svc.get_health())

    @method(name="RunSpeedTest")
    async def RunSpeedTest(self) -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(await self._svc.run_speed_test())

    @method(name="GetRoutingRules")
    async def GetRoutingRules(self) -> "aa{sv}":  # noqa: F821
        rules = await self._svc.list_rules()
        return [_dict_to_a_sv(r) for r in rules]

    @method(name="AddRoutingRule")
    async def AddRoutingRule(self, rule: "a{sv}") -> "s":  # noqa: F821
        try:
            return await self._svc.add_rule(_variant_dict_to_python(rule))
        except ValueError:
            return ""

    @method(name="RemoveRoutingRule")
    async def RemoveRoutingRule(self, rule_id: "s") -> "b":  # noqa: F821
        return await self._svc.remove_rule(rule_id)

    @method(name="CheckDnsLeak")
    async def CheckDnsLeak(self) -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(self._svc.check_dns_leak())

    @method(name="SetKillSwitch")
    async def SetKillSwitch(self, enabled: "b") -> "b":  # noqa: F821
        return await self._svc.set_kill_switch(enabled)

    @method(name="GetKillSwitchStatus")
    async def GetKillSwitchStatus(self) -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(await self._svc.get_kill_switch_status())

    @method(name="AddSubscription")
    async def AddSubscription(self, url: "s", name: "s") -> "b":  # noqa: F821
        return await self._svc.add_subscription(url, name)

    @method(name="RemoveSubscription")
    async def RemoveSubscription(self, url: "s") -> "b":  # noqa: F821
        return await self._svc.remove_subscription(url)

    @method(name="UpdateSubscription")
    async def UpdateSubscription(self, url: "s") -> "i":  # noqa: F821
        return await self._svc.update_subscription(url)

    @method(name="GetSubscriptions")
    async def GetSubscriptions(self) -> "aa{sv}":  # noqa: F821
        subs = await self._svc.list_subscriptions()
        return [_dict_to_a_sv(s) for s in subs]

    @method(name="GetTrafficStats")
    async def GetTrafficStats(self) -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(self._svc.get_traffic_stats())

    @method(name="GetSettings")
    async def GetSettings(self) -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(await self._svc.get_settings())

    @method(name="UpdateSettings")
    async def UpdateSettings(self, patch: "a{sv}") -> "a{sv}":  # noqa: F821
        return _dict_to_a_sv(await self._svc.update_settings(_variant_dict_to_python(patch)))

    @method(name="GetPresets")
    async def GetPresets(self) -> "aa{sv}":  # noqa: F821
        presets = await self._svc.list_presets()
        return [_dict_to_a_sv(p) for p in presets]

    @method(name="TogglePreset")
    async def TogglePreset(self, key: "s", enabled: "b") -> "b":  # noqa: F821
        return await self._svc.toggle_preset(key, enabled)

    # ----------------------------------------------------------------- signals

    @signal(name="StatusChanged")
    def StatusChanged(self, status) -> "a{sv}":  # noqa: F821
        return status

    @signal(name="ServerListChanged")
    def ServerListChanged(self):
        return None

    @signal(name="LogMessage")
    def LogMessage(self, level, message) -> "ss":  # noqa: F821
        return [level, message]

    @signal(name="TrafficUpdate")
    def TrafficUpdate(self, stats) -> "a{sv}":  # noqa: F821
        return stats

    # ----------------------------------------------------------------- callbacks (thread-safe)

    def _on_status_change(self, status_obj) -> None:
        try:
            payload = _dict_to_a_sv(status_obj.model_dump(exclude_none=True))
        except Exception:
            return
        # state listeners are called from inside the event loop (no thread hop needed)
        self.StatusChanged(payload)

    def _on_server_list_change(self) -> None:
        self.ServerListChanged()

    def _on_log(self, level: str, message: str) -> None:
        # Cap message size in signal payload to keep DBus messages small
        msg = message if len(message) <= 1024 else message[:1024] + "..."
        self.LogMessage(level, msg)

    def _on_traffic(self, stats: dict) -> None:
        try:
            self.TrafficUpdate(_dict_to_a_sv(stats))
        except Exception:
            pass


async def serve(service: VpnService) -> MessageBus:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    iface = VpnInterface(service, asyncio.get_running_loop())
    bus.export(OBJECT_PATH, iface)
    reply = await bus.request_name(SERVICE_NAME)
    if reply not in (
        RequestNameReply.PRIMARY_OWNER,
        RequestNameReply.ALREADY_OWNER,
    ):
        raise RuntimeError(
            f"Failed to acquire DBus name {SERVICE_NAME!r} (reply={reply}); "
            f"is another instance running?"
        )
    return bus
