"""Product template database — instant responses for common queries.

⚠️ SIMULATED DATA ONLY — NOT REAL PRICES.
These templates exist as a development fallback and for instant UX feedback.
All data is explicitly marked with source="simulated" and confidence=0.0.

For production use, RAG search should be the primary data source.
"""

import hashlib
import uuid
from functools import lru_cache

# ---------------------------------------------------------------------------
# Image & URL helpers
# ---------------------------------------------------------------------------

PLATFORM_URLS = {
    "京东": "https://search.jd.com/Search?keyword={}",
    "天猫": "https://list.tmall.com/search_product.htm?q={}",
    "淘宝": "https://s.taobao.com/search?q={}",
    "得物": "https://www.dewu.com/search?keyword={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
}

IMAGES = {
    "iPhone": "https://images.unsplash.com/photo-1512054502232-10a0a035e672?w=400&h=400&fit=crop",
    "手机": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&h=400&fit=crop",
    "耳机": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop",
    "笔记本": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop",
    "平板": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&h=400&fit=crop",
    "相机": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=400&h=400&fit=crop",
    "手表": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400&h=400&fit=crop",
    "鞋": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop",
    "美妆": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=400&h=400&fit=crop",
    "护肤": "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=400&h=400&fit=crop",
    "包": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop",
    "香水": "https://images.unsplash.com/photo-1541643600914-78b084683601?w=400&h=400&fit=crop",
    "电视": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=400&h=400&fit=crop",
    "音箱": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=400&h=400&fit=crop",
    "键盘": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=400&h=400&fit=crop",
    "鼠标": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=400&h=400&fit=crop",
    "显示器": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=400&h=400&fit=crop",
    "显卡": "https://images.unsplash.com/photo-1591488320449-011701bb9704?w=400&h=400&fit=crop",
    "游戏机": "https://images.unsplash.com/photo-1486401899868-0e435ed85128?w=400&h=400&fit=crop",
    "Switch": "https://images.unsplash.com/photo-1578303512597-81e6cc155b3e?w=400&h=400&fit=crop",
    "PS5": "https://images.unsplash.com/photo-1606811841689-23dfddce3e95?w=400&h=400&fit=crop",
    "家电": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=400&h=400&fit=crop",
    "床垫": "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=400&h=400&fit=crop",
    "家具": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400&h=400&fit=crop",
    "灯": "https://images.unsplash.com/photo-1507473885765-e6ed057ab6fe?w=400&h=400&fit=crop",
}


def _pid(name: str, platform: str) -> str:
    return str(uuid.UUID(hashlib.md5(f"{name}_{platform}".encode()).hexdigest()))


def _img(keyword: str, name: str) -> str:
    for kw, url in IMAGES.items():
        if kw in name or kw in keyword:
            return url
    seed = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"https://picsum.photos/seed/{seed}/400/400"


def _url(name: str, platform: str) -> str:
    from urllib.parse import quote
    tmpl = PLATFORM_URLS.get(platform, "")
    return tmpl.format(quote(name)) if tmpl else ""


def _make_products(keyword: str, base_name: str, prices: list[tuple[str, float, float, float]]) -> list[dict]:
    """Build enriched product dicts from a price list [(platform, price, orig, rating), ...]."""
    results = []
    for platform, price, orig, rating in prices:
        name = f"{base_name}"
        results.append({
            "id": _pid(name, platform),
            "name": name,
            "platform": platform,
            "price": price,
            "original_price": orig,
            "rating": rating,
            "review_count": int(rating * 2000 + 1000),
            "url": _url(name, platform),
            "image_url": _img(keyword, name),
            "source": "simulated",
            "confidence": 0.0,
        })
    return results


# ---------------------------------------------------------------------------
# Template database — keyword → (products, review)
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, tuple[list[dict], dict]] = {}


def _register(keywords: list[str], base_name: str, prices: list[tuple[str, float, float, float]], review: dict):
    products = _make_products(keywords[0], base_name, prices)
    for kw in keywords:
        TEMPLATES[kw.lower()] = (products, review)


# === Smartphones ===
_register(
    ["iphone", "苹果手机", "iPhone 15", "iPhone 16", "iPhone Pro", "iPhone Max"],
    "iPhone 16 Pro Max 256GB",
    [
        ("京东", 8999, 9999, 4.8),
        ("天猫", 9199, 9999, 4.7),
        ("拼多多", 8499, 9999, 4.5),
    ],
    {"pros": ["A18 Pro芯片性能强劲", "钛金属边框质感出色"], "cons": ["价格较高", "充电速度一般"], "verdict": "预算充足首选，综合体验最佳"},
)

