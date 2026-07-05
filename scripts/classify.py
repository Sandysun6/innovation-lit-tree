"""15 分支 v3 分类器 + 主题标签（本仓库权威版本）。
规则来源：项目 04_数据schema与分支v3.md。含两处修正：
- 11 支（经典综述）触发词 + JEL/review 类型兜底（修复 A 线首轮挂零 bug）
- 06 支补充 trade liberalization / offshoring / exporters（首轮占比过低）
"""
import re

RULES = {
    "01": ["endogenous growth", "schumpeterian", "schumpeter", "creative destruction",
           "quality ladder", "idea production", "knowledge production function", "aghion",
           "romer", "klette-kortum", "akcigit", "growth model", "ideas getting harder",
           "ideas harder to find", "endogenous technical", "knowledge creation",
           "innovation-led growth",
           "内生增长", "熊彼特", "破坏性创新", "质量阶梯", "创新理论"],
    "02": ["firm innovation", "corporate r&d", "firm-level", "ceo", "organizational innovation",
           "firm patent", "internal innovation", "r&d investment", "board of directors",
           "managerial", "acquisition", "m&a", "merger and acquisition", "corporate innovation",
           "firm r&d", "firm growth",
           "企业创新", "公司创新", "企业研发", "公司研发", "高管"],
    "03": ["spillover", "knowledge diffusion", "technology diffusion", "technology transfer",
           "jaffe", "trajtenberg", "geographic spillover", "supply chain spillover",
           "knowledge flow", "citation spillover", "knowledge spillover", "cluster effect",
           "agglomeration economies", "high-tech cluster", "innovation cluster",
           "technology adoption", "management practice",
           "知识溢出", "技术扩散", "技术转移", "技术溢出", "溢出效应", "技术采用"],
    "04": ["r&d tax credit", "innovation policy", "patent policy", "ip protection",
           "intellectual property", "antitrust", "industrial policy", "r&d subsidy",
           "innovation subsidy", "patent reform", "patent system", "taxation and innovation",
           "tax and innovation", "federal funding", "government funding", "government r&d",
           "r&d funding", "research funding", "innovation tax", "merger policy",
           "competition policy", "climate policy", "carbon pricing", "carbon tax", "energy policy",
           "创新政策", "研发补贴", "税收抵免", "专利政策", "产业政策", "知识产权", "专利制度", "反垄断"],
    "05": ["venture capital", "innovation finance", "r&d financing", "equity incentive",
           "financial friction", "bank credit innovation", "stock option innovation",
           "financing constraint", "ipo innovation", "private equity innovation", "venture",
           "vc funding", "angel investor",
           "风险投资", "创业投资", "股权激励", "金融摩擦", "融资约束"],
    "06": ["trade innovation", "import competition", "export innovation", "global value chain",
           "gvc", "tariff innovation", "trade liberalization innovation", "china shock",
           "foreign direct investment", "fdi spillover", "export-led innovation",
           "trade liberalization", "offshoring", "exporters",
           "贸易创新", "进口竞争", "出口创新", "全球价值链", "关税"],
    "07": ["skill-biased", "sbtc", "skill biased", "automation", "inventor mobility",
           "high-skilled", "h-1b", "immigrant", "human capital", "robot", "task-based",
           "labor market", "lifecycle earnings", "new work", "migrant", "stem worker",
           "labor supply",
           "技能偏向", "自动化", "机器人", "人力资本", "高技能移民", "劳动力市场"],
    "08": ["patent citation", "text analysis", "word2vec", "topic model",
           "innovation measurement", "knowledge capital measurement", "patent classification",
           "npl similarity", "patent text", "bibliometric", "patent data", "citation network",
           "专利引用", "文本分析", "创新度量", "创新测度"],
    "09": ["tfp", "total factor productivity", "growth accounting", "misallocation",
           "cross-country innovation", "productivity growth", "national innovation",
           "economic growth", "long-run growth", "productivity",
           "全要素生产率", "增长核算", "误配置", "经济增长"],
    "10": ["china", "chinese",
           "新质生产力", "高质量发展", "中国创新", "自主创新", "中国特色", "中国专利", "中国"],
    "11": ["handbook of economics of innovation", "survey innovation", "handbook innovation",
           "literature review", "a survey of", "survey of the", "review of the literature",
           "what do we learn", "what have we learned",
           "创新综述", "文献综述"],
    "12": ["science funding", "scientific funding", "nih", "nsf", "research grant",
           "grant funding", "basic research", "university research", "academic scientist",
           "scientist", "science of science", "scientific research", "tech transfer",
           "technology licensing", "academic research", "publication", "peer review",
           "ai for science", "scientific labor", "postdoc", "phd",
           "科学经济学", "科研资助", "基础研究", "大学科研", "科学家", "技术转移办公室"],
    "13": ["product market competition", "competition and innovation", "market structure",
           "superstar firm", "market power", "markup", "killer acquisition", "monopoly",
           "duopoly", "firm entry", "market entry", "entry deterrence", "inverted-u",
           "inverted u", "platform competition", "big tech", "digital platform", "antitrust",
           "市场结构", "市场势力", "平台竞争", "反垄断", "加成率"],
    "14": ["inventor", "entrepreneur", "entrepreneurship", "startup", "founder",
           "lost einstein", "innovator", "self-employ", "immigrant inventor", "inventor team",
           "research team", "gender gap", "serial entrepreneur", "star scientist", "top inventor",
           "发明家", "发明者", "企业家", "创业者", "创业", "科学家流动"],
    "15": ["directed technical change", "directed innovation", "directed r&d",
           "green innovation", "clean technology", "clean energy", "climate innovation",
           "environmental innovation", "renewable", "energy transition", "carbon capture",
           "electric vehicle", "pharmaceutical", "drug development", "clinical trial",
           "medical innovation", "vaccine", "mission-oriented", "moonshot",
           "绿色创新", "定向技术", "气候技术", "清洁能源", "医药创新", "新能源"],
}

