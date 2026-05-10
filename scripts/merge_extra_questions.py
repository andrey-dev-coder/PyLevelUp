import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRA_DIR = ROOT / "data" / "extra"
TARGET = ROOT / "data" / "questions.json"


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"missing {TARGET}")
    base = json.loads(TARGET.read_text(encoding="utf-8"))
    seen = {q["external_key"] for q in base}
    added = 0
    duplicates = 0
    if EXTRA_DIR.exists():
        for path in sorted(EXTRA_DIR.glob("*.json")):
            extra = json.loads(path.read_text(encoding="utf-8"))
            for q in extra:
                key = q["external_key"]
                if key in seen:
                    duplicates += 1
                    continue
                _validate(q)
                base.append(q)
                seen.add(key)
                added += 1
    TARGET.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"merged: added={added} duplicates_skipped={duplicates} total={len(base)}")
    return added


def _validate(q: dict) -> None:
    required = ("external_key", "topic", "difficulty", "text", "options", "correct_index", "explanation")
    for f in required:
        if f not in q:
            raise ValueError(f"missing field {f} in {q}")
    if not isinstance(q["options"], list) or len(q["options"]) != 4:
        raise ValueError(f"options must be list of 4: {q['external_key']}")
    if not (0 <= q["correct_index"] < 4):
        raise ValueError(f"bad correct_index: {q['external_key']}")
    if q["difficulty"] not in (1, 2, 3):
        raise ValueError(f"bad difficulty: {q['external_key']}")


if __name__ == "__main__":
    main()
