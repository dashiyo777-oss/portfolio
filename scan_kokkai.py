#!/usr/bin/env python3
"""
統覧 TORAN — 国会議事録自動スキャナー
======================================
国立国会図書館 国会会議録検索API を使い、
評価済み政治家の最近の発言を取得して evidence に追加する。

使い方:
  python3 scan_kokkai.py --days 30          # 直近30日分をスキャン
  python3 scan_kokkai.py --pid P324         # 特定議員のみ
  python3 scan_kokkai.py --dry-run          # 実際には書き込まない

API: https://kokkai.ndl.go.jp/api.html (無料・認証不要)
"""

import json, time, argparse, os, glob, re
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError

BASE_URL = 'https://kokkai.ndl.go.jp/api/speech'
CORRECTIONS_DIR = 'corrections'
BASE_FILE = 'output/politicians_base.json'

# 重要度判定キーワード
HIGH_IMPACT_KEYWORDS = [
    '法律', '改正', '予算', '条約', '決議', '廃案', '成立',
    '大臣', '首相', '大統領', '防衛', '増税', '減税',
]
CAUTION_KEYWORDS = [
    '謝罪', '辞任', '不祥事', '批判', '問題', '誤り', '訂正',
    '献金', '疑惑', '逮捕', '起訴',
]

def fetch_speeches(name: str, from_date: str, to_date: str, max_results: int = 5) -> list:
    """国会会議録APIから議員の発言を取得"""
    params = {
        'speaker': name,
        'from': from_date,
        'until': to_date,
        'maximumRecords': max_results,
        'recordPacking': 'json',
    }
    url = BASE_URL + '?' + urlencode(params)
    try:
        req = Request(url, headers={'User-Agent': 'TORAN-Scanner/1.0'})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        speeches = data.get('speechRecord', [])
        return speeches
    except (URLError, json.JSONDecodeError, KeyError) as e:
        print(f"  ⚠️  API エラー ({name}): {e}")
        return []

def judge_impact(speech_text: str) -> str:
    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in speech_text:
            return '高'
    return '中'

def judge_caution(speech_text: str) -> bool:
    return any(kw in speech_text for kw in CAUTION_KEYWORDS)

def speech_to_evidence(speech: dict, pid: str) -> dict:
    """APIレスポンスのspeechをevidenceフォーマットに変換"""
    text = speech.get('speech', '')[:500]  # 最初の500文字
    summary_raw = text[:80].replace('\n', ' ').strip()
    summary = re.sub(r'\s+', ' ', summary_raw)

    house = speech.get('nameOfHouse', '')
    meeting = speech.get('nameOfMeeting', '')
    date = speech.get('date', '')[:7]  # YYYY-MM

    # 発言のカテゴリ判定
    is_caution = judge_caution(text)
    cat = '問題・疑惑' if is_caution else '発言・主張'

    return {
        'pid': pid,
        'cat': cat,
        'sub': f"{house} {meeting}",
        'summary': summary + '…',
        'detail': text.replace('\n', ' '),
        'src': f"国会会議録 {speech.get('date','')} {house} {meeting}",
        'url': speech.get('speechURL', ''),
        'rel': '安全保障' if '防衛' in text or '安保' in text else '政策全般',
        'impact': judge_impact(text),
        'date': speech.get('date', '')[:7],
    }

def get_next_correction_num() -> int:
    files = glob.glob(f'{CORRECTIONS_DIR}/correction_*.json')
    if not files:
        return 1
    nums = []
    for f in files:
        m = re.search(r'correction_(\d+)', os.path.basename(f))
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1

def main():
    parser = argparse.ArgumentParser(description='国会議事録スキャナー')
    parser.add_argument('--days', type=int, default=30, help='直近N日をスキャン（デフォルト30）')
    parser.add_argument('--pid', type=str, default=None, help='特定議員IDのみスキャン')
    parser.add_argument('--dry-run', action='store_true', help='書き込まずに確認のみ')
    parser.add_argument('--max', type=int, default=3, help='議員あたり最大N件取得')
    args = parser.parse_args()

    to_date = datetime.today().strftime('%Y-%m-%d')
    from_date = (datetime.today() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    print(f"📅 スキャン期間: {from_date} 〜 {to_date}")

    with open(BASE_FILE, encoding='utf-8') as f:
        politicians = json.load(f)

    # 対象: 評価済み・現職・特定PIDなら絞り込み
    targets = [
        p for p in politicians
        if p.get('survey') == '評価済'
        and p.get('status') in ('現職', None)
        and (args.pid is None or p['id'] == args.pid)
    ]
    print(f"🎯 対象議員: {len(targets)}名")

    all_new = []  # {pid, name, evidence}
    for p in targets:
        name = p['name'].replace(' ', '').replace('　', '')
        print(f"  🔍 {p['id']} {name} をスキャン中…", end=' ')

        speeches = fetch_speeches(name, from_date, to_date, max_results=args.max)
        if not speeches:
            print('発言なし')
            time.sleep(0.3)
            continue

        # 既存 evidence の summary と重複排除
        existing = {e.get('summary','')[:30] for e in p.get('evidence', [])}
        new_evs = []
        for sp in speeches:
            ev = speech_to_evidence(sp, p['id'])
            if ev['summary'][:30] not in existing:
                new_evs.append(ev)
                existing.add(ev['summary'][:30])

        if new_evs:
            print(f"✅ {len(new_evs)}件の新規発言を取得")
            all_new.append({'pid': p['id'], 'name': p['name'], 'evidence': new_evs})
        else:
            print('重複のみ（スキップ）')
        time.sleep(0.5)  # API負荷軽減

    if not all_new:
        print('\n✅ 新規発言なし。終了します。')
        return

    print(f'\n📊 取得結果: {len(all_new)}議員 / 合計{sum(len(x["evidence"]) for x in all_new)}件')

    if args.dry_run:
        print('\n[DRY RUN] 以下のcorrectionファイルを生成予定:')
        for item in all_new:
            print(f"  {item['pid']} {item['name']}: {len(item['evidence'])}件")
        return

    # correction ファイル生成
    num = get_next_correction_num()
    filename = f"{CORRECTIONS_DIR}/correction_{num:03d}_kokkai_scan_{to_date.replace('-','')}.json"
    payload = [
        {
            'id': item['pid'],
            '_action': 'update',
            '_changelog_entry': {
                'date': to_date,
                'summary': f"国会議事録スキャン({from_date}〜{to_date})で{len(item['evidence'])}件の発言を自動取得。",
                'before_total': None,
                'after_total': None,
            },
            'evidence': item['evidence'],
        }
        for item in all_new
    ]
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 保存: {filename}')
    print('次のコマンドでマージしてください:')
    print('  python3 merge_batches.py && python3 generate_js_data.py')

if __name__ == '__main__':
    main()
