"""Phase 2: NHTSA complaint data → FMEA 13-column extraction via LLM"""
import sys, io, os, re, json, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
from dotenv import load_dotenv; load_dotenv('D:/code/MWO/LLM-KG-Synthetic-MWO/.env')
from openai import OpenAI

client = OpenAI(api_key=os.getenv('API_KEY'), base_url='https://api.deepseek.com')

# Read NHTSA sample
lines = []
with open('D:/code/MWO/LLM-KG-Synthetic-MWO/data/external/nhtsa_sample.tsv', 'r', encoding='latin-1', errors='replace') as f:
    next(f)
    for line in f:
        cols = line.split('\t')
        if len(cols) >= 20:
            comp = cols[11].strip()
            desc = cols[19].strip()
            if comp and desc and len(desc) > 15:
                lines.append({'component': comp, 'description': desc})

print(f'Total valid: {len(lines)}')

# Sample stratified by system
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

# Process in batches
batch_size = 15
results = []
bad_batches = 0

for bi in range(0, len(sampled), batch_size):
    batch = sampled[bi:bi+batch_size]

    items_text = ''
    for j, entry in enumerate(batch):
        items_text += f'{j+1}. Component: {entry["component"]}\n   Complaint: {entry["description"][:200]}\n\n'

    prompt = f"""You are an automotive FMEA engineer. For each complaint, extract structured FMEA data in Chinese (简体中文).

Return a JSON array. Each object should have:
- system_cn: System name in Chinese
- component_cn: Component name in Chinese
- function: Normal function in Chinese
- failure_mode: What failed in Chinese
- failure_cause: Root cause in Chinese
- failure_effect: Consequence in Chinese
- severity: integer 1-10
- occurrence: integer 1-10
- detection: integer 1-10
- prevention: Preventive measures in Chinese
- detection_measure: Detection methods in Chinese

Items:
{items_text}
Return ONLY a valid JSON array. No markdown."""

    try:
        resp = client.chat.completions.create(
            model='deepseek-chat',
            messages=[{'role': 'system', 'content': 'Output ONLY valid JSON arrays. No explanations.'},
                      {'role': 'user', 'content': prompt}],
            temperature=0.3, top_p=0.95, max_tokens=8192
        )

        content = resp.choices[0].message.content.strip()
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

        batch_results = json.loads(content)
        for j, entry in enumerate(batch_results):
            entry['component_raw'] = batch[j]['component']
            entry['description_raw'] = batch[j]['description']
            results.append(entry)
        print(f'  Batch {bi//batch_size+1}: {len(batch_results)} OK')
    except Exception as e:
        bad_batches += 1
        print(f'  Batch {bi//batch_size+1}: FAILED - {str(e)[:100]}')

print(f'\nExtracted: {len(results)} rows (failed batches: {bad_batches})')

# Build DataFrame
TARGET_COLS = [
    '关注要素层次', '下一低分析层次', '上一高层次功能及要求', '功能',
    '下一低层次功能', '故障影响', '严重度(S)', '故障模式', '故障起因',
    '发生度(O)', '探测度(D)', '预防控制措施', '探测控制措施'
]

rows_data = []
for r in results:
    row = {
        '关注要素层次': str(r.get('system_cn', '')),
        '下一低分析层次': str(r.get('component_cn', '')),
        '上一高层次功能及要求': '满足车辆安全运行要求',
        '功能': str(r.get('function', '')),
        '下一低层次功能': '',
        '故障影响': str(r.get('failure_effect', '')),
        '严重度(S)': str(r.get('severity', '3')),
        '故障模式': str(r.get('failure_mode', '')),
        '故障起因': str(r.get('failure_cause', '')),
        '发生度(O)': str(r.get('occurrence', '2')),
        '探测度(D)': str(r.get('detection', '2')),
        '预防控制措施': str(r.get('prevention', '')),
        '探测控制措施': str(r.get('detection_measure', '')),
        'source': 'NHTSA',
    }
    rows_data.append(row)

df_nhtsa = pd.DataFrame(rows_data)

# Clean
for c in TARGET_COLS:
    if c in df_nhtsa.columns:
        df_nhtsa[c] = df_nhtsa[c].fillna('').astype(str).replace('nan', '')

# Quality
print('\n=== QUALITY ===')
for c in TARGET_COLS:
    filled = (df_nhtsa[c] != '') & (df_nhtsa[c] != 'None')
    print(f'  {c}: {filled.sum()}/{len(df_nhtsa)}')

# Save
out_path = 'D:/code/MWO/LLM-KG-Synthetic-MWO/data/external/_output/fmea_nhtsa.xlsx'
df_nhtsa[TARGET_COLS].to_excel(out_path, index=False)
print(f'\nSaved: {out_path}')
print(f'Rows: {len(df_nhtsa)}, Systems: {df_nhtsa["关注要素层次"].nunique()}')

# Show some samples
print('\n=== Sample outputs ===')
for i in range(0, min(9, len(df_nhtsa)), 3):
    r = df_nhtsa.iloc[i]
    print(f'{r["关注要素层次"]} | {r["下一低分析层次"]} | {r["故障模式"][:50]}')
