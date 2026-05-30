# Sourced via BASH_ENV for Claude Code's non-interactive Bash tool shells.
# Those shells are non-login AND non-interactive, so they source neither
# ~/.profile nor ~/.bashrc (the latter early-returns for non-interactive
# shells). This file restores Node (nvm) and Rust (cargo) on PATH so quality
# gates and npm/cargo commands work without a manual `export PATH=...` prelude.
# Idempotent: safe to source repeatedly (BASH_ENV runs for every subshell).

# Rust / cargo (native Linux toolchain at ~/.cargo/bin)
if [ -d "$HOME/.cargo/bin" ]; then
  case ":$PATH:" in
    *":$HOME/.cargo/bin:"*) ;;
    *) PATH="$HOME/.cargo/bin:$PATH" ;;
  esac
fi

# Node via nvm — select the highest installed version (currently v20.20.2)
if [ -d "$HOME/.nvm/versions/node" ]; then
  _abe_node_bin="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"
  if [ -n "$_abe_node_bin" ]; then
    case ":$PATH:" in
      *":$_abe_node_bin:"*) ;;
      *) PATH="$_abe_node_bin:$PATH" ;;
    esac
  fi
  unset _abe_node_bin
fi

export PATH
