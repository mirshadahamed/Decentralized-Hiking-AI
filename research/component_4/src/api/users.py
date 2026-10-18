"""Manage staff accounts from the command line (passwords are typed, never passed as arguments).

    python -m src.api.users add --username ranger1 --role ranger
    python -m src.api.users list
"""
import argparse
import getpass

from src.api import auth


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--username", required=True)
    add.add_argument("--role", required=True, choices=list(auth.ROLES))
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "add":
        pw = getpass.getpass("Password (min 10 characters): ")
        if pw != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords do not match")
        auth.create_user(a.username, pw, a.role)
        print(f"created {a.role} {a.username}")
    else:
        for u in auth.users():
            print(f"{u['username']:<20} {u['role']:<8} {'active' if u['active'] else 'disabled'}  {u['created']}")


if __name__ == "__main__":
    main()
