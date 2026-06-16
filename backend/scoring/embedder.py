"""
sentence-transformers 单例封装。

懒加载：首次调用 get_embedder() 时才下载/加载模型（~470MB）。
后续运行从 HuggingFace 本地缓存读取，速度快。
线程安全：使用双重检查锁定（DCL），适合 asyncio + thread pool 环境。

国内网络加速：
  export HF_ENDPOINT=https://hf-mirror.com
"""

import logging
import threading
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# 模型已缓存时强制离线，避免企业网络 SSL 问题
import os as _os
_os.environ.setdefault("HF_HUB_OFFLINE", "1")
_os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
_model = None
_lock = threading.Lock()


def get_embedder():
    """懒初始化 SentenceTransformer 单例，线程安全。"""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                logger.info(
                    "首次加载 sentence-transformers 模型：%s（约470MB，请稍候）",
                    _MODEL_NAME,
                )
                from sentence_transformers import SentenceTransformer  # noqa: PLC0415
                _model = SentenceTransformer(_MODEL_NAME)
                logger.info("sentence-transformers 模型加载完成")
    return _model


def encode(texts: List[str]) -> np.ndarray:
    """将文本列表编码为向量矩阵，shape=(N, 384)，float32。"""
    model = get_embedder()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个一维向量的余弦相似度，返回 0.0-1.0。"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
