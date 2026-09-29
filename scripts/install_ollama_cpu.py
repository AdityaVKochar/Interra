"""Install the official Windows CPU runtime without downloading CUDA libraries."""
import argparse
import io
from pathlib import Path
import shutil
import urllib.request
import zipfile

URL = 'https://github.com/ollama/ollama/releases/download/v0.34.3/ollama-windows-amd64.zip'
SIZE = 1460962639


class RemoteZip(io.RawIOBase):
    def __init__(self):
        self.position = 0
        self.cache_start = 0
        self.cache = b''

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (self.position if whence == 1 else SIZE if whence == 2 else 0)
        return self.position

    def read(self, size=-1):
        end = SIZE if size < 0 else min(SIZE, self.position + size)
        if end <= self.position:
            return b''
        if not (self.cache_start <= self.position and end <= self.cache_start + len(self.cache)):
            request_end = min(SIZE, max(end, self.position + 1024 * 1024))
            request = urllib.request.Request(URL, headers={'Range': f'bytes={self.position}-{request_end - 1}'})
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status != 206:
                    raise RuntimeError('Server did not honor range request')
                self.cache = response.read()
                self.cache_start = self.position
        start = self.position - self.cache_start
        result = self.cache[start:start + end - self.position]
        self.position = end
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    destination = Path('.tools/ollama').resolve()
    with zipfile.ZipFile(RemoteZip()) as archive:
        for item in archive.infolist():
            if item.is_dir() or any(part.startswith(('cuda', 'vulkan', 'rocm', 'mlx')) for part in Path(item.filename).parts):
                continue
            if args.list:
                print(item.filename, item.file_size, flush=True)
                continue
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Invalid archive member')
            target.parent.mkdir(parents=True, exist_ok=True)
            print('Extracting', item.filename, item.file_size, flush=True)
            # ZipFile verifies the CRC of each complete member.
            with archive.open(item) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)


if __name__ == '__main__':
    main()
