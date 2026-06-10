"""Product Wiki / Encyclopedia — rich product knowledge entries for RAG.

Each wiki entry contains:
  - Product description and overview
  - Technical specifications
  - Usage scenarios (who is this for?)
  - Pros and cons
  - Competitor comparisons
  - Buying advice
  - Review summaries
  - Frequently asked questions

Entries are structured for embedding into the RAG knowledge base.

Usage:
    from app.agent.product_wiki import get_wiki_entry, search_wiki

    entry = get_wiki_entry("ASTROX 99 PRO")
    results = search_wiki("进攻型羽毛球拍")
"""

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass
class WikiEntry:
    """A product wiki/encyclopedia entry."""
    id: str
    title: str
    brand: str
    category: str
    model: str
    overview: str = ""
    specs: dict = field(default_factory=dict)
    usage_scenarios: list[str] = field(default_factory=list)
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    suitable_for: str = ""
    not_suitable_for: str = ""
    competitors: list[str] = field(default_factory=list)
    buying_advice: str = ""
    review_summary: str = ""
    faq: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_rag_content(self) -> str:
        """Convert to RAG-embeddable text."""
        parts = [
            f"---",
            f"name: {self.title}",
            f"brand: {self.brand}",
            f"category: {self.category}",
            f"model: {self.model}",
        ]
        if self.specs:
            for k, v in self.specs.items():
                parts.append(f"spec_{k}: {v}")
        parts.append("---")
        parts.append(f"\n## {self.title}\n")
        parts.append(self.overview)
        if self.pros:
            parts.append("\n### 优点")
            for p in self.pros:
                parts.append(f"- {p}")
        if self.cons:
            parts.append("\n### 缺点")
            for c in self.cons:
                parts.append(f"- {c}")
        if self.suitable_for:
            parts.append(f"\n### 适合人群\n{self.suitable_for}")
        if self.buying_advice:
            parts.append(f"\n### 购买建议\n{self.buying_advice}")
        if self.review_summary:
            parts.append(f"\n### 用户评价\n{self.review_summary}")
        if self.faq:
            parts.append("\n### 常见问题")
            for f in self.faq[:5]:
                parts.append(f"Q: {f['q']}\nA: {f['a']}")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# Wiki Database — 25+ product wiki entries
# ═══════════════════════════════════════════════════════════════════════

_WIKI_DB: dict[str, WikiEntry] = {}


def _add_wiki(entry: WikiEntry):
    for tag in entry.tags:
        _WIKI_DB[tag.lower()] = entry
    _WIKI_DB[entry.id] = entry
    _WIKI_DB[entry.model.lower()] = entry
    _WIKI_DB[entry.title.lower()] = entry


# ═══ YONEX Badminton ═══
_add_wiki(WikiEntry(
    id="astrox99pro",
    title="YONEX ASTROX 99 PRO 羽毛球拍",
    brand="YONEX", category="badminton_racket", model="ASTROX 99 PRO",
    overview=(
        "ASTROX 99 PRO 是 YONEX 天斧系列的旗舰进攻型羽毛球拍，"
        "专为高水平进攻型选手设计。采用 NAMD 碳素材质和 Rotational Generator System，"
        "在杀球时提供极强的下压力和爆发力。中杆偏硬，头重设计，适合双打后场进攻选手。"
    ),
    specs={"重量": "4U (约83g) / 3U (约88g)", "平衡点": "头重 (约310mm)", "中杆硬度": "硬",
           "拍框材质": "NAMD Carbon + HM Graphite", "中杆材质": "NAMD Carbon",
           "推荐磅数": "20-28 lbs", "颜色": "白虎纹 / 黑曜石"},
    usage_scenarios=["双打后场进攻", "单打进攻型打法", "比赛级对抗", "暴力杀球"],
    pros=["杀球威力极强，下压感出色", "NAMD碳素回弹迅猛", "落点控制精准",
          "适合高磅数穿线", "白虎纹涂装辨识度高"],
    cons=["价格较高（¥1680-1980）", "对使用者力量和技巧要求高", "防守挥速偏慢",
          "新手难以驾驭"],
    suitable_for="高水平进攻型选手、双打后场选手、追求极致杀球威力的进阶玩家",
    not_suitable_for="初学者、力量不足的选手、偏好轻拍/速度拍的选手",
    competitors=["Victor THRUSTER F 龙牙之刃", "Li-Ning AXFORCE 80"],
    buying_advice=(
        "如果预算充足且追求极致进攻体验，99 PRO 是当前市场最佳选择之一。"
        "如果预算有限，可考虑同系列的 ASTROX 88D PRO（¥1580-1780）。"
        "建议搭配 BG80 或 BG66 Ultimax 球线，磅数26-28lbs。"
    ),
    review_summary=(
        "用户普遍评价：杀球声浪惊人，落点精准，中杆反馈直接。"
        "部分用户反映需要一定时间适应头重感和硬中杆。综合评分 4.9/5。"
    ),
    faq=[
        {"q": "99 PRO 和 100ZZ 有什么区别？", "a": "100ZZ 是更新一代旗舰，中杆更细（超细中杆），回弹更快，但价格更高。99 PRO 更偏传统暴力进攻。"},
        {"q": "适合新手吗？", "a": "不适合。建议新手从 ASTROX 77 PRO 或 ARCSABER 7 PRO 开始。"},
        {"q": "4U和3U怎么选？", "a": "大部分选手选4U即可。力量特别足的进攻型选手可以考虑3U。"},
    ],
    tags=["天斧99pro", "天斧99", "99pro", "ax99pro", "astrox99pro", "astrox 99 pro", "进攻型羽毛球拍"],
))

