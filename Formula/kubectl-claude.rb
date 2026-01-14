# typed: false
# frozen_string_literal: true

class KubectlClaude < Formula
  desc "AI-powered multi-cluster Kubernetes management for Claude Code"
  homepage "https://github.com/kubestellar/kubectl-claude"
  license "Apache-2.0"
  version "0.1.0"

  on_macos do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_darwin_amd64.tar.gz"
      sha256 "c25d85821bebb0aa28b32637447a6bd2d768a060a9eb868f7ab6bc66dd536c12"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_darwin_arm64.tar.gz"
      sha256 "ec02f9414a2484bd9ea1901184266391229760c6364560dc1b9f6d2fefee594b"
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_linux_amd64.tar.gz"
      sha256 "0da2044e403d0f12692e04ceb44b1e9b3bd2772f3c39930f2ec4309c654c6554"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.1.0/kubectl-claude_0.1.0_linux_arm64.tar.gz"
      sha256 "4ee18816b0173d303e6f490b374ee0170b0cabbe3e626756186786551364e93a"
    end
  end

  def install
    bin.install "kubectl-claude"
  end

  test do
    system "#{bin}/kubectl-claude", "version"
  end
end
