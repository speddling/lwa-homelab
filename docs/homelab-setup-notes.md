---
title: Kubernetes Homelab Setup Notes
date: 2026-04-15
tags: [homelab, kubernetes, k3s, terraform, navidrome, devops, bios]
---

# Kubernetes Homelab Setup Notes

Personal notes from planning a k3s-based homelab with Navidrome and Terraform, based on hardware at [github.com/speddling/homelab](https://github.com/speddling/homelab).

---

## Hardware

| Component | Spec |
|---|---|
| Control Plane / Dev Machine | MacBook Air M4, 16GB RAM, macOS |
| Worker Node | AMD A10, 16GB RAM, Fractal Design Define R4 |
| Network | TP-Link Omada — OC200, ER605, TL-SG1210P PoE switch, 2× EAP245 APs |
| OS (Worker) | Ubuntu Server 24.04 LTS |
| Kubernetes | k3s |
| Primary Project | Navidrome audio server, ~1TB FLAC/MP3 library |

---

## Hardware Assessment

### Control Plane — MacBook Air M4

Solid and unconventional choice. The M4 is extremely efficient, and running k3s control-plane duties on macOS is well-supported. The 16GB unified memory is comfortable for control-plane-only work.

**Watch out for:** macOS sleep/wake can occasionally disrupt etcd or the k3s API server. Configure *"prevent sleep when display is off"* or keep the Mac tethered while the cluster is active.

### Worker Node — AMD A10 / 16GB RAM

The A10 is an older APU (Piledriver/Steamroller, ~2013–2015 era). For this use case it is **perfectly adequate**:

- Navidrome is extremely lightweight — 3 concurrent streams is trivial for any modern multi-core chip
- 16GB RAM gives plenty of headroom for k3s, Navidrome, and supporting pods
- The Define R4 has excellent thermals and drive mounting — ideal for a ~1TB music library

**Weak spots:** The A10's single-threaded performance is dated. For CPU-heavier future workloads (video transcoding, ML inference), you'll feel it. For Navidrome, you're fine.

### Navidrome Fitness

For 3 concurrent FLAC/MP3 streams, the worker node is more than sufficient. Navidrome typically runs under 200MB RAM and barely registers on CPU unless actively transcoding. Expect the initial library scan to take 10–30 minutes on a spinning HDD, but subsequent startups are fast.

---

## BIOS Settings — AMD A10 Worker Node

### Virtualization & CPU

| Setting | Value | Priority | Notes |
|---|---|---|---|
| AMD-V / SVM Mode | Enable | **Required** | Needed for container runtimes. Under Advanced → CPU Configuration. |
| IOMMU (AMD-Vi) | Enable | Recommended | Good practice; needed for hardware passthrough later. |
| C-States (C6/C7) | Disable deep states, set C1E max | Recommended | Deep sleep causes latency spikes and "Not Ready" events under low load. |
| Hyper-Threading / SMT | Enable | Recommended | More logical cores = more scheduling headroom for pods. |

### Memory

| Setting | Value | Priority | Notes |
|---|---|---|---|
| XMP / EXPO Profile | Enable if available | Optional | Runs RAM at rated speed. Verify stability on older A10 platforms. |
| ECC | N/A | — | A10 consumer APUs don't support ECC. |

### Storage & Boot

| Setting | Value | Priority | Notes |
|---|---|---|---|
| SATA Mode | AHCI | **Required** | Do not use IDE or RAID — breaks Ubuntu disk detection. |
| Boot Mode | UEFI (disable CSM/Legacy) | Recommended | Ubuntu 24.04 strongly prefers pure UEFI. |
| Secure Boot | Disable | Recommended | Can conflict with unsigned k3s kernel modules (Flannel/WireGuard). Re-enable later with enrolled keys if desired. |

### Power & Availability

| Setting | Value | Priority | Notes |
|---|---|---|---|
| Restore on AC Power Loss | Power On | **Required** | Ensures the worker comes back up after any outage. |
| Wake on LAN | Enable | Recommended | Lets you wake the node remotely from the Mac. |
| Spread Spectrum | Disable | Optional | No benefit for a server; can cause subtle timing instability. |

### Display & Onboard Peripherals

| Setting | Value | Priority | Notes |
|---|---|---|---|
| Primary Display | iGPU | Optional | A10 uses integrated graphics. Disable POST display output after setup if running headless. |
| Serial / Parallel Ports | Disable if unused | Optional | Reduces IRQ noise. |

---

## GitOps Workflow — Mac as Dev Platform

### The Key Nuance: GitHub Actions Runners

GitHub's hosted runners (`ubuntu-latest`) **cannot reach inside your home network**. Deployment to the worker node requires one of two approaches:

**Option A — Self-hosted runner (recommended)**
Install the GitHub Actions runner agent directly on the AMD A10 node. When a workflow triggers, GitHub sends the job to your node rather than a cloud VM. The runner makes outbound connections to GitHub — no inbound firewall rules needed.

**Option B — Outbound tunnel**
Use Cloudflare Tunnel or Tailscale to allow GitHub Actions to SSH into the node through a persistent outbound connection. More complex; useful if you can't install a runner.

For a homelab learning DevOps patterns, **Option A is the right call** — simpler, free, and directly translates to enterprise GitOps patterns (ArgoCD, Flux).

### Workflow Architecture

```
MacBook Air M4 (dev)
  └── author Terraform configs, k8s manifests, workflow YAML
  └── git push → GitHub repo (source of truth)
        └── GitHub Actions workflow triggers
              └── job dispatched to self-hosted runner (AMD A10)
                    ├── terraform apply  (infra layer)
                    └── kubectl apply    (app layer)
                          └── k3s cluster → Navidrome pod
```

### What Runs Where

**MacBook (dev tooling):**
- `kubectl` — pointed at k3s cluster via kubeconfig
- `terraform`
- `helm`
- `k9s` — cluster visibility TUI

You never need Docker Desktop. k3s uses `containerd` and workloads run on the worker.

**Worker node (persistent services):**
- `k3s` agent
- GitHub Actions self-hosted runner (installed as a `systemd` service)

### Terraform — Two-Layer Pattern

Split Terraform into two layers for clean separation:

**Layer 1 — Infrastructure**
- Static IP reservation in ER605
- DNS records in Omada
- kubeconfig provisioning

**Layer 2 — Application**
- Navidrome Helm release
- PersistentVolumeClaim for music library mount
- k3s namespace

This lets you `plan`/`apply` the app layer independently without touching network config.

**State file:** Store in a remote backend — Cloudflare R2 (free tier) works well as an S3-compatible backend. Do not store state locally on the Mac.

### Example GitHub Actions Workflow

```yaml
name: Deploy to homelab

on:
  push:
    branches: [master]

jobs:
  deploy:
    runs-on: self-hosted   # targets your AMD A10 runner
    steps:
      - uses: actions/checkout@v4

      - name: Terraform init & apply
        working-directory: terraform/
        run: |
          terraform init
          terraform apply -auto-approve

      - name: Apply Kubernetes manifests
        run: kubectl apply -f kubernetes/
```

### ARM vs x86 — Image Build Note

The MacBook M4 builds `arm64` images locally. The AMD A10 worker is `amd64`. For Navidrome this is irrelevant (pull the official image). For any custom images you build locally, specify `--platform linux/amd64` or use GitHub Actions hosted runners (which are `amd64`) to build and push to a registry before deploying.

---

## Practical First Steps

Get these working in order before building anything else:

1. **Install k3s** on the AMD A10 worker node
2. **Copy kubeconfig** to the Mac — verify `kubectl get nodes` works from macOS
3. **Assign a static IP** to the worker via the ER605 (do this early — kubeconfig embeds the IP)
4. **Install self-hosted runner** on the worker as a systemd service
5. **Write a minimal workflow** that runs `kubectl get nodes` — prove the pipeline end-to-end
6. **Add Terraform** once the loop is proven
7. **Deploy Navidrome** via Helm as your first real workload

One working loop beats a perfect architecture you haven't validated yet.

---
## Upgrade Thoughts

| **Component** | **Choice**                | **Reason for K8s**                                                                                                             |
| ------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **CPU**       | **Ryzen 9 5900X**         | Highest core count that the VRMs can safely handle.                                                                            |
| **RAM**       | **64GB DDR4-3200**        | Critical for running multiple nodes and namespaces.                                                                            |
| **Cooling**   | **Down-draft Air Cooler** | A cooler like the _Noctua NH-L12S_ or _Be Quiet! Shadow Rock LP_ blows air onto the VRMs, which is vital for this motherboard. |
| **Storage**   | **NVMe Gen3 (Slot 1)**    | Use the Ultra M.2 slot for your `etcd` store and boot drive to keep latency low.                                               |


---

### 1. The Storage Architecture (K3s + Navidrome)

Since you have a mix of NVMe, SATA SSDs, and a mechanical HDD, here is the most efficient way to map them in your Kubernetes lab:

- **Boot Drive / Control Plane (Samsung 512GB NVMe):** * Install your OS (likely Ubuntu Server or Debian) here.
    
    - K3s stores its `etcd` database in `/var/lib/rancher/k3s`. The low latency of your NVMe is crucial for preventing "database leader election" timeouts as your cluster grows.
        
- **Media Library SSD (Crucial 1TB SSD):** * Mount this specifically for your **Navidrome** music library.
    
    - **Pro Tip:** Format this with **XFS** or **Ext4**. If you use K3s with **Local Path Provisioner**, you can point a Persistent Volume (PV) directly to this SSD to keep Navidrome’s scanning fast.
        
- **Application Data SSD (Crucial 512GB & 256GB SSD):** * Use this for other lightweight containers (AdGuard Home, Home Assistant, etc.). It keeps your OS drive clean and your media drive dedicated to throughput.
    
- **Backup & Cold Storage (2TB HDD):** * Mount this for long-term backups or large file storage that doesn't require speed. You can also use this as a "Bulk Storage" class in K3s for non-essential pods.
    

---



## Network Stack Reference

| Device | Role |
|---|---|
| OC200 | Omada cloud controller |
| ER605 | Router / gateway |
| TL-SG1210P | PoE switch |
| EAP245 (×2) | Access points |

---

## References

- [speddling/homelab on GitHub](https://github.com/speddling/homelab)
- [k3s documentation](https://docs.k3s.io)
- [Navidrome documentation](https://www.navidrome.org/docs/)
- [GitHub Actions self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners)
- [Terraform Kubernetes provider](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs)
- [Terraform Helm provider](https://registry.terraform.io/providers/hashicorp/helm/latest/docs)





-------------------
New info / conversations:

## 1. The "Must-Have" Dashboard: Lens or k9s

If you are still typing `kubectl get pods` every 30 seconds, you're working too hard.

- **[k9s](https://k9scli.io/):** (Terminal-based) This is the "gold standard" for power users. It’s a lightning-fast TUI (Terminal User Interface) that lets you view logs, shell into containers, and delete pods with single keystrokes.
    
    - _Install:_ `brew install derailed/k9s/k9s`
        
- **[OpenLens](https://github.com/lensapp/lens):** (GUI-based) If you want a visual overview of your node health, storage usage, and networking.
    

## 2. Infrastructure as Code: Terraform / OpenTofu

Since you mentioned Terraform, the real question is: **Is Terraform managing the Monolith's OS/Virtualization, or just the K8s resources?**

- **ProxMox Provider:** If you ever move from bare-metal Ubuntu to a hypervisor like Proxmox, Terraform can spin up your VMs automatically.
    
- **Cloudflare Provider:** If you decide to expose Navidrome to the web, use Terraform to manage your DNS records and Tunnels. This keeps your "homelab-as-code" goal alive.
    

## 3. The Secret Weapon: Talos Linux or Flux/ArgoCD

Since you are already using GitHub Actions, you are 90% of the way to a "Pull-based" deployment model.

- **FluxCD or ArgoCD:** Instead of GitHub Actions "pushing" the YAML to the Monolith, these tools live _inside_ your cluster. They watch your GitHub repo; the moment you commit a change to a YAML, the cluster "pulls" it and updates itself.
    
    - _Why?_ It fixes "Configuration Drift." If someone manually changes a setting on the Monolith, Flux will automatically revert it to match your GitHub repo.
        

## 4. Local Development: Tilt or Skaffold

If you ever start writing your own code or custom manifests and hate waiting for a GitHub Action to run just to see a small change:

- **[Tilt](https://tilt.dev/):** It watches your local directory on your Mac. The second you save a file, it syncs the change directly into the Kubernetes cluster on the Monolith. It makes remote K8s feel like local development.
    

## 5. Better Mac Terminal Experience

- **[Kubectx & Kubens](https://github.com/ahmetb/kubectx):** Essential if you eventually add more clusters or namespaces. Switch contexts (`kubectx monolith`) and namespaces (`kubens navidrome`) instantly.
    
- **[Starship Prompt](https://starship.rs/):** A customizable shell prompt that will show you exactly which K8s context and namespace you are currently targeting, so you never accidentally delete something in the wrong place.
    

---

### My Recommendation for Right Now:

Don't over-tool yet. Start with **k9s**. It will give you a "god-view" of your Monolith from your Mac terminal while that 800GB transfer is running. You can watch the Navidrome logs in real-time to see when it starts scanning those new folders.

**Are you planning on keeping the Monolith as a single "all-in-one" node, or are you thinking about adding more hardware later?** That usually dictates which orchestrator (Terraform vs. Ansible vs. Flux) wins.



-------------------------

k9s sound like a logical step, is it on MacPort?
Terraform provisioned Monolith and deployed the K3s
#3 sound cool, but is a 'later' addition.

  

For now, Monolith is the hardware I own. I think next steps will be grabbing an 8TB HDD to replace the vintage 2TB HDD and replacing my A10 cpu with a best I can get cheap Ryzen upgrade and possibly max out the ram with speed and spec to match the A10 -> Ryzen move

Yes, **k9s** is on MacPorts. You can grab it with: `sudo port install k9s`

It’s the perfect "cockpit" for your Mac terminal. While that 800GB rsync is chugging along, you can open k9s, hit `:pods`, and watch the Navidrome logs in real-time to see if it starts freaking out (or successfully scanning) as the music files land.

---

### The "A10 to Ryzen" Upgrade Path

Since you’re on an A10 (likely an A10-9700), you’re on the **AM4 socket**. This is great news because you have a massive upgrade path, but there are two major "gotchas" for a Homelab build:

#### 1. The "Cheap but Powerful" Sweet Spot

The **Ryzen 5 5600G** is currently the king of budget server upgrades for your board.

- **Why the "G"?** Since your Monolith is a headless server, having integrated graphics (APU) is a lifesaver for troubleshooting. More importantly, Navidrome/Plex/Jellyfin can use that integrated GPU for **hardware transcoding**, which keeps your CPU usage at 1% even when streaming high-bitrate video.
    
- **Performance:** You go from 4 weak cores to 6 very fast cores (12 threads). It will handle K3s and Navidrome without breaking a sweat.
    

#### 2. The RAM Trap

- **Speed:** Ryzen _loves_ fast RAM. Your A10 probably has 2133MHz or 2400MHz DDR4. If you stick with that, you’ll bottleneck the Ryzen. Aim for **3200MHz CL16**—it’s the "sweet spot" for price and performance.
    
- **Spec:** Ensure it's non-ECC unbuffered DDR4 (standard desktop RAM). Maxing out at **32GB** (2x16GB) is usually plenty for a Monolith running K3s and a large media library.
    

#### 3. The BIOS Warning (Critical!)

**Do not swap the CPUs until you update the BIOS.** Your current motherboard BIOS was written before Ryzen 5000 existed. You must:

1. Keep the A10 installed.
    
2. Download the latest BIOS from your motherboard manufacturer.
    
3. Flash it.
    
4. _Then_ swap in the Ryzen. _(Note: Some older boards actually drop support for the A10 once you flash the "Ryzen-ready" BIOS, so once you flash it, you might be committed to the swap immediately.)_
    

---

### The Storage Move

Replacing the "vintage" 2TB with an **8TB HDD** is a solid move. When that time comes, since you’re already comfortable with `rsync`, you’ll just:

1. Mount the new 8TB as `/mnt/lab-backups-new`.
    
2. Rsync everything from the 2TB to the 8TB.
    
3. Update your Terraform/Kubernetes `hostPath` to point to the new disk.




----------------

Asus VM40B 8gb + 160gb HDD  
  

- **AdGuard Home:**
- **Unbound:**
- **Netdata:**
- **Prometheus:**
- **Grafana:**
- **Exporters:**

(edited)

James Hart  [3:01 PM]  

- **Hot storage** (NVMe) — active model weights, datasets being trained on
- **Warm storage** (SSD) — projects, code, containers
- **Cold storage** (HDD) — audio library, backups, archived models