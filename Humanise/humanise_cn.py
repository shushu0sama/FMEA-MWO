"""
Chinese MWO sentence humanization module.
Replaces English-specific humanization (contractions, QWERTY typos, CMU homophones)
with Chinese-specific patterns (pinyin confusion, shape confusion, industrial abbreviations).

Usage:
    from humanise_cn import cn_humanise_sentence
    result = cn_humanise_sentence("前舱主梁组件发现断裂需要更换")
"""

import re
import random

# ============================================================
# Dictionary 1: Chinese Industrial Abbreviations & Jargon
# Format: {original_term: [abbreviated_variants]}
# ============================================================

CN_ABBREVIATIONS = {
    # 发动机 / 引擎相关
    "发动机": ["发", "引擎", "动力"],
    "柴油机": ["柴发", "柴油"],
    "汽油机": ["汽发", "汽油"],

    # 泵、电机
    "液压泵": ["液泵", "HYD泵", "油泵"],
    "燃油泵": ["油泵", "燃泵", "FP"],
    "水泵": ["水泵", "WP"],
    "电机": ["马达", "MOTOR"],

    # 控制器、传感器
    "控制器": ["控", "CTRL", "控制器"],
    "传感器": ["探头", "SENSOR", "感应器", "sensor"],
    "温度传感器": ["温感", "T-sensor", "温度探头"],
    "压力传感器": ["压感", "P-sensor"],

    # 散热、冷却
    "散热器": ["散热", "散热片", "RAD"],
    "冷却系统": ["冷却系", "冷系"],
    "冷却液": ["防冻液", "冷却水"],

    # 制动、刹车
    "制动系统": ["刹车系", "制动系", "刹车"],
    "刹车片": ["制动片", "刹车皮", "闸片"],
    "制动盘": ["刹车盘", "制动碟"],

    # 变速箱、传动
    "变速箱": ["波箱", "变速", "TRANS"],
    "传动轴": ["传轴", "驱动轴"],
    "离合器": ["离合", "CLUTCH"],

    # 起落架（航空）
    "起落架": ["起架", "LG", "起落"],
    "主起落架": ["主起", "MLG"],
    "前起落架": ["前起", "NLG"],

    # 密封件
    "密封圈": ["O型圈", "密封环", "油封", "O-RING"],
    "密封垫": ["垫片", "密封片", "GASKET"],
    "密封件": ["密封", "油封"],

    # 过滤器
    "过滤器": ["滤芯", "滤清器", "FILTER"],
    "空气滤清器": ["空滤", "A/F"],
    "机油滤清器": ["机滤", "O/F"],

    # 结构件
    "主梁": ["大梁", "主桁", "主梁"],
    "蒙皮": ["外壳", "皮", "SKIN"],
    "桁架": ["框架", "骨架", "FRAME"],
    "翼肋": ["肋", "RIB"],

    # 管路、阀
    "作动筒": ["作动", "缸", "ACT"],
    "液压缸": ["油缸", "液缸", "HYD CYL"],
    "阀门": ["阀", "VALVE"],
    "管路": ["管道", "管系", "PIPING"],

    # 电气
    "接线盒": ["接线箱", "J-BOX", "分线盒"],
    "保险丝": ["熔断器", "FUSE", "保险"],
    "继电器": ["继电", "RELAY"],
    "断路器": ["空开", "BREAKER", "开关"],

    # 通用维修术语
    "不工作": ["失效", "罢工", "不灵", "坏了"],
    "更换": ["换", "替换", "更换"],
    "检查": ["查", "排查", "巡检", "点检"],
    "故障": ["毛病", "问题", "坏", "异常"],
    "需要": ["需", "得", "要", "须"],
    "损坏": ["坏了", "破损", "烂了", "损伤"],
    "断裂": ["断了", "裂了", "裂开", "断裂"],
    "泄漏": ["漏了", "渗漏", "漏油"],
    "磨损": ["磨了", "老化", "磨耗"],
    "腐蚀": ["锈蚀", "生锈", "锈了"],
    "松动": ["松了", "不紧", "活动"],
    "堵塞": ["堵了", "不通", "阻塞"],
    "变形": ["歪了", "弯了", "走形"],
    "修复": ["修", "修好", "恢复"],
    "拆检": ["拆开看", "拆检", "解体检查"],

    # 方向
    "左侧": ["L侧", "左边", "LH"],
    "右侧": ["R侧", "右边", "RH"],
    "前部": ["前", "FWD"],
    "后部": ["后", "AFT"],
}

# ============================================================
# Dictionary 2: Pinyin Input Method Confusion Matrix
# Common input method errors where similar pinyin leads to wrong character
# ============================================================

