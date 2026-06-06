#!/usr/bin/env python3
"""
統覧 TORAN — Wikipedia 基礎評価バッチ自動生成スクリプト
==========================================================
情報不足の議員について Wikipedia から経歴を取得し、
保守的スコアリングルールに基づいて batch JSON を自動生成する。

スコアリングルール:
  - デフォルト全軸 = 2（情報限定・中立）
  - 大臣経験あり    → 政策実現力+1, 関連軸+1（max 3）
  - 副大臣/政務官   → 政策実現力+1（max 3）
  - 3期以上当選     → 国民生活改善+1, 説明責任+1（max 3）
  - 2期当選         → 国民生活改善+1（max 3）
  - 問題報道あり    → 政治倫理-1 / 説明責任-1
  ※ Wikipedia情報のみでは軸スコアを4以上にしない

使い方:
  python generate_wikipedia_batches.py
  python generate_wikipedia_batches.py --start 0 --end 50   # 範囲指定
  python generate_wikipedia_batches.py --dry               # 取得のみ・JSON未生成
"""

import requests
import json
import re
import time
import argparse
import os
from datetime import date

WIKIPEDIA_API = "https://ja.wikipedia.org/w/api.php"
DELAY = 0.7
BATCH_SIZE = 15
OUTPUT_DIR = "batches"
CACHE_FILE = "output/wikipedia_cache.json"

# ── スコア計算ヘルパー ─────────────────────────────────────
def calc_rank(total: int) -> str:
    if total >= 90: return "S"
    if total >= 87: return "A+"
    if total >= 83: return "A"
    if total >= 80: return "A-"
    if total >= 77: return "B+"
    if total >= 73: return "B"
    if total >= 70: return "B-"
    if total >= 67: return "C+"
    if total >= 63: return "C"
    if total >= 60: return "C-"
    return "D"

# ── Wikipedia 取得 ────────────────────────────────────────
def fetch_wikipedia(name: str) -> tuple[str, str]:
    """Wikipedia ページ本文 + extract (intro) を返す。失敗時は ('', '')"""
    params = {
        "action": "query",
        "titles": name,
        "prop": "revisions|categories|extracts",
        "rvprop": "content",
        "rvslots": "main",
        "exintro": True,
        "explaintext": True,
        "cllimit": "100",
        "format": "json",
        "formatversion": "2",
    }
    try:
        r = requests.get(WIKIPEDIA_API, params=params, timeout=15,
                         headers={"User-Agent": "TORAN-DataCollector/1.0 (educational)"})
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", [])
        if not pages or "missing" in pages[0]:
            return "", ""
        page = pages[0]
        content = ""
        try:
            content = page["revisions"][0]["slots"]["main"]["content"]
        except (KeyError, IndexError):
            pass
        extract = page.get("extract", "")
        return content, extract
    except Exception as e:
        print(f"    ⚠️ 通信エラー: {e}")
        return "", ""


