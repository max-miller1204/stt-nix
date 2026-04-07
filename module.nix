{ config, lib, pkgs, ... }:

let
  cfg = config.services.stt-nix;
  tomlFormat = pkgs.formats.toml { };
  configFile = tomlFormat.generate "stt-nix-config.toml" cfg.settings;
in
{
  options.services.stt-nix = {
    enable = lib.mkEnableOption "stt-nix speech-to-text daemon";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.stt-nix;
      description = "The stt-nix package to use.";
    };

    groqApiKeyFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = ''
        Path to a file containing the Groq API key in the format:
        GROQ_API_KEY=gsk_...
      '';
    };

    settings = lib.mkOption {
      type = tomlFormat.type;
      default = { };
      description = "Configuration for stt-nix (written to config.toml).";
      example = lib.literalExpression ''
        {
          transcription = {
            backend = "groq";
            language = "en";
          };
          output.paste_key = "ctrl+shift+v";
          hotkey = {
            enabled = true;
            key = "ctrl+space";
            mode = "hold";
          };
        }
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    xdg.configFile."stt-nix/config.toml".source = configFile;

    systemd.user.services.stt-nix = {
      Unit = {
        Description = "STT Nix speech-to-text daemon";
        PartOf = [ "graphical-session.target" ];
        After = [ "graphical-session.target" ];
      };

      Service = {
        ExecStart = "${cfg.package}/bin/stt-nix";
        Restart = "on-failure";
        RestartSec = 5;
      } // lib.optionalAttrs (cfg.groqApiKeyFile != null) {
        EnvironmentFile = cfg.groqApiKeyFile;
      };

      Install = {
        WantedBy = [ "graphical-session.target" ];
      };
    };
  };
}