CN_PINYIN_CONFUSION = {
    # 主-zhǔ / 柱-zhù / 住-zhù
    "主": ["柱", "住", "注", "驻"],
    # 梁-liáng / 粮-liáng / 凉-liáng / 亮-liàng / 粱-liáng
    "梁": ["粮", "凉", "亮", "粱", "量"],
    # 裂-liè / 烈-liè / 列-liè / 劣-liè
    "裂": ["烈", "列", "劣", "猎"],
    # 封-fēng / 风-fēng / 峰-fēng / 丰-fēng
    "封": ["风", "峰", "丰", "蜂"],
    # 泵-bèng / 崩-bēng / 蹦-bèng
    "泵": ["崩", "蹦", "甭"],
    # 散-sàn / 三-sān / 伞-sǎn
    "散": ["三", "伞", "叁"],
    # 热-rè / 惹-rě
    "热": ["惹", "喏"],
    # 器-qì / 气-qì / 弃-qì / 其-qí
    "器": ["气", "弃", "其", "汽"],
    # 检-jiǎn / 见-jiàn / 建-jiàn / 减-jiǎn
    "检": ["见", "建", "减", "简", "捡"],
    # 修-xiū / 休-xiū / 秀-xiù
    "修": ["休", "秀", "锈"],
    # 更-gēng/gèng / 耕-gēng / 庚-gēng
    "更": ["耕", "庚", "耿"],
    # 换-huàn / 环-huán / 幻-huàn / 缓-huǎn
    "换": ["环", "幻", "缓", "唤"],
    # 油-yóu / 由-yóu / 有-yǒu / 游-yóu
    "油": ["由", "有", "游", "邮"],
    # 漏-lòu / 露-lù / 楼-lóu
    "漏": ["露", "楼", "陋"],
    # 发-fā / 法-fǎ / 罚-fá
    "发": ["法", "罚", "阀"],
    # 动-dòng / 东-dōng / 洞-dòng
    "动": ["东", "洞", "冻"],
    # 机-jī / 鸡-jī / 积-jī
    "机": ["鸡", "积", "基", "激"],
    # 故-gù / 古-gǔ / 固-gù
    "故": ["古", "固", "顾"],
    # 障-zhàng / 章-zhāng / 涨-zhǎng
    "障": ["章", "涨", "张"],
    # 组-zǔ / 祖-zǔ / 阻-zǔ
    "组": ["祖", "阻", "族"],
    # 件-jiàn / 见-jiàn / 建-jiàn
    "件": ["见", "建", "键", "健"],
    # 断-duàn / 段-duàn / 短-duǎn
    "断": ["段", "短", "端"],
    # 更-gēng/gèng / 耕-gēng
    "更": ["耕", "庚"],
    # 需-xū / 须-xū / 虚-xū
    "需": ["须", "虚", "许"],
    # 冷-lěng / 愣-lèng
    "冷": ["愣", "楞"],
    # 却-què / 确-què / 缺-quē
    "却": ["确", "缺", "雀"],
    # 系-xì / 细-xì / 戏-xì
    "系": ["细", "戏", "吸"],
    # 统-tǒng / 同-tóng / 通-tōng
    "统": ["同", "通", "痛"],
    # 损-sǔn / 孙-sūn / 笋-sǔn
    "损": ["孙", "笋", "榫"],
    # 坏-huài / 还-huán / 怀-huái
    "坏": ["还", "怀", "徊"],
    # 查-chá / 茶-chá / 察-chá
    "查": ["茶", "察", "差"],
}

# ============================================================
# Dictionary 3: Character Shape (字形) Confusion Matrix
# Characters that look similar and might be typed incorrectly
# ============================================================

CN_SHAPE_CONFUSION = {
    "梁": ["粱"],
    "裂": ["烈"],
    "换": ["唤", "焕"],
    "泵": ["汞"],
    "器": ["嚣"],
    "封": ["卦"],
    "检": ["捡", "睑"],
    "修": ["脩"],
    "漏": ["陋"],
    "油": ["汕", "泔"],
    "故": ["敌", "效"],
    "障": ["幛", "嶂"],
    "散": ["撒", "潵"],
    "热": ["熟", "塾"],
    "机": ["矶", "玑"],
    "动": ["恸"],
    "组": ["租", "阻", "诅"],
    "件": ["仵", "伡"],
    "断": ["继"],
    "损": ["殒"],
    "查": ["杳"],
    "坏": ["坯", "抔"],
    "冷": ["泠"],
    "系": ["係"],
}

# ============================================================
# Typo Functions
# ============================================================

def cn_replace_pinyin(char, chance=0.4):
    """Replace character with pinyin-similar character."""
    if random.random() < chance and char in CN_PINYIN_CONFUSION:
        return random.choice(CN_PINYIN_CONFUSION[char])
    return char

def cn_replace_shape(char, chance=0.15):
    """Replace character with shape-similar character."""
    if random.random() < chance and char in CN_SHAPE_CONFUSION:
        return random.choice(CN_SHAPE_CONFUSION[char])
    return char

def cn_omit_char(char, chance=0.03):
    """Omit a character (simulating input method skipping)."""
    # Only omit if the character is not critical
    if random.random() < chance and len(char) == 1:
        non_critical = set("的了吗呢啊嗯吧")
        if char in non_critical:
            return ""
    return char

def cn_insert_char(chars, chance=0.02):
    """Insert an extra character (simulating double-tap or联想误触)."""
    if random.random() < chance and len(chars) > 0:
        idx = random.randint(0, len(chars) - 1)
        # Duplicate or insert common filler
        return chars[:idx] + chars[idx] + chars[idx:]
    return chars

