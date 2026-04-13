import json
import os
from openai import OpenAI


_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8086/v1"),
            api_key=os.environ.get("LLM_API_KEY", "sk-octopus-72DjJixqBZuBT7woR3Nza4LR50eYMdYfMkRBrDEtMukFltzk")
        )
    return _client


def generate_summary(description: str) -> str:
    """
    调用大模型生成工作概要摘要

    Args:
        description: 完整的工作描述

    Returns:
        不超过 32 个中文字符宽度的摘要
    """
    if not description or description == "-":
        return description

    client = _get_client()
    response = client.chat.completions.create(
        model="cheap-text",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"请用不超过16个中文字（或等价宽度）概括以下工作内容，直接输出摘要，不要任何解释和标点：\n\n{description}"
        }]
    )
    return response.choices[0].message.content.strip()


def ensure_summary(dev_context_path: str) -> str | None:
    """
    确保 context.json 中有 summary 字段，没有则生成并写入

    Args:
        dev_context_path: context.json 的目录路径

    Returns:
        摘要文本，失败返回 None
    """
    # 查找 context 文件
    context_candidates = [
        os.path.join(dev_context_path, ".devpipe", "context.json"),
    ]

    # 追加：检查 .devpipe/ 内 symlink 指向的 docs 目录
    devpipe_dir = os.path.join(dev_context_path, ".devpipe")
    if os.path.isdir(devpipe_dir):
        for entry in os.listdir(devpipe_dir):
            entry_path = os.path.join(devpipe_dir, entry)
            if os.path.islink(entry_path) and os.path.isdir(entry_path):
                context_candidates.append(os.path.join(entry_path, "context.json"))

    context_file = None
    for candidate in context_candidates:
        if os.path.exists(candidate):
            context_file = candidate
            break

    if not context_file:
        return None

    try:
        with open(context_file, "r", encoding="utf-8") as f:
            context = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    # 已有 summary 则直接返回
    if context.get("summary"):
        return context["summary"]

    description = context.get("description", "")
    if not description or description == "-":
        return None

    try:
        summary = generate_summary(description)
    except Exception:
        return None

    # 写回文件
    context["summary"] = summary
    try:
        with open(context_file, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2)
    except IOError:
        pass

    return summary
