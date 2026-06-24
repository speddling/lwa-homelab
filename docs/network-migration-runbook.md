# LWA Infra — Network Migration Runbook
> Last updated: 2026-06-23

Operational sequence for moving from the flat `192.168.0.0/24` network to the 5-VLAN segmented design.

**Design principle:** nothing breaks until cutover, and cutover has a one-click rollback.

**Maintenance window:** ~60 minutes. Family gets a 30-minute warning before takedown.

---

## VLAN Reference

| VLAN | Name | Subnet | Gateway | Trust |
|------|------|--------|---------|-------|
| 10 | Mgmt | 192.168.10.0/24 | .10.1 | Network infrastructure only |
| 20 | Users | 192.168.20.0/24 | .20.1 | Trusted users & personal devices |
| 30 | Infra | 192.168.30.0/24 | .30.1 | Trusted infrastructure / compute |
| 40 | IoT | 192.168.40.0/24 | .40.1 | Low-trust networked devices |
| 50 | Guest | 192.168.50.0/24 | .50.1 | Untrusted / school-managed |
| 999 | Pit | none | none | Trunk native — untagged frames dropped |

**DHCP pool layout (all VLANs except Guest and Pit):**
- `.1` — gateway (ER605)
- `.2–.99` — static reservations
- `.100–.200` — dynamic pool
- `.201–.254` — reserved

**Guest exception:** dynamic pool is `.50–.200` (more DHCP capacity, fewer statics).

---

## Static IP Plan

### Mgmt (192.168.10.0/24)
| IP | Device |
|----|--------|
| .10.1 | ER605 management interface |
| .10.2 | SG2218P |
| .10.3 | OC200 |
| .10.4 | EAP245 — Downstairs Hall |
| .10.5 | EAP245 — Upstairs Hall |
| .10.6 | EAP225-Outdoor — Balcony *(future)* |

### Infra (192.168.30.0/24)
| IP | Device |
|----|--------|
| .30.10 | monolith |
| .30.11 | watchtower |
| .30.12 | Obelisk (Win11 VM on monolith) |
| .30.20 | Lore — Ollama inference *(future)* |
| .30.21 | Data — production LLM build *(future)* |

### IoT (192.168.40.0/24)
| IP | Device |
|----|--------|
| .40.10 | Big Brother NVR |
| .40.11 | Reolink camera #1 (porch) |
| .40.12 | Reolink camera #2 (driveway PTZ) |
| .40.20 | Brother HL-L3290CWD printer |

### Users (192.168.20.0/24)
| IP | Device | Notes |
|----|--------|-------|
| .20.2 | apex | MAC-bound reservation. Disable WiFi MAC randomization for `LittleWolfAcres` SSID before cutover. |
| .20.3 | Studio | MAC-bound reservation. Same — disable randomization. |

All other Users devices are pure DHCP.

### Guest (192.168.50.0/24)
Pure DHCP. Capture daughter's Chromebook MAC on first connection and add as a reservation.

---

## Switch Port Map

See [`switch-port-map.svg`](switch-port-map.svg) for a visual reference.

| Port | Device | Mode | Native VLAN | Tagged VLANs | PoE |
|------|--------|------|-------------|--------------|-----|
| 1 | ER605 uplink | Trunk | 999 (Pit) | 10, 20, 30, 40, 50 | off |
| 2 | monolith | Trunk | 30 (Infra) | *(add tags as VMs need other VLANs)* | off |
| 3 | watchtower | Access | 30 (Infra) | — | off |
| 4 | Lore *(future)* | Access | 30 (Infra) | — | off |
| 5 | Data *(future)* | Access | 30 (Infra) | — | off |
| 6 | spare — Infra | Access | 30 (Infra) | — | off |
| 7 | Big Brother NVR | Access | 40 (IoT) | — | off *(wall powered)* |
| 8 | Reolink cam #1 | Access | 40 (IoT) | — | **PoE+ on** |
| 9 | Reolink cam #2 | Access | 40 (IoT) | — | **PoE+ on** |
| 10 | reserved — coop/run | Access | 40 (IoT) | — | on *(pre-staged, disabled until cable pulled)* |
| 11 | OC200 | Access | 10 (Mgmt) | — | **PoE on** |
| 12 | EAP245 — Downstairs Hall | Trunk | 10 (Mgmt) | 20, 40, 50 | **PoE+ on** |
| 13 | EAP245 — Upstairs Hall | Trunk | 10 (Mgmt) | 20, 40, 50 | **PoE+ on** |
| 14 | EAP225-Outdoor — Balcony *(future)* | Trunk | 10 (Mgmt) | 20, 40, 50 | **PoE on** *(802.3af)* |
| 15 | spare — Users | Access | 20 (Users) | — | off |
| 16 | unused | **shutdown** | — | — | off |
| SFP1 | reserved | — | — | — | n/a |
| SFP2 | reserved | — | — | — | n/a |

