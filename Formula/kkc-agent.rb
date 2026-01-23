# typed: false
# frozen_string_literal: true

class KkcAgent < Formula
  desc "Local agent for KubeStellar Klaude Console - bridges browser to kubeconfig and Claude Code"
  homepage "https://github.com/kubestellar/console"
  url "https://github.com/kubestellar/console/archive/refs/tags/v0.3.2.tar.gz"
  sha256 "8bc6fa785a77f5d9d12dc8353f4378859e5acb64bf28fbd351e043db5bf2886f"
  license "Apache-2.0"

  head "https://github.com/kubestellar/console.git", branch: "main"

  depends_on "go" => :build

  def install
    # Build the kkc-agent binary
    system "go", "build", *std_go_args(ldflags: "-s -w -X github.com/kubestellar/console/pkg/agent.Version=#{version}"), "./cmd/kkc-agent"
  end

  def caveats
    <<~EOS
      The kkc-agent provides a local bridge between your browser and:
        - Your kubeconfig clusters
        - Claude Code token usage

      To start the agent:
        kkc-agent

      The agent listens on http://127.0.0.1:8585 (localhost only).
      Open the KubeStellar Klaude Console in your browser to connect.

      Environment variables:
        KKC_ALLOWED_ORIGINS  - Comma-separated list of additional allowed origins
        KKC_AGENT_TOKEN      - Optional shared secret for authentication
    EOS
  end

  service do
    run [opt_bin/"kkc-agent"]
    keep_alive true
    log_path var/"log/kkc-agent.log"
    error_log_path var/"log/kkc-agent.log"
  end

  test do
    assert_match "v0.3.2", shell_output("#{bin}/kkc-agent --version")
  end
end
