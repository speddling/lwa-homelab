# Claude MCPs — Little Wolf Acres AI Tooling

Three MCP servers give Claude structured, safe access to the homelab. Each has a distinct role and runs on a dedicated host. Together they cover the full operational surface: cluster state, git workflow, and monitoring layer.

| Server | Host | Role | Port | Transport |
|---|---|---|---|---|
| **Synapse** | monolith | k3s cluster, Prometheus metrics, monolith filesystem | 30800 | Streamable HTTP (FastMCP · Kubernetes) |
| **Scribe** | apex | Git workflow — branch, commit, push, PR | 8765 | Streamable HTTP (FastMCP · launchd) |
| **Argus** | watchtower | Live monitoring configs, systemd, journald, Alertmanager API, Prometheus rules | 9800 | Streamable HTTP (FastMCP · systemd) |

All three follow the same security pattern: dedicated system user, no shell, UFW-restricted to apex (`192.168.0.19`), no write surface except where explicitly scoped (Scribe — git only, branch-protected).

---

## Claude Desktop Configuration (apex)

All three entries belong in `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "synapse": {
      "command": "/Users/speddling/.nvm/versions/node/v24.15.0/bin/npx",
      "args": ["mcp-remote", "http://monolith.littlewolfacres.com:30800/mcp", "--allow-http"]
    },
    "scribe": {
      "command": "/Users/speddling/.nvm/versions/node/v24.15.0/bin/npx",
      "args": ["mcp-remote", "http://apex.littlewolfacres.com:8765/mcp", "--allow-http"]
    },
    "argus": {
      "command": "/Users/speddling/.nvm/versions/node/v24.15.0/bin/npx",
      "args": ["mcp-remote", "http://watchtower.littlewolfacres.com:9800/mcp", "--allow-http"]
    }
  }
}
```

Quit and relaunch Claude Desktop after editing. A hammer icon in the chat interface confirms the connections.

---

## Synapse — Monolith MCP Server

Claude's eyes on the cluster. Read-only access to k3s pod state, Prometheus metrics, Alertmanager alerts, and the monolith filesystem.

Named for the neural connection — the junction between Claude and the homelab's nervous system.

### Tools

| Tool | Description |
|---|---|
| `k8s_get_pods` | List pods in a namespace or cluster-wide |
| `k8s_get_nodes` | Node status, kubelet version, CPU/memory capacity |
| `k8s_get_logs` | Tail pod log output |
| `k8s_describe_pod` | Pod details, resource requests/limits, recent events |
| `k8s_get_pvcs` | PersistentVolumeClaim status |
| `prom_query` | Instant PromQL query against Prometheus on Watchtower |
| `prom_active_alerts` | Currently firing Prometheus alerts |
| `fs_read_file` | Read a file from an allowlisted path on Monolith |
| `fs_list_dir` | List a directory from an allowlisted path |

### Deployment

- **Host:** `monolith.littlewolfacres.com`
- **Port:** `30800` (UFW restricts to `apex` only — `192.168.0.19`)
- **Transport:** Streamable HTTP (FastMCP)
- **Deploy method:** Kubernetes (namespace: `synapse`) — GitHub Actions `deploy-synapse.yml`
- **Image:** `ghcr.io/speddling/synapse:latest`
- **MCP URL:** `http://monolith.littlewolfacres.com:30800/mcp`

### File Layout

```
services/synapse/
  server/
    server.py           # MCP server — tools, streamable HTTP transport
    requirements.txt
    Dockerfile          # Multi-stage, runs as uid 1000
  kubernetes/
    namespace.yaml
    rbac.yaml           # ServiceAccount + least-privilege ClusterRole
    configmap.yaml      # PROMETHEUS_URL, ALLOWED_READ_PATHS
    deployment.yaml
    service.yaml        # NodePort 30800
.github/workflows/
  deploy-synapse.yml    # Build image → push ghcr.io → apply manifests → UFW
```

