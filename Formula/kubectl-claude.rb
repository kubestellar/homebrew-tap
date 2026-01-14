# typed: false
# frozen_string_literal: true

class KubectlClaude < Formula
  desc "AI-powered multi-cluster Kubernetes management for Claude Code"
  homepage "https://github.com/kubestellar/kubectl-claude"
  license "Apache-2.0"
  version "0.2.0"

  on_macos do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.2.0/kubectl-claude_0.2.0_darwin_amd64.tar.gz"
      sha256 "f553035d9df21c3cfdf0833e89cd80fd74876ccbfba6af0c28fc95beea53cd00"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.2.0/kubectl-claude_0.2.0_darwin_arm64.tar.gz"
      sha256 "0ef5be88023662c1fca2bd32ec565eb44b00c85a3aaf74552c0a7c8c30cec66e"
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.2.0/kubectl-claude_0.2.0_linux_amd64.tar.gz"
      sha256 "1c1296150e00edc6ec3031d69d7fa29405324561432dae571cc9e10d19305fd7"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.2.0/kubectl-claude_0.2.0_linux_arm64.tar.gz"
      sha256 "ef64a8d92e6f6341bcf2df64367aa6be426bf78f7fec393f87917661931c37ab"
    end
  end

  def install
    bin.install "kubectl-claude"
  end

  test do
    system "#{bin}/kubectl-claude", "version"
  end
end
