"""轻量翻译辅助模块，供 server.py 的 /translate 端点调用。"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 src/ 目录可导入
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from search import _is_ascii, _translate_to_chinese, _translate_to_english  # noqa: E402


def translate_term(term: str) -> dict:
    """返回原词的双向翻译结果。

    Returns:
        {
            "original": str,
            "translated": str | None,
            "direction": "zh->en" | "en->zh" | "none",
        }
    """
    term = term.strip()
    if not term:
        return {"original": term, "translated": None, "direction": "none"}

    if _is_ascii(term):
        translated = _translate_to_chinese(term)
        direction = "en->zh"
    else:
        translated = _translate_to_english(term)
        direction = "zh->en"

    # 若翻译结果与原词相同则视为无效
    if translated and translated.lower() == term.lower():
        translated = None

    return {"original": term, "translated": translated, "direction": direction}
