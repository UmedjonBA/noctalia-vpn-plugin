# Noctalia VPN Plugin — Backend

A production-quality VPN/proxy management backend for [Noctalia Shell](https://noctalia.dev).

## What it does

- Manages VPN/proxy connections via sing-box and OpenSSH
- Exposes a DBus API consumed by the Noctalia Shell plugin UI
- Supports multiple protocols and routing modes

## Supported protocols

- **VLESS** with Reality/TLS (sing-box)
- **VMess** (sing-box)
- **Shadowsocks** (sing-box)
- **SSH** tunnel (OpenSSH + sshpass)
- **SOCKS5** passthrough (sing-box)

## Features

- Rules/Global routing modes
- System Proxy and TUN/VPN modes
- Custom routing rules (force-proxy / direct / block)
- Regional bypass presets (RU, CN, IR)
- Subscription import (`vless://`, `vmess://`, `ss://`, `socks5://`)
- Health monitoring and speed testing
- Traffic metrics
- DNS leak prevention
- Kill switch (nftables)
- Streaming logs via DBus

## Architecture

```
Noctalia Shell Plugin (QML)
            ↓ DBus
Python Backend Service (this repo)
            ↓
   sing-box  /  OpenSSH
            ↓
        Internet
```

## Requirements

- Python 3.12+
- sing-box 1.8+
- openssh + sshpass (for SSH protocol)
- DBus session bus

## Installation

```bash
git clone https://github.com/UmedjonBA/noctalia-vpn-plugin.git
cd noctalia-vpn-plugin
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Running

```bash
.venv/bin/python3 -m backend.app
```

Or as a systemd user service (included in the Noctalia plugin):

```bash
cp noctalia-vpn-backend.service ~/.config/systemd/user/
systemctl --user enable --now noctalia-vpn-backend.service
```

## DBus API

- **Service:** `org.noctalia.VpnPlugin`
- **Path:** `/org/noctalia/VpnPlugin`

Key methods: `StartProxy`, `StopProxy`, `GetStatus`, `GetServers`, `AddServer`,
`RemoveServer`, `SetMode`, `SetProxyMode`, `PingServer`, `RunSpeedTest`,
`GetHealth`, `AddRoutingRule`, `GetRoutingRules`, `AddSubscription`.

## Plugin UI

The QML frontend lives in the Noctalia plugin repository:
<https://github.com/UmedjonBA/noctalia-vpn> (coming soon)

## Ports used

- `11080` — transport layer (SSH tunnel / sing-box transport)
- `11081` — rules mux (sing-box with routing rules)
- `11082` — global mux (sing-box, all traffic through proxy)
- `11089` — sing-box Clash API (internal)

## License

MIT
