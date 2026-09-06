"""本地 Markdown 知识库解析与章节路径提取测试。"""

import pytest

from app.services.knowledge.local_knowledge import LocalKnowledgeError, parse_markdown


def test_parse_markdown_keeps_heading_path_and_number() -> None:
    """标题块应保留章节路径、编号，并生成可检索切片。"""
    content = (
        "# 1. 计算机基础\n"
        "这是第一段课程说明，包含足够多的文本内容用于生成一个可检索切片。"
        "这里继续补充背景和定义，确保句子长度足以通过短文本过滤。\n"
        "## 1.2 数据结构\n"
        "数组、链表、栈和队列是常见的数据结构，本节会逐个介绍其特点、复杂度与适用场景。"
    ).encode("utf-8")

    chunks = parse_markdown(content)

    assert chunks
    data_structure_chunk = next(chunk for chunk in chunks if "栈" in chunk.content)
    assert data_structure_chunk.heading_path == ["1. 计算机基础", "1.2 数据结构"]
    assert data_structure_chunk.heading_number == "1.2"


def test_parse_markdown_strips_yaml_frontmatter() -> None:
    """YAML frontmatter 不应进入可检索正文。"""
    content = (
        "---\ntitle: demo\nlicense: MIT\n---\n"
        "# 正文标题\n"
        "这段正文是课程资料的真实内容，不会被页面头部元数据污染。"
        "它可以被完整索引，并在检索时返回给学习者查看。"
    ).encode("utf-8")

    chunks = parse_markdown(content)

    assert chunks
    assert all("license:" not in chunk.content for chunk in chunks)


def test_parse_markdown_falls_back_for_text_without_heading() -> None:
    """没有标题的短文本仍应生成一个降级切片。"""
    chunks = parse_markdown(
        "这是一段没有 Markdown 标题的课程说明，内容超过二十四字，因此应该能够生成可检索切片。".encode(
            "utf-8"
        )
    )

    assert len(chunks) == 1
    assert chunks[0].section_path is None
    assert chunks[0].heading_path == []


def test_parse_markdown_raises_for_empty_content() -> None:
    """空文件或只有导航占位的内容必须明确报错。"""
    with pytest.raises(LocalKnowledgeError, match="Markdown 未提取到可检索文本"):
        parse_markdown(b"# \n\n")
