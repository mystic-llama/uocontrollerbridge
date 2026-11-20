"""Maintainer build. End users install the generated application, never run this."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import os
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent


def copy_dependency_licenses(target):
    licenses = target / 'licenses'
    shutil.copytree(ROOT / 'packaging' / 'licenses', licenses, dirs_exist_ok=True)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        (licenses / 'CPython').mkdir(exist_ok=True)
        shutil.copy2(python_license, licenses / 'CPython' / 'LICENSE.txt')

    for distribution in metadata.distributions():
        package = distribution.metadata.get('Name', 'dependency')
        for entry in distribution.files or []:
            name = entry.name.lower()
            if not name.startswith(('license', 'licence', 'copying', 'copyright', 'notice', 'lgpl')):
                continue
            if entry.suffix.lower() in {'.py', '.pyc', '.pyo'}:
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file():
                continue
            destination = licenses / package / entry.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                digest = hashlib.sha256(str(entry).encode()).hexdigest()[:8]
                destination = destination.with_name(digest + '-' + destination.name)
            shutil.copy2(source, destination)


def main():
    if os.name!='nt': raise SystemExit('Build Windows releases on Windows or use the included GitHub Actions workflow.')
    from controller_bridge import VERSION
    os.chdir(ROOT)
    subprocess.run([sys.executable,'-m','unittest','discover','-v'],check=True)
    # A folder bundle avoids temporary executable extraction during an administrator restart.
    subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--windowed','--onedir',
        '--name','ControllerStudio','--icon','assets/studio.ico',
        '--add-data','bindings.defaults.json;.', '--add-data','razor_listener.py;.',
        '--add-data','assets;assets', '--hidden-import','pynput.keyboard._win32',
        '--hidden-import','pynput.mouse._win32', '--exclude-module','tkinter',
        'app.py'],check=True)
    target=ROOT/'dist'/'ControllerStudio'
    for name in ['README.md','LICENSE','THIRD_PARTY_NOTICES.md']:
        shutil.copy2(ROOT/name,target/name)
    shutil.copytree(ROOT/'docs',target/'docs',dirs_exist_ok=True)
    copy_dependency_licenses(target)
    output=ROOT/'release';output.mkdir(exist_ok=True)
    portable=output/('ControllerStudio-'+VERSION+'-Windows-portable.zip')
    with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in target.rglob('*'):
            if file.is_file(): archive.write(file,file.relative_to(target.parent))
    compiler=shutil.which('ISCC') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if not Path(compiler).is_file(): raise SystemExit('Install Inno Setup 6 to produce the installer. The portable build is ready in release/.')
    subprocess.run([compiler,'/DAppVersion='+VERSION,str(ROOT/'packaging'/'installer.iss')],check=True)
    installer = output / ('ControllerStudio-' + VERSION + '-Windows-Setup.exe')
    files = sorted((portable, installer))
    (output/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files),encoding='utf-8')
    print('Windows packages created in',output)


if __name__=='__main__': main()
