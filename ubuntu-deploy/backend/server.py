"""Compatible launch command: python server.py."""
from app_backend import create_app, main, password_hash

__all__ = ['create_app', 'password_hash']

if __name__ == '__main__':
    main()
