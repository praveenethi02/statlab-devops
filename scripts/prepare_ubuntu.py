"""Refresh the self-contained Ubuntu deployment copy and create its transfer ZIP."""
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'ubuntu-deploy'


def main():
    files = []

    def copy(source, destination):
        target = BUNDLE / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
        files.append(target)

    copy('hrml', 'frontend/index.html')
    for name in ('package.json', 'package-lock.json', 'nginx.conf', 'scripts/vendor.mjs'):
        copy(name, 'frontend/' + name)
    for source in sorted((ROOT / 'static').rglob('*')):
        if source.is_file() and 'vendor' not in source.relative_to(ROOT / 'static').parts:
            copy(source.relative_to(ROOT), Path('frontend') / source.relative_to(ROOT))
    for name in ('server.py', 'app_backend.py', 'database.py', 'statistics_engine.py', 'reports.py', 'requirements.txt', 'scripts/maintenance.py'):
        copy(name, 'backend/' + name)
    for source in sorted((ROOT / 'migrations').glob('*.sql')):
        copy(source.relative_to(ROOT), Path('backend') / source.relative_to(ROOT))
    files.extend(BUNDLE / name for name in (
        'compose.yaml', '.env.example', 'setup_env.py', 'README.md',
        'frontend/Dockerfile', 'frontend/.dockerignore',
        'backend/Dockerfile', 'backend/.dockerignore',
    ))
    archive = ROOT / 'output' / 'statlab-ubuntu.zip'
    archive.parent.mkdir(exist_ok=True)
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as output:
        for source in sorted(files):
            output.write(source, Path('ubuntu-deploy') / source.relative_to(BUNDLE))
    print(f'Prepared {len(files)} files in {BUNDLE}')
    print(f'Transfer archive: {archive}')


if __name__ == '__main__':
    main()
