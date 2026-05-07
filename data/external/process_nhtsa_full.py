"""Phase 2: NHTSA → FMEA full processing"""
import sys, io, os, re, json, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
from dotenv import load_dotenv; load_dotenv('D:/code/MWO/LLM-KG-Synthetic-MWO/.env')
from openai import OpenAI

client = OpenAI(api_key=os.getenv('API_KEY'), base_url='https://api.deepseek.com')

# Read all valid NHTSA entries
lines = []
with open('D:/code/MWO/LLM-KG-Synthetic-MWO/data/external/nhtsa_sample.tsv', 'r', encoding='latin-1', errors='replace') as f:
    next(f)
    for line in f:
        cols = line.split('\t')
        if len(cols) >= 20:
            comp = cols[11].strip()
            desc = cols[19].strip()
            if comp and desc and len(desc) > 20:
                lines.append({'component': comp, 'description': desc})

print(f'Total valid: {len(lines)}')

# Stratified sampling: up to 20 per system
random.seed(42)
by_system = {}
for row in lines:
    sys_name = row['component'].split(':')[0].strip()
    by_system.setdefault(sys_name, []).append(row)

sampled = []
for sys_name, rows in by_system.items():
    n = min(20, len(rows))
    sampled.extend(random.sample(rows, n))

print(f'Sampled: {len(sampled)} across {len(by_system)} systems')

# Process in batches of 10
batch_size = 10
results = []
errors = 0

for bi in range(0, len(sampled), batch_size):
    batch = sampled[bi:bi+batch_size]
    items_text = ''
    for j, entry in enumerate(batch):
        items_text += f'{j+1}. Component: {entry["component"]}\n   Complaint: {entry["description"][:180]}\n\n'

    prompt = f'''Extract FMEA data in Chinese. Return JSON array. Fields:
system_cn, component_cn, function, failure_mode, failure_cause, failure_effect,
severity(int 1-10), occurrence(int 1-10), detection(int 1-10),
prevention, detection_measure.

{items_text}
Return ONLY valid JSON. No markdown.'''

    try:
        resp = client.chat.completions.create(
            model='deepseek-chat',
            messages=[{'role': 'system', 'content': 'Output ONLY valid JSON array. No markdown, no explanation.'},
                      {'role': 'user', 'content': prompt}],
            temperature=0.3, max_tokens=8192
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

        batch_results = json.loads(content)
        for j, entry in enumerate(batch_results):
            entry['_comp_raw'] = batch[j]['component']
            results.append(entry)
        print(f'  [{bi//batch_size+1}/{(len(sampled)+batch_size-1)//batch_size}] {len(batch_results)} items')
        sys.stdout.flush()
    except Exception as e:
        errors += 1
        print(f'  [{bi//batch_size+1}] ERR: {str(e)[:80]}')
        sys.stdout.flush()

print(f'\nDone: {len(results)} rows ({errors} batch errors)')

# Build DataFrame
TARGET_COLS = [
    '关注要素层次', '下一低分析层次', '上一高层次功能及要求', '功能',
    '下一低层次功能', '故障影响', '严重度(S)', '故障模式', '故障起因',
    '发生度(O)', '探测度(D)', '预防控制措施', '探测控制措施'
]

rows_data = []
for r in results:
    rows_data.append({
        '关注要素层次': str(r.get('system_cn', '')).replace('None', ''),
        '下一低分析层次': str(r.get('component_cn', '')).replace('None', ''),
        '上一高层次功能及要求': '满足车辆安全运行要求',
        '功能': str(r.get('function', '')).replace('None', ''),
        '下一低层次功能': '',
        '故障影响': str(r.get('failure_effect', '')).replace('None', ''),
        '严重度(S)': str(r.get('severity', '3')).replace('None', '3'),
        '故障模式': str(r.get('failure_mode', '')).replace('None', ''),
        '故障起因': str(r.get('failure_cause', '')).replace('None', ''),
        '发生度(O)': str(r.get('occurrence', '2')).replace('None', '2'),
        '探测度(D)': str(r.get('detection', '2')).replace('None', '2'),
        '预防控制措施': str(r.get('prevention', '')).replace('None', ''),
        '探测控制措施': str(r.get('detection_measure', '')).replace('None', ''),
    })

df = pd.DataFrame(rows_data)

# Quality report
print('\n=== QUALITY ===')
for c in TARGET_COLS:
    filled = (df[c] != '') & (df[c] != 'None')
    pct = filled.sum()/len(df)*100
    flag = 'OK' if pct >= 80 else ('WARN' if pct >= 50 else 'GAP')
    print(f'  [{flag}] {c}: {filled.sum()}/{len(df)} ({pct:.0f}%)')

print(f'\nSystems: {df["关注要素层次"].nunique()}')
for s, cnt in df['关注要素层次'].value_counts().head(15).items():
    print(f'  {s}: {cnt}')

# Save
out = 'D:/code/MWO/LLM-KG-Synthetic-MWO/data/external/_output/fmea_nhtsa.xlsx'
df[TARGET_COLS].to_excel(out, index=False)
print(f'\nSaved: {out} ({len(df)} rows)')
