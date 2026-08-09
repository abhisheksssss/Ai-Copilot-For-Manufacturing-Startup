# utils/kb_lookup.py
import os
import re
import glob

def get_manufacturing_kb_dir() -> str:
    base_data_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data")
    )
    mfg_dir = os.path.join(base_data_dir, "Knowledge_manufacturing")
    if os.path.exists(mfg_dir):
        return mfg_dir
    okf_dir = os.path.join(base_data_dir, "Knowledge_OKF")
    if os.path.exists(okf_dir):
        return okf_dir
    return mfg_dir

_INDEX_CACHE = {}

def load_index(kb_dir: str) -> list[tuple[str, str]]:
    """
    Reads index.md and returns list of (name, relative_path) tuples.
    Caches results in memory to avoid repetitive file reads.
    """
    if kb_dir in _INDEX_CACHE:
        return _INDEX_CACHE[kb_dir]

    index_path = os.path.join(kb_dir, "index.md")
    if not os.path.exists(index_path):
        print(f"[WARNING] index.md not found at {index_path}")
        return []

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = r'\[([^\]]+)\]\(([^)]+\.md)\)'
        matches = re.findall(pattern, content)
        print(f"[KB] index.md loaded — {len(matches)} entries found")
        _INDEX_CACHE[kb_dir] = matches
        return matches
    except Exception as e:
        print(f"[WARNING] Failed to read index.md: {e}")
        return []


def fetch_product_content(product: str, kb_dir: str) -> tuple[str, str]:
    """
    Finds the best matching product file from index.md or KB directories.

    Returns:
        (matched_name, full_content) — both empty if not found (triggers dynamic fallback engine)
    """
    all_entries = load_index(kb_dir)
    if not all_entries:
        return "", ""

    query_words = [w for w in product.lower().split() if len(w) > 2]
    best_score  = 0
    best_match  = None

    for name, rel_path in all_entries:
        name_lower = name.lower()
        score = sum(1 for w in query_words if w in name_lower)
        if score > best_score:
            best_score = score
            best_match = (name, rel_path)

    # Secondary check: Direct filename glob matching
    if not best_match or best_score == 0:
        for w in query_words:
            glob_pattern = os.path.join(kb_dir, "**", f"*{w}*.md")
            found_files = glob.glob(glob_pattern, recursive=True)
            if found_files:
                rel_f = os.path.relpath(found_files[0], kb_dir)
                fname = os.path.basename(found_files[0]).replace(".md", "").replace("_", " ").title()
                best_match = (fname, rel_f)
                best_score = 1
                break

    if not best_match or best_score == 0:
        print(f"[INFO] No static KB file for '{product}' -> Seamlessly engaging dynamic calculation engine.")
        return "", ""

    full_path = os.path.join(kb_dir, best_match[1])
    if not os.path.exists(full_path):
        return best_match[0], ""

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        print(f"[SUCCESS] KB match: '{best_match[0]}' | file: {best_match[1]} | score={best_score}")
        return best_match[0], content
    except Exception as e:
        print(f"[WARNING] Error reading KB file {full_path}: {e}")
        return "", ""



def extract_section(content: str, *section_keywords: str) -> str:
    """
    Extracts content under a markdown header matching any of the given keywords.

    Example:
        extract_section(content, "machinery", "equipment", "machines")
        → returns text under ## Machinery or ## Equipment header
    """
    lines   = content.splitlines()
    capture = False
    result  = []

    for line in lines:
        stripped = line.strip()

        # Check if this line is a matching header
        if stripped.startswith("#"):
            header_text = stripped.lstrip("#").strip().lower()
            if any(kw in header_text for kw in section_keywords):
                capture = True
                continue
            elif capture:
                # Hit a new unrelated header — stop
                break

        if capture and stripped:
            result.append(stripped)

    return "\n".join(result[:10])  # Max 10 lines per section to minimize token usage


def extract_all_sections(content: str) -> dict[str, str]:
    """
    Splits the entire markdown into a dict of {header: content_block}.
    Useful when you need multiple sections from one file read.
    """
    sections = {}
    lines    = content.splitlines()
    current  = "general"
    buffer   = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if buffer:
                sections[current] = "\n".join(buffer).strip()
            current = stripped.lstrip("#").strip().lower()
            buffer  = []
        else:
            if stripped:
                buffer.append(stripped)

    if buffer:
        sections[current] = "\n".join(buffer).strip()

    return sections


def parse_list_items(text: str) -> list[str]:
    """
    Extracts bullet/numbered list items from a markdown text block.

    Input:  "- Item A\n- Item B\n1. Item C"
    Output: ["Item A", "Item B", "Item C"]
    """
    items = []
    for line in text.splitlines():
        cleaned = re.sub(r'^[\s\-\*\d\.\)]+', '', line).strip()
        if cleaned:
            items.append(cleaned)
    return items


def parse_table_rows(text: str) -> list[dict]:
    """
    Parses a simple markdown table into list of dicts.

    | Material     | Qty  | Supplier  |
    |--------------|------|-----------|
    | Steel Sheet  | 2 kg | Wholesale |
    →
    [{"Material": "Steel Sheet", "Qty": "2 kg", "Supplier": "Wholesale"}]
    """
    rows    = []
    headers = []

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not headers:
            headers = cells
        elif re.match(r'^[-|:\s]+$', line):
            continue  # separator row
        else:
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))

    return rows



def parse_budget_to_lakhs(budget_str: str) -> float:
    """
    Converts any budget string to float in Lakhs.
    '2 crore' -> 200.0 | '50 lakhs' -> 50.0 | '5000000' -> 50.0
    """
    text = budget_str.lower().strip()
    text = text.replace("₹", "").replace("rs", "").replace("inr", "").strip()

    number_match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if not number_match:
        return 0.0

    value = float(number_match.group())

    if any(k in text for k in ["crore", " cr"]):
        return value * 100
    elif any(k in text for k in ["lakh", "lac", " l"]):
        return value
    elif value >= 100_000:
        return value / 100_000

    return value