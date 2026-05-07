"""
数据处理脚本 v2：将 StingRAY + Zenodo 转换为 FMEA 13列格式
"""
import sys, io, os, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import numpy as np
from dotenv import load_dotenv
load_dotenv('D:/code/MWO/LLM-KG-Synthetic-MWO/.env')
from openai import OpenAI

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
client = OpenAI(api_key=os.getenv('API_KEY'), base_url=DEEPSEEK_BASE_URL)

TARGET_COLS = [
    '关注要素层次', '下一低分析层次', '上一高层次功能及要求', '功能',
    '下一低层次功能', '故障影响', '严重度(S)', '故障模式', '故障起因',
    '发生度(O)', '探测度(D)', '预防控制措施', '探测控制措施'
]
OUTPUT_DIR = 'D:/code/MWO/LLM-KG-Synthetic-MWO/data/external/_output'

# ---- StingRAY column indices (from row 4 header) ----
# col0=empty, col1=RiskID, col2=ItemDescription, col3=Function,
# col6=FailureMode, col7=FailureEffects, col8=FailureCause,
# col10=RiskReduction, col11=PreventativeDetection, col12=PostFailureDetection,
# col14=Occurrence, col15=HumanSafety(severity)
STINGRAY_COL_MAP = {
    'component': 2,
    'function': 3,
    'failure_mode': 6,
    'failure_effect': 7,
    'failure_cause': 8,
    'risk_reduction': 10,
    'prevention': 11,
    'detection': 12,
    'repair': 13,
    'occurrence': 14,
    'severity': 15,
}

def get_system_name(sheet_name):
    """Extract clean system name from sheet name like '0100 Hull System'"""
    name = sheet_name.replace(' System', '').strip()
    name = re.sub(r'^\d{4}\s+', '', name)
    return name

def extract_stingray():
    """Extract StingRAY FMECA data with correct column indices"""
    stingray_dir = 'D:/code/MWO/LLM-KG-Synthetic-MWO/data/external/stingray'
    all_rows = []
    stats = {'ok': 0, 'skip': 0, 'error': 0}

    for fname in sorted(os.listdir(stingray_dir)):
        if not fname.endswith('.xlsx'):
            continue
        fpath = os.path.join(stingray_dir, fname)
        try:
            xls = pd.ExcelFile(fpath)
            data_sheets = [s for s in xls.sheet_names
                           if s not in ['Data Rights Notice', 'version history', 'set up', 'linkedPage']]
            if not data_sheets:
                stats['skip'] += 1
                continue

            sheet = data_sheets[0]
            system_name = get_system_name(sheet)
            df = pd.read_excel(xls, sheet, header=None)

            # Find header row (contains Risk|ID + Failure|Mode)
            header_row = None
            for i in range(min(8, len(df))):
                row_text = ' '.join([str(v) for v in df.iloc[i] if pd.notna(v)])
                if 'failure' in row_text.lower() and 'mode' in row_text.lower() and 'risk' in row_text.lower():
                    header_row = i
                    break

            if header_row is None:
                stats['skip'] += 1
                continue

            # Iterate data rows
            file_rows = 0
            for idx in range(header_row + 1, len(df)):
                row = df.iloc[idx]
                comp = str(row.iloc[STINGRAY_COL_MAP['component']]).strip()
                fm = str(row.iloc[STINGRAY_COL_MAP['failure_mode']]).strip()

                # Skip empty rows
                if not comp or comp in ['nan', 'NaN', 'none', 'None']:
                    continue

                # Clean function: remove pipe separators for readability
                func_raw = str(row.iloc[STINGRAY_COL_MAP['function']]).strip()
                func = func_raw.replace('|', '；') if func_raw and func_raw != 'nan' else ''

                fe_raw = str(row.iloc[STINGRAY_COL_MAP['failure_effect']]).strip()
                fe = fe_raw.replace('|', '；') if fe_raw and fe_raw != 'nan' else ''

                fc_raw = str(row.iloc[STINGRAY_COL_MAP['failure_cause']]).strip()
                fc = fc_raw.replace('|', '；') if fc_raw and fc_raw != 'nan' else ''

                prev_raw = str(row.iloc[STINGRAY_COL_MAP['prevention']]).strip()
                prev = prev_raw.replace('|', '；') if prev_raw and prev_raw != 'nan' else ''

                det_raw = str(row.iloc[STINGRAY_COL_MAP['detection']]).strip()
                det = det_raw.replace('|', '；') if det_raw and det_raw != 'nan' else ''

                repair_raw = str(row.iloc[STINGRAY_COL_MAP['repair']]).strip()
                repair = repair_raw.replace('|', '；') if repair_raw and repair_raw != 'nan' else ''

                occ_raw = str(row.iloc[STINGRAY_COL_MAP['occurrence']]).strip()
                sev_raw = str(row.iloc[STINGRAY_COL_MAP['severity']]).strip()

                # Extract numeric severity/occurrence if present
                occ = ''
                sev = ''
                try:
                    occ = str(int(float(occ_raw))) if occ_raw and occ_raw != 'nan' else ''
                except (ValueError, TypeError):
                    occ = occ_raw if occ_raw and occ_raw != 'nan' else ''
                try:
                    sev = str(int(float(sev_raw))) if sev_raw and sev_raw != 'nan' else ''
                except (ValueError, TypeError):
                    sev = sev_raw if sev_raw and sev_raw != 'nan' else ''

                # Combine detection + repair into 探测控制措施
                detection_combined = det
                if repair and repair not in ['nan', 'none']:
                    detection_combined = f'{det}；{repair}' if det else repair

                record = {
                    '关注要素层次': system_name,
                    '下一低分析层次': comp,
                    '上一高层次功能及要求': '满足系统持续运行要求',
                    '功能': func,
                    '下一低层次功能': '',
                    '故障影响': fe,
                    '严重度(S)': sev,
                    '故障模式': fm,
                    '故障起因': fc,
                    '发生度(O)': occ,
                    '探测度(D)': '2',
                    '预防控制措施': prev,
                    '探测控制措施': detection_combined,
                    'source': f'StingRAY/{fname}',
                }
                all_rows.append(record)
                file_rows += 1

            stats['ok'] += 1
            print(f'  OK {fname}: {file_rows} rows')

        except Exception as e:
            stats['error'] += 1
            print(f'  ERROR {fname}: {e}')

    df = pd.DataFrame(all_rows)
    print(f'\nStingRAY: {len(df)} total rows (ok={stats["ok"]}, skip={stats["skip"]}, err={stats["error"]})')
    return df

