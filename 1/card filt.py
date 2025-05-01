import sqlite3
import pandas as pd
from tabulate import tabulate

# 属性、种族、类型、效果标签映射表
ATTR_MAP = {
    0x01: "地", 0x02: "水", 0x04: "炎", 0x08: "风",
    0x10: "光", 0x20: "暗", 0x40: "神"
}
RACE_MAP = {
    0x1: "战士", 0x2: "魔法师", 0x4: "天使", 0x8: "恶魔", 0x10: "不死", 0x20: "机械",
    0x40: "水", 0x80: "炎", 0x100: "岩石", 0x200: "鸟兽", 0x400: "植物", 0x800: "昆虫",
    0x1000: "雷", 0x2000: "龙", 0x4000: "兽", 0x8000: "兽战士", 0x10000: "恐龙",
    0x20000: "鱼", 0x40000: "海龙", 0x80000: "爬虫", 0x100000: "念动力", 0x200000: "幻神兽",
    0x400000: "创造神", 0x800000: "幻龙", 0x1000000: "电子界", 0x2000000: "幻想魔",
}
TYPE_MAP = {
    0x1: "怪兽", 0x2: "魔法", 0x4: "陷阱", 0x10: "通常",
    0x20: "效果", 0x40: "融合", 0x80: "仪式", 0x100: "陷阱怪兽",
    0x200: "灵魂", 0x400: "同盟", 0x800: "二重", 0x1000: "调整",
    0x2000: "同调", 0x4000: "衍生物", 0x10000: "速攻", 0x20000: "永续",
    0x40000: "装备", 0x80000: "场地", 0x100000: "反击", 0x200000: "翻转",
    0x400000: "卡通", 0x800000: "超量", 0x1000000: "灵摆", 0x2000000: "特殊召唤",
    0x4000000: "连接",
}
CATEGORY_TAGS = {
    1100: '魔陷破坏', 1101: '怪兽破坏', 1102: '卡片除外', 1103: '送去墓地', 1104: '返回手卡', 1105: '返回卡组',
    1106: '手卡破坏', 1107: '卡组破坏', 1108: '抽卡辅助', 1109: '卡组检索', 1110: '卡片回收', 1111: '表示形式',
    1112: '控制权', 1113: '攻守变化', 1114: '穿刺伤害', 1115: '多次攻击', 1116: '攻击限制', 1117: '直接攻击',
    1118: '特殊召唤', 1119: '衍生物', 1120: '种族相关', 1121: '属性相关', 1122: 'LP伤害', 1123: 'LP回复',
    1124: '破坏耐性', 1125: '效果耐性', 1126: '指示物', 1127: '幸运', 1128: '融合相关', 1129: '同调相关',
    1130: '超量相关', 1131: '效果无效'
}
LINK_MARKER_MAP = {
    0x001: "左下",
    0x002: "下",
    0x004: "右下",
    0x008: "左",
    0x020: "右",
    0x040: "左上",
    0x080: "上",
    0x100: "右上"
}

def parse_flags(value, mapping):
    return [name for bit, name in mapping.items() if value & bit]


def parse_category(cat):
    return [CATEGORY_TAGS[1100 + i] for i in range(64) if (cat >> i) & 1 and (1100 + i) in CATEGORY_TAGS]


def extract_level_masks(level_val: int):
    level = level_val & 0xff
    lscale = (level_val >> 24) & 0xff
    rscale = (level_val >> 16) & 0xff
    linkmarker = (level_val >> 8) & 0xff
    return level, lscale, rscale, linkmarker


def load_card_database(path):
    conn = sqlite3.connect(path)
    datas = pd.read_sql_query("SELECT id, type, atk, def, level, race, attribute, category FROM datas", conn,
                              index_col="id")
    texts = pd.read_sql_query("SELECT id, name, desc FROM texts", conn, index_col="id")
    conn.close()
    return datas.join(texts, how="inner")


def parse_link_marker(marker_val):
    return [name for bit, name in LINK_MARKER_MAP.items() if marker_val & bit]


def search_cards(keyword, db):
    df = db[db["name"].str.contains(keyword, case=False, na=False)].copy()
    if df.empty:
        print(f"[!] 未找到包含 “{keyword}” 的卡片")
        return

    df["属性"] = df["attribute"].map(lambda x: ATTR_MAP.get(x, f"0x{x:X}"))
    df["种族"] = df["race"].map(lambda x: RACE_MAP.get(x, f"0x{x:X}"))
    df["等级"], df["左刻度"], df["右刻度"], _ = zip(*df["level"].map(extract_level_masks))
    df["类型"] = df["type"].map(lambda x: "|".join(parse_flags(x, TYPE_MAP)))
    df["效果标签"] = df["category"].map(lambda x: "|".join(parse_category(x)))

    display_df = df[["name", "atk", "def", "类型", "等级", "左刻度", "右刻度", "种族", "属性", "效果标签"]]
    display_df.columns = ["卡名", "攻击", "守备", "类型", "等级", "左刻度", "右刻度", "种族", "属性", "效果标签"]
    print(tabulate(display_df, headers="keys", tablefmt="grid", showindex=False))

def load_card_database(path):
    conn = sqlite3.connect(path)
    df = pd.read_sql_query("""
        SELECT d.id, d.type, d.atk, d.def, d.level, d.race, d.attribute, d.category,
               t.name, t.desc
        FROM datas d
        JOIN texts t ON d.id = t.id
    """, conn)
    conn.close()

    df["等级"] = df["level"].apply(lambda x: x & 0xFF)
    df["刻度"] = df["level"].apply(lambda x: (x >> 16) & 0xFF)
    df["属性"] = df["attribute"].map(lambda x: ATTR_MAP.get(x, f"0x{x:X}"))
    df["种族"] = df["race"].map(lambda x: RACE_MAP.get(x, f"0x{x:X}"))
    df["类型"] = df["type"].map(lambda x: "|".join(parse_flags(x, TYPE_MAP)))
    df["效果标签"] = df["category"].map(lambda x: "|".join(parse_category(x)))

    df["守备"] = df.apply(lambda row: "-" if "连接" in row["类型"] else row["def"], axis=1)

    return df[["name", "atk", "守备", "类型", "等级", "刻度", "种族", "属性", "效果标签", "desc"]]

if __name__ == "__main__":
    db = load_card_database("cards.cdb")
    print("🃏 请输入卡名关键词（如 青眼、黑魔导），回车查询，空白退出")
    while True:
        kw = input("关键词：").strip()
        if not kw:
            break
        search_cards(kw, db)


