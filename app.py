"""Streamlit 演示界面：streamlit run app.py

支持深链接：http://localhost:8501/?q=家庭经济困难学生认定多久评一次？
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

from src.index import RagIndex
from src.pipeline import RagPipeline

st.set_page_config(page_title="高校学生政策问答助手", page_icon="📚", layout="wide")

st.title("📚 高校学生政策问答助手")
st.caption("真实公开政策原文（学生管理规定 / 资助政策）· 混合检索（BM25 + 向量 + RRF）· 引用溯源")

EXAMPLES = [
    "家庭经济困难学生认定多久评一次？",
    "国家奖学金一年多少钱、多少个名额？",
    "勤工助学一个月最多能打多少小时工？",
    "国家助学贷款额度是多少？",
]


@st.cache_resource(show_spinner="加载索引中…")
def load_pipeline(index_dir: str, top_k: int, mode: str) -> RagPipeline:
    return RagPipeline(RagIndex.load(index_dir), top_k=top_k, mode=mode)


def render_answer(pipe: RagPipeline, question: str) -> None:
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
                st.markdown(
                    "**[" + str(ctx["id"]) + "] " + ctx["doc_id"] + " · " + ctx["title"]
                    + " · 块 " + str(ctx["chunk_index"]) + "**"
                )
                st.caption("score=" + str(ctx["score"]))
                st.write(ctx["snippet"])
        with st.expander("调试：完整 JSON"):
            st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")


with st.sidebar:
    st.header("配置")
    index_dir = st.text_input("索引目录", os.environ.get("RAG_INDEX", "data/index"))
    top_k = st.slider("召回数量 top_k", 1, 10, 5)
    mode = st.selectbox("检索模式", ["hybrid", "bm25", "vector"], index=0)
    st.divider()
    st.caption("大模型生成：配置 .env 中的 LLM_API_KEY 后自动启用；否则返回检索摘录。")
    with st.expander("示例问题", expanded=True):
        for q in EXAMPLES:
            if st.button(q, key="ex_" + q, use_container_width=True):
                st.session_state["pending_q"] = q

if not Path(index_dir).exists():
    st.error("索引不存在：" + index_dir + " —— 请先运行 python scripts/build_index.py")
    st.stop()

pipe = load_pipeline(index_dir, top_k, mode)

pending = st.session_state.pop("pending_q", None)
question = st.chat_input("向政策知识库提问，例如：评贫困生多久一次？")
deep_link = st.query_params.get("q")

if question:
    render_answer(pipe, question)
elif pending:
    render_answer(pipe, pending)
elif deep_link:
    render_answer(pipe, deep_link)
