import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'ui\screens\scanner_screen.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# File has literal backslash-n in the source strings
replacements = [
    ('("best_score","Điểm tốt\\nnhất")', '("best_score","Điểm tốt nhất")'),
    ('("buy_score","Điểm\\nmua")', '("buy_score","Điểm mua")'),
    ('("sell_score","Điểm\\nbán")', '("sell_score","Điểm bán")'),
    ('("macro_score","Vĩ mô\\n(0-30)")', '("macro_score","Vĩ mô (0-30)")'),
    ('("macro_bias","Thuận\\nvĩ mô")', '("macro_bias","Thuận vĩ mô")'),
]

count = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        count += 1
        print(f'OK: replaced #{count}')
    else:
        print(f'NOT FOUND: {repr(old)}')

if count > 0:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Done: {count} replacements written')
else:
    print('No replacements made')
