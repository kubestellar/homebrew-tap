# typed: false
# frozen_string_literal: true

class KubectlClaude < Formula
  desc "AI-powered multi-cluster Kubernetes management for Claude Code"
  homepage "https://github.com/kubestellar/kubectl-claude"
  license "Apache-2.0"
  version "0.3.0"

  on_macos do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.3.0/kubectl-claude_0.3.0_darwin_amd64.tar.gz"
      sha256 "f89727ec82a4b8e3338565fbed3909d9ba431104ce79d3b925f63d419aeee493"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.3.0/kubectl-claude_0.3.0_darwin_arm64.tar.gz"
      sha256 "d03e48a253abe8413f7aa58c2c4303e06fb14f195a7f3b15e9e7d2d96111f216"
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.3.0/kubectl-claude_0.3.0_linux_amd64.tar.gz"
      sha256 "0317905596ace7d50e33de79cdc78d504ecebbd35648d8ffa297a881aa46d288"
    end
    on_arm do
      url "https://github.com/kubestellar/kubectl-claude/releases/download/v0.3.0/kubectl-claude_0.3.0_linux_arm64.tar.gz"
      sha256 "b0083981106b5a21f2d2a925213e6fa54389bd629f477ec5c3c8558f158e0801"
    end
  end

  def install
    bin.install "kubectl-claude"
  end

  test do
    system "#{bin}/kubectl-claude", "version"
  end
end