def extract_zenodo():
    """Extract Zenodo IMPACT FMECA data"""
    fpath = 'D:/code/MWO/LLM-KG-Synthetic-MWO/data/external/fmeca_impact_h2020.xlsx'
    xls = pd.ExcelFile(fpath)
    all_rows = []

    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet)
        except Exception:
            continue

        system_name = sheet.strip().lstrip()
        cols = {c.lower().replace('\n', ' ').strip(): c for c in df.columns}

        # Find columns by keyword
        comp_col = next((c for k, c in cols.items() if 'component' in k), None)
        fm_col = next((c for k, c in cols.items() if 'failure mode' in k and 'annual' not in k), None)
        effect_col = next((c for k, c in cols.items() if ('effect' in k) and ('failure' in k or 'consequence' in k)), None)
        cause_col = next((c for k, c in cols.items() if 'mechanism' in k and 'failure' in k), None)
        sev_col = next((c for k, c in cols.items() if 'severity' in k and ('s' == k.strip()[-1:].lower() or '(s)' in k)), None)
        occ_col = next((c for k, c in cols.items() if 'occur' in k), None)
        sub_col = next((c for k, c in cols.items() if 'sub' in k and 'system' in k), None)

        # If no sub-system column, use sheet name
        # Build row index: component is at same position as sub-system (forward-filled)
        last_sub = system_name
        last_comp = ''

        for _, row in df.iterrows():
            sub_val = str(row[sub_col]).strip() if sub_col else ''
            comp_val = str(row[comp_col]).strip() if comp_col else ''

            # Forward-fill sub-system
            if sub_val and sub_val != 'nan':
                last_sub = sub_val
            if comp_val and comp_val != 'nan':
                last_comp = comp_val

            fm_val = str(row[fm_col]).strip() if fm_col else ''
            if fm_val == 'nan' or (not last_comp and not fm_val):
                continue

            sev_val = row[sev_col] if sev_col else np.nan
            occ_val = row[occ_col] if occ_col else np.nan

            record = {
                '关注要素层次': last_sub,
                '下一低分析层次': last_comp,
                '上一高层次功能及要求': '满足系统持续运行要求',
                '功能': '',
                '下一低层次功能': '',
                '故障影响': str(row[effect_col]).strip() if effect_col else '',
                '严重度(S)': str(int(sev_val)) if not pd.isna(sev_val) else '',
                '故障模式': fm_val,
                '故障起因': str(row[cause_col]).strip() if cause_col else '',
                '发生度(O)': str(int(occ_val)) if not pd.isna(occ_val) else '',
                '探测度(D)': '2',
                '预防控制措施': '',
                '探测控制措施': '',
                'source': f'Zenodo/{sheet}',
            }
            for k in list(record.keys()):
                if record[k] in ['nan', 'NaN', '']:
                    record[k] = ''
            all_rows.append(record)

        sheet_rows = len([r for r in all_rows if r['source'] == f'Zenodo/{sheet}'])
        print(f'  OK Zenodo/{sheet}: {sheet_rows} rows')

    df = pd.DataFrame(all_rows)
    print(f'\nZenodo: {len(df)} total rows from {len(xls.sheet_names)} sheets')
    return df

