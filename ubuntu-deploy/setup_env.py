"""Create a fresh server configuration without printing its signing secret."""
import argparse
import ipaddress
import re
import secrets
from pathlib import Path


def host_name(value):
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        if len(value) <= 253 and all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part) for part in value.split('.')):
            return value
    raise argparse.ArgumentTypeError('Use an IP address or hostname without a scheme, port, or path.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', action='append', type=host_name, default=[], help='Ubuntu server IP or hostname; repeat to allow several.')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535.')
    target = Path(__file__).resolve().parent / '.env'
    hosts = ','.join(dict.fromkeys(['localhost', '127.0.0.1', *args.host]))
    try:
        with target.open('x', encoding='utf-8', newline='\n') as output:
            target.chmod(0o600)
            output.write(f'APP_SECRET={secrets.token_hex(32)}\nALLOWED_HOSTS={hosts}\nBIND_ADDRESS=0.0.0.0\nHTTP_PORT={args.port}\n')
    except FileExistsError:
        parser.error('.env already exists; edit it in place to preserve the signing key.')
    print(f'Created {target.name}. Allowed hosts: {hosts}. HTTP port: {args.port}.')


if __name__ == '__main__':
    main()