_register(
    ["华为", "huawei", "mate", "pura", "鸿蒙"],
    "HUAWEI Mate 70 Pro 512GB",
    [
        ("京东", 6999, 7999, 4.7),
        ("天猫", 7199, 7999, 4.6),
        ("拼多多", 6699, 7999, 4.5),
    ],
    {"pros": ["鸿蒙生态体验好", "卫星通信实用"], "cons": ["应用生态有待完善", "GMS不可用"], "verdict": "华为用户首选，鸿蒙生态体验佳"},
)

_register(
    ["小米", "xiaomi", "红米", "redmi"],
    "Xiaomi 15 Ultra 512GB",
    [
        ("京东", 5999, 6999, 4.6),
        ("天猫", 6199, 6999, 4.6),
        ("拼多多", 5699, 6999, 4.4),
    ],
    {"pros": ["徕卡影像出色", "性价比极高"], "cons": ["系统广告较多", "品牌溢价有限"], "verdict": "性价比之王，拍照党首选"},
)

_register(
    ["三星", "samsung", "galaxy", "s25"],
    "Samsung Galaxy S25 Ultra 256GB",
    [
        ("京东", 8999, 10199, 4.7),
        ("天猫", 9199, 10199, 4.6),
        ("得物", 8799, 10199, 4.5),
    ],
    {"pros": ["屏幕素质顶级", "S Pen生产力强"], "cons": ["价格对标iPhone", "系统更新偏慢"], "verdict": "安卓机皇，适合商务人士"},
)

# === Headphones ===
_register(
    ["耳机", "蓝牙耳机", "降噪耳机", "airpods", "earphone", "headphone"],
    "AirPods Pro 3 (USB-C)",
    [
        ("京东", 1799, 1999, 4.8),
        ("天猫", 1849, 1999, 4.7),
        ("得物", 1699, 1999, 4.6),
    ],
    {"pros": ["主动降噪效果业界标杆", "空间音频沉浸感强"], "cons": ["安卓兼容性一般", "续航中等"], "verdict": "iPhone用户无脑入，体验最好的TWS耳机"},
)

# === Laptops ===
_register(
    ["笔记本", "电脑", "macbook", "laptop", "thinkpad", "笔记本推荐"],
    "MacBook Pro 14 M4 Pro 512GB",
    [
        ("京东", 14999, 16999, 4.8),
        ("天猫", 15299, 16999, 4.7),
        ("拼多多", 14299, 16999, 4.6),
    ],
    {"pros": ["M4 Pro性能续航双王", "Liquid Retina XDR屏幕惊艳"], "cons": ["价格较高", "接口较少需转接"], "verdict": "专业用户首选，视频剪辑/编程利器"},
)

_register(
    ["游戏本", "拯救者", "rog", "暗影精灵"],
    "Lenovo 拯救者 Y9000P 2025",
    [
        ("京东", 8999, 9999, 4.6),
        ("天猫", 9199, 9999, 4.5),
        ("拼多多", 8599, 9999, 4.4),
    ],
    {"pros": ["RTX 5060满血释放", "散热优秀"], "cons": ["重量较大不便携", "续航较短"], "verdict": "游戏党/学生党首选，同价位性能最强"},
)

# === Tablets ===
_register(
    ["平板", "ipad", "tablet", "平板电脑"],
    "iPad Pro M4 11英寸 256GB",
    [
        ("京东", 7299, 8499, 4.8),
        ("天猫", 7499, 8499, 4.7),
        ("拼多多", 6999, 8499, 4.6),
    ],
    {"pros": ["M4芯片性能无敌", "Tandem OLED屏幕顶级"], "cons": ["iPadOS多任务限制", "配件价格贵"], "verdict": "最强平板，适合绘画/设计/影视"},
)

# === Watches ===
_register(
    ["手表", "watch", "智能手表", "apple watch"],
    "Apple Watch Ultra 3",
    [
        ("京东", 5999, 6499, 4.7),
        ("天猫", 6199, 6499, 4.6),
        ("得物", 5799, 6499, 4.5),
    ],
    {"pros": ["户外运动功能齐全", "续航大幅提升"], "cons": ["价格较高", "仅限iPhone使用"], "verdict": "运动爱好者首选，日常佩戴也出色"},
)

# === Shoes ===
_register(
    ["鞋", "球鞋", "运动鞋", "sneaker", "aj", "jordan", "dunk", "倒钩"],
    "Air Jordan 1 High OG 倒钩",
    [
        ("得物", 5499, 6499, 4.8),
        ("天猫", 5799, 6499, 4.6),
        ("京东", 5999, 6499, 4.5),
    ],
    {"pros": ["联名设计辨识度高", "收藏价值持续看涨"], "cons": ["价格溢价严重", "假货风险需鉴别"], "verdict": "球鞋收藏玩家必入，注意鉴别真伪"},
)

