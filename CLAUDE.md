# Noctalia VPN Plugin — Backend Development Guide

## CRITICAL: Protected ports — NEVER touch these
Ports 1080, 1081, 1082 are used by a running proxy. Killing processes on these
ports will disconnect the developer from the server.
Use ports 11080, 11081, 11082 for all testing.
Never run pkill without very specific pattern matching.
Never run killall.

## Project Goal
Build a production-quality VPN/proxy management backend for Noctalia Shell.
Backend first, UI later.

## Technology Stack
- Python 3.12+ with asyncio
- dbus-next for DBus IPC
- pydantic for data models
- sing-box as proxy engine (/usr/bin/sing-box)
- Platform: Arch Linux

## Architecture
```
QML (later) → DBus → Python Backend Service → sing-box → Internet
```

## DBus Interface
Service name: org.noctalia.VpnPlugin
Object path: /org/noctalia/VpnPlugin

Methods:
  StartProxy(server_id: str, mode: str, proxy_mode: str) → bool
  StopProxy() → bool
  GetStatus() → dict
  GetServers() → list
  AddServer(server: dict) → str  (returns id)
  RemoveServer(server_id: str) → bool
  UpdateServer(server: dict) → bool
  SwitchServer(server_id: str) → bool
  SetMode(mode: str) → bool          (rules/global)
  SetProxyMode(proxy_mode: str) → bool  (system/tun)
  PingServer(server_id: str) → int   (latency ms)
  GetLogs() → list[str]              (last 100 lines, formatted)

  # health
  GetHealth() → dict                 {latency_ms, last_check (ISO), consecutive_failures, status}

  # routing rules
  GetRoutingRules() → list
  AddRoutingRule(rule: dict) → str   (rule {name?, type: force-proxy|direct|block, pattern})
  RemoveRoutingRule(rule_id: str) → bool

  # DNS leak prevention
  CheckDnsLeak() → dict              {leaking: bool, dns_servers: list[str], reason: str}

  # kill switch (requires root or pkexec to install nftables rules)
  SetKillSwitch(enabled: bool) → bool
  GetKillSwitchStatus() → dict       {enabled, active}

  # subscriptions
  AddSubscription(url: str, name: str) → bool
  UpdateSubscription(url: str) → int (newly-imported server count)
  RemoveSubscription(url: str) → bool
  GetSubscriptions() → list

  # traffic metrics
  GetTrafficStats() → dict           {bytes_sent, bytes_received, uptime_seconds, connection_count}

Signals:
  StatusChanged(status: dict)
  ServerListChanged()
  LogMessage(level: str, message: str)
  TrafficUpdate(stats: dict)         (every 5s while proxy is active)

## Proxy Architecture (PROVEN WORKING)
```
Transport layer → port 11080:
  SSH      → sshpass + ssh -D 127.0.0.1:11080 -o SetEnv=NOCTALIA_VPN_TAG=1
  VLESS    → sing-box (vless outbound + socks5 inbound on 11080)
  VMess    → sing-box (vmess outbound + socks5 inbound on 11080)
  SS       → sing-box (ss outbound + socks5 inbound on 11080)
  SOCKS5   → remote server directly

Mux layer:
  Rules  → sing-box on 127.0.0.1:11081
           (refilter rules → proxy, rest → direct)
  Global → sing-box on 127.0.0.1:11082
           (everything → proxy)

System Proxy mode:
  Rules  → gsettings socks = 127.0.0.1:11081
  Global → gsettings socks = 127.0.0.1:11082

TUN mode (PROVEN WORKING architecture):
  sing-box TUN → outbound: socks5://127.0.0.1:11081 or 11082
  (connects to localhost mux, never causes routing loop)
  TUN config:
  {
    "inbounds": [{"type":"tun","interface_name":"noctalia-tun0",
                  "inet4_address":"172.19.0.1/30",
                  "auto_route":true,"strict_route":true,"stack":"system"}],
    "outbounds": [
      {"type":"socks","tag":"proxy","server":"127.0.0.1","server_port":11081},
      {"type":"direct","tag":"direct"}
    ],
    "route": {
      "rules":[{"ip_is_private":true,"outbound":"direct"}],
      "final":"proxy","auto_detect_interface":true
    }
  }
```

## sing-box Config Files
~/.config/sing-box/noctalia-vpn-{transport,rules,global,tun}.json
Logs: /tmp/noctalia-vpn-{transport,rules,global,tun}.log
State: /tmp/noctalia-vpn.state.json
Cache: ~/.config/sing-box/noctalia-vpn-rules.db

## Reference sing-box configs (WORKING, copy structure):
~/.config/sing-box/noctalia-rules.json
~/.config/sing-box/noctalia-global.json

## Server Object Schema
SSH:    {id, name, protocol:"ssh", host, port:22, user, password, keyFile, localPort:11080}
VLESS:  {id, name, protocol:"vless", address, port, uuid, transport, tls:bool, sni,
         security:"tls|reality", flow, fp, pbk, sid}
