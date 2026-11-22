{
  config,
  lib,
  pkgs,
  clickerBotPackage ? null,
  ...
}:

let
  cfg = config.services.clicker-bot;
  statePath = "/var/lib/${cfg.stateDirectory}";
  databasePath = if cfg.databasePath == null then "${statePath}/clicker.db" else cfg.databasePath;
  startScript = pkgs.writeShellScript "clicker-bot-start" ''
    ${lib.optionalString (cfg.tokenFile != null) ''
      export BOT_TOKEN="$(${pkgs.coreutils}/bin/tr -d '\r\n' < "$CREDENTIALS_DIRECTORY/bot-token")"
    ''}
    exec ${cfg.package}/bin/clicker-bot
  '';
in
{
  options.services.clicker-bot = {
    enable = lib.mkEnableOption "the clickerBot Telegram bot";

    package = lib.mkOption {
      type = lib.types.package;
      default = clickerBotPackage;
      defaultText = lib.literalExpression "packages.default";
      description = ''
        Package containing the bot source, assets, and Python runtime. The
        flake's exported module supplies its default; override this to pin or
        replace the package.
      '';
    };

    tokenFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/run/secrets/clicker-bot-token";
      description = ''
        Path to a root-readable file containing only the Telegram bot token.
        The file is loaded as a systemd credential and is never copied into
        the Nix store. Keep it outside the flake and provision it with a
        secret manager or other host-specific mechanism.
      '';
    };

    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/etc/clicker-bot/environment";
      description = ''
        Optional systemd EnvironmentFile containing non-secret settings. This
        is useful for host-local overrides; use tokenFile for BOT_TOKEN.
      '';
    };

    environment = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = { };
      example = lib.literalExpression ''
        {
          CLICK_COOLDOWN = "5";
          INVEST_MAX_HOURS = "12";
        }'';
      description = ''
        Additional environment variables passed to the bot. DATABASE_PATH
        defaults to the persistent state directory. DATABASE_PATH is managed
        by databasePath and cannot be overridden here.
        Prefer tokenFile for BOT_TOKEN so secrets are not included in the Nix
        store or evaluated configuration.
      '';
    };

    databasePath = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/var/lib/clicker-bot/clicker.db";
      description = ''
        Absolute path to the SQLite database. It defaults to clicker.db inside
        the configured stateDirectory. If this is outside that directory,
        include its parent directory in readWritePaths.
      '';
    };

    readWritePaths = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [ "/var/lib/clicker-bot" ];
      description = ''
        Additional absolute paths that the service may write when the
        databasePath is outside the systemd StateDirectory.
      '';
    };

    stateDirectory = lib.mkOption {
      type = lib.types.str;
      default = "clicker-bot";
      description = ''
        Name of the systemd StateDirectory used for the SQLite database. This
        is a name below /var/lib, not an arbitrary filesystem path.
      '';
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "clicker-bot";
      description = "User under which the bot service runs.";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "clicker-bot";
      description = "Group under which the bot service runs.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion =
          (cfg.tokenFile != null && cfg.tokenFile != "")
          || (lib.hasAttr "BOT_TOKEN" cfg.environment && cfg.environment.BOT_TOKEN != "");
        message = "services.clicker-bot requires tokenFile or environment.BOT_TOKEN when enabled.";
      }
      {
        assertion = builtins.match "[A-Za-z0-9][A-Za-z0-9_.-]*" cfg.stateDirectory != null;
        message = "services.clicker-bot.stateDirectory must be a single safe directory name.";
      }
      {
        assertion = lib.hasPrefix "/" databasePath;
        message = "services.clicker-bot.databasePath must be an absolute path.";
      }
    ];

    users.groups.${cfg.group} = { };
    users.users.${cfg.user} = {
      isSystemUser = lib.mkDefault true;
      group = lib.mkDefault cfg.group;
    };

    systemd.services.clicker-bot = {
      description = "clickerBot Telegram bot";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];

      environment = cfg.environment // {
        DATABASE_PATH = databasePath;
      };

      serviceConfig = {
        ExecStart = "${startScript}";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = statePath;
        StateDirectory = cfg.stateDirectory;
        StateDirectoryMode = "0750";

        Restart = "on-failure";
        RestartSec = "5s";
        TimeoutStopSec = "30s";
        KillSignal = "SIGINT";
        UMask = "0077";

        NoNewPrivileges = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectControlGroups = true;
        RestrictNamespaces = true;
        RestrictSUIDSGID = true;
        RestrictRealtime = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        SystemCallArchitectures = "native";
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
          "AF_UNIX"
        ];
        ReadWritePaths = [ statePath ] ++ cfg.readWritePaths;
      }
      // lib.optionalAttrs (cfg.tokenFile != null) {
        LoadCredential = [ "bot-token:${cfg.tokenFile}" ];
      }
      // lib.optionalAttrs (cfg.environmentFile != null) {
        EnvironmentFile = [ cfg.environmentFile ];
      };
    };
  };
}