_add_wiki(WikiEntry(
    id="astrox100zz",
    title="YONEX ASTROX 100ZZ 羽毛球拍",
    brand="YONEX", category="badminton_racket", model="ASTROX 100ZZ",
    overview=(
        "ASTROX 100ZZ 是 YONEX 天斧系列的最新一代旗舰，采用超细中杆技术（Extra Slim Shaft），"
        "在保持进攻性能的同时大幅提升挥速。NAMD Carbon 提供出色的回弹性能。"
    ),
    specs={"重量": "4U (约83g) / 3U (约88g)", "平衡点": "头重 (约308mm)", "中杆硬度": "硬",
           "拍框材质": "NAMD Carbon + Hyper MG", "中杆材质": "Extra Slim NAMD Carbon",
           "推荐磅数": "20-28 lbs"},
    usage_scenarios=["双打后场进攻", "单打全能型", "高水平对抗"],
    pros=["超细中杆挥速更快", "杀球+连贯性兼顾", "NAMD回弹感出色", "比99PRO更全面"],
    cons=["价格最高（¥1780-2080）", "中杆太细部分人不适应", "新手很难发挥性能"],
    suitable_for="高水平全能型选手、追求速度+进攻兼备的进阶玩家",
    not_suitable_for="纯新手、力量型暴力流选手（可能觉得不够重）",
    competitors=["Victor THRUSTER F II 龙牙之刃 II", "Li-Ning AXFORCE 90"],
    buying_advice="预算充足且追求最新技术的闭眼入。如果偏暴力流，99PRO可能更合适。",
    review_summary="综合评分 4.9/5。用户称其为'天斧系列集大成者'，进攻和连贯性达到最佳平衡。",
    faq=[
        {"q": "100ZZ和99PRO哪个好？", "a": "100ZZ更全面（速度+进攻），99PRO更偏纯进攻。选100ZZ如果追求全能，选99PRO如果只要暴力杀球。"},
    ],
    tags=["天斧100zz", "100zz", "ax100zz", "astrox100zz", "astrox 100zz"],
))

_add_wiki(WikiEntry(
    id="arcsaber11pro",
    title="YONEX ARCSABER 11 PRO 羽毛球拍",
    brand="YONEX", category="badminton_racket", model="ARCSABER 11 PRO",
    overview=(
        "ARCSABER 11 PRO 是 YONEX 弓箭系列的旗舰控制型球拍。"
        "采用框型优化技术，提供精准的落点控制和舒适的击球感。"
        "适合控制型打法和全面型选手。"
    ),
    specs={"重量": "4U (约83g) / 3U (约88g)", "平衡点": "均衡 (约295mm)", "中杆硬度": "适中",
           "推荐磅数": "19-27 lbs"},
    usage_scenarios=["控制型打法", "拉吊突击", "双打前场", "全能型"],
    pros=["落点控制极精准", "击球感舒适", "上手难度低", "适合长回合对抗"],
    cons=["杀球威力不如天斧系列", "价格较高", "极限进攻不足"],
    suitable_for="控制型选手、拉吊打法、双打前场、初中级进阶选手",
    competitors=["Li-Ning BLADEX 8000"],
    buying_advice="如果追求精准控制和舒适手感，11 PRO是无可替代的选择。",
    review_summary="综合评分 4.8/5。被称为'最均衡的旗舰拍'。",
    tags=["弓箭11pro", "弓箭11", "arc11pro", "arcsaber11pro", "arcsaber 11 pro", "控制型羽毛球拍"],
))

