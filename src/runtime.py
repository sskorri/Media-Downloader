"""Select the local interpreter for a source checkout or a portable build."""

import os
import subprocess
import sys
from pathlib import Path


def use_project_python(entrypoint: str) -> None:
    script = Path(entrypoint).resolve()
    root = Path(__file__).resolve().parents[1]
    python_name = "python"
    if os.name == "nt":
        python_name = "pythonw.exe" if Path(sys.executable).name.lower() == "pythonw.exe" else "python.exe"
    runtime = root / "runtime"
    venv = root / ".venv"
    if (runtime / "python.exe").is_file():
        if Path(sys.executable).resolve().parent == runtime:
            tools = str(runtime / "bin")
            search_path = os.get_exec_path()
            if not search_path or Path(search_path[0]) != Path(tools):
                os.environ["PATH"] = os.pathsep.join([tools, *search_path])
            return
        python = runtime / python_name
    else:
        if sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == venv.resolve():
            return
        python = venv / ("Scripts" if os.name == "nt" else "bin") / python_name
    if not python.is_file():
        raise SystemExit(f"Project interpreter missing. Follow the install steps in {root / 'README.md'}.")
    raise SystemExit(subprocess.call([str(python), str(script), *sys.argv[1:]]))
