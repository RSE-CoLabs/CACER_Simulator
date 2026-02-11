def setup_venv(venv_path=".venv", requirements_file="requirements.txt"):

    """
    Setup a virtual environment in the specified path.

    Parameters
    ----------
    venv_path : str, optional
        The path where the virtual environment will be created. Defaults to ".venv".
    requirements_file : str, optional
        The path to the requirements.txt file containing the packages to install. Defaults to "requirements.txt".

    Returns
    -------
    None
    """
    
    import os
    import subprocess
    import sys
    from pathlib import Path

    venv_path = Path(venv_path)
    python_exe = venv_path / "Scripts" / "python.exe" if os.name == "nt" else venv_path / "bin" / "python" # Percorso all'eseguibile Python nel venv

    # 1️⃣ Crea il virtual environment se non esiste
    if not venv_path.exists():
        print(f"⚙️ Creazione del virtual environment in {venv_path}...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)]) # Crea il venv
    else:
        print(f"✅ Virtual environment già presente in {venv_path}")

    # 2️⃣ Installa i pacchetti dal requirements.txt (se esiste)
    if Path(requirements_file).exists():
        print(f"📦 Installazione pacchetti da {requirements_file}...")
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"]) # Aggiorna pip
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "-r", requirements_file]) # Installa i pacchetti
    else:
        print(f"⚠️ Nessun file '{requirements_file}' trovato. Nessun pacchetto installato.")

    # 3️⃣ Suggerisci come usare il nuovo ambiente nel notebook
    print("\n🎉 Virtual environment pronto!")
    print(f"📍 Percorso: {venv_path}")
    print("\n💡 Per usare questo ambiente nel notebook, esegui:")
    print(f"!{python_exe} -m ipykernel install --user --name={venv_path.name} --display-name '{venv_path.name}'")
    print("Poi riavvia il kernel e seleziona il nuovo ambiente da Kernel → Change Kernel → .venv")


if __name__ == "__main__":
    setup_venv()