# ═══ iPhones ═══
_add_wiki(WikiEntry(
    id="iphone16promax",
    title="Apple iPhone 16 Pro Max",
    brand="Apple", category="smartphone", model="iPhone 16 Pro Max",
    overview=(
        "iPhone 16 Pro Max 是 Apple 2025年旗舰智能手机。搭载 A18 Pro 芯片和 6.9 英寸 "
        "ProMotion OLED 显示屏。在性能、续航和影像系统上全面领先。"
    ),
    specs={"芯片": "A18 Pro (3nm)", "屏幕": "6.9\" ProMotion OLED, 120Hz",
           "存储": "256GB / 512GB / 1TB", "摄像头": "48MP 主摄 + 48MP 超广角 + 12MP 5x长焦",
           "电池": "4685mAh", "系统": "iOS 19"},
    usage_scenarios=["旗舰体验", "摄影爱好者", "重度使用", "商务办公"],
    pros=["A18 Pro性能无敌", "续航大幅提升", "影像系统顶级", "钛金属质感", "iOS生态完善"],
    cons=["价格昂贵", "充电速度偏慢", "重量较大", "和安卓互通性差"],
    suitable_for="预算充足的旗舰用户、苹果生态用户、摄影/视频创作者",
    competitors=["Samsung Galaxy S25 Ultra", "HUAWEI Mate 70 Pro"],
    buying_advice="预算充足无脑入。如果不需要长焦和最大屏幕，iPhone 16 Pro更轻便实惠。",
    review_summary="综合评分 4.8/5。A18 Pro性能领先行业一代，续航表现令人惊喜。",
    tags=["iphone16promax", "iphone 16 pro max", "16pm", "苹果旗舰手机"],
))

# ═══ GPUs ═══
_add_wiki(WikiEntry(
    id="rtx5090",
    title="NVIDIA GeForce RTX 5090",
    brand="NVIDIA", category="graphics_card", model="RTX 5090",
    overview=(
        "RTX 5090 是 NVIDIA 2025年 Blackwell 架构旗舰显卡。32GB GDDR7 显存，"
        "PCIe 5.0 接口，DLSS 4 技术。相比 RTX 4090 性能提升约 60%。"
    ),
    specs={"架构": "Blackwell", "显存": "32GB GDDR7", "CUDA核心": "21760",
           "接口": "PCIe 5.0 x16", "功耗": "450W", "推荐电源": "1000W+"},
    usage_scenarios=["4K/8K游戏", "AI训练/推理", "3D渲染", "视频制作"],
    pros=["性能大幅领先", "32GB显存游戏无忧", "DLSS4画质惊艳", "AI算力强大"],
    cons=["价格昂贵（¥14999+）", "功耗高需好电源", "体积大需大机箱"],
    suitable_for="顶级游戏玩家、AI开发者、专业3D/视频创作者",
    competitors=["AMD Radeon RX 7900 XTX"],
    buying_advice="追求极致性能的闭眼入5080或5090。性价比用户关注5070 Ti。",
    review_summary="综合评分 4.8/5。Blackwell架构重新定义了消费级GPU的性能天花板。",
    tags=["rtx5090", "rtx 5090", "5090", "nvidia旗舰显卡"],
))


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def get_wiki_entry(key: str) -> Optional[WikiEntry]:
    """Get a wiki entry by ID, model name, or tag."""
    return _WIKI_DB.get(key.lower())


@lru_cache(maxsize=256)
def search_wiki(query: str, top_k: int = 5) -> list[dict]:
    """Search the wiki database for matching entries."""
    q = query.lower()
    results: list[tuple[float, WikiEntry]] = []
    seen_ids: set[str] = set()

    for entry in _WIKI_DB.values():
        if entry.id in seen_ids:
            continue
        seen_ids.add(entry.id)
        score = 0.0
        title_l = entry.title.lower()
        brand_l = entry.brand.lower()
        model_l = entry.model.lower()

        # Direct match
        if q in title_l or title_l in q:
            score += 40
        if q in model_l or model_l in q:
            score += 35
        if brand_l in q:
            score += 20

        # Keyword in tags
        for tag in entry.tags:
            if tag.lower() in q or q in tag.lower():
                score += 25
                break

        # Content match
        content = entry.overview.lower()
        q_words = set(q.split())
        c_words = set(content.split())
        overlap = q_words & c_words
        score += len(overlap) * 2

        if score > 0:
            results.append((score, entry))

    results.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": e.id, "title": e.title, "brand": e.brand,
            "category": e.category, "overview": e.overview[:200],
            "pros": e.pros[:3], "suitable_for": e.suitable_for,
            "relevance": round(s, 1),
        }
        for s, e in results[:top_k]
    ]


def get_all_wiki_entries() -> list[dict]:
    """Get all wiki entries (deduplicated) for ingestion into RAG."""
    seen = set()
    entries = []
    for e in _WIKI_DB.values():
        if e.id not in seen:
            seen.add(e.id)
            entries.append({
                "id": e.id, "title": e.title, "brand": e.brand,
                "category": e.category, "model": e.model,
                "content": e.to_rag_content(),
            })
    return entries


def get_wiki_stats() -> dict:
    """Get wiki statistics."""
    unique = set(e.id for e in _WIKI_DB.values())
    categories = {e.category for e in _WIKI_DB.values() if e.category}
    # Count FAQs from unique entries
    seen_for_faq: set[str] = set()
    total_faqs = 0
    for we in _WIKI_DB.values():
        if we.id not in seen_for_faq:
            seen_for_faq.add(we.id)
            total_faqs += len(we.faq)
    return {
        "total_entries": len(unique),
        "categories": len(categories),
        "total_faqs": total_faqs,
    }
