"""
Build script for freezing Ragger Engine into a standalone onedir distribution via PyInstaller.
Produces engine/dist/engine/ragger-engine.exe.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent.parent
    engine_dir = root_dir / "engine"
    main_py = engine_dir / "ragger_engine" / "main.py"
    dist_dir = engine_dir / "dist"
    build_dir = engine_dir / "build"
    spec_dir = engine_dir

    print(f"=== [Bundle Engine] Starting PyInstaller Freeze ===")
    print(f"  Root Dir:   {root_dir}")
    print(f"  Engine Dir: {engine_dir}")
    print(f"  Main Entry: {main_py}")
    print(f"  Dist Dir:   {dist_dir}")

    # Resolve python in .venv
    venv_py = engine_dir / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = Path(sys.executable)

    print(f"  Python Bin: {venv_py}")

    hidden_imports = [
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "fastapi",
        "fastapi.middleware.cors",
        "pydantic",
        "pydantic_core",
        "pydantic_settings",
        "httpx",
        "httpcore",
        "h11",
        "lxml",
        "docx",
        "pptx",
        "openpyxl",
        "xlrd",
        "xlsxwriter",
        "pypdf",
        "pypdf._cryptography",
        "pypdf._utils",
        "pypdf.generic",
        "bs4",
        "soupsieve",
        "ragger_engine",
        "ragger_engine.api",
        "ragger_engine.api.routes",
        "ragger_engine.models",
        "ragger_engine.models.catalog",
        "ragger_engine.models.downloader",
        "ragger_engine.models.hardware",
        "ragger_engine.models.ollama_manager",
        "ragger_engine.models.service",
        "ragger_engine.recommendation",
        "ragger_engine.evaluation",
        "ragger_engine.retrieval",
        "ragger_engine.builder",
        "ragger_engine.ingestion",
        "ragger_engine.generation",
        "ragger_engine.generation.providers",
        "ragger_engine.generation.providers.gguf",
        "ragger_engine.generation.providers.ollama",
        "ragger_engine.agent_workspace",
        "ragger_engine.multi_rag",
        "llama_cpp",
        "onnxruntime",
    ]

    cmd = [
        str(venv_py),
        "-m", "PyInstaller",
        "--name", "engine",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(spec_dir),
        "--paths", str(engine_dir),
        "--collect-data", "ragger_engine",
        "--collect-all", "pypdf",
        "--collect-all", "llama_cpp",
        "--collect-all", "onnxruntime",
    ]

    for hi in hidden_imports:
        cmd.extend(["--hidden-import", hi])

    cmd.append(str(main_py))

    print(f"  Running PyInstaller command...")
    result = subprocess.run(cmd, cwd=str(engine_dir))
    if result.returncode != 0:
        print(f"FATAL: PyInstaller failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    target_engine_dir = dist_dir / "engine"
    output_exe = target_engine_dir / "ragger-engine.exe"
    # If PyInstaller created engine.exe from --name engine, rename executable to ragger-engine.exe
    if not output_exe.exists() and (target_engine_dir / "engine.exe").exists():
        if output_exe.exists():
            output_exe.unlink()
        (target_engine_dir / "engine.exe").rename(output_exe)

    if not output_exe.exists():
        print(f"FATAL: Expected output executable not found at {output_exe}", file=sys.stderr)
        sys.exit(1)

    size_mb = output_exe.stat().st_size / (1024 * 1024)
    print(f"[OK] Frozen engine created successfully at: {output_exe} ({size_mb:.2f} MB)")

    # Ensure bge-small-en-v1.5_tokenizer.json is present in the bundled engine's resources and root
    tok_source = root_dir / "storage" / "models" / "embedding" / "bge-small-en-v1.5_tokenizer.json"
    if tok_source.exists():
        engine_res_dir = target_engine_dir / "ragger_engine" / "resources"
        engine_res_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tok_source, engine_res_dir / "bge-small-en-v1.5_tokenizer.json")
        # Also copy directly into target_engine_dir for convenient fallback
        shutil.copy2(tok_source, target_engine_dir / "bge-small-en-v1.5_tokenizer.json")
        print(f"[OK] Bundled BGE tokenizer into {engine_res_dir}")

    print(f"=== [Bundle Engine] Completed Successfully ===")


if __name__ == "__main__":
    main()
