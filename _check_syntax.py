import ast
import sys

files = [
    'components/theme.py',
    'components/score_gauge.py',
    'components/skill_gap_chart.py',
    'app.py',
    'pages/1_Home.py',
    'pages/2_Analyzer.py',
    'styles.css',  # not Python, will intentionally fail ast — skip
]

py_files = [f for f in files if f.endswith('.py')]

errors = []
for f in py_files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            source = fh.read()
        ast.parse(source)
        print(f'  OK  {f}')
    except SyntaxError as e:
        errors.append(f'SYNTAX ERROR in {f}: {e}')
        print(f'FAIL  {f}: {e}')
    except FileNotFoundError:
        errors.append(f'FILE NOT FOUND: {f}')
        print(f'MISS  {f}')

if errors:
    print('\n=== ERRORS ===')
    for err in errors:
        print(err)
    sys.exit(1)
else:
    print(f'\nAll {len(py_files)} Python files passed syntax check.')
