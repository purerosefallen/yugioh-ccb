from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import pandas as pd
import random
import numbers

app = Flask(__name__)
db = None
target_row = None
app.secret_key = "你自己的随机 Secret Key"

from map import SETNAME_MAP,RACE_MAP,TYPE_MAP,CATEGORY_TAGS,TYPE_LINK,LINK_MARKERS,SETNAME_MAP ,ATTR_MAP

def parse_flags(value, mapping):
    return [name for bit, name in mapping.items() if value & bit]

def parse_category(cat):
    return [CATEGORY_TAGS[1100 + i] for i in range(64) if (cat >> i) & 1 and (1100 + i) in CATEGORY_TAGS]


def parse_setcode(setcode, name_map):
    # 1. 转成大写十六进制字符串
    hex_str = f"{setcode:X}"
    # 2. 左侧补零，使长度成为 4 的倍数
    pad_len = (-len(hex_str)) % 4
    if pad_len:
        hex_str = hex_str.zfill(len(hex_str) + pad_len)
    # 3. 每 4 位一组
    names = []
    for i in range(0, len(hex_str), 4):
        segment = hex_str[i:i+4]
        # 全 0 的段跳过
        if segment == "0000":
            continue
        code = int(segment, 16)
        if code in name_map:
            names.append(name_map[code])
    return names

def extract_arrows(def_value):
    """
    从 link_marker 的整数值中提取出 所有 生效的箭头符号，返回一个列表。
    """
    return [sym for bit, sym in LINK_MARKERS.items() if def_value & bit]


