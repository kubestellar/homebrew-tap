# KubeStellar Homebrew Tap

Official Homebrew tap for KubeStellar tools.

## Installation

```bash
brew tap kubestellar/tap

# Install the local agent (bridges browser to kubeconfig and Claude Code)
brew install kc-agent

# Install KubeStellar operational tools
brew install kubestellar-ops
brew install kubestellar-deploy
```

## kubectl-claude

`kubectl-claude` is planned, but it is not published as a Homebrew formula
in this tap yet.

For now, install it from the upstream project or use the Claude Code plugin
marketplace when that workflow is what you need.

## kubestellar-console

Multi-cluster Kubernetes management console with built-in AI support.

> **Note:** There is no `kubestellar-console` Homebrew formula yet.
> Use the quick-start script below or install from source.

### Quick start

```bash
curl -sSL https://raw.githubusercontent.com/kubestellar/console/main/start.sh | bash
```

This downloads and runs the pre-built KubeStellar Console binary, starts `kc-agent` as a background daemon, and opens your browser automatically. Press `Ctrl+C` to stop the console (kc-agent continues in background).

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
