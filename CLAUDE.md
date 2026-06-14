# 統覧 TORAN — プロジェクトナレッジ

## 概要

国会議員（衆参計822名）を8軸で独自評価するデータベースサイト。
GitHub Pages でホスティング。データは `data.js` に格納。

- URL: `https://dashiyo777-oss.github.io/politicians.html`
- 評価済: 710名（2026.06時点） / Wikipedia基礎評価: 85名 / 情報不足: 27名

---

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `data.js` | 全政治家データ（POLITICIANS配列）約1.5MB |
| `politicians.html` | ランキング一覧ページ |
| `politician.html` | 議員個別カルテページ |
| `parties.html` | 政党別評価比較ページ |
| `history_ranking.html` | 歴史ランキング |
| `scripts/validate_data.py` | data.js整合性チェックスクリプト |
| `.github/workflows/validate-data.yml` | CI（PR時自動検証） |
| `generate_wikipedia_batches.py` | Wikipedia情報から一括評価生成 |
| `generate_js_data.py` | data.js生成ツール |
| `apply.py` | バッチ評価結果をdata.jsに適用 |

---

## data.js エントリ構造

```javascript
{
    id:"P001", name:"氏名", reading:"よみがな", party:"政党", role:"衆議院議員",
    chamber:"衆議院",  // または "参議院"
    district:"選挙区", status:"現職", gender:"男",  // または "女"
    age:null,
    total:63, rank:"C",
    axes:[3,3,3,3,3,3,3,3],  // 8軸 各0〜5
    stances:{tax_cut:"◎", active_fiscal:"○", ...},
    plus:"強み記述", minus:"弱み記述",
    comment:"総合コメント",
    links:{tw:"", hp:"", wiki:"", yt:""},
    flag_crime:false, flag_caution:false,
    updated:"2026.06", survey:"評価済"
}
```

### survey の種類
- `"評価済"` — 本格評価済み（710名）
- `"Wikipedia基礎評価"` — Wikipedia情報のみで仮評価（85名）
- `"情報不足"` — 評価不可（27名）

---

## スコア計算式（必須）

```python
# 8軸の合計から total を計算
axes_sum = sum(axes)  # 0〜40
total = int(axes_sum * 100 / 40)  # 0〜100

# ランク判定（generate_wikipedia_batches.py の calc_rank）
def calc_rank(total):
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
```

### 有効な total 値（axes合計→total の対応例）
- sum=25 → total=62（C-）
- sum=26 → total=65（C）
- sum=27 → total=67（C+）
- sum=28 → total=70（B-）
- sum=29 → total=72（B-）
- sum=30 → total=75（B）
- sum=32 → total=80（A-）
- sum=34 → total=85（A）
- sum=35 → total=87（A+）
- sum=36 → total=90（S）

**重要**: total=76、71等は数学的に不可能な値。CI で検出される。

---

## CI 整合性チェック

PRマージ前に自動実行（`.github/workflows/validate-data.yml`）:

1. **ファイルサイズ** — 500KB 以上
2. **JavaScript 構文** — `node --check data.js`
3. **ヘッダーコメント** — "統覧 TORAN" を含む
4. **政治家数** — 800件以上
5. **total/rank 整合性** — `scripts/validate_data.py` で検証

ローカル確認コマンド:
```bash
node --check data.js && python3 scripts/validate_data.py
```

---

## data.js 手動更新手順

### 1. エントリを探して置換（Python）

```python
import re

data = open('data.js', encoding='utf-8').read()
pid = "P001"

# ブレース深度マッチングでエントリを取得
start = data.find(f'id:"{pid}"')
ob = data.rfind('{', 0, start)
depth = 1; i = ob + 1
while i < len(data) and depth > 0:
    if data[i] == '{': depth += 1
    elif data[i] == '}': depth -= 1
    i += 1
old_entry = data[ob:i]

# 新エントリで置換
new_entry = '{ id:"P001", ... }'
data = data.replace(old_entry, new_entry, 1)
open('data.js', 'w', encoding='utf-8').write(data)
```

### 2. 複数エントリを更新する場合
**逆順処理**が必須（文字列オフセットがずれないため）:
```python
matches = list(pattern.finditer(data))
matches.reverse()
for m in matches:
    # 後ろから順に置換
```

