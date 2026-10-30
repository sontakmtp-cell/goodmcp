"""One approved calculator invocation per isolated container; no search runtime."""
import json
import os
import resource
import socket
import sys
import time
from pathlib import Path
from common import canonical


def probes(args):
    # Only an operator-only fixture binding can select this trusted test adapter.
    kind=args['kind']
    if kind=='sleep':time.sleep(120)
    if kind=='crash':os._exit(17)
    if kind=='boundaries':
        checks={}
        for path in ('/run/secrets/runtime_password','/data','/var/run/docker.sock','/plugin/../run/secrets/admin_password'):
            checks[path]=not Path(path).exists()
        try:Path('/plugin/forbidden').write_text('bad'); checks['source_readonly']=False
        except OSError:checks['source_readonly']=True
        try:socket.create_connection(('1.1.1.1',443),timeout=1); checks['network_denied']=False
        except OSError:checks['network_denied']=True
        Path('/job/allowed').write_text('private ephemeral job output');checks['job_writable']=True
        return {'data':checks,'warnings':[]}
    raise ValueError('Invalid probe')



def main():
    start=time.monotonic();request=json.loads(os.environ['HUB_JOB_INPUT'])
    from adapter import run
    try:
        result=probes(request['arguments']) if request['operation']=='_probe' else run(request['operation'],request['arguments'])
        result.update(ok=True,metrics={'operation_s':time.monotonic()-start,'peak_rss_MiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
        print(canonical(result))
    except Exception:
        print(canonical({'ok':False,'error':'validation'}));sys.exit(2)


if __name__=='__main__':main()
