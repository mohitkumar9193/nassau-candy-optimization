"""Create a clean GitHub-ready source ZIP and checksum inventory."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT.parent/'project-1-github-ready.zip'
SKIP={'.git','__pycache__','.venv','venv','node_modules','.vercel','.pytest_cache','.idea','.vscode'}


def package():
    files=[]
    for path in sorted(ROOT.rglob('*')):
        relative=path.relative_to(ROOT)
        if not path.is_file() or any(part in SKIP for part in relative.parts):
            continue
        if path.name in {'secrets.toml','.DS_Store','Thumbs.db','package_manifest.json'} or path.suffix in {'.pyc','.log'} or path.name.startswith('.env'):
            continue
        files.append(path)
    manifest={'archive_root':'project-1','contains_secrets':False,
              'files':{path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    inventory=ROOT/'deployment/package_manifest.json'
    inventory.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(DEST,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in [*files,inventory]:
            archive.write(path, 'project-1/'+path.relative_to(ROOT).as_posix())
    digest=hashlib.sha256(DEST.read_bytes()).hexdigest()
    DEST.with_suffix('.zip.sha256').write_text(digest+'  '+DEST.name+'\n',encoding='utf-8')
    print(f'{DEST.name}: {len(files)+1} files, {DEST.stat().st_size:,} bytes, SHA256 {digest}')


if __name__=='__main__':
    package()
