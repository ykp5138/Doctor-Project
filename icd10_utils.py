"""
ICD-10-CM utilities: code range parsing, lookup, and validation.
Uses the simple_icd_10_cm package (bundles the full CMS ICD-10-CM dataset).
Degrades gracefully if the package is not installed.
"""
import re
from typing import Optional

try:
    import simple_icd_10_cm as cm
    _HAS_DB = True
except ImportError:
    _HAS_DB = False
    print("[icd10] Warning: simple_icd_10_cm not installed — run: pip install simple_icd_10_cm")

# Cached sorted code list (loaded once on first use)
_ALL_CODES: list[str] = []


def _get_all_codes() -> list[str]:
    global _ALL_CODES
    if not _ALL_CODES and _HAS_DB:
        _ALL_CODES = cm.get_all_codes(with_dots=True)
    return _ALL_CODES


def _parse_segments(raw: str) -> list[str]:
    """Split 'I00-I99, L00-L99, E11.9' into ['I00-I99', 'L00-L99', 'E11.9']."""
    return [s.strip().upper() for s in raw.split(',') if s.strip()]


def _expand_segment(seg: str) -> list[dict]:
    """
    Expand a single segment into [{code, description}].
    Handles ranges ('L00-L99', 'E11-E14') and specific codes ('E11.9', 'E11').
    """
    if not _HAS_DB:
        return []

    all_codes = _get_all_codes()

    # Range pattern: two code-like tokens separated by a hyphen (no dot in boundary)
    range_m = re.match(r'^([A-Z]\d+(?:\.\d+)?)-([A-Z]\d+(?:\.\d+)?)$', seg)
    if range_m:
        start, end = range_m.group(1), range_m.group(2)

        # Find start index — first code >= start
        start_idx = None
        try:
            start_idx = cm.get_index(start)
        except Exception:
            for i, c in enumerate(all_codes):
                if c >= start:
                    start_idx = i
                    break
        if start_idx is None:
            return []

        # Find end index — last code that starts with end prefix or <= end
        end_prefix = end.split('.')[0]
        end_idx = start_idx
        try:
            end_idx = cm.get_index(end)
        except Exception:
            # end code not in DB — collect until we pass the prefix
            for i in range(start_idx, len(all_codes)):
                c_prefix = all_codes[i].split('.')[0]
                if c_prefix <= end_prefix:
                    end_idx = i
                else:
                    break

        codes_in_range = all_codes[start_idx: end_idx + 1]
        result = []
        for code in codes_in_range:
            try:
                result.append({"code": code, "description": cm.get_description(code)})
            except Exception:
                pass
        return result

    # Specific code (or parent code — include descendants)
    try:
        if cm.is_valid_item(seg):
            result = []
            try:
                result.append({"code": seg, "description": cm.get_description(seg)})
            except Exception:
                pass
            try:
                for c in cm.get_descendants(seg):
                    try:
                        result.append({"code": c, "description": cm.get_description(c)})
                    except Exception:
                        pass
            except Exception:
                pass
            return result
    except Exception:
        pass

    return []


def get_codes_for_range_input(code_range_str: str, max_codes: int = 50) -> list[dict]:
    """
    Parse user input like 'I00-I99, L00-L99, E11.9' and return a deduplicated
    [{code, description}] list capped at max_codes.

    When the set is too large, reduces to 3-char category codes only so the
    Ollama context stays manageable.
    """
    if not code_range_str or not code_range_str.strip() or not _HAS_DB:
        return []

    seen: set[str] = set()
    all_items: list[dict] = []

    for seg in _parse_segments(code_range_str):
        for item in _expand_segment(seg):
            if item['code'] not in seen:
                seen.add(item['code'])
                all_items.append(item)

    if len(all_items) <= max_codes:
        return all_items

    # Too many to pass to LLM — prioritise 3-char category codes, then fill up
    # to max_codes with leaf codes so the LLM still has specific options.
    parents = [c for c in all_items if re.match(r'^[A-Z]\d{2}$', c['code'])]
    if len(parents) >= max_codes:
        return parents[:max_codes]

    others = [c for c in all_items if not re.match(r'^[A-Z]\d{2}$', c['code'])]
    return parents + others[:max_codes - len(parents)]


def validate_and_describe(code: str) -> Optional[str]:
    """Return the description if the code is a valid ICD-10-CM code, else None."""
    if not _HAS_DB:
        return None
    try:
        if cm.is_valid_item(code.upper()):
            return cm.get_description(code.upper())
    except Exception:
        pass
    return None