# ── 経歴解析 ─────────────────────────────────────────────
def analyze_career(name: str, content: str, extract: str) -> dict:
    """Wikipedia テキストから経歴情報を抽出してキャリア辞書を返す"""
    text = (content[:8000] + " " + extract[:3000]).strip()

    def hit(pattern: str) -> bool:
        return bool(re.search(pattern, text))

    # 大臣・長官（正大臣のみ、副/政務は除く）
    is_minister = hit(r'(?<!副)(?<!政務)大臣|長官(?!付|補)') and not hit(r'^副大臣|^政務官')
    # 副大臣・政務官
    is_vice = hit(r'副大臣|政務官|政務次官')
    # 委員長
    is_chair = hit(r'委員会委員長|委員長')
    # 幹事長・国対委員長
    is_party_exec = hit(r'幹事長|国会対策委員長|政調会長|代表(?!選|質問)')
    # 当選回数
    terms = 0
    m = re.search(r'当選(\d+)回', text)
    if m:
        terms = int(m.group(1))
    else:
        # 「X期」の形式
        m2 = re.search(r'(\d+)期', text[:3000])
        if m2:
            terms = min(int(m2.group(1)), 12)

    # 関連政策ドメイン（大臣職のみ）
    domains = []
    if hit(r'財務|税制|金融(?!庁)'):      domains.append('economy')
    if hit(r'経済産業|経済再生|内閣府特命.*経済'): domains.append('economy')
    if hit(r'防衛|自衛隊'):               domains.append('defense')
    if hit(r'外務|外交'):                 domains.append('defense')
    if hit(r'厚生|社会保障|医療|福祉'):   domains.append('welfare')
    if hit(r'少子化|こども|子ども|教育'):  domains.append('birthrate')
    if hit(r'環境|気候|エネルギー|再生可能'): domains.append('energy')
    if hit(r'農林|水産|食料'):            domains.append('food')
    if hit(r'国土交通|インフラ|地域活性|地方創生'): domains.append('regional')
    if hit(r'経済安全保障|サイバー|半導体'): domains.append('econ_sec')

    # 問題フラグ
    has_crime    = hit(r'逮捕|起訴|有罪|刑事事件')
    has_caution  = hit(r'政治資金.*問題|不記載|裏金|統一教会.*接点|収賄|選挙違反')
    has_caution2 = hit(r'政治資金規正法.*違反|離党勧告|除名処分')

    # Wikipedia ページが存在したか
    has_page = bool(text.strip())

    return {
        "has_page":      has_page,
        "is_minister":   is_minister and has_page,
        "is_vice":       is_vice and has_page and not is_minister,
        "is_chair":      is_chair and has_page,
        "is_party_exec": is_party_exec and has_page,
        "terms":         terms,
        "domains":       list(set(domains)),
        "has_crime":     has_crime,
        "has_caution":   has_caution or has_caution2,
        "intro":         extract[:400].strip() if extract else "",
    }


