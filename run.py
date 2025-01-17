# run.py
import argparse
import os
import sys
from app import app, db
from app.models import *

def parse_args():
    parser = argparse.ArgumentParser(description='Start the VDI API server.')
    parser.add_argument('command', choices=['run', 'initdb', 'migratedb'], help='Command to execute')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Hostname to listen on')
    parser.add_argument('--port', type=int, default=5575, help='Port to listen on')
    parser.add_argument('--cert', type=str, default='certs/fullchain.pem', help='Path to the SSL certificate')
    parser.add_argument('--key', type=str, default='certs/privkey.pem', help='Path to the SSL key')
    return parser.parse_args()

def main():
    args = parse_args()

    if args.command == 'initdb':
        with app.app_context():
            db.create_all() # Ensure that this is within the application context
        print("Database initialised.")
    elif args.command == 'migrate':
        migrated_db()
        print("Database migrated.")
    elif args.command == 'run':
        context = (args.cert, args.key) 
        app.run(host=args.host, port=args.port, ssl_context=context, debug=True)
    else:
        print("Unknown command.")

def migrate_db():
    pass

if __name__ == "__main__":
    main()
