# clickerBot NixOS flake

This flake packages the Telegram clicker bot, its assets and strings, and a
Python 3.12 runtime containing the `aiogram` and `python-dotenv` dependencies.
It exports a NixOS module, package/app outputs, a development shell, and an
overlay.

## NixOS

Add the flake as an input and import its module in the host configuration:

```nix
{
  inputs.clicker-bot.url = "github:TimurSl/clickerBot/momer";

  outputs = { self, nixpkgs, clicker-bot, ... }:
    {
      nixosConfigurations.bot = nixpkgs.lib.nixosSystem {
        modules = [
          ./hardware-configuration.nix
          clicker-bot.nixosModules.default
          {
            services.clicker-bot = {
              enable = true;
              tokenFile = "/run/secrets/clicker-bot-token";
            };
          }
        ];
      };
    };
}
```

Run the host with `nixos-rebuild switch --flake .#bot`. The repository's
`nix/hosts/clicker-bot.nix` is also a ready-to-copy service configuration with
example tuning values. The token path above is only a placeholder; provision
the file with agenix, sops-nix, systemd credentials, or another host-specific
secret mechanism. The file must contain only the token, for example:

```text
123456:replace-me
```

The service fails at evaluation time unless either `tokenFile` or
`environment.BOT_TOKEN` is configured. `tokenFile` is preferred: putting a
literal token in Nix `environment` makes it part of the evaluated system
configuration and potentially the Nix store. An optional `environmentFile`
can hold non-secret settings in systemd EnvironmentFile syntax.

## Module options

`services.clicker-bot` provides:

- `enable` — enable the hardened `clicker-bot` systemd service.
- `tokenFile` — path to a raw token file, loaded through systemd credentials.
- `environmentFile` — optional systemd EnvironmentFile for non-secret settings.
- `environment` — additional bot settings such as cooldowns and investment
  limits.
- `databasePath` — SQLite path, defaulting to `/var/lib/clicker-bot/clicker.db`.
- `readWritePaths` — additional paths writable under filesystem hardening.
- `package` — override the package supplied by this flake.
- `stateDirectory` — systemd state directory name, defaulting to
  `/var/lib/clicker-bot`.
- `user` and `group` — dedicated service account defaults.

SQLite state is stored at `/var/lib/clicker-bot/clicker.db` by default and is
created through systemd's persistent `StateDirectory`. The service uses a
dedicated system user, strict filesystem protection, no new privileges, a
private temporary directory, restricted address families, and automatic
restart on failure.

## Useful commands

```console
$ nix run .
$ nix build .#clicker-bot
$ nix develop
$ nix flake check
```

Set `BOT_TOKEN` in the development shell environment before running the bot.
The packaged executable reads all source-relative assets from its immutable
store path while keeping its mutable SQLite database in the service state
directory.
