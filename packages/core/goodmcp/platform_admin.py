"""Explicit operator provisioning; workspace ownership never confers platform rights."""
import argparse
import json
from uuid import UUID

from .admin import connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--user-id', type=UUID, required=True)
    args = parser.parse_args()
    with connect() as conn:
        row = conn.execute('UPDATE users SET platform_admin=true WHERE id=%s AND active RETURNING id', (args.user_id,)).fetchone()
        if row is None:
            raise RuntimeError('Active account not found')
        conn.execute("INSERT INTO platform_audit_events(actor_user_id,action,details) VALUES(%s,'platform.operator_provisioned','{}')", (args.user_id,))
    print(json.dumps({'platform_admin_user_id': str(row[0])}))


if __name__ == '__main__':
    main()
