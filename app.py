"""Streamlit 演示界面：streamlit run app.py"""
from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

from src.index import RagIndex
from src.pipeline import RagPipeline

st.set_page_config(page_title="企业知识库问答 Demo", page_icon="📚", layout="wide")

st.title("📚 企业知识库问答 Demo")
st.caption("混合检索（BM25 + 向量 + RRF）· 引用溯源 · 可替换任意领域文档")


@st.cache_resource(show_spinner="加载索引中…")
def load_pipeline(index_dir: str, top_k: int, mode: str) -> RagPipeline:
    return RagPipeline(RagIndex.load(index_dir), top_k=top_k, mode=mode)


with st.sidebar:
    st.header("配置")
    index_dir = st.text_input("索引目录", os.environ.get("RAG_INDEX", "data/index"))
    top_k = st.slider("召回数量 top_k", 1, 10, 5)
    mode = st.selectbox("检索模式", ["hybrid", "bm25", "vector"], index=0)
    st.divider()
    st.caption("大模型生成：配置 .env 中的 LLM_API_KEY 后自动启用；否则返回检索摘录。")
    with st.expander("示例问题"):
        for q in [
            "智擎云有哪些核心模块？",
            "私有化部署最低配置是什么？",
            "遇到 429 错误怎么办？",
            "专业版一年多少钱？",
        ]:
            st.markdown("- " + q)

if not Path(index_dir).exists():
    st.error("索引不存在：" + index_dir + " —— 请先运行 python scripts/build_index.py")
    st.stop()

pipe = load_pipeline(index_dir, top_k, mode)

question = st.chat_input("向知识库提问，例如：支持私有化部署吗？")
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("检索并生成中…"):
            result = pipe.ask(question)
        st.markdown(result["answer"])
        gen_label = "大模型" if result["used_llm"] else "抽取式"
        st.caption("模式 " + result["mode"] + " · 生成 " + gen_label + " · " + str(result["latency_ms"]) + " ms")
        with st.expander("引用来源（" + str(len(result["contexts"])) + " 条）"):
            for ctx in result["contexts"]:
                st.markdown("**[" + str(ctx["id"]) + "] " + ctx["doc_id"] + " · " + ctx["title"] + " · 块 " + str(ctx["chunk_index"]) + "**")
                st.caption("score=" + str(ctx["score"]))
                st.write(ctx["snippet"])
        with st.expander("调试：完整 JSON"):
            st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")
