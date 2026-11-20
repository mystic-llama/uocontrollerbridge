#!/usr/bin/env python3
"""Single entry point for the desktop application and its console-free host child."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main():
    if '--host' in sys.argv:
        arguments=sys.argv[1:];arguments.remove('--host')
        try:
            from controller_bridge import main as run_host
            run_host(arguments)
            return 0
        except Exception as exc:
            parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--config',type=Path);parser.add_argument('--status',type=Path)
            args,_=parser.parse_known_args(arguments)
            if args.config:
                (args.config.parent/'host-error.log').write_text(traceback.format_exc(),encoding='utf-8')
            if args.status:
                from controller_bridge import save_config
                save_config(args.status,{'at':time.time(),'error':str(exc)})
            return 1
    parser=argparse.ArgumentParser(description='Mystic Llama Controller Studio')
    parser.add_argument('--data-dir',type=Path,help='Override per-user settings folder')
    args=parser.parse_args()
    from app_services import data_directory
    from desktop_app import main as run_gui
    return run_gui(data_directory(args.data_dir))


if __name__=='__main__':
    sys.exit(main())