_register(
    ["跑鞋", "跑步鞋", "nike跑鞋", "adidas跑鞋"],
    "Nike Vaporfly Next% 4",
    [
        ("京东", 2199, 2599, 4.7),
        ("天猫", 2299, 2599, 4.6),
        ("得物", 2099, 2599, 4.6),
    ],
    {"pros": ["碳板回弹极佳", "比赛日PB神器"], "cons": ["日常训练磨损较快", "对配速有要求"], "verdict": "马拉松/速度训练首选，值得投资"},
)

# === Skincare / Beauty ===
_register(
    ["美妆", "护肤", "化妆品", "精华", "面霜", "skincare", "beauty"],
    "La Mer 海蓝之谜精华面霜 60ml",
    [
        ("天猫", 2399, 2800, 4.7),
        ("京东", 2499, 2800, 4.6),
        ("得物", 2299, 2800, 4.5),
    ],
    {"pros": ["修护保湿效果显著", "贵妇级使用体验"], "cons": ["价格不菲", "对油皮略厚重"], "verdict": "干皮/敏感肌冬季必备，值得投资"},
)

_register(
    ["香水", "perfume", "fragrance"],
    "Tom Ford Oud Wood 50ml",
    [
        ("得物", 1499, 1800, 4.7),
        ("天猫", 1599, 1800, 4.6),
        ("京东", 1649, 1800, 4.6),
    ],
    {"pros": ["乌木沉香高级感拉满", "留香持久8h+"], "cons": ["价格偏高", "前调略冲"], "verdict": "商务/约会场合首选，成熟男士必备"},
)

# === Gaming ===
_register(
    ["PS5", "ps5", "playstation", "索尼游戏"],
    "PlayStation 5 Pro 数字版",
    [
        ("京东", 4999, 5299, 4.8),
        ("天猫", 5099, 5299, 4.7),
        ("拼多多", 4799, 5299, 4.6),
    ],
    {"pros": ["独占大作阵容豪华", "DualSense手柄沉浸感强"], "cons": ["体积较大", "游戏价格偏高"], "verdict": "主机玩家必入，次世代体验无可替代"},
)

_register(
    ["Switch", "switch", "ns", "任天堂", "nintendo"],
    "Nintendo Switch 2 OLED",
    [
        ("京东", 2999, 3299, 4.7),
        ("天猫", 3099, 3299, 4.6),
        ("拼多多", 2799, 3299, 4.5),
    ],
    {"pros": ["独占IP丰富", "便携+TV双模式"], "cons": ["性能不及次世代主机", "Joy-Con漂移问题"], "verdict": "家庭娱乐首选，马里奥/塞尔达必玩"},
)

# === Home appliances ===
_register(
    ["电视", "tv", "电视机"],
    "Sony XR-A95L 65英寸 QD-OLED",
    [
        ("京东", 17999, 19999, 4.8),
        ("天猫", 18499, 19999, 4.7),
        ("拼多多", 17299, 19999, 4.5),
    ],
    {"pros": ["QD-OLED色彩顶级", "XR芯片画质调教好"], "cons": ["价格较高", "QD-OLED亮度有限"], "verdict": "影音发烧友首选，画质天花板"},
)

_register(
    ["扫地", "扫地机", "扫地机器人", "石头", "科沃斯"],
    "石头 G30 Ultra 自清洁扫拖机器人",
    [
        ("京东", 4599, 5299, 4.7),
        ("天猫", 4699, 5299, 4.6),
        ("拼多多", 4299, 5299, 4.5),
    ],
    {"pros": ["自清洁基站省心", "避障精准不撞家具"], "cons": ["价格偏高", "角落清洁有死角"], "verdict": "懒人福音，养宠家庭强烈推荐"},
)

_register(
    ["空调", "ac", "格力", "美的"],
    "Gree 格力 云锦-III 1.5匹 新一级能效",
    [
        ("京东", 3499, 3899, 4.6),
        ("天猫", 3599, 3899, 4.6),
        ("拼多多", 3299, 3899, 4.4),
    ],
    {"pros": ["新一级能效省电", "制冷制热速度快"], "cons": ["外观设计中规中矩", "遥控器功能复杂"], "verdict": "家庭空调首选，格力品质有保障"},
)

