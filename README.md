# KubeStellar Homebrew Tap

Official Homebrew tap for KubeStellar tools.

## Installation

```bash
brew tap kubestellar/tap
brew install kubectl-claude
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

## Links

- [kubectl-claude](https://github.com/kubestellar/kubectl-claude)
- [KubeStellar](https://kubestellar.io)
- [Claude Plugins Marketplace](https://github.com/kubestellar/claude-plugins)

## License

Apache License 2.0
