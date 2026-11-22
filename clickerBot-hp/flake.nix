{
  description = "Reusable NixOS module and package for the clickerBot Telegram bot";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      forAllSystems =
        function: lib.genAttrs systems (system: function (import nixpkgs { inherit system; }));

      mkPackage =
        pkgs:
        let
          pythonRuntime = pkgs.python312.withPackages (pythonPackages: [
            pythonPackages.aiogram
            pythonPackages."python-dotenv"
          ]);

          source = pkgs.lib.cleanSourceWith {
            src = ./.;
            filter =
              path: _type:
              let
                name = builtins.baseNameOf (toString path);
              in
              !(builtins.elem name [
                ".git"
                ".direnv"
                ".venv"
                "__pycache__"
                "result"
              ])
              && name != ".env"
              && !(pkgs.lib.hasSuffix ".db" name)
              && !(pkgs.lib.hasSuffix ".pyc" name)
              && !(pkgs.lib.hasSuffix ".pyo" name)
              && !(pkgs.lib.hasSuffix "-journal" name)
              && !(pkgs.lib.hasSuffix "-wal" name)
              && !(pkgs.lib.hasSuffix "-shm" name);
          };
        in
        pkgs.stdenvNoCC.mkDerivation {
          pname = "clicker-bot";
          version = "0.1.0";
          src = source;

          nativeBuildInputs = [ pkgs.makeWrapper ];
          dontConfigure = true;
          dontBuild = true;

          installPhase = ''
            runHook preInstall
            install -d "$out/bin" "$out/lib/clicker-bot"
            cp -R . "$out/lib/clicker-bot"
            makeWrapper "${pythonRuntime}/bin/python" "$out/bin/clicker-bot" \
              --add-flags "$out/lib/clicker-bot/main.py"
            runHook postInstall
          '';

          passthru.pythonRuntime = pythonRuntime;

          meta = {
            description = "Telegram clicker game bot";
            homepage = "https://github.com/TimurSl/clickerBot/tree/momer";
            platforms = lib.platforms.unix;
            mainProgram = "clicker-bot";
          };
        };
    in
    {
      packages = forAllSystems (
        pkgs:
        let
          package = mkPackage pkgs;
        in
        {
          default = package;
          clicker-bot = package;
        }
      );

      apps = forAllSystems (
        pkgs:
        let
          package = self.packages.${pkgs.system}.default;
          app = {
            type = "app";
            program = "${package}/bin/clicker-bot";
          };
        in
        {
          default = app;
          clicker-bot = app;
        }
      );

      devShells = forAllSystems (
        pkgs:
        let
          pythonRuntime = pkgs.python312.withPackages (pythonPackages: [
            pythonPackages.aiogram
            pythonPackages."python-dotenv"
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [
              pythonRuntime
              pkgs.sqlite
            ];
            shellHook = ''
              run-bot() {
                exec ${pythonRuntime}/bin/python ./main.py "$@"
              }
              echo "clickerBot shell ready; use run-bot after setting BOT_TOKEN"
            '';
          };
        }
      );

      checks = forAllSystems (pkgs: {
        package = self.packages.${pkgs.system}.default;
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);

      overlays.default = final: _prev: {
        clicker-bot = self.packages.${final.system}.default;
      };

      nixosModules.default =
        moduleArgs@{ pkgs, ... }:
        import ./nix/modules/clicker-bot.nix (
          moduleArgs
          // {
            clickerBotPackage = self.packages.${pkgs.system}.default;
          }
        );

      nixosModules.clicker-bot = self.nixosModules.default;
    };
}
