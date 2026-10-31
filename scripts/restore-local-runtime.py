"""Restore the exact approved OCI image from retained local BuildKit history.

No release/database/binding is reapproved or edited. The original image index,
platform manifest, config, layers and attestations are all digest-checked before
Docker loads the recovered archive. This is an operator CLI, never an HTTP API.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(list(args), cwd=ROOT)


def blob_name(digest):
    algorithm, value = digest.split(':', 1)
    if algorithm != 'sha256' or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Expected an immutable SHA-256 image descriptor')
    return 'blobs/sha256/' + value


def validated(raw, descriptor):
    if len(raw) != descriptor['size'] or hashlib.sha256(raw).hexdigest() != descriptor['digest'].split(':')[1]:
        raise ValueError('Retained image content does not match its approved descriptor')
    return raw


def restore(release_path, build_ref, source_image, output, supplemental=None):
    release = json.loads(release_path.read_text())
    expected = release['image_digest']
    blob_name(expected)
    record = json.loads(command('docker', 'buildx', 'history', 'inspect', build_ref, '--format', 'json'))
    if not any(a['Digest'] == expected and a['Type'] == 'application/vnd.oci.image.index.v1+json' for a in record['Attachments']):
        raise ValueError('Build history does not contain the approved image index')
    original = command('docker', 'buildx', 'history', 'inspect', 'attachment', build_ref, expected)
    descriptor = {'digest': expected, 'size': len(original), 'mediaType': 'application/vnd.oci.image.index.v1+json'}
    validated(original, descriptor)
    output.mkdir(parents=True, exist_ok=True)
    source_tar = output / 'source-image.tar'
    subprocess.run(['docker', 'image', 'save', source_image, '--output', str(source_tar)], cwd=ROOT, check=True)
    recovered_tar = output / 'approved-image.tar'
    fetched = {blob_name(expected): original}
    descriptors = {}
    with tarfile.open(source_tar) as source:
        members = {m.name: m for m in source.getmembers()}

        def read(desc):
            name = blob_name(desc['digest'])
            if name in fetched:
                return validated(fetched[name], desc)
            if name in members:
                return validated(source.extractfile(members[name]).read(), desc)
            if supplemental is not None:
                retained = supplemental / desc['digest'].split(':')[1]
                if retained.is_file():
                    fetched[name] = validated(retained.read_bytes(), desc)
                    return fetched[name]
            raw = command('docker', 'buildx', 'history', 'inspect', 'attachment', build_ref, desc['digest'])
            fetched[name] = validated(raw, desc)
            return raw

        def visit(desc):
            name = blob_name(desc['digest'])
            if name in descriptors: return
            descriptors[name] = desc
            raw = read(desc)
            if desc['mediaType'] in ('application/vnd.oci.image.index.v1+json', 'application/vnd.oci.image.manifest.v1+json'):
                obj = json.loads(raw)
                for child in obj.get('manifests', []): visit(child)
                if obj.get('config'): visit(obj['config'])
                for child in obj.get('layers', []): visit(child)

        visit(descriptor)
        with tarfile.open(recovered_tar, 'w') as target:
            def add(name, raw):
                info = tarfile.TarInfo(name); info.size = len(raw); info.mode = 0o644
                target.addfile(info, io.BytesIO(raw))
            add('oci-layout', b'{"imageLayoutVersion":"1.0.0"}')
            add('index.json', json.dumps({'schemaVersion': 2, 'manifests': [{**descriptor, 'annotations': {
                'io.containerd.image.name': 'docker.io/library/goodmcp-finance:g6-approved-restored',
                'org.opencontainers.image.ref.name': 'g6-approved-restored'}}]}).encode())
            for name, desc in descriptors.items(): add(name, read(desc))
    subprocess.run(['docker', 'image', 'load', '--input', str(recovered_tar)], cwd=ROOT, check=True)
    actual = command('docker', 'image', 'inspect', expected, '--format', '{{.Id}}').decode().strip()
    if actual != expected: raise RuntimeError('Docker did not restore the exact approved image identity')
    result = {'restored': True, 'image_digest': actual, 'release_digest': release['release_digest'],
              'build_ref': build_ref, 'validated_blobs': len(descriptors), 'release_or_database_changed': False}
    (output / 'result.json').write_text(json.dumps(result, indent=2))
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--release', type=Path, default=ROOT / '.local/g4/active/release.json')
    p.add_argument('--build-ref', required=True)
    p.add_argument('--source-image', required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'work/g6-runtime-restore')
    p.add_argument('--supplemental-blob-dir', type=Path, help='Additional retained OCI blobs named by SHA-256; each must match the approved descriptor byte for byte')
    a = p.parse_args()
    print(json.dumps(restore(a.release, a.build_ref, a.source_image, a.output, a.supplemental_blob_dir)))


if __name__ == '__main__': main()
