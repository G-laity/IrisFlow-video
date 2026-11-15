"""对话上下文压缩。

当消息历史超过模型上下文窗口预算时，在发送请求前对消息进行压缩：
1. 超长工具结果截断（保留首尾，中间标注省略）
2. 从最老轮次开始丢弃完整对话轮（保持 assistant(tool_calls)↔tool 配对）
3. 有丢弃时在请求最前插入压缩提示 system 消息

仅压缩发送给 LLM 的请求副本，不修改持久化的会话历史（chat.messages）。
"""

from __future__ import annotations

import logging
import math

from llm.constants import (
    CONTEXT_COMPRESS_NOTICE,
    CONTEXT_OUTPUT_RESERVE,
    CONTEXT_WINDOW_TOKENS,
    ROLE_SYSTEM,
    ROLE_TOOL,
    ROLE_USER,
    TOOL_RESULT_HEAD_CHARS,
    TOOL_RESULT_MAX_CHARS,
    TOOL_RESULT_TAIL_CHARS,
)
from llm.models import ChatMessage

_log = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """估算文本 token 数：CJK 字符 ≈ 1 token，其余字符 ≈ 4 字符 1 token。

    启发式估算（无 tokenizer 依赖），用于判断是否需要压缩，不要求精确。
    """
    if not text:
        return 0
    cjk = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
    other = len(text) - cjk
    return cjk + math.ceil(other / 4)


def build_budget(max_tokens: int | None) -> int:
    """按模型窗口与输出预留计算输入预算（token）。"""
    reserve = max_tokens if max_tokens else CONTEXT_OUTPUT_RESERVE
    budget = CONTEXT_WINDOW_TOKENS - reserve
    return max(budget, 0)


def _message_tokens(m: ChatMessage) -> int:
    """估算单条消息占用的 token（content + tool_calls + reasoning_content）。"""
    total = estimate_tokens(str(m.content))
    if m.tool_calls:
        total += estimate_tokens(str(m.tool_calls))
    if m.reasoning_content:
        total += estimate_tokens(m.reasoning_content)
    return total


def _truncate_tool_result(m: ChatMessage) -> ChatMessage:
    """超长工具结果保留首尾。返回新对象，不修改原消息。"""
    content = m.content
    if not isinstance(content, str) or len(content) <= TOOL_RESULT_MAX_CHARS:
        return m
    head = content[:TOOL_RESULT_HEAD_CHARS]
    tail = content[-TOOL_RESULT_TAIL_CHARS:]
    omitted = len(content) - TOOL_RESULT_HEAD_CHARS - TOOL_RESULT_TAIL_CHARS
    new_content = f"{head}\n\n[工具结果过长，已省略中间 {omitted} 字符]\n\n{tail}"
    return m.model_copy(update={"content": new_content})


def _split_rounds(messages: list[ChatMessage]) -> list[list[ChatMessage]]:
    """按对话轮切分：每轮从 user 消息开始，至下一条 user 消息前结束。

    system 消息不参与切分（单独保留）。
    """
    rounds: list[list[ChatMessage]] = []
    current: list[ChatMessage] = []
    for m in messages:
        if m.role == ROLE_USER and current:
            rounds.append(current)
            current = []
        if m.role != ROLE_SYSTEM:
            current.append(m)
    if current:
        rounds.append(current)
    return rounds


def compress_messages(
    messages: list[ChatMessage],
    budget_tokens: int,
) -> tuple[list[ChatMessage], int]:
    """压缩消息列表至预算内。

    Args:
        messages: 完整消息列表（不会修改原对象）。
        budget_tokens: 输入 token 预算（窗口减去输出预留）。

    Returns:
        (压缩后的消息副本, 被丢弃的对话轮数)。
    """
    # 快速路径：预算内且无超长工具结果 → 原样返回（零开销）
    total = sum(_message_tokens(m) for m in messages)
    needs_truncate = any(
        m.role == ROLE_TOOL and isinstance(m.content, str)
        and len(m.content) > TOOL_RESULT_MAX_CHARS
        for m in messages
    )
    if total <= budget_tokens and not needs_truncate:
        return messages, 0

    # 1. 超长工具结果截断（副本，不改原对象）
    working = [_truncate_tool_result(m) if m.role == ROLE_TOOL else m for m in messages]

    # 2. 按轮丢弃（从最老开始），至少保留最后一轮
    system_msgs = [m for m in working if m.role == ROLE_SYSTEM]
    sys_tokens = sum(_message_tokens(m) for m in system_msgs)
    rounds = _split_rounds(working)
    dropped = 0
    while len(rounds) > 1:
        kept_tokens = sum(_message_tokens(m) for r in rounds for m in r)
        if sys_tokens + kept_tokens <= budget_tokens:
            break
        rounds.pop(0)
        dropped += 1

    result = system_msgs + [m for r in rounds for m in r]

    # 3. 极端情况：仅剩最后一轮仍超预算 → 进一步降级截断工具结果
    if dropped and sum(_message_tokens(m) for m in result) > budget_tokens:
        _log.warning("上下文压缩：仅剩 1 轮仍超预算，跳过轮丢弃")
    total_after = sum(_message_tokens(m) for m in result)
    if total_after > budget_tokens:
        _log.warning(
            "上下文压缩后仍超预算: %d > %d token（消息 %d 条）",
            total_after, budget_tokens, len(result),
        )

    # 4. 注入压缩提示
    if dropped:
        notice = ChatMessage(
            role=ROLE_SYSTEM,
            content=CONTEXT_COMPRESS_NOTICE.format(dropped=dropped),
        )
        result = [notice] + result

    if dropped:
        _log.info("上下文压缩: 丢弃 %d 轮, 消息 %d→%d, 估算 %d/%d token",
                  dropped, len(messages), len(result), total_after, budget_tokens)
    return result, dropped