# ============================================================
# Abbreviation / Jargon Functions
# ============================================================

def cn_introduce_abbreviations(sentence, chance=0.4):
    """Replace formal terms with industrial abbreviations/jargon."""
    # Shuffle to vary which replacements happen
    items = list(CN_ABBREVIATIONS.items())
    random.shuffle(items)
    for original, variants in items:
        if original in sentence and random.random() < chance:
            variant = random.choice(variants)
            if variant != original:
                sentence = sentence.replace(original, variant, 1)
                # Only do one replacement per call for natural feel
                # but continue checking other terms
    return sentence

# ============================================================
# Typo Introduction
# ============================================================

def cn_introduce_typos(sentence, chance=0.08, max_typos=3):
    """Introduce Chinese-specific typos into a sentence.

    Typo types:
    - Pinyin confusion (40%): 主梁 → 柱梁
    - Shape confusion (15%): 梁 → 粱
    - Character omission (20%): dropping 的/了/吗
    - Character insertion (10%): double character
    - Mixed (15%): multiple types
    """
    if random.random() < 0.1:  # 10% chance no typos at all
        return sentence

    # Work at character level
    chars = list(sentence)
    if len(chars) < 3:
        return sentence

    # Select up to max_typos positions
    num_typos = random.randint(1, min(max_typos, len(chars)))
    positions = random.sample(range(len(chars)), num_typos)

    weights = [40, 15, 20, 10, 15]  # pinyin, shape, omit, insert, mixed
    func_dist = ['pinyin', 'shape', 'omit', 'insert', 'mixed']

    for pos in positions:
        if random.random() > chance:
            continue
        func_choice = random.choices(func_dist, weights=weights, k=1)[0]

        if func_choice == 'pinyin':
            chars[pos] = cn_replace_pinyin(chars[pos], 1.0)
        elif func_choice == 'shape':
            chars[pos] = cn_replace_shape(chars[pos], 1.0)
        elif func_choice == 'omit':
            new_char = cn_omit_char(chars[pos], 1.0)
            if new_char == "":
                chars[pos] = "\0"  # Mark for removal
            else:
                chars[pos] = new_char
        elif func_choice == 'insert':
            # Double this character
            chars[pos] = chars[pos] + chars[pos]
        elif func_choice == 'mixed':
            if random.random() < 0.5:
                chars[pos] = cn_replace_pinyin(chars[pos], 1.0)
            else:
                chars[pos] = cn_replace_shape(chars[pos], 1.0)

    # Remove marked characters
    chars = [c for c in chars if c != "\0"]

    return ''.join(chars)

# ============================================================
# Number / Symbol Mixing (Chinese-specific)
# ============================================================

def cn_number_symbol_mixing(sentence, chance=0.1):
    """Mix Chinese numbers and symbols into the text (common in real MWOs)."""
    mappings = [
        ("一", "1"), ("二", "2"), ("三", "3"),
        ("四", "4"), ("五", "5"), ("六", "6"),
    ]
    for cn_num, digit in mappings:
        if cn_num in sentence and random.random() < chance:
            # Only replace standalone numbers, not part of words
            sentence = re.sub(rf'\b{cn_num}\b', digit, sentence)
    return sentence

# ============================================================
# Main Humanization Function
# ============================================================

def cn_humanise_sentence(sentence, use_llm=False, client=None):
    """Humanize a Chinese MWO sentence.

    Pipeline:
    1. Introduce industrial abbreviations/jargon (40% chance per term)
    2. Mix number/symbol formats (10% chance)
    3. Introduce Chinese-specific typos (8% chance, max 3 chars)

    Args:
        sentence: Chinese MWO sentence
        use_llm: Whether to use LLM for typo introduction (not implemented for Chinese)
        client: OpenAI client (not used, kept for API compatibility)

    Returns:
        Humanized Chinese MWO sentence
    """
    if not sentence or len(sentence) < 3:
        return sentence

    # Step 1: Abbreviations/jargon
    sentence = cn_introduce_abbreviations(sentence, chance=0.4)

    # Step 2: Number/symbol mixing
    sentence = cn_number_symbol_mixing(sentence, chance=0.1)

    # Step 3: Chinese typos
    sentence = cn_introduce_typos(sentence, chance=0.08, max_typos=3)

    return sentence


# ============================================================
# Test
# ============================================================
if __name__ == '__main__':
    test_sentences = [
        "前舱主梁组件发现断裂需要更换",
        "发动机冷却系统散热器堵塞清理",
        "燃油泵泄漏需要更换密封圈",
        "液压作动筒密封失效需更换密封件",
        "刹车组件磨损超限更换刹车片",
        "电气系统接线盒进水腐蚀需清理端子",
    ]

    print("=== Chinese Humanization Test ===\n")
    for original in test_sentences:
        print(f"原文: {original}")
        for i in range(3):
            result = cn_humanise_sentence(original)
            if result != original:
                print(f"  -> 变体{i+1}: {result}")
            else:
                print(f"  -> (无变化)")
        print()