### Security

| Control | Detail |
|---|---|
| Network | UFW: port 30800 allowed from `192.168.0.19` (apex) only |
| k8s permissions | Custom ClusterRole: read-only get/list/watch + pods/log. No write, no exec, no secrets. |
| Filesystem | hostPath volumes mounted `readOnly: true`. Path allowlist enforced in `server.py`. |
| Prometheus | Read-only HTTP queries against Watchtower |
| Container | Runs as uid 1000, non-root, multi-stage build |

### Operations

```bash
# Pod status
kubectl get pods -n synapse

# Logs
kubectl logs -n synapse deployment/synapse --tail=50 -f

# Health check (from apex)
curl http://monolith.littlewolfacres.com:30800/health

# Restart after config change
kubectl rollout restart deployment/synapse -n synapse

# UFW check (on monolith)
sudo ufw status numbered | grep 30800

# Trigger deploy manually
gh workflow run deploy-synapse.yml
```

---

## Scribe — Apex MCP Server

Claude's git control plane. Branch, stage, commit, push, and open PRs against the homelab repo — with branch protection and path allowlisting baked in at the server level.

The human stays in the loop at exactly one point: GitHub PR review and merge. Everything before that is handled by Scribe.

### Tools

| Tool | Description |
|---|---|
| `git_status` | Show current branch, staged/unstaged changes, and untracked files |
| `git_branch` | Create and checkout a new branch (`git checkout -b <name>`) |
| `git_commit` | Stage a specified list of paths and commit with a message |
| `git_rm` | Remove tracked files from disk and stage the deletion |
| `git_push` | Push the current branch to origin and set upstream |
| `git_pr` | Open a GitHub PR via `gh pr create` with title and body |

`git_status` is read-only. All mutating tools refuse to operate on `master` or `main`.

### Architecture

```
Claude (claude.ai)
  └── MCP connection → http://apex.littlewolfacres.com:8765/mcp
        └── Scribe (FastMCP, launchd, apex)
              └── subprocess — git + gh CLI
                    └── ~/homelab repo (and other configured REPO_ROOTS)
```

**Key design decisions:**
- No shell passthrough — each tool is a hardcoded function that does exactly one thing
- Repo-locked — `SCRIBE_REPO_ROOTS` is set at startup; repo path is never user-controlled
- Branch-protected — all mutating tools refuse `master`/`main` at the Python level
- Path-allowlisted staging — `git_commit` validates every path inside the repo root before staging

### Deployment

- **Host:** `apex.littlewolfacres.com`
- **Port:** `8765`
- **Transport:** Streamable HTTP (FastMCP)
- **Deploy method:** launchd service on apex — GitHub Actions `deploy-scribe.yml`
- **User:** `speddling` (inherits existing SSH key and `gh` auth)
- **MCP URL:** `http://apex.littlewolfacres.com:8765/mcp`

### File Layout

```
services/apex/
├── scribe/
│   ├── server.py            # FastMCP server — all five tools
│   └── requirements.txt
└── ansible/
    ├── ansible.cfg
    ├── inventory.ini
    ├── playbooks/
    │   └── scribe.yml
    └── roles/
        └── scribe/
            ├── defaults/main.yml
            ├── tasks/main.yml
            └── templates/
                └── com.littlewolfacres.scribe.plist.j2
.github/workflows/
└── deploy-scribe.yml
```

### Key Defaults

| Variable | Default | Notes |
|---|---|---|
| `scribe_port` | `8765` | Port Scribe listens on |
| `scribe_repo_roots` | `/Users/speddling/homelab` | Colon-separated list of allowed repo roots |
| `scribe_venv` | `~/.venv/scribe` | Python venv location |
| `scribe_log` | `~/Library/Logs/scribe.log` | launchd stdout/stderr target |

### Security