# ── スコア生成 ────────────────────────────────────────────
def score_from_career(career: dict, name: str) -> dict:
    """
    キャリア情報からスコアを計算する。
    axes: [国民生活改善, 経済財政, 安全保障, 政策実現力, 説明責任, 長期国益, 公共性, 政治倫理]
    """
    axes = [2, 2, 2, 2, 2, 2, 2, 2]
    plus_pts = []
    minus_pts = []
    evidence = []

    if not career["has_page"]:
        # Wikipedia記事なし → 情報不足のまま
        return None

    # ── 当選回数 ────────────────────────────────────────
    t = career["terms"]
    if t >= 4:
        axes[0] = min(3, axes[0] + 1)  # 国民生活改善
        axes[4] = min(3, axes[4] + 1)  # 説明責任（継続的信任）
        plus_pts.append(f"{t}期当選の継続的な議員活動による経験")
    elif t >= 2:
        axes[0] = min(3, axes[0] + 1)
        plus_pts.append(f"{t}期当選の議員経験")

    # ── 大臣・長官 ──────────────────────────────────────
    if career["is_minister"]:
        axes[3] = min(3, axes[3] + 1)  # 政策実現力
        axes[5] = min(3, axes[5] + 1)  # 長期国益
        plus_pts.append("大臣・長官職としての行政経験（詳細は公式記録を参照）")
        evidence.append({
            "cat": "実績", "sub": "政策実現",
            "summary": "大臣・長官職の経験（Wikipedia確認）",
            "detail": "Wikipediaの記載により大臣または長官職の経験が確認された。政策実現力・行政手腕の評価根拠。",
            "src": "Wikipedia",
            "url": f"https://ja.wikipedia.org/wiki/{name}",
            "rel": "政策実現力", "impact": "中",
            "date": "（確認中）"
        })
        # ドメイン別 +1（max 3）
        dom_map = {
            "economy":  1,  # 経済財政
            "defense":  2,  # 安全保障
            "welfare":  0,  # 国民生活改善
            "birthrate": 5, # 長期国益
            "energy":   5,  # 長期国益
            "food":     5,  # 長期国益
            "regional": 0,  # 国民生活改善
            "econ_sec": 2,  # 安全保障
        }
        for dom in career["domains"]:
            if dom in dom_map:
                ax = dom_map[dom]
                axes[ax] = min(3, axes[ax] + 1)

    # ── 副大臣・政務官 ──────────────────────────────────
    elif career["is_vice"]:
        axes[3] = min(3, axes[3] + 1)  # 政策実現力
        plus_pts.append("副大臣・政務官として行政を補佐した経験（詳細は公式記録を参照）")
        evidence.append({
            "cat": "実績", "sub": "政策実現",
            "summary": "副大臣・政務官職の経験（Wikipedia確認）",
            "detail": "Wikipediaの記載により副大臣または政務官の経験が確認された。",
            "src": "Wikipedia",
            "url": f"https://ja.wikipedia.org/wiki/{name}",
            "rel": "政策実現力", "impact": "低",
            "date": "（確認中）"
        })

    # ── 委員長 / 党幹部 ────────────────────────────────
    if career["is_chair"] or career["is_party_exec"]:
        axes[3] = min(3, axes[3] + 1)  # 政策実現力
        if career["is_party_exec"]:
            axes[6] = min(3, axes[6] + 1)  # 公共性
        plus_pts.append("委員会委員長・党幹部職の経験（詳細は公式記録を参照）")

    # ── 問題フラグ ──────────────────────────────────────
    flag_crime   = career["has_crime"]
    flag_caution = career["has_caution"]

    if flag_crime:
        axes[7] = max(0, axes[7] - 2)  # 政治倫理
        axes[4] = max(0, axes[4] - 1)  # 説明責任
        minus_pts.append("逮捕・起訴・有罪に関する記録がある（Wikipedia）")
        evidence.append({
            "cat": "問題・疑惑", "sub": "犯罪・違反",
            "summary": "逮捕・起訴等の記録（Wikipedia確認）",
            "detail": "Wikipediaに逮捕・起訴または有罪に関する記述が確認された。詳細は報道機関・公式記録を参照。",
            "src": "Wikipedia",
            "url": f"https://ja.wikipedia.org/wiki/{name}",
            "rel": "政治倫理", "impact": "高",
            "date": "（確認中）"
        })
    elif flag_caution:
        axes[7] = max(1, axes[7] - 1)  # 政治倫理
        minus_pts.append("政治資金・不記載・統一教会関係等の問題が報道されている（Wikipedia）")
        evidence.append({
            "cat": "問題・疑惑", "sub": "政治資金問題",
            "summary": "政治資金・不記載等の問題報道（Wikipedia確認）",
            "detail": "Wikipediaに政治資金問題・不記載・選挙違反等に関する記述が確認された。詳細は報道機関・公式記録を参照。",
            "src": "Wikipedia",
            "url": f"https://ja.wikipedia.org/wiki/{name}",
            "rel": "政治倫理", "impact": "中",
            "date": "（確認中）"
        })

    total = int(sum(axes) * 100 / 40)
    rank  = calc_rank(total)

    intro = career.get("intro", "")
    plus_str  = "。".join(plus_pts)  + "。" if plus_pts  else "Wikipediaの公開情報からは特筆すべき実績を確認できなかった。"
    minus_str = "。".join(minus_pts) + "。" if minus_pts else "Wikipediaの公開情報のみでは詳細な課題を特定できなかった。"

    return {
        "axes":        axes,
        "total":       total,
        "rank":        rank,
        "plus":        plus_str,
        "minus":       minus_str,
        "comment":     f"Wikipedia基礎評価。{intro[:120]}{'…' if len(intro)>120 else ''}",
        "survey":      "Wikipedia基礎評価",
        "flag_crime":  flag_crime,
        "flag_caution": flag_caution,
        "evidence":    evidence,
    }


# ── バッチ生成 ────────────────────────────────────────────
def generate_batch_entry(p: dict, scored: dict) -> dict:
    """politicians_base の1件 + スコア情報を correction 形式にまとめる"""
    entry = {
        "_action": "update",
        "_note": f"{p['name']}({p['id']}): Wikipedia基礎評価 total={scored['total']} rank={scored['rank']}",
        "id":          p["id"],
        "survey":      scored["survey"],
        "axes":        scored["axes"],
        "total":       scored["total"],
        "rank":        scored["rank"],
        "plus":        scored["plus"],
        "minus":       scored["minus"],
        "comment":     scored["comment"],
        "flag_crime":  scored["flag_crime"],
        "flag_caution": scored["flag_caution"],
        "_replace_evidence": False,
        "evidence":    scored["evidence"],
    }
    return entry


