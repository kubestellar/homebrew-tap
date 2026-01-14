# typed: false
# frozen_string_literal: true

# This formula is auto-updated by GoReleaser
class KubectlClaude < Formula
  desc "AI-powered multi-cluster Kubernetes management for Claude Code"
  homepage "https://github.com/kubestellar/kubectl-claude"
  license "Apache-2.0"
  version "0.1.0"

  on_macos do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_darwin_amd64.tar.gz"
      sha256 "PLACEHOLDER_AMD64"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_darwin_arm64.tar.gz"
      sha256 "PLACEHOLDER_ARM64"
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_linux_amd64.tar.gz"
      sha256 "PLACEHOLDER_LINUX_AMD64"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_linux_arm64.tar.gz"
      sha256 "PLACEHOLDER_LINUX_ARM64"
    end
  end

  def install
    bin.install "kubectl-claude"
  end

  test do
    system "#{bin}/kubectl-claude", "version"
  end
end
