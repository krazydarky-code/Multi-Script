#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Publisher-only release signing. Requires `pip install cryptography`.

Generate a key OUTSIDE the project/distribution once; keep it private/backed up.
Pin its PUBLIC key and HTTPS feed in runtime/update-channel.json before building.
Sign the final Dev ZIP after build_release.py; upload ZIP then feed (last).
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'runtime'))
from update_manager import https, verify_envelope


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--key', type=Path, required=True)
    p.add_argument('--init', action='store_true')
    p.add_argument('--feed-url')
    p.add_argument('--config', type=Path, default=ROOT/'runtime/update-channel.json')
    p.add_argument('--archive', type=Path)
    p.add_argument('--archive-url')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    if a.key.resolve().is_relative_to(ROOT):
        p.error('Private signing keys must be outside the project/distribution')
    if a.init:
        if a.key.exists() or not a.feed_url:
            p.error('--init requires --feed-url and a new private-key path')
        https(a.feed_url)
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        with a.key.open('xb') as handle:
            handle.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        a.key.chmod(0o600)
        pub = key.public_key().public_numbers()
        a.config.write_text(json.dumps({'channel':'dev','feedUrl':a.feed_url,'publicKey':{'n':format(pub.n,'x'),'e':pub.e}},indent=2)+'\n',encoding='utf-8')
        product_path = ROOT/'runtime/product-manifest.json'
        product = json.loads(product_path.read_text(encoding='utf-8'))
        product.setdefault('updates', {})['configured'] = True
        product_path.write_text(json.dumps(product,indent=2)+'\n',encoding='utf-8')
        print('Pinned PUBLIC release key/feed. Keep the private key outside all packages. Rebuild before signing.')
        return
    if not all([a.archive, a.archive_url, a.output]):
        p.error('Signing requires --archive, --archive-url and --output')
    import zipfile
    key = serialization.load_pem_private_key(a.key.read_bytes(), password=None)
    cfg = json.loads(a.config.read_text(encoding='utf-8'))
    with zipfile.ZipFile(a.archive) as z:
        manifest = json.loads(z.read('Multi-Script/extension/manifest.json'))
        if json.loads(z.read('Multi-Script/runtime/update-channel.json')) != cfg:
            p.error('Archive must already contain this exact pinned feed/key. Rebuild it first.')
        if json.loads(z.read('Multi-Script/runtime/edition.json')).get('edition') != 'dev':
            p.error('Only Dev archives may be signed')
    raw = a.archive.read_bytes()
    data = {'product':'Multi-Script','channel':'dev','version':manifest['version'],'url':https(a.archive_url),'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    payload = json.dumps(data,sort_keys=True,separators=(',',':')).encode()
    signature = key.sign(payload,padding.PKCS1v15(),hashes.SHA256())
    envelope = {'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(signature).decode()}
    verify_envelope(envelope,cfg['publicKey'])
    a.output.write_text(json.dumps(envelope,indent=2)+'\n',encoding='utf-8')
    print('Signed verified Dev release '+manifest['version']+'. Publish the archive first, then replace the feed.')


if __name__ == '__main__':
    main()