# ── メイン ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",  type=int, default=0,   help="処理開始インデックス（0始まり）")
    parser.add_argument("--end",    type=int, default=None, help="処理終了インデックス（省略=全件）")
    parser.add_argument("--dry",    action="store_true",   help="取得のみ、JSON未生成")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    # ── 対象リスト読み込み ─────────────────────────────────
    with open("output/politicians_base.json", encoding="utf-8") as f:
        all_pols = json.load(f)

    targets = [p for p in all_pols
               if p.get("rank") == "情報不足" or p.get("survey") == "情報不足"]

    if args.end:
        targets = targets[args.start:args.end]
    else:
        targets = targets[args.start:]

    print(f"📋 処理対象: {len(targets)}名 (全情報不足 {len([p for p in all_pols if p.get('rank')=='情報不足'])}名中)")
    print(f"   → {math.ceil(len(targets)/args.batch_size)}バッチ生成予定\n")

    # ── キャッシュ読み込み ─────────────────────────────────
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"💾 キャッシュ: {len(cache)}件読み込み済み\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── 既存 correction ファイルの最大番号を取得 ─────────────
    import glob
    existing = glob.glob("corrections/correction_*.json")
    max_num = 0
    for f in existing:
        m = re.search(r'correction_(\d+)', f)
        if m:
            max_num = max(max_num, int(m.group(1)))

    # ── バッチ処理 ─────────────────────────────────────────
    batch_entries = []
    batch_idx     = 1
    ok_count      = 0
    skip_count    = 0
    corr_num      = max_num + 1

    for i, p in enumerate(targets):
        name = p["name"].replace(" ", "").replace("　", "")
        pid  = p["id"]

        print(f"[{i+1:03d}/{len(targets)}] {pid} {p['name']} ... ", end="", flush=True)

        # キャッシュ確認
        if name in cache:
            content, extract = cache[name]["content"], cache[name]["extract"]
            print("(キャッシュ)", end=" ")
        else:
            content, extract = fetch_wikipedia(name)
            cache[name] = {"content": content, "extract": extract}
            # キャッシュ保存（途中でも保存）
            if (i + 1) % 10 == 0:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False)
            time.sleep(DELAY)

        career = analyze_career(name, content, extract)
        scored = score_from_career(career, name)

        if scored is None:
            print("❌ Wikipedia記事なし → スキップ")
            skip_count += 1
            continue

        # サマリー出力
        markers = []
        if career["is_minister"]:   markers.append("大臣")
        if career["is_vice"]:       markers.append("副大臣/政務官")
        if career["is_chair"]:      markers.append("委員長")
        if career["is_party_exec"]: markers.append("党幹部")
        if career["terms"] >= 2:    markers.append(f"{career['terms']}期")
        if career["has_crime"]:     markers.append("🚨犯罪")
        if career["has_caution"]:   markers.append("⚠️注意")
        marker_str = " ".join(markers) if markers else "一般議員"

        print(f"✅ total={scored['total']:3d} {scored['rank']:3s} [{marker_str}]")

        entry = generate_batch_entry(p, scored)
        batch_entries.append(entry)
        ok_count += 1

        # バッチファイル書き出し
        if len(batch_entries) >= args.batch_size or i == len(targets) - 1:
            if batch_entries and not args.dry:
                # バッチ番号の範囲から議員IDを取得
                ids = [e["id"] for e in batch_entries]
                id_range = f"{ids[0]}-{ids[-1]}"
                fname = f"corrections/correction_{corr_num:03d}_wiki_{id_range}.json"
                with open(fname, "w", encoding="utf-8") as f:
                    json.dump(batch_entries, f, ensure_ascii=False, indent=2)
                print(f"\n  💾 保存: {fname} ({len(batch_entries)}件)\n")
                corr_num += 1
            batch_entries = []
            batch_idx += 1

    # キャッシュ最終保存
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"✅ 完了: 評価生成 {ok_count}名 / Wikipedia記事なし {skip_count}名")
    print(f"   correction_*.json → merge_batches.py --force で適用")
    print(f"   → generate_js_data.py で data.js を再生成")


import math
if __name__ == "__main__":
    main()
