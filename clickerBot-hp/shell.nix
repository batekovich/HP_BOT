{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312.withPackages (pythonPackages: [
    pythonPackages.pip
  ]);
in
pkgs.mkShell {
  packages = [
    python
    pkgs.sqlite
  ];

  shellHook = ''
    export VIRTUAL_ENV="$PWD/.venv"

    if [ -x "$VIRTUAL_ENV/bin/python" ] && ! "$VIRTUAL_ENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1; then
      echo "Replacing the existing virtualenv with a Python 3.12 virtualenv..."
      rm -rf "$VIRTUAL_ENV"
    fi

    if [ ! -x "$VIRTUAL_ENV/bin/python" ]; then
      python -m venv --system-site-packages "$VIRTUAL_ENV"
    fi

    . "$VIRTUAL_ENV/bin/activate"

    if ! python -c 'import aiogram, dotenv' >/dev/null 2>&1; then
      echo "Installing Python dependencies from requirements.txt..."
      if ! python -m pip install --disable-pip-version-check -r requirements.txt; then
        echo "Dependency installation failed; the shell is not ready." >&2
        return 1
      fi
    fi

    run-bot() {
      python main.py
    }

    echo "clickerBot shell ready"
    echo "Run: run-bot"
  '';
}