**Trunk semantics:**
- Port 1 (ER605): all five active VLANs tagged; native 999 drops any stray untagged frames
- Port 2 (monolith): trunk with native = Infra so the host interface sees untagged Infra traffic; add VLAN tags later if VMs need other segments
- Ports 12, 13, 14 (APs): native = Mgmt so APs reach OC200 untagged; tagged VLANs carry the wireless SSIDs

---

## SSID Plan

| SSID | VLAN | Notes |
|------|------|-------|
| `LittleWolfAcres` | 20 (Users) | Main household SSID. Name retained so family devices reconnect transparently after cutover. |
| `LittleWolfAcres-IoT` | 40 (IoT) | Printer and any future IoT WiFi devices. Created pre-cutover, disabled until cutover. |
| `LittleWolfAcres-Guest` | 50 (Guest) | Daughter's school Chromebook, visitor devices. Created pre-cutover, disabled until cutover. |

No Infra SSID — Infra is wired-only by design. All three APs broadcast all three SSIDs.

---

## DNS Strategy

**Split-horizon via AdGuard on watchtower (`.30.11`):**
- Mgmt, Users, Infra, IoT → receive `.30.11` as primary DNS via DHCP from the ER605
- AdGuard handles all `*.littlewolfacres.com` rewrites for internal hostnames and forwards external queries upstream
- Guest → receives `1.1.1.1` and `9.9.9.9` via DHCP; bypasses AdGuard entirely — no internal hostname resolution, no AdGuard log noise

Internal service naming convention: `<service>.littlewolfacres.com` with AdGuard rewrites pointing to private IPs.

**Critical sequencing:** AdGuard rewrites must be updated to new IPs *before* the IaC PR deploys. Prometheus scrapes target `monolith.littlewolfacres.com` — if the rewrite still points to `192.168.0.20` when Ansible runs, every scrape job fails. Verify with `dig monolith.littlewolfacres.com @192.168.30.11` from an Infra device before triggering any post-cutover automation.

---

## Firewall Rules

**Default policy on the ER605:** all inter-VLAN traffic **denied**, all WAN-outbound **allowed**, all WAN-inbound **denied**. Rules below are explicit allows on top of that. The ER605 is stateful — return traffic is permitted automatically.

### From Users (192.168.20.0/24)

| Source | Destination | Port / Protocol | Purpose |
|--------|-------------|-----------------|---------|
| Studio `.20.3` | Infra `.30.12` (Obelisk) | TCP 3389 | **DENY** — must be ordered **above** the general RDP allow below. First-match wins; if this isn't first, the broader allow fires and the exception never triggers. |
| Users (all) | Infra `.30.12` (Obelisk) | TCP 3389 | RDP — apex and all other Users devices (Studio excluded by deny above) |
| Users (all) | Infra `.30.11` (watchtower) | TCP/UDP 53 | DNS via AdGuard |
| Users (all) | Infra `.30.10` (monolith) | TCP 445, 139 | Samba — wife's laptop, Studio, daughter iPad |
| apex `.20.2` | Infra `.30.20` (Lore) *(future)* | TCP 11434 | Ollama |
| apex `.20.2` | Infra `.30.21` (Data) *(future)* | TCP 11434 | Ollama |
| Users (all) | IoT `.40.20` (printer) | TCP 631, 9100; UDP 5353 | Print + mDNS discovery |
| Users (all) | Mgmt (all) | TCP 22, 80, 443 | Admin access to router/switch/APs/OC200 |

