from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import pandas as pd
import random
from flask import jsonify

app = Flask(__name__)
db = None
target_row = None

# --- 与原 CLI 版本相同的配置 ---
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
    0x1: "怪兽", 0x2: "魔法", 0x4: "陷阱", 0x10: "通常", 0x20: "效果", 0x40: "融合", 0x80: "仪式",
    0x100: "陷阱怪兽", 0x200: "灵魂", 0x400: "同盟", 0x800: "二重", 0x1000: "调整", 0x2000: "同调",
    0x4000: "衍生物", 0x10000: "速攻", 0x20000: "永续", 0x40000: "装备", 0x80000: "场地",
    0x100000: "反击", 0x200000: "翻转", 0x400000: "卡通", 0x800000: "超量",
    0x1000000: "灵摆", 0x2000000: "特殊召唤", 0x4000000: "连接"
}
CATEGORY_TAGS = {
    1100: '魔陷破坏', 1101: '怪兽破坏', 1102: '卡片除外', 1103: '送去墓地', 1104: '返回手卡', 1105: '返回卡组',
    1106: '手卡破坏', 1107: '卡组破坏', 1108: '抽卡辅助', 1109: '卡组检索', 1110: '卡片回收', 1111: '表示形式',
    1112: '控制权', 1113: '攻守变化', 1114: '穿刺伤害', 1115: '多次攻击', 1116: '攻击限制', 1117: '直接攻击',
    1118: '特殊召唤', 1119: '衍生物', 1120: '种族相关', 1121: '属性相关', 1122: 'LP伤害', 1123: 'LP回复',
    1124: '破坏耐性', 1125: '效果耐性', 1126: '指示物', 1127: '幸运', 1128: '融合相关', 1129: '同调相关',
    1130: '超量相关', 1131: '效果无效'
}

def parse_flags(value, mapping):
    return [name for bit, name in mapping.items() if value & bit]

def parse_category(cat):
    return [CATEGORY_TAGS[1100 + i] for i in range(64) if (cat >> i) & 1 and (1100 + i) in CATEGORY_TAGS]

def load_card_database(path):
    conn = sqlite3.connect(path)
    datas = pd.read_sql_query("SELECT id, type, atk, def, level, race, attribute, category FROM datas", conn, index_col="id")
    texts = pd.read_sql_query("SELECT id, name FROM texts", conn, index_col="id")
    conn.close()
    return datas.join(texts, how="inner")

def card_to_tags(row):
    return {
        "卡名": row["name"],
        "攻击": row["atk"],
        "守备": row["def"],
        "等级": row["level"] & 0xFF,
        "刻度": (row["level"] >> 24) & 0xFF,
        "类型": parse_flags(row["type"], TYPE_MAP),
        "属性": ATTR_MAP.get(row["attribute"], f"0x{row['attribute']:X}"),
        "种族": RACE_MAP.get(row["race"], f"0x{row['race']:X}"),
        "效果标签": parse_category(row["category"])
    }

def compare_tags(guess_tags, answer_tags):
    def cmp(val1, val2):
        if isinstance(val1, int):
            if val1 == val2:
                return f"{val1} ✅"
            elif val1 > val2:
                return f"{val1} ↓"
            else:
                return f"{val1} ↑"
        elif isinstance(val1, list):
            inter = set(val1) & set(val2)
            only_guess = set(val1) - inter
            result = []
            if inter:
                result.append(f"✅ 相同: {', '.join(inter)}")
            if only_guess:
                result.append(f"❌ 你猜的有但目标没有: {', '.join(only_guess)}")

            return "<br>".join(result)
        else:
            return f"{val1} ✅" if val1 == val2 else f"{val1} ❌"
    return {key: cmp(guess_tags[key], answer_tags[key]) for key in guess_tags}

@app.route("/", methods=["GET", "POST"])
def index():
    global target_row
    feedback = None
    if target_row is None:
        monster_df = db[(db["type"] & 0x1) != 0]
        target_row = monster_df.sample(1).iloc[0]

    if request.method == "POST":
        user_input = request.form.get("guess", "").strip()
        match = db[db["name"].str.contains(user_input, case=False, na=False)]

        if match.empty:
            feedback = {"error": f"未找到包含“{user_input}”的卡片。"}
        else:
            guess = match.iloc[0]
            if guess.name == target_row.name:
                feedback = {"success": f"🎉 恭喜你猜中了！答案就是【{guess['name']}】"}
                target_row = None
            else:
                feedback = {
                    "compare": compare_tags(card_to_tags(guess), card_to_tags(target_row)),
                    "guess_name": guess['name']
                }

    return render_template("index.html", feedback=feedback)

@app.route("/suggest")
def suggest():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    matches = db[db["name"].str.contains(q, case=False, na=False)]["name"].head(10).tolist()
    return jsonify(matches)

if __name__ == "__main__":
    db = load_card_database("cards.cdb")
    app.run(debug=True)
