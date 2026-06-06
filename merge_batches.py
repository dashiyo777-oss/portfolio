#!/usr/bin/env python3
"""
統覧 TORAN — バッチマージスクリプト
=====================================
使い方:
  python merge_batches.py

  batches/batch_*.json を読み込み、
  output/politicians_base.json に上書きマージして
  output/politicians_merged.json を出力します。
"""

import json, glob, os, sys
from datetime import date
from validate_batch import validate_batch, load_base

BASE_FILE       = 'output/politicians_base.json'
BATCHES_DIR     = 'batches'
CORRECTIONS_DIR = 'corrections'   # 手動修正ファイル（バッチより後に適用）
OUT_FILE        = 'output/politicians_merged.json'
DATA_JS         = '../portfolio/data.js'   # HTMLが読み込むファイル（任意）

def main():
    # ── ベースJSONを読み込む ──
    with open(BASE_FILE, encoding='utf-8') as f:
        base_list = json.load(f)

    base_map = {p['id']: p for p in base_list}
    print(f"📂 ベース: {len(base_list)}名")

    # ── バッチを順番に読み込む ──
    batch_files = sorted(glob.glob(f'{BATCHES_DIR}/batch_*.json'))
    if not batch_files:
        print(f"⚠️  {BATCHES_DIR}/ にバッチファイルが見つかりません。")
        return

    merged_count = 0
    evidence_count = 0
    total_errors = 0
    VALIDATED_DIR = os.path.join(BATCHES_DIR, '.validated')
    os.makedirs(VALIDATED_DIR, exist_ok=True)

    # 未検証バッチのみチェック
    unvalidated = [bf for bf in batch_files
                   if not os.path.exists(os.path.join(VALIDATED_DIR,
                       os.path.basename(bf) + '.ok'))]

    if unvalidated:
        print(f"\n{'='*55}")
        print(f"🔍 バッチ検証フェーズ（未検証 {len(unvalidated)} 件）")
        print(f"{'='*55}")
        for bf in unvalidated:
            ok, warn, err = validate_batch(bf, base_map, silent=False)
            total_errors += err
            # ERRORなしなら検証済みフラグを作成
            if err == 0:
                flag = os.path.join(VALIDATED_DIR, os.path.basename(bf) + '.ok')
                open(flag, 'w').close()

        if total_errors > 0:
            print(f"\n{'='*55}")
            print(f"❌ 合計 {total_errors} 件の ERROR が検出されました。")
            print(f"   該当バッチのJSONを確認・修正してください。")
            print(f"   ※ corrections/ で上書き修正した場合は --force で強制続行できます。")
            print(f"{'='*55}\n")
            if '--force' not in sys.argv:
                print("⛔ マージを中止しました。")
                return
            else:
                print("⚠️  --force 指定のため続行します。\n")
        else:
            print(f"\n✅ 全バッチ検証OK。マージを開始します。\n")
    else:
        print(f"✅ 全バッチ検証済み。マージを開始します。")

    for bf in batch_files:
        with open(bf, encoding='utf-8') as f:
            batch = json.load(f)

        for item in batch:
            pid = item.get('id')
            if pid not in base_map:
                print(f"  ⚠️  {pid} はベースに存在しません → スキップ")
                continue

            p = base_map[pid]

            # スコア・評価フィールドを上書き
            for key in ['total','rank','axes','stances','role',
                        'plus','minus','comment',
                        'flag_crime','flag_caution']:
                if key in item:
                    p[key] = item[key]

            # evidenceを追加（重複しないように）
            existing_summaries = {e.get('summary','') for e in p.get('evidence', [])}
            new_ev = item.get('evidence', [])
            added = 0
            for ev in new_ev:
                # pid を付与
                ev['pid'] = pid
                if ev.get('summary','') not in existing_summaries:
                    p.setdefault('evidence', []).append(ev)
                    existing_summaries.add(ev.get('summary',''))
                    added += 1

            # survey フラグ更新
            if item.get('total', 0) > 0:
                p['survey'] = '評価済'
                p['updated'] = date.today().strftime('%Y.%m')
            elif item.get('rank') == '情報不足':
                p['survey'] = '情報不足'

            merged_count += 1
            evidence_count += added

        print(f"  ✅ {os.path.basename(bf)}: {len(batch)}名マージ")

    # ── corrections/ を適用（バッチより後＝優先） ──
    corr_files = sorted(glob.glob(f'{CORRECTIONS_DIR}/correction_*.json'))
    if corr_files:
        corr_count = 0
        for cf in corr_files:
            with open(cf, encoding='utf-8') as f:
                corrections = json.load(f)
            for item in corrections:
                pid = item.get('id')
                action = item.get('_action', 'update')  # 'update', 'reset', or 'add'
                if pid not in base_map:
                    if action == 'add':
                        # 新規政治家を追加
                        new_p = {
                            'id': pid, 'name': item.get('name',''), 'reading': item.get('reading',''),
                            'party': item.get('party',''), 'faction': item.get('faction',''),
                            'role': item.get('role',''), 'chamber': item.get('chamber',''),
                            'district': item.get('district',''), 'status': item.get('status','元職'),
                            'gender': item.get('gender',''), 'age': item.get('age', None),
                            'total': item.get('total',0), 'rank': item.get('rank','未評価'),
                            'axes': item.get('axes',[0]*8), 'stances': item.get('stances',{}),
                            'plus': item.get('plus',''), 'minus': item.get('minus',''),
                            'comment': item.get('comment',''), 'flag_crime': item.get('flag_crime',False),
                            'flag_caution': item.get('flag_caution',False),
                            'updated': item.get('updated', date.today().strftime('%Y.%m')),
                            'survey': item.get('survey','評価済'),
                            'links': item.get('links', {'hp':'','tw':'','yt':'','wiki':''}),
                            'evidence': [dict(ev, pid=pid) for ev in item.get('evidence',[])]
                        }
                        base_map[pid] = new_p
                        print(f"  ➕ 新規追加: {pid} {new_p['name']}")
                        corr_count += 1
                        continue
                    else:
                        print(f"  ⚠️  修正 {pid} はベースに存在しません → スキップ")
                        continue
                p = base_map[pid]

                if action == 'reset':
                    # 評価データをリセット（未評価状態に戻す）
                    p['axes']       = [0]*8
                    p['total']      = 0
                    p['rank']       = '未評価'
                    p['survey']     = '未評価'
                    p['plus']       = ''
                    p['minus']      = ''
                    p['comment']    = ''
                    p['flag_crime'] = False
                    p['flag_caution'] = False
                    p['evidence']   = []
                    if 'role' in item:
                        p['role'] = item['role']
                    if 'stances' in item:
                        p['stances'] = item['stances']
                    print(f"  🔄 修正RESET: {pid} {p['name']}")
                else:
                    # 指定フィールドのみ上書き
                    for key in ['total','rank','axes','stances','role',
                                'plus','minus','comment','survey','party',
                                'flag_crime','flag_caution','updated']:
                        if key in item:
                            p[key] = item[key]
                    # links はフィールドごとにマージ（既存tw/wikiを消さない）
                    if 'links' in item:
                        p.setdefault('links', {}).update(item['links'])
                    # evidence は replace_all=true のとき全置換
                    if item.get('_replace_evidence'):
                        p['evidence'] = item.get('evidence', [])
                        for ev in p['evidence']:
                            ev['pid'] = pid
                    elif 'evidence' in item:
                        existing_summaries = {e.get('summary','') for e in p.get('evidence', [])}
                        for ev in item['evidence']:
                            ev['pid'] = pid
                            if ev.get('summary','') not in existing_summaries:
                                p.setdefault('evidence', []).append(ev)
                                existing_summaries.add(ev.get('summary',''))
                    print(f"  ✏️  修正UPDATE: {pid} {p['name']}")
                corr_count += 1
            print(f"  ✅ {os.path.basename(cf)}: {len(corrections)}件適用")

    # ── 集計 ──
    result = list(base_map.values())

    evaluated   = sum(1 for p in result if p.get('total', 0) > 0)
    info_lack   = sum(1 for p in result if p.get('rank') == '情報不足')
    pending     = sum(1 for p in result if p.get('rank') == '未評価')
    total_ev    = sum(len(p.get('evidence', [])) for p in result)
    crime_flags = sum(1 for p in result if p.get('flag_crime'))
    caution_flags = sum(1 for p in result if p.get('flag_caution'))

    # ── 出力 ──
    os.makedirs('output', exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n📄 出力: {OUT_FILE}")

    print(f"\n【現在の進捗】")
    print(f"  評価済:    {evaluated}名 ({evaluated/len(result)*100:.1f}%)")
    print(f"  情報不足:  {info_lack}名")
    print(f"  未評価:    {pending}名")
    print(f"  根拠件数:  {total_ev}件")
    print(f"  🚨犯罪フラグ: {crime_flags}名")
    print(f"  ⚠️ 要注意フラグ: {caution_flags}名")
    print(f"  残りバッチ: あと約{pending//15 + 1}バッチ")

    # ── base を上書き更新 ──
    with open(BASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {BASE_FILE} も更新しました")

if __name__ == '__main__':
    main()
