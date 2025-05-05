import os
import random
import sys

from flask import Flask, render_template, request, redirect, url_for, session, jsonify

from data_utils import load_card_database, card_to_tags, compare_tags

base_path = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
template_folder = os.path.join(base_path, "templates")

app = Flask(__name__, template_folder=template_folder)
db = None
target_row = None
app.secret_key = os.getenv("SECRET_KEY", "你自己的随机 Secret Key")

db = load_card_database()


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
    """游戏开始前，选择卡牌范围和猜测次数"""
    if request.method == "POST":
        # 1. 读卡片类型
        mode = request.form["mode"]

        # 2. 读猜测次数（range 滑块传回的是字符串）
        try:
            max_attempts = int(request.form.get("attempts", 5))
        except ValueError:
            max_attempts = 5

        # 3. 初始化 session
        session.clear()
        session["mode"] = mode
        session["max_attempts"] = max_attempts
        session["guess_count"] = 0
        session["hints_shown"] = []

        # 4. 随机选一个目标卡片 ID
        pool = filter_db(mode)
        session["target_id"] = int(pool.sample(1).index[0])

        return redirect(url_for("game"))

    # GET：渲染 start.html（包含滑块）
    return render_template("start.html")


@app.route("/game", methods=["GET", "POST"])
def game():
    feedback = None
    mode = session.get('mode')
    if not mode:
        return redirect(url_for("start"))

    if 'target_id' not in session:
        pool = filter_db(mode)
        session['target_id'] = int(pool.sample(1).index[0])
        session['history'] = []
        session['hints'] = []
        session['hinted_chars'] = []
    max_attempts = session.get('max_attempts', 5)
    guess_count = session.get('guess_count', 0)

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
            # 1. 先做一次对比
            compare = compare_tags(card_to_tags(target), card_to_tags(target))
            # 2. 把这条全绿记录追加到本局历史
            history.append({
                "guess_name": target['name'],
                "compare": compare
            })
            # 3. 带上 compare 和 hints 给模板渲染
            feedback = {"giveup": True, "answer": target["name"], "compare": compare, "hints": hints}
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
            guess_count += 1
            session['guess_count'] = guess_count

            if guess_count > max_attempts:
                feedback = {
                    "error": f"😢 猜测次数已用尽！答案是【{target['name']}】",
                    "giveup": True,
                    "answer": target["name"],
                    "hints": hints
                }
                for key in ('target_id', 'history', 'hints', 'hinted_chars', 'guess_count'):
                    session.pop(key, None)
                return render_template(
                    "index.html",
                    feedback=feedback,
                    history=history,
                    hints=hints,
                    mode=mode,
                    guess_count=guess_count,
                    max_attempts=max_attempts
                )

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

    return render_template(
        "index.html",
        feedback=feedback,
        history=history,
        hints=hints,
        mode=mode,
        guess_count=guess_count,
        max_attempts=max_attempts
    )


@app.route("/suggest")
def suggest():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    mode = session.get('mode', 'all')
    pool = filter_db(mode)
    matches = pool[
        pool["name"].str.contains(q, case=False, na=False)
    ]["name"].tolist()
    return jsonify(matches)


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 5000))

    app.run(host=host, port=port, debug=False)
