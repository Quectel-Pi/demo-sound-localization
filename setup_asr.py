#!/usr/bin/env python3
"""Download the official INT8 SenseVoice model; does not upload user audio."""
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent
MODEL_NAME = 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'
MODEL_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/'+MODEL_NAME+'.tar.bz2'


def main():
    target = ROOT/'models'/MODEL_NAME
    if (target/'model.int8.onnx').is_file() and (target/'tokens.txt').is_file():
        print('Model already available:', target)
        return
    target.parent.mkdir(exist_ok=True)
    archive = target.parent/(MODEL_NAME+'.tar.bz2')
    partial = archive.with_suffix('.partial')
    print('Downloading official SenseVoice INT8 model (about 230 MB)…', flush=True)
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response, partial.open('wb') as file:
        while True:
            chunk = response.read(1024*1024)
            if not chunk:
                break
            file.write(chunk)
            digest.update(chunk)
            total += len(chunk)
            if total % (32*1024*1024) == 0:
                print(f'Downloaded {total//(1024*1024)} MiB', flush=True)
    partial.replace(archive)
    with tarfile.open(archive, 'r:bz2') as file:
        for member in file.getmembers():
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != MODEL_NAME:
                raise ValueError('Unexpected model archive path')
            if not member.isfile():
                continue
            destination = target.parent/path
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = file.extractfile(member)
            staged = destination.with_name(destination.name+'.partial')
            with staged.open('wb') as output:
                while True:
                    chunk = source.read(1024*1024)
                    if not chunk:
                        break
                    output.write(chunk)
            staged.replace(destination)
    if not (target/'model.int8.onnx').is_file() or not (target/'tokens.txt').is_file():
        raise RuntimeError('Model archive missing required files')
    (target/'download.json').write_text(json.dumps({'url': MODEL_URL, 'bytes': total,
        'sha256': digest.hexdigest()}, indent=2)+'\n')
    print('Model installed:', target, flush=True)


if __name__ == '__main__':
    main()
