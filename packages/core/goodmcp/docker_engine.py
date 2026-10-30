"""Small fixed Docker Engine API client used only by the privileged dispatcher.

No host path, command, image or environment from an invocation reaches create().
"""
import http.client
import json
import socket
import struct
from urllib.parse import urlencode, quote


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self,timeout=70):super().__init__('localhost',timeout=timeout)
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout);self.sock.connect('/var/run/docker.sock')


def demux(raw):
    out=bytearray();err=bytearray();offset=0
    while offset<len(raw):
        if offset+8>len(raw):raise RuntimeError('Invalid engine output')
        size=struct.unpack('>I',raw[offset+4:offset+8])[0];stream=raw[offset];offset+=8
        if offset+size>len(raw):raise RuntimeError('Truncated engine output')
        (out if stream==1 else err).extend(raw[offset:offset+size]);offset+=size
    return bytes(out),bytes(err)


class Engine:
    def request(self,method,path,body=None,*,binary=False):
        conn=UnixHTTP()
        try:
            conn.request(method,'/v1.45'+path,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json'})
            response=conn.getresponse();raw=response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise RuntimeError('Runner output exceeds limit')
            if response.status not in (200,201,204,304):raise RuntimeError('Engine request failed')
            return raw if binary else json.loads(raw) if raw else None
        finally:conn.close()

    def containers(self,project):
        return self.request('GET','/containers/json?'+urlencode({'all':'true','filters':json.dumps({'label':['goodmcp.project='+project]})}))

    def inspect(self,container):return self.request('GET','/containers/'+quote(container,safe='')+'/json')

    def remove(self,container):
        try:self.request('DELETE','/containers/'+quote(container,safe='')+'?force=true&v=true')
        except RuntimeError:
            # A concurrent fenced worker may already have removed the same owned container.
            if any(c['Id']==container for c in self.request('GET','/containers/json?all=true')):raise

    def create(self,project,name,image,*,payload):
        body={'Image':image,'User':'10001:10001','WorkingDir':'/job','Tty':False,
            'Cmd':['python','/runtime/main.py','light'],
            'Env':['OMP_NUM_THREADS=1','OPENBLAS_NUM_THREADS=1','MKL_NUM_THREADS=1']+(['HUB_JOB_INPUT='+json.dumps(payload,allow_nan=False)] if payload else []),
            'Labels':{'goodmcp.project':project,'goodmcp.runner':'light','goodmcp.job':name},
            'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true'],
                'PidsLimit':64,'Memory':256*1024*1024,'MemorySwap':256*1024*1024,
                'NanoCpus':1*1000000000,'Tmpfs':{'/tmp':'rw,noexec,nosuid,size=64m,uid=10001,gid=10001','/job':'rw,noexec,nosuid,size=16m,uid=10001,gid=10001'},
                'LogConfig':{'Type':'json-file','Config':{'max-size':'2m','max-file':'1'}}}}
        container=self.request('POST','/containers/create?'+urlencode({'name':name}),body)['Id']
        self.request('POST','/containers/'+container+'/start');return container

    def output(self,container):
        state=self.inspect(container)['State']
        if state.get('OOMKilled'):raise RuntimeError('oom')
        if state['ExitCode']!=0:raise RuntimeError('tool_exit')
        stdout,stderr=demux(self.request('GET','/containers/'+container+'/logs?stdout=true&stderr=true',binary=True))
        return json.loads(stdout)
