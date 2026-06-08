import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'ui\screens\scanner_screen.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for i in range(41, 49):
    print(f'Line {i+1}: {repr(lines[i])[:120]}')
