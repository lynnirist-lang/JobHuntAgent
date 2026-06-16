"""
技能词汇表 + 混合技能提取器。

两阶段：
  1. 关键词扫描：预编译 regex，大小写/CJK 均支持
  2. 语义扫描（可选）：复用 backend/scoring/embedder.py，无需新模型
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# 词汇表（按类别分组，最终扁平化）
# --------------------------------------------------------------------------
_VOCAB_BY_CATEGORY: Dict[str, List[str]] = {
    "languages": [
        "Python", "Java", "Go", "Golang", "TypeScript", "JavaScript",
        "C++", "C#", "Rust", "Kotlin", "Swift", "Ruby", "PHP",
        "Scala", "R", "Shell", "Bash", "SQL", "MATLAB", "Dart",
    ],
    "web_frameworks": [
        "FastAPI", "Django", "Flask", "Spring Boot", "Spring",
        "Node.js", "React", "Next.js", "Vue", "Vue.js", "Angular",
        "Svelte", "Express", "NestJS", "Gin", "Echo", "Fiber",
        "Actix", "Axum", "Rails",
    ],
    "ai_ml": [
        "PyTorch", "TensorFlow", "Keras", "scikit-learn", "Pandas",
        "NumPy", "LangChain", "LlamaIndex", "OpenAI", "DeepSeek",
        "LLM", "RAG", "RLHF", "Fine-tuning", "LoRA", "Transformers",
        "HuggingFace", "BERT", "GPT", "Stable Diffusion", "Embedding",
        "Vector DB", "Prompt Engineering", "Multi-Agent", "AutoGen",
        "Semantic Search", "XGBoost", "LightGBM", "CatBoost",
        "Computer Vision", "NLP", "OCR", "CLIP", "Whisper",
    ],
    "devops_infra": [
        "Docker", "Kubernetes", "K8s", "Helm", "Terraform", "Ansible",
        "CI/CD", "GitHub Actions", "Jenkins", "ArgoCD", "GitLab CI",
        "AWS", "GCP", "Azure", "Aliyun", "阿里云", "腾讯云",
        "Linux", "Nginx", "Caddy", "Prometheus", "Grafana",
        "ELK", "OpenTelemetry",
    ],
    "databases": [
        "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis",
        "Elasticsearch", "ClickHouse", "TiDB", "Cassandra",
        "Kafka", "RabbitMQ", "Pulsar", "NATS",
        "Qdrant", "Milvus", "Weaviate", "Pinecone", "Chroma",
        "DynamoDB", "Firestore",
    ],
    "tools_practices": [
        "Git", "GitHub", "GitLab", "Jira", "Confluence",
        "REST API", "GraphQL", "gRPC", "WebSocket",
        "Microservices", "Event-Driven", "DDD",
        "pytest", "Jest", "TDD", "Unit Test",
        "OpenAPI", "Swagger", "Protobuf",
    ],
    "chinese_specific": [
        "微服务", "分布式", "高并发", "消息队列", "缓存",
        "爬虫", "数据分析", "机器学习", "深度学习", "自然语言处理",
        "计算机视觉", "推荐系统", "知识图谱", "搜索引擎",
        "大数据", "实时计算", "流式处理",
    ],
}

SKILL_VOCAB: List[str] = [
    skill
    for skills in _VOCAB_BY_CATEGORY.values()
    for skill in skills
]


# --------------------------------------------------------------------------
# 预编译 regex（模块加载时执行一次）
# --------------------------------------------------------------------------
def _is_cjk(s: str) -> bool:
    return any(unicodedata.category(c) == "Lo" for c in s)


_PATTERNS: List[Tuple[re.Pattern, str]] = []
for _skill in SKILL_VOCAB:
    _escaped = re.escape(_skill)
    if _is_cjk(_skill):
        _pat = re.compile(_escaped)
    else:
        _pat = re.compile(r"\b" + _escaped + r"\b", re.IGNORECASE)
    _PATTERNS.append((_pat, _skill))


# --------------------------------------------------------------------------
# Phase 1: 关键词扫描
# --------------------------------------------------------------------------
def keyword_scan(text: str) -> List[str]:
    """扫描文本，返回词库中命中的规范技能名列表（有序、去重）。"""
    found: List[str] = []
    seen: set = set()
    for pattern, canonical in _PATTERNS:
        if canonical not in seen and pattern.search(text):
            found.append(canonical)
            seen.add(canonical)
    return found


# --------------------------------------------------------------------------
# Phase 2: 语义扫描（复用 embedder.py，无新模型）
# --------------------------------------------------------------------------
def semantic_scan(
    skills_section_text: str,
    already_found: List[str],
    threshold: float = 0.72,
) -> List[str]:
    """
    对词库中未被关键词扫描命中的项，通过 embedding 相似度补充识别。
    仅当 skills_section_text 足够长时运行（短文本噪声大）。
    阈值 0.72：paraphrase-multilingual-MiniLM-L12-v2 在该值下能捕获
    多语言同义词（如"机器学习"↔"Machine Learning"）同时抑制误报。
    """
    if len(skills_section_text.strip()) < 20:
        return []

    already_set = set(already_found)
    candidates = [s for s in SKILL_VOCAB if s not in already_set]
    if not candidates:
        return []

    try:
        from ..scoring import embedder  # 延迟导入，避免循环依赖
        all_texts = [skills_section_text] + candidates
        vecs = embedder.encode(all_texts)  # (N+1, 384)
    except Exception as e:
        logger.warning("语义扫描跳过（embedding 模型不可用）: %s", e)
        return []
    text_vec = vecs[0]

    extra: List[str] = []
    for i, skill_name in enumerate(candidates):
        sim = embedder.cosine_similarity(text_vec, vecs[i + 1])
        if sim >= threshold:
            extra.append(skill_name)
    return extra


# --------------------------------------------------------------------------
# 公开 API
# --------------------------------------------------------------------------
def extract_skills(
    full_text: str,
    skills_section_text: str = "",
    use_semantic: bool = True,
) -> List[str]:
    """
    混合技能提取。

    Args:
        full_text: 完整简历文本（用于关键词阶段）
        skills_section_text: 技能章节文本（用于语义阶段，更精准）
        use_semantic: 是否启用语义扫描（确定性场景传 False）

    Returns:
        规范技能名列表，关键词命中在前，语义补充在后，已去重。
    """
    keyword_results = keyword_scan(full_text)
    if not use_semantic or not skills_section_text:
        return keyword_results
    semantic_results = semantic_scan(skills_section_text, keyword_results)
    return keyword_results + semantic_results
