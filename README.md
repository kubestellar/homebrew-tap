# KubeStellar Homebrew Tap

Official Homebrew tap for KubeStellar tools.

## Installation

```bash
brew tap kubestellar/tap

# Install the KubeStellar Console (includes kc-agent as dependency)
brew install kubestellar-console

# Install kubectl-claude (AI-powered multi-cluster management)
brew install kubectl-claude

# Install KubeStellar operational tools
brew install kubestellar-ops
brew install kubestellar-deploy
```

## kubectl-claude

AI-powered multi-cluster Kubernetes management for Claude Code.

### Usage Methods

**1. Claude Code Plugin (Recommended)**

Install as a Claude Code plugin for the best experience:
```
/plugin marketplace add kubestellar/claude-plugins
```
Then go to `/plugin` → **Discover** → Install **kubectl-claude**.

**2. kubectl Plugin**
```bash
kubectl claude clusters list
kubectl claude clusters health
kubectl claude "show me failing pods"
```

**3. MCP Server**
```bash
kubectl-claude --mcp-server
```

### Slash Commands

| Command | Description |
|---------|-------------|
| `/k8s-health` | Check health of all Kubernetes clusters |
| `/k8s-issues` | Find issues across clusters (pods, deployments, events) |
| `/k8s-analyze` | Comprehensive namespace analysis |
| `/k8s-security` | Security audit (privileged, root, host access) |
| `/k8s-rbac` | Analyze RBAC permissions for a subject |
| `/k8s-audit-kubeconfig` | Audit kubeconfig clusters and recommend cleanup |
| `/k8s-ownership` | Set up resource ownership tracking with OPA Gatekeeper |

### MCP Tools (30 tools)

**Cluster Management**
- `list_clusters` - Discover clusters from kubeconfig
- `get_cluster_health` - Check cluster health status
- `get_nodes` - List cluster nodes with status
- `audit_kubeconfig` - Audit all clusters for connectivity and recommend cleanup

**Workloads**
- `get_pods`, `get_deployments`, `get_services`, `get_events`
- `describe_pod`, `get_pod_logs`

**RBAC Analysis**
- `get_roles`, `get_cluster_roles`, `get_role_bindings`, `get_cluster_role_bindings`
- `can_i`, `analyze_subject_permissions`, `describe_role`

**Diagnostics**
- `find_pod_issues` - CrashLoopBackOff, ImagePullBackOff, OOMKilled, pending
- `find_deployment_issues` - Stuck rollouts, unavailable replicas
- `check_resource_limits` - Missing CPU/memory limits
- `check_security_issues` - Privileged containers, root users, host network
- `analyze_namespace` - Comprehensive namespace analysis
- `get_warning_events` - Warning events only
- `find_resource_owners` - Find who owns/manages resources via managedFields, labels

**OPA Gatekeeper Policy**
- `check_gatekeeper` - Check if Gatekeeper is installed
- `get_ownership_policy_status` - Get policy config and violation count
- `list_ownership_violations` - List resources missing ownership labels
- `install_ownership_policy` - Install ownership policy (dryrun/warn/enforce)
- `set_ownership_policy_mode` - Change enforcement mode
- `uninstall_ownership_policy` - Remove the policy

### Allow Tools Without Prompts

Add to `~/.claude/settings.json`:
```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_kubectl-claude_kubectl-claude__*"
    ]
  }
}
```

### Example Questions

Ask Claude Code:
- "List my Kubernetes clusters"
- "Find pods with issues in the production namespace"
- "Check for security misconfigurations"
- "What permissions does the admin service account have?"
- "Audit my kubeconfig and show stale clusters"

## kubestellar-console

Multi-cluster Kubernetes management console with built-in AI support.

### Installation

```bash
brew tap kubestellar/tap
brew install kubestellar-console
```

This installs the console server binary and a launcher script. The `kc-agent` formula is installed automatically as a dependency.

### Usage

```bash
# Start the console (opens browser to http://localhost:8080)
kubestellar-console

# Start on a custom port
kubestellar-console --port 9090

# Show help
kubestellar-console --help
```

### Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `KC_CONSOLE_PORT` | Console server port | `8080` |
| `KC_DATA_DIR` | Data directory for PID files, logs, .env | `~/.kubestellar-console` |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID (optional) | (none) |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret (optional) | (none) |

To enable GitHub OAuth login, create `~/.kubestellar-console/.env`:

```bash
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-client-secret
```

Without OAuth credentials, the console starts in dev mode with auto-login.

### What it does

- Downloads and runs the pre-built KubeStellar Console binary
- Starts `kc-agent` as a background daemon (bridges browser to local kubeconfig)
- Opens your browser automatically
- Press `Ctrl+C` to stop the console (kc-agent continues in background)

### Quick start (without Homebrew)

```bash
curl -sSL https://raw.githubusercontent.com/kubestellar/console/main/start.sh | bash
```

## kc-agent

Local agent for KubeStellar Console - bridges your browser to your kubeconfig and Claude Code CLI.

### Installation

```bash
brew tap kubestellar/tap
brew install kc-agent
```

### Usage

```bash
# Start the agent (runs on localhost:8585)
kc-agent

# Or run as a background service
brew services start kubestellar/tap/kc-agent
```

### Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `KC_ALLOWED_ORIGINS` | Comma-separated list of allowed origins for CORS | localhost only |
| `KC_AGENT_TOKEN` | Optional shared secret for authentication | (none) |

#### Adding Custom Origins

If you're running the console on a custom domain:

```bash
# Single origin
KC_ALLOWED_ORIGINS="https://my-console.example.com" kc-agent

# Multiple origins
KC_ALLOWED_ORIGINS="https://console1.example.com,https://console2.example.com" kc-agent
```

#### Running as a Service with Custom Origins

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export KC_ALLOWED_ORIGINS="https://my-console.example.com"
```

Then restart:

```bash
brew services restart kubestellar/tap/kc-agent
```

### Security

- **Origin Validation**: Only allows connections from configured origins
- **Localhost Only**: Binds to `127.0.0.1` - not accessible from other machines
- **Optional Token Auth**: Can require a shared secret via `KC_AGENT_TOKEN`
- **Command Allowlist**: Only permits safe kubectl commands

## Links

- [KubeStellar Console](https://github.com/kubestellar/console)
- [kubectl-claude](https://github.com/kubestellar/kubectl-claude)
- [KubeStellar](https://kubestellar.io)
- [Claude Plugins Marketplace](https://github.com/kubestellar/claude-plugins)

## License

Apache License 2.0
