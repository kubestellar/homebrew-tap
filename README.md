# KubeStellar Homebrew Tap

Official Homebrew tap for KubeStellar tools.

## Installation

```bash
brew tap kubestellar/tap
brew install kubectl-claude
```

## Available Formulae

| Formula | Description |
|---------|-------------|
| kubectl-claude | AI-powered multi-cluster Kubernetes management for Claude Code |

## Usage

After installation, kubectl-claude can be used as:

**kubectl plugin:**
```bash
kubectl claude clusters list
kubectl claude "show me failing pods"
```

**MCP server for Claude Code:**
```bash
kubectl-claude --mcp-server
```

Or install via the Claude Code plugin marketplace:
```
/plugin marketplace add kubestellar/claude-plugins
```

**Allow tools without prompts** - add to `~/.claude/settings.json`:
```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_kubectl-claude_kubectl-claude__*"
    ]
  }
}
```

## Links

- [kubectl-claude](https://github.com/kubestellar/kubectl-claude)
- [KubeStellar](https://kubestellar.io)
- [Claude Plugins Marketplace](https://github.com/kubestellar/claude-plugins)