| Constraint | Mechanism |
|---|---|
| Repo lock | `SCRIBE_REPO_ROOTS` hardcoded in plist env — not a tool parameter |
| Branch protection | Tools refuse `master`/`main` at the Python level before any subprocess call |
| Merged-PR guard | `git_commit`, `git_rm`, `git_push`, `git_pr` call `gh pr view` and refuse if the branch's PR is already merged. Fails open if gh is unavailable. |
| Staging allowlist | `git_commit` resolves and validates every path before `git add` |
| Network exposure | Port restricted to LAN — UFW to taste |
| Auth | Runs as `speddling`, inherits `~/.ssh/id_ed25519` and `gh` token |

### Operations

```bash
# Check launchd service status
launchctl list | grep scribe

# View logs
tail -f ~/Library/Logs/scribe.log

# Confirm server is responding
curl http://localhost:8765/mcp
```

### Typical Workflow

1. Claude reads the repo via the filesystem MCP
2. Claude edits files via the filesystem MCP
3. `git_branch` — create a feature branch
4. `git_status` — confirm what changed
5. `git_commit` — stage explicit paths, conventional commit message
6. `git_push` — push the branch
7. `git_pr` — open PR with title and structured body
8. **Human reviews diff on GitHub and merges** ← only required human action

### Adding Additional Repos

Set `SCRIBE_REPO_ROOTS` to a colon-separated list of absolute paths in the launchd plist. Each repo must already have `gh` auth and a configured remote.

```
SCRIBE_REPO_ROOTS=/Users/speddling/homelab:/Users/speddling/other-repo
```

---

## Argus — Watchtower MCP Server

Claude's eyes on the monitoring layer. Read-only access to live Alertmanager and Prometheus configs, systemd service and timer state, journald logs, and the Alertmanager and Prometheus HTTP APIs.

Named for the hundred-eyed giant of Greek mythology — perpetual vigilance, nothing escapes notice.

### Tools

#### `fs_read_file(path)`
Read a file from an allowlisted directory on Watchtower.

**Allowed paths:** `/etc/alertmanager`, `/etc/prometheus`, `/etc/systemd/system`, `/usr/local/bin`, `/opt/argus`

Useful for:
- Comparing live `/etc/alertmanager/alertmanager.yml` against the repo template
- Verifying deployed `/usr/local/bin/daily-summary.py` matches `daily-summary.py.j2`
- Reading `/etc/systemd/system/daily-summary.timer` to confirm schedule

#### `fs_list_dir(path)`
List a directory within the same allowlist.

#### `systemd_status(unit)`
Run `systemctl status <unit> --no-pager` on Watchtower.

```
systemd_status("daily-summary.timer")
→ Shows next scheduled trigger, last run result, active state
```

#### `journald_tail(unit, lines=50)`
Return recent journal entries for a systemd unit (max 200 lines).

```
journald_tail("daily-summary.service", lines=20)
→ Last 20 lines from the most recent summary run
```

#### `alertmanager_alerts()`
Query the live Alertmanager API (`/api/v2/alerts`) — returns all active alerts with labels, severity, and description.

#### `alertmanager_status()`
Query `/api/v2/status` — returns the **live routing config** as Alertmanager has parsed it, plus version and uptime. Ground truth on what's actually loaded, not what the repo template says.

#### `prometheus_rules()`
Query `/api/v1/rules` — returns all alert rules currently loaded by Prometheus, grouped by rule group, with each rule's current state (`inactive`, `pending`, `firing`).

### Deployment

- **Host:** `watchtower.littlewolfacres.com`
- **Port:** `9800` (UFW restricts to `apex` only — `192.168.0.19`)
- **User:** `argus` (dedicated system user, no shell, no home dir)
- **Venv:** `/opt/argus/venv`
- **Script:** `/opt/argus/server.py`
- **Transport:** Streamable HTTP (FastMCP)
- **Deploy method:** Ansible `argus` role — triggered by push to `services/watchtower/**` or `ansible/vars/**` on master
- **MCP URL:** `http://watchtower.littlewolfacres.com:9800/mcp`

