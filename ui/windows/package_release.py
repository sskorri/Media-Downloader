"""Package the root launcher and application with fresh portable settings."""

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


def package_release(dist: Path, *, bundle_runtime: bool = False) -> Path:
    project = dist.parent
    name = "Media Downloader"
    suffix = "-Full" if bundle_runtime else ""
    archive = dist / f"Media-Downloader-Windows-x64{suffix}.zip"
    runtime = dist / name / "runtime"
    if not (project / "Media Downloader.exe").is_file():
        raise FileNotFoundError("Build the root launcher with ui/windows/build_gui.ps1 first.")
    if bundle_runtime and not (runtime / "pythonw.exe").is_file():
        raise FileNotFoundError("Run ui/windows/build_gui.ps1 -BundleRuntime first.")

    app_files = [
        project / relative for relative in (
            "Media Downloader.exe", "cli.py", "README.md", "LICENSE", "requirements.txt",
            "ui/index.html", "ui/requirements.txt", "ui/windows/setup.cmd",
        )
    ]
    for pattern in ("src/*.py", "ui/*.py", "ui/assets/**/*"):
        app_files.extend(path for path in sorted(project.glob(pattern)) if path.is_file())

    dist.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dist) as temporary:
        staged = Path(temporary) / archive.name
        with ZipFile(staged, "w", compression=ZIP_DEFLATED, compresslevel=5) as output:
            for path in app_files:
                output.write(path, f"{name}/{path.relative_to(project).as_posix()}")
            if bundle_runtime:
                for folder, directories, files in os.walk(runtime):
                    if "__pycache__" in directories:
                        directories.remove("__pycache__")
                    for filename in files:
                        path = Path(folder) / filename
                        if path.suffix not in (".pyc", ".pyo"):
                            output.write(path, f"{name}/runtime/{path.relative_to(runtime).as_posix()}")
            output.writestr(f"{name}/data/settings.json", '{"download_dir":"media"}\n')
            output.writestr(f"{name}/media/", "")
        staged.replace(archive)
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-runtime", action="store_true", help="Include the full Windows runtime")
    args = parser.parse_args()
    print(package_release(Path(__file__).resolve().parents[2] / "dist", bundle_runtime=args.bundle_runtime))