### From Guest (192.168.50.0/24)

| Destination | Port / Protocol | Purpose |
|-------------|-----------------|---------|
| IoT `.40.20` (printer) | TCP 631, 9100; UDP 5353 | Print (Chromebook + visitors) |
| WAN | * | Internet only |

No DNS allow to Infra. Guest DNS is `1.1.1.1` / `9.9.9.9` via DHCP.

### From Infra (192.168.30.0/24)

| Source | Destination | Port / Protocol | Purpose |
|--------|-------------|-----------------|---------|
| Infra (all) | Mgmt (all) | UDP 161, ICMP | watchtower SNMP scrapes + ping monitoring |
| watchtower `.30.11` | Mgmt `.10.3` (OC200) | TCP 8043 | Omada Open API — network IaC reconcile (see Post-Cutover Follow-Ups). Scoped to watchtower only, not all of Infra. Port must match the OC200 Interface Access Address; default controller HTTPS is 8043. |
| Infra (all) | WAN | * | Updates, container pulls, ArgoCD, ntfy |

No allow to Users or Guest. Infra does not initiate to user devices.

### From IoT (192.168.40.0/24)

| Destination | Port / Protocol | Purpose |
|-------------|-----------------|---------|
| WAN | * | Cameras phone home, printer firmware updates, NTP |

No allow to any internal VLAN. NVR ↔ cameras is intra-VLAN (no rule needed). Printer is a destination only, never a source.

### From Mgmt (192.168.10.0/24)

| Destination | Port / Protocol | Purpose |
|-------------|-----------------|---------|
| WAN | * | OC200 cloud access, firmware updates |

Default deny everything else from Mgmt.

### mDNS / Bonjour cross-VLAN (printer)

The `UDP 5353` entries above open the port, but opening a port is not the same as enabling cross-VLAN multicast. mDNS discovery (`224.0.0.251`) doesn't cross VLAN boundaries on its own regardless of what the ACL permits.

**Solution:** Settings → Services → mDNS → mDNS Repeater on the Gateway (ER605). Configure forwarding rules: Users→IoT and Guest→IoT, scoped to the printer's Bonjour/IPP service specifically.

Requires Controller 5.6+ (have 5.14.x ✓) and matching ER605 firmware (have 2.2.3 ✓).

If ACL rules prohibiting Users/Guest→IoT are in place, they can independently block forwarded mDNS traffic even when the repeater rule is configured correctly. If discovery doesn't work after setup, check the ACL before assuming the repeater rule is wrong.

**Fallback:** skip auto-discovery and add the printer by static IP (`.40.20`) on each device directly. Works regardless of mDNS Repeater state.

---

## Remote Access

Single entry point: **WireGuard on the ER605**, one inbound UDP port (51820) on the WAN, no per-service port forwards. WireGuard clients land in their own subnet with full reach into Users, Infra, IoT. New self-hosted services become reachable over the tunnel without additional firewall changes.

Configuration (subnet allocation, client keys, policy) is deferred — tracked in Post-Cutover Follow-Ups.

---

## Pre-Cutover Checklist

Work that can be done while the flat network keeps running.

### OC200

- [x] Create VLANs 10, 20, 30, 40, 50, 999 in OC200
- [x] Flip each VLAN to **Interface** purpose and define DHCP scopes (pool, DNS) with DHCP Server on — networks not yet active
- [x] Rename EAP245s: Foyer → **Downstairs Hall**, Yarn Studio → **Upstairs Hall**
- [ ] Pre-create static reservations:
  - Infra: `.30.10` monolith, `.30.11` watchtower, `.30.12` Obelisk
  - IoT: `.40.10` Big Brother NVR, `.40.11–.12` Reolinks, `.40.20` printer
  - Mgmt: `.10.1–.6` infrastructure (controller auto-assigns most via Omada discovery)
  - Users: `.20.2` apex, `.20.3` Studio — capture MACs first; **disable WiFi MAC randomization for `LittleWolfAcres` on both devices before cutover**
    - macOS: Settings → Wi-Fi → Details → Private Wi-Fi Address → off (per network)
    - Windows: Settings → Wi-Fi → [network] → Random hardware addresses → off
