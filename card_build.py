#!/usr/bin/env python3
# mark_hot_cards.py

import requests
import sqlite3
import sys

API_URL = "https://sapi.moecube.com:444/ygopro/analytics/single/type"
PARAMS = {
    "type":   "month",
    "lang":   "cn",
    "extra":  "name",
    "source": "mycard-athletic"
}
DB_PATH = "cards.cdb"

def fetch_hot_names():
    print("🔄 正在从 API 获取本月热门卡牌数据……")
    resp = requests.get(API_URL, params=PARAMS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    hot_names = []
    # API 返回示例：{ "monster": [...], "spell": [...], "trap": [...] }
    for category, items in data.items():
        if not isinstance(items, list):
            continue
        for entry in items:
            # 取中文名
            cn = entry.get("name", {}).get("zh-CN")
            if cn:
                hot_names.append(cn)
    # 去重
    return sorted(set(hot_names))

def ensure_hot_column(cur):
    cur.execute("PRAGMA table_info(datas);")
    cols = [r[1] for r in cur.fetchall()]
    if "hot" not in cols:
        print("➕ 在 datas 表中添加 hot 字段（默认 0）")
        cur.execute("ALTER TABLE datas ADD COLUMN hot INTEGER DEFAULT 0;")
    else:
        print("ℹ️ 字段 hot 已存在，跳过添加")

def mark_hot_cards(conn, hot_names):
    cur = conn.cursor()
    update_sql = """
    UPDATE datas
       SET hot = 1
     WHERE id IN (
       SELECT id FROM texts WHERE name = ?
     );
    """
    print(f"🔄 开始将 {len(hot_names)} 张热门卡标记为 hot=1 …")
    for name in hot_names:
        cur.execute(update_sql, (name,))
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM datas WHERE hot=1;")
    count = cur.fetchone()[0]
    print(f"✅ 完成！共有 {count} 张卡标记为热门。")

def main():
    try:
        hot_names = fetch_hot_names()
    except Exception as e:
        print(f"❌ 获取热门卡失败：{e}", file=sys.stderr)
        sys.exit(1)

    print("🔎 本月热门卡（共 %d 张）：" % len(hot_names))
    print(", ".join(hot_names))

    print(f"🔄 打开数据库：{DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    ensure_hot_column(cur)
    conn.commit()

    mark_hot_cards(conn, hot_names)

    conn.close()

if __name__ == "__main__":
    main()
