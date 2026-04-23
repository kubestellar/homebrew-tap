# typed: false
# frozen_string_literal: true

class KubestellarConsole < Formula
  desc "Multi-cluster Kubernetes management console with built-in AI support"
  homepage "https://github.com/kubestellar/console"
  version "0.3.21"
  license "Apache-2.0"

  depends_on "kubestellar/tap/kc-agent"

  on_macos do
    if Hardware::CPU.intel?
      url "https://github.com/kubestellar/console/releases/download/v0.3.21/console_0.3.21_darwin_amd64.tar.gz"
      sha256 "f817851fbbe387e08e4187fa1ed931afa5092ff561e9938193cf01010979fba2"
    end
    if Hardware::CPU.arm?
      url "https://github.com/kubestellar/console/releases/download/v0.3.21/console_0.3.21_darwin_arm64.tar.gz"
      sha256 "fd3e191cff72211b69616bf387d6c68151d76d93ea8918619deb3d0db6450baa"
    end
  end

  on_linux do
    if Hardware::CPU.intel? && Hardware::CPU.is_64_bit?
      url "https://github.com/kubestellar/console/releases/download/v0.3.21/console_0.3.21_linux_amd64.tar.gz"
      sha256 "3db90dba17fb9d341fe47fa8fa72fec3a32da6822732e5cc49cb7f591a0e7a7e"
    end
    if Hardware::CPU.arm? && Hardware::CPU.is_64_bit?
      url "https://github.com/kubestellar/console/releases/download/v0.3.21/console_0.3.21_linux_arm64.tar.gz"
      sha256 "29881acb0862e17a471e1e565ad23eb24418b6728493e66d29f40647b43bd549"
    end
  end

  def install
    bin.install "console" => "kubestellar-console-server"

    # Install wrapper script that starts kc-agent and console together
    (bin/"kubestellar-console").write <<~BASH
      #!/bin/bash
      # KubeStellar Console launcher
      # Starts kc-agent (background) and the console server together.

      set -e

      PORT="${KC_CONSOLE_PORT:-8080}"
      AGENT_PORT=8585
      DATA_DIR="${KC_DATA_DIR:-${HOME}/.kubestellar-console}"

      mkdir -p "$DATA_DIR"

      # --- Parse args ---
      while [[ $# -gt 0 ]]; do
          case $1 in
              --port|-p) PORT="$2"; shift 2 ;;
              --help|-h)
                  echo "Usage: kubestellar-console [OPTIONS]"
                  echo ""
                  echo "Options:"
                  echo "  --port, -p <port>   Console port (default: 8080, or KC_CONSOLE_PORT env)"
                  echo "  --help, -h          Show this help message"
                  echo ""
                  echo "Environment variables:"
                  echo "  KC_CONSOLE_PORT     Console port (default: 8080)"
                  echo "  KC_DATA_DIR         Data directory (default: ~/.kubestellar-console)"
                  echo "  GITHUB_CLIENT_ID    GitHub OAuth client ID (optional)"
                  echo "  GITHUB_CLIENT_SECRET GitHub OAuth client secret (optional)"
                  echo ""
                  echo "kc-agent runs as a background daemon on port $AGENT_PORT."
                  echo "To stop kc-agent: kill \\$(cat $DATA_DIR/kc-agent.pid)"
                  exit 0
                  ;;
              *) shift ;;
          esac
      done

      # Load .env if present in data dir or current dir
      load_env() {
          local envfile="$1"
          if [ -f "$envfile" ]; then
              echo "Loading $envfile..."
              while IFS='=' read -r key value; do
                  [[ $key =~ ^#.*$ ]] && continue
                  [[ -z "$key" ]] && continue
                  value="${value%\\"}"
                  value="${value#\\"}"
                  value="${value%\\'}"
                  value="${value#\\'}"
                  export "$key=$value"
              done < "$envfile"
          fi
      }

      load_env "$DATA_DIR/.env"
      load_env ".env"

      if [ -z "$GITHUB_CLIENT_ID" ] || [ -z "$GITHUB_CLIENT_SECRET" ]; then
          echo ""
          echo "Note: No GitHub OAuth credentials found."
          echo "  Console will start in dev mode (auto-login, no GitHub authentication)."
          echo "  To enable GitHub login, create $DATA_DIR/.env with:"
          echo "    GITHUB_CLIENT_ID=<your-client-id>"
          echo "    GITHUB_CLIENT_SECRET=<your-client-secret>"
          echo ""
      fi

      # Start kc-agent if not already running
      KC_AGENT_BIN="$(brew --prefix)/bin/kc-agent"
      if [ -x "$KC_AGENT_BIN" ]; then
          AGENT_PID_FILE="$DATA_DIR/kc-agent.pid"
          AGENT_LOG_FILE="$DATA_DIR/kc-agent.log"

          if [ -f "$AGENT_PID_FILE" ]; then
              EXISTING_AGENT_PID=$(cat "$AGENT_PID_FILE")
              if kill -0 "$EXISTING_AGENT_PID" 2>/dev/null; then
                  echo "kc-agent is already running (PID: $EXISTING_AGENT_PID)"
              else
                  echo "Stale kc-agent PID file found, removing..."
                  rm -f "$AGENT_PID_FILE"
              fi
          fi

          if [ ! -f "$AGENT_PID_FILE" ]; then
              echo "Starting kc-agent as background daemon..."
              nohup "$KC_AGENT_BIN" >> "$AGENT_LOG_FILE" 2>&1 &
              echo $! > "$AGENT_PID_FILE"
              sleep 1

              if kill -0 "$(cat "$AGENT_PID_FILE")" 2>/dev/null; then
                  echo "  kc-agent started (PID: $(cat "$AGENT_PID_FILE"), log: $AGENT_LOG_FILE)"
              else
                  echo "  Warning: kc-agent failed to start. Check $AGENT_LOG_FILE for details."
                  rm -f "$AGENT_PID_FILE"
              fi
          fi
      fi

      # Generate JWT_SECRET if not set
      if [ -z "$JWT_SECRET" ]; then
          if command -v openssl &>/dev/null; then
              export JWT_SECRET=$(openssl rand -hex 32)
          else
              export JWT_SECRET=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n')
          fi
      fi

      # Cleanup on exit
      CONSOLE_PID=""
      cleanup() {
          echo ""
          echo "Shutting down console..."
          [ -n "$CONSOLE_PID" ] && kill "$CONSOLE_PID" 2>/dev/null || true
          echo "  kc-agent continues running in the background."
          echo "  To stop it: kill \\$(cat $DATA_DIR/kc-agent.pid)"
          exit 0
      }
      trap cleanup SIGINT SIGTERM

      # Kill any existing console on the port
      EXISTING_PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
      if [ -n "$EXISTING_PID" ]; then
          echo "Killing existing process on port $PORT (PID: $EXISTING_PID)..."
          kill -TERM "$EXISTING_PID" 2>/dev/null || true
          sleep 2
          kill -9 "$EXISTING_PID" 2>/dev/null || true
      fi

      echo "Starting console on port $PORT..."
      kubestellar-console-server --port "$PORT" &
      CONSOLE_PID=$!

      # Wait for console to be ready
      echo ""
      echo "Waiting for console to start..."
      MAX_WAIT=60
      WAITED=0
      while [ $WAITED -lt $MAX_WAIT ]; do
          HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${PORT}" 2>/dev/null || echo "000")
          if [ "$HTTP_CODE" = "200" ]; then
              break
          fi
          sleep 2
          WAITED=$((WAITED + 2))
          printf "  %ds..." "$WAITED"
      done
      echo ""

      if [ "$HTTP_CODE" = "200" ]; then
          echo ""
          echo "=== KubeStellar Console is running ==="
          echo ""
          echo "  Console:  http://localhost:${PORT}"
          if [ -f "$DATA_DIR/kc-agent.pid" ] && kill -0 "$(cat "$DATA_DIR/kc-agent.pid")" 2>/dev/null; then
              echo "  kc-agent: http://localhost:${AGENT_PORT} (PID: $(cat "$DATA_DIR/kc-agent.pid"))"
          fi
          echo ""
          # Open browser
          if command -v open &>/dev/null; then
              open "http://localhost:${PORT}"
          elif command -v xdg-open &>/dev/null; then
              xdg-open "http://localhost:${PORT}"
          else
              echo "  Open your browser to: http://localhost:${PORT}"
          fi
          echo "Press Ctrl+C to stop the console (kc-agent continues in background)"
          echo ""
          wait
      else
          echo ""
          echo "Warning: Console did not respond within ${MAX_WAIT}s"
          echo "Check if it's still starting: curl http://localhost:${PORT}"
          echo ""
          wait
      fi
    BASH
  end

  def caveats
    <<~EOS
      KubeStellar Console has been installed!

      To start the console:
        kubestellar-console

      To start on a custom port:
        kubestellar-console --port 9090

      To enable GitHub OAuth login, create ~/.kubestellar-console/.env with:
        GITHUB_CLIENT_ID=<your-client-id>
        GITHUB_CLIENT_SECRET=<your-client-secret>

      kc-agent (installed as a dependency) runs as a background daemon.
      It bridges your browser to your local kubeconfig.

      More info: https://github.com/kubestellar/console
    EOS
  end

  test do
    assert_predicate bin/"kubestellar-console", :exist?
    assert_predicate bin/"kubestellar-console-server", :exist?
    assert_predicate bin/"kubestellar-console", :executable?
  end
end
