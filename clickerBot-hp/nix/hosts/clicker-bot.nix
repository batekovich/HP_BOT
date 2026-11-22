{ ... }:

# Example host configuration. Import the flake module first, then adapt this
# file to the host's secret-management and networking conventions:
#
#   imports = [
#     clicker-bot.nixosModules.default
#     ./nix/hosts/clicker-bot.nix
#   ];
#
# The token file is deliberately only a path. No secret belongs in this file.
{
  services.clicker-bot = {
    enable = true;
    tokenFile = "/run/secrets/clicker-bot-token";

    # All values are strings because they are passed directly to systemd.
    # DATABASE_PATH is automatically set below /var/lib/clicker-bot.
    environment = {
      CLICK_COOLDOWN = "10";
      INVEST_MAX_HOURS = "24";
    };
  };
}