def load_card_database(path):
    conn = sqlite3.connect(path)
    # 先把两个表读进 DataFrame
    datas = pd.read_sql_query(
        "SELECT id, type, atk, def, level, race, attribute, category ,hot,setcode FROM datas",
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
    is_link = bool(row["type"] & TYPE_LINK)
    # 链接怪兽的“守备”清空
    defense = "" if is_link else row["def"]
    # 如果是链接怪兽，从 link_marker 提取箭头
    arrows = extract_arrows(row["def"]) if is_link else []
    return {
        "卡名": row["name"],
        "攻击": row["atk"],
        "守备": defense,
        "等级": row["level"] & 0xFF,
        "箭头": arrows,
        "刻度": (row["level"] >> 24) & 0xFF,
        "类型": parse_flags(row["type"], TYPE_MAP),
        "属性": ATTR_MAP.get(row["attribute"], f"0x{row['attribute']:X}"),
        "种族": RACE_MAP.get(row["race"], f"0x{row['race']:X}"),
        "效果标签": parse_category(row["category"]),
        "系列": parse_setcode(row["setcode"], SETNAME_MAP),
    }


def compare_tags(guess_tags, answer_tags):
    def cmp(key, val1, val2):
        if val1 is None or val1 == "" or val2 is None or val2 == "":
            # 要么是用户没猜，要么目标也无该字段，都算“未猜”
            return '<span class="partial">—</span>'

        if key == "箭头":
            pills = []
            # 对八个方向都展示一个小标签
            for bit, sym in LINK_MARKERS.items():
                if sym in val1:
                    # 猜的里有
                    cls = "tag-green" if sym in val2 else "tag-red"
                else:
                    # 猜的里没有
                    cls = "tag-gray"
                pills.append(f'<span class="tag {cls}">{sym}</span>')
            return " ".join(pills)
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
                cls = "tag-green" if t in val2 else "tag-gray"
                pills.append(f'<span class="tag {cls}">{t}</span>')
            return " ".join(pills) or '<span class="tag tag-gray">—</span>'

        # 其它（字符串等）完全匹配才 green，否则 gray
        else:
            cls = "tag-green" if val1 == val2 else "tag-gray    "
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
        #session['target_id'] = 71818935
        # 重置本局提示相关状态
        session['guess_count'] = 0
        session['hints_shown'] = []
        return redirect(url_for("game"))
    return render_template("start.html")

@app.route("/game", methods=["GET", "POST"])
def game():
    feedback = None
    mode = session.get('mode')
    if not mode :
        return redirect(url_for("start"))

    if 'target_id' not in session:
        pool = filter_db(mode)
        session['target_id'] = int(pool.sample(1).index[0])
        session['history'] = []
        session['hints'] = []
        session['hinted_chars'] = []

    filtered = filter_db(mode)
    target = db.loc[session['target_id']]

    # 本局历史记录和提示
    history = session.get('history', [])
    hints = session.get('hints', [])
    hinted_chars = session.get('hinted_chars', [])

    if request.method == "POST":
        action = request.form.get("action", "guess")

        if action == "change_mode":
            new_mode = request.form.get("mode")
            session['mode'] = new_mode
            # 直接把上一行 target_id 删掉，触发上面自动重置
            session.pop('target_id', None)
            return redirect(url_for("game"))

        if action == "surrender":
            # 认输
            feedback = {"giveup": True, "answer": target["name"], "hints": hints}
            session.pop('target_id', None)
            session.pop('history', None)
            session.pop('hints', None)
            session.pop('hinted_chars', None)

        elif action == "restart":
            # 重新开始
            session.pop('target_id', None)
            session.pop('mode', None)
            session.pop('history', None)
            session.pop('hints', None)
            session.pop('hinted_chars', None)
            return redirect(url_for("game"))

        else:
            # 普通猜测
            user_input = request.form.get("guess", "").strip()
            match = filtered[filtered["name"].str.contains(user_input, case=False, na=False)]

            if match.empty:
                feedback = {"error": f"未找到包含“{user_input}”的卡片。", "hints": hints}

            else:
                guess = match.iloc[0]
                if guess.name == target.name:
                    # 1. 先做一次对比
                    compare = compare_tags(card_to_tags(guess), card_to_tags(target))
                    # 2. 把这条全绿记录追加到本局历史
                    history.append({
                        "guess_name": guess['name'],
                        "compare": compare
                    })
                    # 3. 带上 compare 和 hints 给模板渲染
                    feedback = {
                        "success": f"🎉 恭喜你猜中了！答案就是【{guess['name']}】",
                        "compare": compare,
                        "hints": hints
                    }
                    # 清理本局 session
                    session.pop('target_id', None)
                    session.pop('history', None)
                    session.pop('hints', None)
                    session.pop('hinted_chars', None)

                else:
                    # 对比并入历史
                    compare = compare_tags(card_to_tags(guess), card_to_tags(target))
                    history.append({
                        "guess_name": guess['name'],
                        "compare": compare
                    })

                    # —— 第二次猜测，给一个新的“效果标签”提示 —— #
                    if len(history) == 2:
                        target_tags = set(card_to_tags(target)["效果标签"])
                        guessed_tags = set()
                        for h in history:
                            # history 里保存的 compare 里没有原始 list，
                            # 所以直接重新取一次 guess 的原始标签：
                            row = db[db["name"] == h["guess_name"]].iloc[0]
                            guessed_tags |= set(card_to_tags(row)["效果标签"])
                        remaining = list(target_tags - guessed_tags)
                        if remaining:
                            tag_hint = random.choice(remaining)
                            hints.append(f"提示：目标卡有效果标签 “{tag_hint}”")

                    # —— 第五次猜测，给一个新的名称字符提示 —— #
                    if len(history) == 5:
                        name_chars = [c for c in target["name"] if c.strip()]
                        candidates = [c for c in name_chars if c not in hinted_chars]
                        if candidates:
                            char_hint = random.choice(candidates)
                            hinted_chars.append(char_hint)
                            hints.append(f"提示：目标卡名称中包含 “{char_hint}” 这个字")

                    # 更新 session
                    session['history'] = history
                    session['hints'] = hints
                    session['hinted_chars'] = hinted_chars

                    feedback = {
                        "compare": compare,
                        "guess_name": guess['name'],
                        "hints": hints
                    }

    return render_template("index.html",
                           feedback=feedback,
                           history=history,
                           hints=hints,
                           mode=mode)

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