---

## 政党別スタンス定義（主要政党）

stances の各キーの意味:

| キー | 内容 |
|------|------|
| tax_cut | 減税・基礎控除拡大 |
| active_fiscal | 積極財政 |
| discipline | 財政規律 |
| defense | 防衛力強化 |
| econ_sec | 経済安全保障 |
| immigration | 外国人受け入れ |
| renewable | 再生可能エネルギー |
| nuclear | 原子力発電 |
| expo | 万博・大型イベント |
| ir | IR・カジノ |
| mynumber | マイナンバー推進 |
| birthrate | 少子化対策 |
| education | 教育投資 |
| regional | 地方創生 |
| china | 対中強硬路線 |
| foreign | 外交積極推進 |
| food | 食料安全保障 |
| semi | 半導体・先端産業 |

記号: `◎`=強く支持、`○`=支持、`△`=中立、`×`=反対

---

## よくある作業

### 新規評価追加（Excelデータ受け取り時）

1. Excelをアップロード → Python でパース
2. 8軸スコアを設定（各0〜5）
3. `total = int(sum(axes) * 100 / 40)` を計算
4. `rank = calc_rank(total)` を設定
5. plus / minus / comment を記述
6. stances を政党傾向に合わせて設定
7. `scripts/validate_data.py` で整合性確認
8. コミット・プッシュ → PR → CI pass → マージ

### 不整合を一括修正する場合

```bash
python3 /tmp/fix_data.py  # 過去に使用したスクリプト（/tmp に保存）
python3 scripts/validate_data.py  # 確認
```

### データ更新日の表示

`politicians.html` の JS が POLITICIANS 配列の `updated` フィールド最大値を自動取得して表示。
エントリの `updated:"2026.06"` を更新するだけで反映される。

---

## ⚠️ changelog.js 必須更新ルール

**data.js を変更したら、必ず同じ PR で `changelog.js` も更新すること。**
CI がこれを自動検出して失敗させる（data.js 変更時に changelog.js 未更新は ❌ でブロック）。

### changelog.js の書き方

```javascript
// changelog.js の先頭に追記（新しいものを上に）
const SITE_CHANGELOG = [
  {
    date: "2026.06.14",          // 更新日（YYYY.MM.DD）
    label: "変更の種類を一言で",   // 例: "評価追加", "バグ修正", "機能追加"
    entries: [
      "変更内容を箇条書きで（何件追加・何を修正など）",
      "複数行OK",
    ]
  },
  // ... 既存のエントリ
];
```

### 更新例

| 作業内容 | changelog に書くこと |
|---------|-------------------|
| 評価済み人数が増えた | "評価済みXX名に到達" |
| 特定議員のデータ修正 | "XX（氏名）の◯◯を修正" |
| 情報不足→Wikipedia基礎評価 | "情報不足X件にWikipedia基礎評価を適用" |
| スタンス・コメント更新 | "XX名のスタンス・コメントを更新" |

---

## Git 運用

- 開発ブランチ: `claude/amazing-volta-Ii6eP`
- マージ方法: squash merge
- stop-hook エラー時:
  ```bash
  git config user.email "noreply@anthropic.com"
  git config user.name "Claude"
  git fetch origin main
  git rebase --exec "git commit --amend --no-edit --reset-author" origin/main
  ```

---

## 残タスク（2026.06.14時点）

### データ系
- [ ] `Wikipedia基礎評価` 91件の本格評価（優先度：高）

### 機能系
- [ ] 更新告知自動化（GitHub Actions + X API 連携）

### 完了済み
- ✅ `[ ]` 付き43件（参議院）の正式名称・政党確定（2026.06.14）
- ✅ `情報不足` 全件解消 → 0件（2026.06.14）
- ✅ Google Search Console 登録（2026.06.14）
- ✅ サイトマップ（sitemap.xml）作成（2026.06.14）

---

## アクセス改善（実施済み）

- ✅ OGPタグ（politicians.html・politician.html）
- ✅ Xシェアボタン（議員カルテページ）
- ✅ title タグ動的最適化（議員名・ランク・点数を含む）
- ✅ 政党別比較ページ（parties.html）
- ✅ データ更新日表示