### Security

- Listens on all interfaces, UFW restricted to `192.168.0.19` (apex)
- Runs as the `argus` system user — no sudo, no shell
- Filesystem reads allowlisted in the systemd `Environment=` — not user-supplied at runtime
- Unit name validation for `systemd_status` and `journald_tail` — regex whitelist, no shell passthrough (`subprocess` list args only)
- No write tools — Argus is read-only by design

### Operations

```bash
# Check status
systemctl status argus

# Logs
journalctl -u argus -n 50

# Restart
sudo systemctl restart argus
```

---

## What Belongs Where

| Need | Use |
|---|---|
| Inspect k3s pods, deployments, PVCs | Synapse → `k8s_*` tools |
| Query Prometheus metrics | Synapse → `prom_query` / `prom_active_alerts` |
| Read files on Monolith | Synapse → `fs_read_file` / `fs_list_dir` |
| Branch, commit, push, open PR | Scribe → `git_*` tools |
| Remove tracked files from the repo | Scribe → `git_rm` |
| Read live Alertmanager or Prometheus config | Argus → `alertmanager_status` / `prometheus_rules` |
| Check systemd service or timer state | Argus → `systemd_status` |
| Read journald logs for a Watchtower service | Argus → `journald_tail` |
| Read config files on Watchtower | Argus → `fs_read_file` / `fs_list_dir` |

Synapse never touches git. Scribe never touches the cluster. Argus never writes anything.

---

## Kiro CLI — Native Alternative

Kiro is an AI coding agent that runs directly in the terminal on apex. Unlike the MCP setup above, it requires no running servers, no config files, and no Claude Desktop — just `kiro` in any repo directory.

```bash
cd ~/homelab
kiro
```

### What Kiro Does Natively

| Capability | How |
|---|---|
| Read and edit files in the repo | Built-in filesystem tools — no Scribe needed |
| Run shell commands (Ansible, gh, git) | Direct shell execution on apex |
| SSH into monolith / watchtower | Via apex's existing SSH keys — same access as you |
| Query AWS APIs | Native `use_aws` tool — no CLI wrapper needed |
| Search and understand code | AST-aware code intelligence built in |
| Branch, commit, push, open PRs | Shell + `gh` CLI — same as Scribe, no MCP server required |

### Comparison to the MCP Stack

| Task | MCP approach | Kiro approach |
|---|---|---|
| Check k3s pod state | Synapse → `k8s_get_pods` | `ssh monolith kubectl get pods -A` |
| Query Prometheus | Synapse → `prom_query` | `ssh watchtower curl -s 'localhost:9090/api/v1/query?...'` |
| Read journald logs | Argus → `journald_tail` | `ssh watchtower journalctl -u <unit> -n 50` |
| Commit and open PR | Scribe → `git_*` tools | `git` + `gh` CLI directly on apex |
| Edit homelab files | Claude filesystem MCP | Built-in file tools |

The MCP servers add structured guardrails (branch protection, path allowlists, read-only enforcement) and work inside Claude Desktop's chat interface. Kiro trades those guardrails for flexibility — it can do anything apex can do, and asks before taking destructive actions.

### When to Use Which

- **Claude + MCPs** — conversational, long-running sessions in Claude Desktop where you want the structured tool interface and guardrails
- **Kiro** — terminal-native work, AWS operations, tasks that need full shell access, or when you don't want to manage MCP server state

### Installation

```bash
# Install
npm install -g @aws/kiro-cli   # or via the Kiro installer

# Launch in any repo
cd ~/homelab
kiro
```

### Notes

- Kiro runs as `speddling` on apex — inherits all SSH keys, `gh` auth, AWS credentials, and Ansible vault access
- No inbound ports required — Kiro is a local process, not a server
- Context window usage shown in the TUI (`Auto X%`) — resets each session
- Sessions can be saved/restored with `/chat save` and `/chat load`
