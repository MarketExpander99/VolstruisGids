import os
import sys

def _switch_to_venv_python():
    """If we're not already running under .venv, re-launch using the venv python.
    This makes `python run.py` work even if the user forgot to activate.
    """
    exe = sys.executable.replace('\\', '/').lower()
    if '/.venv/' in exe or '\\.venv\\' in exe.lower():
        return  # already correct

    # Locate the project's .venv python
    here = os.path.dirname(os.path.abspath(__file__))
    venv_py = os.path.join(here, '.venv', 'Scripts', 'python.exe')

    if os.path.isfile(venv_py):
        print(">>> Auto-switching to project .venv Python (so imports work)...")
        # Replace current process with the venv interpreter running the same script + args
        os.execv(venv_py, [venv_py] + sys.argv)

_switch_to_venv_python()

try:
    from app import create_app
except ModuleNotFoundError as e:
    print("\n" + "="*60)
    print("ERROR: Missing Python package -", e)
    print("="*60)
    print("\nYou are probably using the wrong Python interpreter.")
    print("This project requires the virtual environment (.venv).")
    print("\nEASIEST FIX (Windows):")
    print("  Run one of these instead of 'python run.py':")
    print("    .\\start-dev.ps1     (PowerShell)")
    print("    start-dev.bat       (Command Prompt)")
    print("\nOr simply use:")
    print("  .\\.venv\\Scripts\\python.exe run.py")
    print("="*60 + "\n")
    sys.exit(1)

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)