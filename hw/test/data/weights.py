"""Read selected BF16 safetensors ranges, refusing a whole-shard HTTP fallback."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import threading
import time

from common import read_json, sha256


class WeightReader:
    def __init__(self, source, model_cache, range_cache, max_download_mib=128):
        self.source = source
        self.local = Path(model_cache) / source["cache_name"]
        self.cache = Path(range_cache) / source["cache_name"]
        self.cache.mkdir(parents=True, exist_ok=True)
        self.index = read_json(self.local / "model.safetensors.index.json")["weight_map"]
        self.headers = {}
        self.receipts = []
        self.lock = threading.Lock()
        self.network_bytes = 0
        self.budget = max_download_mib * 1024 * 1024

    def _range(self, shard, start, end):
        length = end - start + 1
        identity = f"{self.source['repo']}:{self.source['revision']}:{shard}:{start}:{end}"
        path = self.cache / (hashlib.sha256(identity.encode()).hexdigest() + ".bin")
        origin = "cached_range"
        # An earlier interrupted full-shard cache is not evidence of valid
        # weights. Always use our pinned, length-checked ranges instead.
        if path.exists():
            data = path.read_bytes()
        else:
            import requests
            with self.lock:
                if self.network_bytes + length > self.budget:
                    raise ValueError("Weight range download budget exceeded; no full-shard fallback")
                self.network_bytes += length
            url = (f"https://huggingface.co/{self.source['repo']}/resolve/"
                   f"{self.source['revision']}/{shard}?dp_range={start}-{end}")
            for attempt in range(3):
                try:
                    with requests.get(url, headers={"Range": f"bytes={start}-{end}"},
                                      stream=True, timeout=(15, 60)) as response:
                        expected = f"bytes {start}-{end}/"
                        if response.status_code != 206 or not response.headers.get("Content-Range", "").startswith(expected):
                            raise ValueError("HTTP Range not honored; refusing response body")
                        data = response.raw.read(length + 1)
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
            if len(data) == length:
                path.write_bytes(data)
            origin = "http_range"
        if len(data) != length:
            raise ValueError("Truncated or oversized tensor range")
        with self.lock:
            self.receipts.append(dict(shard=shard, start=start, bytes=length,
                                      sha256=hashlib.sha256(data).hexdigest(), origin=origin))
        return data

    def _header(self, shard):
        if shard not in self.headers:
            size = struct.unpack("<Q", self._range(shard, 0, 7))[0]
            if not 0 < size <= 16 * 1024 * 1024:
                raise ValueError("Invalid safetensors header length")
            self.headers[shard] = (8 + size, json.loads(self._range(shard, 8, 7 + size)))
        return self.headers[shard]

    def tensor(self, key, rows=None):
        import torch
        shard = self.index[key]
        base, header = self._header(shard)
        info = header[key]
        if info["dtype"] != "BF16":
            raise ValueError(f"Expected native BF16: {key}")
        shape = info["shape"]
        first, last = info["data_offsets"]
        if rows is None:
            data = self._range(shard, base + first, base + last - 1)
            return torch.frombuffer(bytearray(data), dtype=torch.bfloat16).reshape(shape)
        if len(shape) != 2 or any(not 0 <= r < shape[0] for r in rows):
            raise ValueError("Invalid tensor row selection")
        row_bytes = shape[1] * 2
        unique = sorted(set(map(int, rows)))
        # Pre-read the header above, before parallel requests touch shared state.
        def get_row(row):
            start = base + first + row * row_bytes
            return row, self._range(shard, start, start + row_bytes - 1)
        with ThreadPoolExecutor(max_workers=8) as pool:
            selected = dict(pool.map(get_row, unique))
        data = b"".join(selected[int(row)] for row in rows)
        return torch.frombuffer(bytearray(data), dtype=torch.bfloat16).reshape(len(rows), shape[1])

    def provenance(self):
        return dict(model=self.source, index_sha256=sha256(self.local / "model.safetensors.index.json"),
                    network_bytes=self.network_bytes, ranges=self.receipts,
                    note="Range hashes are slice fingerprints, not verification of a full shard SHA-256")
