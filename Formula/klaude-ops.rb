# typed: false
# frozen_string_literal: true

# Placeholder - will be updated by GoReleaser on release
class KlaudeOps < Formula
  desc "Multi-cluster Kubernetes diagnostics, RBAC analysis, and security checks"
  homepage "https://github.com/kubestellar/klaude"
  version "0.0.0"
  license "Apache-2.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-ops_0.0.0_darwin_arm64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-ops"
      end
    end
    if Hardware::CPU.intel?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-ops_0.0.0_darwin_amd64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-ops"
      end
    end
  end

  on_linux do
    if Hardware::CPU.arm? && Hardware::CPU.is_64_bit?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-ops_0.0.0_linux_arm64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-ops"
      end
    end
    if Hardware::CPU.intel? && Hardware::CPU.is_64_bit?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-ops_0.0.0_linux_amd64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-ops"
      end
    end
  end

  test do
    system "#{bin}/klaude-ops", "version"
  end
end
