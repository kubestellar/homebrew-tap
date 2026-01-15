# typed: false
# frozen_string_literal: true

# Placeholder - will be updated by GoReleaser on release
class KlaudeDeploy < Formula
  desc "App-centric multi-cluster deployment and operations for Kubernetes"
  homepage "https://github.com/kubestellar/klaude"
  version "0.0.0"
  license "Apache-2.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-deploy_0.0.0_darwin_arm64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-deploy"
      end
    end
    if Hardware::CPU.intel?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-deploy_0.0.0_darwin_amd64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-deploy"
      end
    end
  end

  on_linux do
    if Hardware::CPU.arm? && Hardware::CPU.is_64_bit?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-deploy_0.0.0_linux_arm64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-deploy"
      end
    end
    if Hardware::CPU.intel? && Hardware::CPU.is_64_bit?
      url "https://github.com/kubestellar/klaude/releases/download/v0.0.0/klaude-deploy_0.0.0_linux_amd64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      def install
        bin.install "klaude-deploy"
      end
    end
  end

  test do
    system "#{bin}/klaude-deploy", "version"
  end
end
