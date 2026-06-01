#!/usr/bin/env python3
"""
統覧 TORAN — data.js 生成スクリプト
=====================================
output/politicians_base.json → data.js を出力。
politicians.html / politician.html は data.js を外部読み込みするため、
バッチ更新時は data.js の1ファイルだけをアップロードすれば OK。
"""

import json, os, re, glob

BASE_FILE    = 'output/politicians_base.json'
DATA_JS      = 'data.js'
POLITICIANS_HTML = 'politicians.html'
POLITICIAN_HTML  = 'politician.html'

def fmt_val(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return 'null'
    return json.dumps(v, ensure_ascii=False)

def politician_to_js(p):
    axes = p.get('axes', [0]*8)
    stances = p.get('stances', {})
    stance_keys = ['tax_cut','active_fiscal','discipline','defense','econ_sec',
                   'immigration','renewable','nuclear','expo','ir','mynumber',
                   'birthrate','education','regional','china','foreign','food','semi']
    stances_js = '{' + ','.join(f"{k}:{fmt_val(stances.get(k,'△'))}" for k in stance_keys) + '}'
    axes_js = '[' + ','.join(str(a) for a in axes) + ']'
    links = p.get('links', {}) or {'hp':'','tw':'','yt':'','wiki':''}
    links_js = '{' + ','.join(f"{k}:{fmt_val(v)}" for k,v in links.items()) + '}'
    return (
        f"  {{\n"
        f"    id:{fmt_val(p['id'])}, name:{fmt_val(p['name'])}, reading:{fmt_val(p.get('reading',''))}, "
        f"party:{fmt_val(p.get('party',''))}, role:{fmt_val(p.get('role',''))},\n"
        f"    chamber:{fmt_val(p.get('chamber',''))}, district:{fmt_val(p.get('district',''))}, "
        f"status:{fmt_val(p.get('status','現職'))}, gender:{fmt_val(p.get('gender','男'))}, age:{fmt_val(p.get('age'))},\n"
        f"    total:{p.get('total',0)}, rank:{fmt_val(p.get('rank','未評価'))},\n"
        f"    axes:{axes_js},\n"
        f"    stances:{stances_js},\n"
        f"    plus:{fmt_val(p.get('plus',''))}, minus:{fmt_val(p.get('minus',''))},\n"
        f"    comment:{fmt_val(p.get('comment',''))},\n"
        f"    links:{links_js},\n"
        f"    flag_crime:{fmt_val(p.get('flag_crime',False))}, flag_caution:{fmt_val(p.get('flag_caution',False))}, "
        f"updated:{fmt_val(p.get('updated',''))}, survey:{fmt_val(p.get('survey','未評価'))}\n"
        f"  }}"
    )

def evidence_to_js(e):
    return (
        f"  {{id:{fmt_val(e.get('id',''))}, pid:{fmt_val(e.get('pid',''))}, "
        f"cat:{fmt_val(e.get('cat',''))}, sub:{fmt_val(e.get('sub',''))}, "
        f"summary:{fmt_val(e.get('summary',''))}, detail:{fmt_val(e.get('detail',''))}, "
        f"src:{fmt_val(e.get('src',''))}, url:{fmt_val(e.get('url',''))}, "
        f"rel:{fmt_val(e.get('rel',''))}, impact:{fmt_val(e.get('impact',''))}, "
        f"date:{fmt_val(e.get('date',''))}}}"
    )

def main():
    with open(BASE_FILE, encoding='utf-8') as f:
        politicians = json.load(f)
    print(f"📂 読み込み: {len(politicians)}名")

    # POLITICIANS JS配列
    pols_js = "const POLITICIANS = [\n" + ",\n".join(politician_to_js(p) for p in politicians) + "\n];"

    # EVIDENCE 収集
    ev_counter = 1
    evidence_items = []
    for p in politicians:
        for ev in p.get('evidence', []):
            ev_copy = dict(ev)
            ev_copy['pid'] = p['id']
            if not ev_copy.get('id'):
                ev_copy['id'] = f"E{ev_counter:04d}"
            ev_counter += 1
            evidence_items.append(ev_copy)

    ev_js = "const EVIDENCE = [\n" + ",\n".join(evidence_to_js(e) for e in evidence_items) + "\n];"
    print(f"📋 根拠: {len(evidence_items)}件")

    # CHANGELOG 収集（correction_*.json の _changelog_entry を集約）
    changelog_items = []
    for cf in sorted(glob.glob('corrections/correction_*.json')):
        with open(cf, encoding='utf-8') as f:
            corrections = json.load(f)
        for item in corrections:
            entry = item.get('_changelog_entry')
            if entry:
                changelog_items.append({
                    'pid': item.get('id',''),
                    'date': entry.get('date',''),
                    'summary': entry.get('summary',''),
                    'before_total': entry.get('before_total', None),
                    'after_total': entry.get('after_total', None),
                    'action': item.get('_action','update')
                })
    def changelog_to_js(c):
        bt = str(c['before_total']) if c['before_total'] is not None else 'null'
        at = str(c['after_total']) if c['after_total'] is not None else 'null'
        return (f"  {{pid:{fmt_val(c['pid'])}, date:{fmt_val(c['date'])}, "
                f"summary:{fmt_val(c['summary'])}, before_total:{bt}, after_total:{at}, "
                f"action:{fmt_val(c['action'])}}}")
    changelog_js = "const CHANGELOG = [\n" + ",\n".join(changelog_to_js(c) for c in changelog_items) + "\n];"
    print(f"📝 変更履歴: {len(changelog_items)}件")

    # ── data.js を出力 ──
    evaluated   = sum(1 for p in politicians if p.get('total', 0) > 0)
    crime_flags = sum(1 for p in politicians if p.get('flag_crime'))
    caution_flags = sum(1 for p in politicians if p.get('flag_caution'))

    data_js_content = f"""// 統覧 TORAN — data.js
// 自動生成ファイル。直接編集しないでください。
// generate_js_data.py で再生成されます。
// 評価済: {evaluated}名 / 🚨{crime_flags}名 / ⚠️{caution_flags}名 / 根拠{len(evidence_items)}件

{pols_js}

{ev_js}

{changelog_js}
"""
    with open(DATA_JS, 'w', encoding='utf-8') as f:
        f.write(data_js_content)
    print(f"  ✅ {DATA_JS} 出力完了 ({os.path.getsize(DATA_JS)//1024}KB)")

    # ── HTML側のインライン配列を削除してsrc読み込みに差し替え ──
    # （初回のみ必要。すでに外部化済みならスキップ）
    for html_file in [POLITICIANS_HTML, POLITICIAN_HTML]:
        if not os.path.exists(html_file):
            continue
        with open(html_file, encoding='utf-8') as f:
            content = f.read()

        # すでに外部化済みかチェック（?v=xxx キャッシュバスターも含む）
        if 'src="data.js' in content:
            print(f"  ✅ {html_file} はすでに外部化済み → スキップ")
            continue

        # POLITICIANS配列 + EVIDENCE配列をまるごと削除
        content = re.sub(
            r'const POLITICIANS = \[.*?\];\s*\n\s*const EVIDENCE = \[.*?\];',
            '',
            content, flags=re.DOTALL
        )
        # <script> タグの直前に <script src="data.js"></script> を挿入
        content = content.replace(
            '<script>\n/* ── DATA ──',
            '<script src="data.js"></script>\n<script>\n/* ── DATA ──'
        )

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ {html_file} を外部data.js方式に更新")

    print(f"\n✅ 完了！次回からは data.js の1ファイルだけをアップロードしてください。")

if __name__ == '__main__':
    main()
