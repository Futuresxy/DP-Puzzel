"""Fetch pinned metadata/tokenizers and WikiText-2; never download weight shards."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import HERE, ROOT, read_json


def fetch_model(source, cache):
    from huggingface_hub import hf_hub_download, list_repo_files
    directory = Path(cache) / source["cache_name"]
    directory.mkdir(parents=True, exist_ok=True)

    def download(name):
        return Path(hf_hub_download(source["repo"], name, revision=source["revision"],
                                  local_dir=directory))

    download("model.safetensors.index.json")
    available = list_repo_files(source["repo"], revision=source["revision"])
    metadata = [name for name in ("config.json", "tokenizer.json", "tokenizer_config.json",
                "vocab.json", "merges.txt", "LICENSE", "LICENSE.txt", "README.md") if name in available]
    for name in metadata:
        download(name)
    print(f"{source['repo']} pinned {source['revision']}: metadata ready; weights use HTTP Range", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("all", "qwen_qproj", "moe_downproj"), default="all")
    parser.add_argument("--cache", type=Path, default=ROOT / ".deps")
    args = parser.parse_args()
    sources = read_json(HERE / "sources.json")
    from huggingface_hub import hf_hub_download
    data = sources["dataset"]
    path = hf_hub_download(data["repo"], data["file"], repo_type="dataset",
                           revision=data["revision"], local_dir=args.cache / "wikitext2-test")
    print(f"WikiText-2 test: {path}", flush=True)
    selected = sources["models"].items() if args.source == "all" else [(args.source, sources["models"][args.source])]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda item: fetch_model(item[1], args.cache), selected))


if __name__ == "__main__":
    main()
