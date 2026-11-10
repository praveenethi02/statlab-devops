"""Explicit migration and online backup utility; never deletes an existing database."""
import argparse
import os
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['migrate','backup','restore'])
    parser.add_argument('--source', default=os.environ.get('DATABASE_PATH','accounts.sqlite3'))
    parser.add_argument('--target')
    parser.add_argument('--owner', type=int, help='Linux UID/GID for restored database')
    args = parser.parse_args()
    source = Path(args.source).resolve()
    if args.operation == 'migrate':
        database.initialize(source)
        print('Additive migrations applied.')
    else:
        if not source.is_file():
            parser.error('Source database does not exist.')
        if not args.target:
            parser.error('--target is required.')
        target = Path(args.target).resolve()
        if target.exists():
            parser.error('Target already exists; choose a new target. Existing data is never overwritten.')
        target.parent.mkdir(parents=True,exist_ok=True)
        database.backup(source,target)
        if args.operation == 'restore':
            database.initialize(target)
            if args.owner is not None and os.name != 'nt':
                os.chown(target,args.owner,args.owner)
        print(f'Database {args.operation} completed: {target}')
    with closing(database.connect(source)) as db:
        print('Integrity check:', db.execute('PRAGMA integrity_check').fetchone()[0])


if __name__ == '__main__':
    main()