- [ ] Pre-create SSIDs `LittleWolfAcres-IoT` (VLAN 40) and `LittleWolfAcres-Guest` (VLAN 50), marked **disabled**
- [ ] Confirm `LittleWolfAcres` SSID is retained and will move to VLAN 20 (Users) at cutover
- [ ] Configure mDNS Repeater per the Firewall Rules section above

### AdGuard

- [ ] Export current local DNS rewrites (backup)
- [ ] Prepare updated rewrite list mapping every `*.littlewolfacres.com` entry to its new IP
- [ ] Confirm AdGuard listener is bound to `0.0.0.0` (not a specific interface)

### IaC Prep

- [ ] `grep -rn '192.168.0.' .` across the repo — list every occurrence, group by file
- [ ] Stage all changes (Ansible vars, K8s manifests, monitoring configs, `homelab-state.md`) in a parallel PR branch — **hold until post-cutover**
- [ ] Rename Prometheus job `snmp-eap-yarn-studio` → `snmp-eap-upstairs-hall` in that PR
- [ ] Rewrite UFW rules on monolith — `192.168.0.0/24` catch-all must be split by VLAN:
  - HTTP/HTTPS, Samba → `192.168.20.0/24` (Users) only
  - node_exporter, ArgoCD metrics → watchtower `192.168.30.11` only
  - Synapse MCP → apex `192.168.20.2` only
  - SSH → apex and Studio at their reserved IPs
- [ ] Update ER605 syslog destination `192.168.0.21:1514` → `192.168.30.11:1514` in the IaC PR

### Backups

- [ ] OC200 config export
- [ ] ER605 config export
- [ ] AdGuard config snapshot
- [ ] Ansible vault committed and tagged (rollback reference)

### Logistics

- [ ] Confirm 30-minute family warning channel
- [ ] Pick maintenance window — late evening or weekend morning
- [ ] Stage monitor and keyboard at watchtower for wired recovery during cutover

---

## Cutover

Issue **30-minute family warning** before starting.

1. **Snapshot OC200 config** — this is your rollback point
2. In OC200, **enable the new networks** (VLANs 10/20/30/40/50/999). ER605 immediately begins listening on the new VLAN gateways
3. **Push the SG2218P port plan** — trunks, native VLANs, tagged VLANs per the switch port table above. Ports change behavior immediately
4. Update static-IP devices that don't pull config from Omada:
   - **watchtower** — `.0.21` → `.30.11` (change static config, or convert to DHCP reservation and reboot)
   - **monolith** — `.0.20` → `.30.10`
   - **Big Brother NVR** — `.0.4` → `.40.10` (via NVR web UI)
   - **Reolink cam #1** — → `.40.11` (via Reolink app)
   - **Reolink cam #2** — → `.40.12` (via Reolink app)
5. **Push AdGuard DNS rewrites** — paste the prepared list. Verify: `dig monolith.littlewolfacres.com @192.168.30.11` from an Infra device before proceeding
6. **Enable new SSIDs** in OC200 (`LittleWolfAcres-IoT`, `LittleWolfAcres-Guest`). Move `LittleWolfAcres` to VLAN 20 (Users)

---

## Post-Cutover Verification

Per-VLAN smoke test. Don't skip any of these.

### DHCP
- [ ] Users device gets `192.168.20.x`, gateway `.20.1`, DNS `.30.11`
- [ ] IoT device gets `192.168.40.x`, gateway `.40.1`, DNS `.30.11`
- [ ] Guest device gets `192.168.50.x`, gateway `.50.1`, DNS `1.1.1.1` / `9.9.9.9`
- [ ] Infra device gets `192.168.30.x`, gateway `.30.1`, DNS `.30.11`
- [ ] Mgmt interfaces visible at `.10.x` from an Infra device

### DNS
- [ ] `dig monolith.littlewolfacres.com` from a Users device returns `192.168.30.10`
- [ ] AdGuard query log shows queries from the Users VLAN subnet
- [ ] AdGuard query log shows **no** queries from the Guest VLAN subnet (confirms split-horizon DNS)

