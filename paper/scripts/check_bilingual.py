#!/usr/bin/env python3
"""Check structural parity of the English master and Chinese review chapters.

This does not assess translation quality or silently synchronize either text.
It checks paired headings, labels, source references and citations, display
equations, table data, and figure sources to catch structural and numerical drift.
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


def table_signature(text):
    tables = re.findall(r"\\begin\{(table\*?)\}(.*?)\\end\{\1\}", text, re.S)
    return [
        [
            (kind, grid_signature(grid))
            for kind, grid in re.findall(
                r"\\begin\{(tabular\*?)\}(.*?)\\end\{\1\}", table, re.S
            )
        ]
        for _, table in tables
    ]


def grid_signature(grid):
    # Compare cell boundaries and technical values. Captions, headings, and
    # other prose are reviewed separately because they are translated.
    grid = re.sub(r"(?m)^\s*%.*$", "", grid)
    values = re.compile(r"\$[^$]*\$|\\[A-Z]+(?![A-Za-z])|[+-]?\d+(?:\.\d+)?")
    result = []
    depth = start = 0
    for match in re.finditer(r"\\(?:[A-Za-z]+|.)|[{}&]", grid):
        token = match[0]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
        elif depth == 0 and token in ("&", r"\\"):
            cell = grid[start:match.start()]
            result.append((token, tuple(normalized(value) for value in values.findall(cell))))
            start = match.end()
    result.append(("", tuple(normalized(value) for value in values.findall(grid[start:]))))
    return result


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
        "table data": table_signature(text),
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
        for field, en_value in en_sig.items():
            zh_value = zh_sig[field]
            if field in ("references", "citations"):
                missing = zh_value - en_value
                if missing:
                    errors.append(f"{name}: missing {field}: {', '.join(missing)}")
            elif en_value != zh_value:
                errors.append(f"{name}: {field} differ")
    if errors:
        raise SystemExit("Bilingual check failed:\n" + "\n".join(errors))
    print(f"PASS: {len(pairs)} review pairs; headings, labels, source references and citations, "
          "display equations, table data, and figure sources agree.")
    print("Prose meaning and inline numerical claims still require editorial review.")


if __name__ == "__main__":
    main()
