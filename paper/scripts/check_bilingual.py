#!/usr/bin/env python3
"""Check structural parity of the English master and Chinese review chapters.

This does not assess translation quality or silently synchronize either text.
It checks paired sections, labels, references, citations, display equations,
tables, and figure sources so a chapter review can catch numerical drift.
"""

from collections import Counter
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def expand_tables(text):
    return re.sub(
        r"\\input\{(tables/[^}]+)\}",
        lambda match: (ROOT / match[1]).read_text(),
        text,
    )


def normalized(text):
    text = re.sub(r"(?m)^\s*%.*$", "", text)
    return re.sub(r"\s+", "", text)


def blocks(text, pattern):
    return [normalized(match[0]) for match in re.finditer(pattern, text, re.S)]


def signatures(text):
    return {
        "headings": re.findall(r"\\(section|subsection|subsubsection)\{", text),
        "labels": Counter(re.findall(r"\\label\{([^}]+)\}", text)),
        "references": Counter(re.findall(r"\\(?:ref|eqref)\{([^}]+)\}", text)),
        "citations": Counter(
            key.strip()
            for group in re.findall(r"\\cite\{([^}]+)\}", text)
            for key in group.split(",")
        ),
        "equations": blocks(
            text, r"\\begin\{(equation\*?|align\*?)\}.*?\\end\{\1\}"
        ),
        "tables": blocks(text, r"\\begin\{(table\*?)\}.*?\\end\{\1\}"),
        "figures": Counter(
            re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", text)
        ),
    }


def main():
    english = (ROOT / "dp_puzzle.tex").read_text()
    errors = []
    if re.search(r"[\u4e00-\u9fff]", english):
        errors.append("English master contains Chinese characters")
    if re.search(r"\\(?:input|include)\{", english):
        errors.append("English chapters and table bodies must remain inline")
    pairs = re.findall(
        r"% BEGIN REVIEW PAIR: ([^\n]+)\n(.*?)% END REVIEW PAIR: \1", english, re.S
    )
    expected = sorted(path.name for path in (ROOT / "sections").glob("*.tex"))
    if [name for name, _ in pairs] != expected:
        errors.append("Missing, duplicated, or reordered review-pair markers")
    for name, en_text in pairs:
        zh_text = expand_tables((ROOT / "sections" / name).read_text())
        en_sig, zh_sig = signatures(en_text), signatures(zh_text)
        for field in en_sig:
            if en_sig[field] != zh_sig[field]:
                errors.append(f"{name}: {field} differ")
    if errors:
        raise SystemExit("Bilingual check failed:\n" + "\n".join(errors))
    print(f"PASS: {len(pairs)} review pairs; headings, labels, references, citations, "
          "display equations, tables, and figure sources agree.")
    print("Prose meaning and inline numerical claims still require editorial review.")


if __name__ == "__main__":
    main()