TAGS = {
    "AI": ["artificial intelligence", "machine learning", "deep learning", "generative ai",
           "large language model", "algorithm", "人工智能", "机器学习", "大模型"],
    "绿色": ["green", "climate", "clean energy", "carbon", "environmental", "renewable",
           "emission", "绿色", "气候", "新能源"],
    "数字平台": ["platform", "digital economy", "e-commerce", "online market", "gig economy",
           "big tech", "平台经济", "数字经济", "电商"],
    "新质生产力": ["new quality productive", "新质生产力", "高质量发展"],
}

def _has_cjk(s):
    return any("一" <= ch <= "鿿" for ch in s)

def _compile(phrases):
    pats = []
    for p in phrases:
        if _has_cjk(p):
            pats.append(("zh", p))
        else:
            # 英文短语：两侧不能紧邻字母数字（兼容 r&d、inverted-u 等含符号短语）
            pats.append(("en", re.compile(r"(?<![a-z0-9])" + re.escape(p.lower()) + r"(?![a-z0-9])")))
    return pats

_RULES_C = {code: _compile(ph) for code, ph in RULES.items()}
_TAGS_C = {tag: _compile(ph) for tag, ph in TAGS.items()}

def _match(pats, text):
    for kind, p in pats:
        if kind == "zh":
            if p in text:
                return True
        elif p.search(text):
            return True
    return False

def classify(title, abstract, journal=None, wtype=None):
    """返回 (branches, tags)。text 匹配 + 类型兜底。"""
    text = f"{title or ''} {abstract or ''}".lower()
    branches = [c for c, pats in _RULES_C.items() if _match(pats, text)]
    # 11 支兜底：JEL 期刊或 review 类型直接归架
    if "11" not in branches and (journal == "JEL" or (wtype and "review" in str(wtype).lower())):
        branches.append("11")
    tags = [t for t, pats in _TAGS_C.items() if _match(pats, text)]
    return sorted(branches), tags