def translate_field_batch(texts, field_name):
    """Batch translate English texts to Chinese"""
    unique_texts = {}
    for t in texts:
        if t and str(t).strip() and str(t).strip() != 'nan':
            s = str(t).strip()
            if s not in unique_texts:
                unique_texts[s] = []

    if not unique_texts:
        return {t: t for t in texts}

    text_list = list(unique_texts.keys())
    translated = {}

    # Process in small batches
    batch_size = 20
    for i in range(0, len(text_list), batch_size):
        batch = text_list[i:i+batch_size]
        items = '\n'.join([f'{j+1}. {t[:250]}' for j, t in enumerate(batch)])

        prompt = f'''Translate the following FMEA/engineering terms to Simplified Chinese (简体中文).
Be concise and technically accurate. Keep technical abbreviations if widely used.

Field type: {field_name}

{items}

Return exactly one translation per line, numbered. Only output the translations.'''

        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{'role': 'system', 'content': 'You translate engineering FMEA data to Chinese. Output only numbered translations.'},
                      {'role': 'user', 'content': prompt}],
            temperature=0.2, top_p=0.9, max_tokens=4096
        )
        content = resp.choices[0].message.content

        for line in content.strip().split('\n'):
            line = line.strip()
            m = re.match(r'^(\d+)[\.\)、\s]+(.*)', line)
            if m:
                idx = int(m.group(1)) - 1
                if idx < len(batch):
                    translated[batch[idx]] = m.group(2).strip() or batch[idx]

        print(f'    [{field_name}] batch {i//batch_size+1}: {len(batch)} texts')

    # Map back
    result = {}
    for t in texts:
        s = str(t).strip() if t and str(t).strip() != 'nan' else ''
        result[t] = translated.get(s, s) if s else t
    return result

def translate_dataframe(df):
    """Translate all English fields to Chinese"""
    print('\n--- Translating English → Chinese ---')
    fields_to_translate = [
        '关注要素层次', '下一低分析层次', '功能', '故障模式',
        '故障影响', '故障起因', '预防控制措施', '探测控制措施'
    ]

    for field in fields_to_translate:
        values = df[field].tolist()
        non_empty = [v for v in values if v and str(v).strip() and str(v).strip() != 'nan']
        if not non_empty:
            print(f'  Skip {field}: all empty')
            continue

        print(f'  Translating {field} ({len(non_empty)} items)...')
        mapping = translate_field_batch(values, field)

        new_vals = [mapping.get(v, v) for v in values]
        df[field] = new_vals

    return df

