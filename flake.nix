{
  description = "Simple speech-to-text for NixOS with GPU support";

  nixConfig = {
    extra-substituters = [
      "https://cuda-maintainers.cachix.org"
    ];
    extra-trusted-public-keys = [
      "cuda-maintainers.cachix.org-1:0dq3bujKpuEPMCX6U4WylrUDZ9JyUG0VpVZa7CNfq5E="
    ];
  };

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";

      # GPU build (CUDA)
      pkgsCuda = import nixpkgs {
        inherit system;
        config = {
          allowUnfree = true;
          cudaSupport = true;
          # Only build for mainstream desktop GPUs; forward compat covers newer archs via PTX.
          # To support all architectures, remove these two lines and use a larger CI runner
          # (see: https://docs.github.com/en/actions/using-github-hosted-runners/using-larger-runners).
          cudaCapabilities = [ "7.5" "8.6" "8.9" ];
          cudaForwardCompat = true;
        };
      };

      # CPU-only build (fast, no CUDA)
      pkgsCpu = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };

      mkSttNix = pkgs:
        let
          python = pkgs.python313;
        in
        python.pkgs.buildPythonApplication {
          pname = "stt-nix";
          version = "0.1.0";
          src = self;
          pyproject = true;

          build-system = [ python.pkgs.setuptools ];

          dependencies = with python.pkgs; [
            faster-whisper
            sounddevice
            dbus-fast
            evdev
            httpx
            numpy
            tomli
          ];

          nativeBuildInputs = [ pkgs.makeWrapper ];

          postInstall = ''
            mkdir -p $out/lib/python3.13/site-packages/stt_nix/icons
            cp assets/icons/*.png $out/lib/python3.13/site-packages/stt_nix/icons/
          '';

          postFixup = ''
            wrapProgram $out/bin/stt \
              --prefix PATH : ${pkgs.lib.makeBinPath [
                pkgs.wl-clipboard
                pkgs.dotool
              ]}
            wrapProgram $out/bin/stt-nix \
              --prefix PATH : ${pkgs.lib.makeBinPath [
                pkgs.wl-clipboard
                pkgs.dotool
              ]}
          '';

          meta = {
            description = "Simple speech-to-text for NixOS with GPU support";
            mainProgram = "stt-nix";
          };
        };

    in
    {
      packages.${system} = {
        default = mkSttNix pkgsCuda;
        cpu = mkSttNix pkgsCpu;
      };

      overlays.default = final: prev: {
        stt-nix = self.packages.${final.stdenv.hostPlatform.system}.cpu;
        stt-nix-cuda = self.packages.${final.stdenv.hostPlatform.system}.default;
      };

      homeManagerModules.default = import ./module.nix;

      apps.${system} = {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/stt-nix";
        };
        stt = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/stt";
        };
      };
    };
}
