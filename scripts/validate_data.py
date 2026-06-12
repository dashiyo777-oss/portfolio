#!/usr/bin/env python3
"""data.js 整合性チェック — CI で実行"""
import re, sys

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

data = open('data.js', encoding='utf-8').read()

entry_pat = re.compile(
    r'id:"(P\d+)".*?total:(\d+),\s*rank:"([^"]+)".*?axes:\[([^\]]+)\].*?survey:"([^"]+)"',
    re.DOTALL
)

errors = []
checked = 0

for m in entry_pat.finditer(data):
    pid, total_s, rank, axes_s, survey = m.groups()
    if survey != '評価済':
        continue
    checked += 1
    total = int(total_s)
    axes = [int(x.strip()) for x in axes_s.split(',')]
    axes_sum = sum(axes)
    expected_total = int(axes_sum * 100 / 40)
    expected_rank = calc_rank(total)

    if total != expected_total:
        errors.append(
            f"  {pid}: total={total} (axes sum={axes_sum} → expected {expected_total})"
        )
    if rank != expected_rank:
        errors.append(
            f"  {pid}: rank=\"{rank}\" total={total} → expected \"{expected_rank}\""
        )

print(f"チェック対象: {checked}件 (survey:評価済)")

if errors:
    print(f"\n❌ 不整合 {len(errors)}件:\n" + "\n".join(errors))
    print("\n修正方法: python3 /tmp/fix_data.py または手動で data.js を修正してください")
    sys.exit(1)

print(f"✅ total/rank 整合性 OK")