### Inter-VLAN Rules
- [ ] RDP from apex → Obelisk (`.30.12`) works
- [ ] RDP from Studio → Obelisk is **blocked** (Studio deny rule ordered above the general allow)
- [ ] Samba from Studio → monolith works
- [ ] Samba from wife's laptop → monolith works
- [ ] Print job from any Users device → printer succeeds
- [ ] Print job from Guest → printer succeeds
- [ ] If relying on AirPrint auto-discovery: confirm printer *appears* in device list without manual IP entry — a successful print via manually-added IP does not confirm the mDNS Repeater is working
- [ ] Users device cannot reach Infra on non-allowed ports (SSH from Users → monolith — should fail)
- [ ] IoT device cannot reach Users or Infra (`ping 192.168.30.10` from NVR debug shell — should fail)
- [ ] Guest device cannot reach anything internal except the printer (`ping 192.168.30.11` from guest device — should fail)

### Monitoring
- [ ] Prometheus targets all green in Grafana
- [ ] SNMP scrapes return data for ER605, SG2218P, both EAP245s
- [ ] node_exporter scrapes succeed for monolith and watchtower

### Services
- [ ] NVR recording continues on both Reolinks
- [ ] Internet works from a device on every VLAN
- [ ] ArgoCD on watchtower reaches GitHub
- [ ] Synapse (`monolith.littlewolfacres.com:30800`) reachable from apex; UFW restriction effective

---

## Cleanup & Commit

- [ ] Disable VLAN 1 on all switch ports (replaced by VLAN 999 Pit as native blackhole)
- [ ] Confirm ports 16, SFP1, SFP2 are administratively shut down
- [ ] Confirm port 10 is Access/VLAN 40, PoE on, disabled until coop cable is pulled
- [ ] Land the IaC PR — all `192.168.0.x` → new subnet replacements
- [ ] Update `docs/homelab-state.md` to reflect new addressing
- [ ] Take a fresh OC200 config backup as the new baseline
- [ ] Decommission TL-SG1210P or label as cold spare for the SG2218P
- [ ] Capture daughter's Chromebook MAC after first Guest SSID connection; add DHCP reservation in OC200

---

## Rollback

Triggered if verification reveals a critical failure that can't be debugged within the window.

1. In OC200, **restore the snapshot** taken at cutover step 1
2. ER605 reverts to flat network gateway
3. SG2218P drops back to no-VLAN behavior; all ports become access on default VLAN
4. APs revert to original SSID only
5. Devices re-DHCP back to `192.168.0.x`

**Note:** static-IP devices changed in cutover step 4 must be manually reverted — the OC200 snapshot alone doesn't cover those. Keep a note of which devices were touched and their old IPs before starting.

**Estimated rollback time:** 5–10 minutes from decision to fully reverted.

---

## Post-Cutover Follow-Ups

Not part of the maintenance window — tracked separately.

- **Balcony AP (EAP225-Outdoor):** mount above master suite balcony slider, run outdoor cable through duct chase from basement, inline Ethernet surge protector at basement entry, plug into port 14 — AP self-adopts to `.10.6`
- **Coop/run cable:** pulled when power-to-coop project happens; terminates in weatherproof junction box at coop end, lands on port 10
- **Network IaC / Omada GitOps:** manage VLANs, DHCP scopes, SSIDs, and PoE declaratively via the Omada Open API (Client Credentials app, already created). Ansible role at `services/omada/`, deployed by `deploy-omada.yml` on the watchtower runner. Phased rollout: read-only state export → dry-run diff → reconcile → migrate hand-built config into declarative files. Requires the Infra→OC200 TCP 8043 ACL above. Vault keys: `vault_omada_client_id`, `vault_omada_client_secret`, `vault_omada_id`, `vault_omada_api_base`. Only `omada_api_base` changes at cutover (OC200 → .10.3); credentials are stable.
- **WireGuard on ER605:** subnet allocation, client policy, key rotation
- **Reverse proxy / Cloudflare Tunnel:** for selectively WAN-exposed services
- **Mermaid topology diagram:** `docs/network-topology.md`
- **VLAN-aware Linux bridge on monolith:** netplan/networkd config required before any VM lands on a non-Infra VLAN
