from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import pandas as pd
import random
import numbers

app = Flask(__name__)
db = None
target_row = None
app.secret_key = "你自己的随机 Secret Key"

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
    # 先把两个表读进 DataFrame
    datas = pd.read_sql_query(
        "SELECT id, type, atk, def, level, race, attribute, category ,hot FROM datas",
        conn, index_col="id"
    )
    texts = pd.read_sql_query(
        "SELECT id, name FROM texts",
        conn, index_col="id"
    )
    conn.close()
    # 合并
    df = datas.join(texts, how="inner").reset_index()
    # 按 id 升序排序，drop_duplicates 保留每个 name 的第一个（即最小 id）
    df = df.sort_values("id").drop_duplicates(subset="name", keep="first")
    # 以 id 重新设为索引
    df = df.set_index("id")
    return df

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
    def cmp(key, val1, val2):
        # 数值型字段：攻击、守备、等级、刻度
        if isinstance(val1, numbers.Number):
            diff = abs(val1 - val2)
            # 先判断完全相等
            if diff == 0:
                cls = "tag-green"
            else:
                if key in ("攻击", "守备"):
                    if diff <= 500:
                        cls = "tag-yellow"
                    else:
                        cls = "tag-gray"
                elif key in ("等级", "刻度"):
                    if diff <= 2:
                        cls = "tag-yellow"
                    else:
                        cls = "tag-gray"
                else:
                    cls = "tag-gray"
            # 箭头
            arrow = "" if diff == 0 else ("↑" if val1 < val2 else "↓")
            return f'<span class="tag {cls}">{val1}{arrow}</span>'

        # 列表型字段：如 类型、效果标签……
        elif isinstance(val1, list):
            pills = []
            for t in val1:
                # 猜的 tag 在目标里才 green，否则 red
                cls = "tag-green" if t in val2 else "tag-red"
                pills.append(f'<span class="tag {cls}">{t}</span>')
            return " ".join(pills) or '<span class="tag tag-gray">—</span>'

        # 其它（字符串等）完全匹配才 green，否则 gray
        else:
            cls = "tag-green" if val1 == val2 else "tag-gray"
            return f'<span class="tag {cls}">{val1}</span>'

    return {
        key: cmp(key, guess_tags[key], answer_tags[key])
        for key in guess_tags
    }

def filter_db(mode):
    """
    mode: 'monster' | 'spell' | 'trap' | 'hot' | 'all'
    """
    if mode == 'monster':
        # 怪兽卡 & 排除通常怪兽
        mask = ((db['type'] & 0x1) > 0) & ((db['type'] & 0x10) == 0)
        return db[mask]
    if mode == 'spell':
        return db[(db['type'] & 0x2) > 0]
    if mode == 'trap':
        return db[(db['type'] & 0x4) > 0]
    if mode == 'hot':
        mask = ((db['type'] & 0x1) > 0) & ((db['type'] & 0x10) == 0) & (db['hot'] == 1)
        return db[mask]
    # all
    return db



@app.route("/", methods=["GET", "POST"])
def start():
    """游戏开始前，选择卡牌范围"""
    if request.method == "POST":
        mode = request.form.get("mode")
        session.clear()
        session['mode'] = mode
        # 随机选一个 target_id
        pool = filter_db(mode)
        session['target_id'] = int(pool.sample(1).index[0])
        # 重置本局提示相关状态
        session['guess_count'] = 0
        session['hints_shown'] = []
        return redirect(url_for("game"))
    return render_template("start.html")

@app.route("/game", methods=["GET", "POST"])
def game():
    feedback = None
    mode = session.get('mode')
    if not mode or 'target_id' not in session:
        return redirect(url_for("start"))

    # 确保本局猜测计数与提示列表存在
    if 'guess_count' not in session:
        session['guess_count'] = 0
        session['hints_shown'] = []

    filtered = filter_db(mode)
    target = db.loc[session['target_id']]
    history = session.get('history', [])

    if request.method == "POST":
        action = request.form.get("action", "guess")

        if action == "surrender":
            # 投降：显示答案并清理本局
            feedback = {"giveup": True, "answer": target["name"]}
            for key in ('target_id', 'history', 'guess_count', 'hints_shown'):
                session.pop(key, None)

        elif action == "restart":
            # 重新开始：回到选择范围页
            for key in ('target_id', 'mode', 'history', 'guess_count', 'hints_shown'):
                session.pop(key, None)
            return redirect(url_for("start"))

        else:
            # 普通猜测
            user_input = request.form.get("guess", "").strip()
            match = filtered[filtered["name"].str.contains(user_input, case=False, na=False)]

            if match.empty:
                feedback = {"error": f"未找到包含“{user_input}”的卡片。"}
            else:
                guess = match.iloc[0]
                if guess.name == target.name:
                    # 猜中：恭喜并清理本局
                    feedback = {"success": f"🎉 恭喜你猜中了！答案就是【{guess['name']}】"}
                    for key in ('target_id', 'history', 'guess_count', 'hints_shown'):
                        session.pop(key, None)

                else:
                    # 有效一次猜测
                    session['guess_count'] += 1
                    # 在第2次和第5次时给提示
                    if session['guess_count'] in (2, 5):
                        name_chars = list(target['name'])
                        shown = session['hints_shown']
                        choices = [c for c in name_chars if c not in shown]
                        if choices:
                            hint_char = random.choice(choices)
                            shown.append(hint_char)
                            session['hints_shown'] = shown
                            feedback = {"hint": hint_char}
                    # 对比并存入 history
                    compare = compare_tags(card_to_tags(guess), card_to_tags(target))
                    feedback = feedback or {}
                    feedback.update({
                        "compare": compare,
                        "guess_name": guess['name']
                    })
                    history.append({
                        "guess_name": guess['name'],
                        "compare": compare
                    })
                    session['history'] = history

    return render_template("index.html",
                           feedback=feedback,
                           history=history)

@app.route("/suggest")
def suggest():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    mode = session.get('mode', 'all')
    pool = filter_db(mode)       # ← 改这里
    matches = pool[
        pool["name"].str.contains(q, case=False, na=False)
    ]["name"].tolist()
    return jsonify(matches)

if __name__ == "__main__":
    db = load_card_database("cards.cdb")
    app.run(debug=True)