VMess:  {id, name, protocol:"vmess", address, port, uuid, alterId:0, security:"auto"}
SS:     {id, name, protocol:"shadowsocks", address, port, method, password}
SOCKS5: {id, name, protocol:"socks5", host, port, username, password}

## Process Management Rules
1. Before starting: stop_all() → pkill_zombies() → asyncio.sleep(1.0)
2. SSH tag: always -o SetEnv=NOCTALIA_VPN_TAG=1
3. pkill patterns (ONLY these):
   - ssh.*NOCTALIA_VPN_TAG=1
   - sing-box.*noctalia-vpn-
4. TUN requires CAP_NET_ADMIN: getcap /usr/bin/sing-box
   If missing: pkexec setcap cap_net_admin+ep /usr/bin/sing-box
5. Monitor all PIDs, if any dies → teardown everything → emit StatusChanged

## Storage
~/.config/noctalia-vpn/
├── servers.json         (list of server profiles)
├── settings.json        (activeServerId, mode, proxyMode, healthCheckIntervalSec,
│                         killSwitchEnabled, clashApiPort, ...)
├── rules.json           (custom routing rules: {id, name, type, pattern, enabled})
└── subscriptions.json   ({url, name, last_updated, server_count})

## Module Structure
backend/
├── app.py                          (entry point, asyncio event loop)
├── service/
│   ├── vpn_service.py              (main orchestrator)
│   └── kill_switch.py              (nftables ruleset + apply/remove)
├── dbus/
│   └── dbus_server.py              (DBus interface)
├── core/
│   └── state.py                    (application state)
├── models/
│   └── server.py                   (pydantic models incl. RoutingRule)
├── config/
│   └── settings.py                 (load/save settings)
├── singbox/
│   ├── config_builder.py           (sing-box configs incl. DNS + clash_api)
│   ├── process_manager.py          (start/stop/monitor sing-box + ssh)
│   └── transport.py                (protocol-specific outbound builders)
├── routing/
│   └── rules.py                    (rule classification helpers)
├── monitoring/
│   ├── health.py                   (TCP ping, HealthMonitor, DNS-leak check)
│   ├── log_streamer.py             (tail sing-box logs → LogMessage)
│   └── traffic.py                  (clash_api poller → TrafficUpdate)
├── subscription/
│   ├── parsers.py                  (vless/vmess/ss/socks5 share links + base64)
│   └── manager.py                  (fetch, import, 24h auto-update)
└── storage/
    ├── persistence.py              (servers.json + rules.json)
    └── subscriptions.py            (subscriptions.json)

## Running the backend
Dependencies live in `.venv/`. Start the daemon with:
    .venv/bin/python3 -m backend.app

It exits cleanly on SIGINT/SIGTERM. To restart after edits:
    pgrep -f 'python3 -m backend.app' | xargs -r kill ; sleep 1 ; \
        nohup .venv/bin/python3 -m backend.app > /tmp/noctalia-backend.log 2>&1 &

## Mux clash API port
Each rules/global mux config enables sing-box's clash_api on 127.0.0.1:11089
(configurable via Settings.clashApiPort). It's the data source for
GetTrafficStats and TrafficUpdate.

## Kill switch
SetKillSwitch(true) generates a self-contained `table inet noctalia_killswitch`
and installs it via `nft -f -` (root) or `pkexec nft -f -` (interactive). The
ruleset allows: loopback, established/related, the noctalia-tun0 device, UDP/53,
RFC1918 ranges, the active server's IP:port, and proxy ports 11080/11081/11082/
11089. SetKillSwitch(false) deletes the table.

## Development Phases
Phase 1 (DONE): Backend core — DBus service, sing-box orchestration, all protocols
Phase 1.5 (DONE): Health, log streaming, routing rules, DNS leak prevention,
                  kill switch, subscription import, traffic metrics
Phase 2: QML UI using Noctalia plugin system
Phase 3: Failover, sub-bookmarks, profile sharing

## Testing
Use ports 11080, 11081, 11082 (NOT 1080, 1081, 1082)
Test server (VLESS+Reality):
{
  "id": "test-vless",
  "name": "paravoz",
  "protocol": "vless",
  "address": "217.179.49.16",
  "port": 443,
  "uuid": "5b19f0ec-aeff-403d-8c75-0a99f3f9723b",
  "transport": "tcp",
  "tls": true,
  "sni": "www.amazon.com",
  "security": "reality",
  "flow": "xtls-rprx-vision",
  "fp": "chrome",
  "pbk": "CepymQv_SuhyrOfEXkai8DQKgN9Rzo7o4YcrSacMqHY",
  "sid": "30756342"
}

Test server (SSH):
{"id":"test-ssh","name":"test","protocol":"ssh","host":"213.155.15.139","port":22,"user":"root","password":"CunOQfYgTFSW1","localPort":11080}

Test server (SOCKS5):
{"id":"test-socks5","name":"ub","protocol":"socks5","host":"217.179.49.16","port":1080,"username":"socks","password":"paravoz_socks"}

## Quality Requirements
- Full async/await throughout
- Structured logging
- Graceful shutdown
- Never crash on malformed input
- Config validation before applying
- Clear error messages