def fill_missing_and_validate(df):
    """Fill missing fields and validate quality"""
    print('\n--- Filling Missing Fields ---')

    # Ensure all 13 target columns exist
    for col in TARGET_COLS:
        if col not in df.columns:
            df[col] = ''

    # Fill defaults
    df['上一高层次功能及要求'] = df['上一高层次功能及要求'].replace('', '满足系统持续运行要求')
    df['探测度(D)'] = df['探测度(D)'].replace('', '2')

    # Estimate S/O from context if missing
    empty_sev = (df['严重度(S)'].isna() | (df['严重度(S)'] == ''))
    empty_occ = (df['发生度(O)'].isna() | (df['发生度(O)'] == ''))

    for idx in df.index:
        if empty_sev.iloc[idx] if hasattr(empty_sev, 'iloc') else empty_sev[idx]:
            effect = str(df.at[idx, '故障影响']).lower()
            mode = str(df.at[idx, '故障模式']).lower()
            if any(w in effect+mode for w in ['severe', 'critical', 'safety', 'loss', 'destroy', 'fatal', '坠毁', '严重', '致命']):
                df.at[idx, '严重度(S)'] = '5'
            elif any(w in effect+mode for w in ['major', 'significant', 'degraded', 'failure', '失效', '损坏']):
                df.at[idx, '严重度(S)'] = '4'
            else:
                df.at[idx, '严重度(S)'] = '3'

        if empty_occ.iloc[idx] if hasattr(empty_occ, 'iloc') else empty_occ[idx]:
            df.at[idx, '发生度(O)'] = '2'

    # ---- Quality Report ----
    print('\n=== QUALITY REPORT ===')
    print(f'Total rows: {len(df)}')

    stats = []
    for col in TARGET_COLS:
        filled = (df[col].notna() & (df[col] != '') & (df[col] != 'nan')).sum()
        pct = filled / len(df) * 100 if len(df) > 0 else 0
        flag = '✅' if pct >= 80 else ('⚠️' if pct >= 50 else '❌')
        print(f'  {flag} {col}: {filled}/{len(df)} ({pct:.0f}%)')
        stats.append((col, filled, pct))

    # Check for excessive English remaining
    en_pattern = re.compile(r'[a-zA-Z]{15,}')
    en_count = 0
    for col in ['关注要素层次', '下一低分析层次', '故障模式', '故障影响', '故障起因']:
        for val in df[col]:
            if en_pattern.search(str(val)):
                en_count += 1
    print(f'  {"⚠️" if en_count > len(df)*0.1 else "✅"} Long English text remaining: {en_count} cells')

    # Duplicates
    if len(df) > 0:
        dupes = df.duplicated(subset=['下一低分析层次', '故障模式', '故障起因']).sum()
        print(f'  {"⚠️" if dupes > 0 else "✅"} Duplicate rows: {dupes}')

    # System coverage
    systems = df['关注要素层次'].value_counts()
    print(f'\n  System coverage ({len(systems)} systems):')
    for sys_name, cnt in systems.items():
        print(f'    {sys_name}: {cnt} rows')

    # Source distribution
    sources = df.get('source', pd.Series(['unknown']*len(df))).value_counts()
    print(f'\n  Source distribution:')
    for src, cnt in sources.items():
        print(f'    {src}: {cnt} rows')

    return df

# ============================================================
if __name__ == '__main__':
    print('='*60)
    print('PHASE 1: Extract StingRAY + Zenodo')
    print('='*60)

    df_stingray = extract_stingray()
    df_stingray.to_csv(f'{OUTPUT_DIR}/stage1_stingray.csv', index=False, encoding='utf-8-sig')

    df_zenodo = extract_zenodo()
    df_zenodo.to_csv(f'{OUTPUT_DIR}/stage1_zenodo.csv', index=False, encoding='utf-8-sig')

    df_all = pd.concat([df_stingray, df_zenodo], ignore_index=True)
    print(f'\nCombined: {len(df_all)} rows')
    df_all.to_csv(f'{OUTPUT_DIR}/stage1_combined.csv', index=False, encoding='utf-8-sig')

    print('\n' + '='*60)
    print('PHASE 2: Translate to Chinese')
    print('='*60)

    df_translated = translate_dataframe(df_all)
    df_translated.to_csv(f'{OUTPUT_DIR}/stage2_translated.csv', index=False, encoding='utf-8-sig')

    print('\n' + '='*60)
    print('PHASE 3: Fill + Validate')
    print('='*60)

    df_final = fill_missing_and_validate(df_translated)

    # Final output with correct column order
    cols_out = [c for c in TARGET_COLS if c in df_final.columns]
    df_out = df_final[cols_out]

    out_xlsx = f'{OUTPUT_DIR}/fmea_stingray_zenodo.xlsx'
    df_out.to_excel(out_xlsx, index=False)
    print(f'\n✅ Output saved: {out_xlsx}')
    print(f'   Rows: {len(df_out)}, Columns: {len(cols_out)}')
    print(f'   Shape matches data1014.xlsx: {set(cols_out) == set(TARGET_COLS)}')
    print('Done!')