# === Graphics Cards ===
_register(
    ["显卡", "GPU", "RTX", "rtx", "GeForce", "显卡推荐", "游戏显卡"],
    "NVIDIA GeForce RTX 5090 32GB",
    [
        ("京东", 15999, 17999, 4.8),
        ("天猫", 16499, 17999, 4.7),
        ("拼多多", 14999, 17999, 4.5),
    ],
    {"pros": ["Blackwell架构性能翻倍", "32GB显存4K无忧"], "cons": ["价格昂贵", "功耗较高"], "verdict": "顶级游戏/AI计算显卡，预算充足闭眼入"},
)

_register(
    ["RTX5080", "rtx5080", "5080"],
    "NVIDIA GeForce RTX 5080 16GB",
    [
        ("京东", 9499, 10999, 4.7),
        ("天猫", 9799, 10999, 4.6),
        ("拼多多", 8999, 10999, 4.5),
    ],
    {"pros": ["4K高刷无压力", "DLSS 4画质惊艳"], "cons": ["16GB显存略紧", "性价比不如5070Ti"], "verdict": "4K游戏最佳性价比之选"},
)

_register(
    ["RTX5070", "rtx5070", "5070", "5070ti"],
    "NVIDIA GeForce RTX 5070 Ti 16GB",
    [
        ("京东", 6499, 7499, 4.6),
        ("天猫", 6799, 7499, 4.6),
        ("拼多多", 6199, 7499, 4.5),
    ],
    {"pros": ["2K通吃/4K可玩", "能耗比出色"], "cons": ["高端VRAM不够充裕", "光追极限场景吃力"], "verdict": "2K游戏甜点卡，性价比极高"},
)

# === CPUs ===
_register(
    ["CPU", "cpu", "处理器", "英特尔", "酷睿", "i9", "i7", "i5"],
    "Intel Core i9-14900K",
    [
        ("京东", 4399, 4999, 4.8),
        ("天猫", 4599, 4999, 4.7),
        ("拼多多", 4199, 4999, 4.6),
    ],
    {"pros": ["8P+16E核多任务王", "单核6.0GHz游戏强"], "cons": ["功耗较高需好散热", "AM5平台竞争激烈"], "verdict": "兼顾游戏和生产力，Intel平台旗舰"},
)

_register(
    ["AMD", "amd", "锐龙", "ryzen", "Ryzen"],
    "AMD Ryzen 7 7800X3D",
    [
        ("京东", 2799, 3299, 4.8),
        ("天猫", 2899, 3299, 4.7),
        ("拼多多", 2599, 3299, 4.6),
    ],
    {"pros": ["3D V-Cache游戏性能王", "能耗比出色"], "cons": ["生产力弱于同级Intel", "不支持DDR4"], "verdict": "纯游戏玩家首选，帧率王者"},
)

# === Monitors ===
_register(
    ["显示器", "屏幕", "monitor", "4K显示器", "电竞显示器"],
    "Dell U3225QE 32英寸 4K IPS Black",
    [
        ("京东", 3999, 4699, 4.6),
        ("天猫", 4199, 4699, 4.5),
        ("拼多多", 3799, 4699, 4.4),
    ],
    {"pros": ["IPS Black对比度翻倍", "出厂校色ΔE<1"], "cons": ["60Hz不适合电竞", "HDR400偏弱"], "verdict": "专业设计/办公首选，色彩准确度顶级"},
)

_register(
    ["电竞", "高刷", "240hz", "360hz"],
    "Samsung Odyssey G9 57英寸 Dual 4K 240Hz",
    [
        ("京东", 14999, 17999, 4.7),
        ("天猫", 15499, 17999, 4.6),
        ("拼多多", 13999, 17999, 4.4),
    ],
    {"pros": ["双4K沉浸式体验", "240Hz电竞流畅"], "cons": ["桌面深度要求高", "显卡压力巨大"], "verdict": "极致沉浸游戏体验，桌面空间充足必入"},
)

# === General / fallback ===
_register(
    ["推荐", "recommend", "性价比", "值得买", "必买"],
    "年度性价比之选 综合推荐",
    [
        ("京东", 999, 1299, 4.5),
        ("天猫", 989, 1299, 4.5),
        ("拼多多", 899, 1299, 4.3),
    ],
    {"pros": ["性价比突出", "同价位配置领先"], "cons": ["需多方比价", "库存可能紧张"], "verdict": "建议多家比价后入手，当前价格有竞争力"},
)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1024)
def match_template(query: str) -> tuple[list[dict], dict] | None:
    """Return (products, review) if query matches a known template, else None."""
    q = query.lower()
    # Longest match first for better accuracy
    for keyword in sorted(TEMPLATES, key=len, reverse=True):
        if keyword in q:
            return TEMPLATES[keyword]
    return None
