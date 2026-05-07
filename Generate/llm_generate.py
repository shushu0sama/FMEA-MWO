import os
import re
import sys
import csv
import json
import random
from openai import OpenAI
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
from dotenv import load_dotenv

sys.path.append(os.path.abspath('../PathExtraction'))

from path_queries import direct_queries, complex_queries, cn_direct_queries, cn_complex_queries
from llm_prompt import initialise_prompts, initialise_cn_prompts

BLACKLIST = ['shows signs of', 'showing signs of', 'detected',
             'observed', 'requires attention', 'identified', 'application']

CN_BLACKLIST = ['发现', '检测到', '观察到', '显示有', '需要关注',
                '需要进行', '建议', '可能存在', '疑似', '似乎']

# Read all the paths extracted from MaintIE KG
def get_all_paths(valid=True, label=False, schema='maintie'):
    """ Read all the paths extracted from MaintIE Gold Dataset KG or Chinese FMEA KG """
    if schema == 'fmea':
        queries = cn_direct_queries + cn_complex_queries
    else:
        queries = direct_queries + complex_queries

    paths_list = []
    paths_dict = {}
    for query in queries:
        filepath = f"../PathExtraction/path_patterns/{query['outfile']}.json"
        try:
            with open(filepath, encoding='utf-8') as f:
                paths_json = json.load(f)
                if valid and label:
                    paths_json = [path for path in paths_json if path.get('valid', True) == valid and 'failure_mode' in path]
                elif valid:
                    paths_json = [path for path in paths_json if path.get('valid', True) == valid]
                elif label:
                    paths_json = [path for path in paths_json if 'failure_mode' in path]
                print(f"{len(paths_json)}\tpaths in {query['outfile']}")
                paths_dict[query['outfile']] = paths_json
                paths_list.extend(paths_json)
        except FileNotFoundError:
            print(f"WARNING: {filepath} not found, skipping")
    print(f"Total number of paths: {len(paths_list)}")
    return paths_list, paths_dict

# Direct Neo4j path extraction for Chinese FMEA KG
def get_cn_paths_from_neo4j(driver, valid=True):
    """ Extract paths directly from Chinese FMEA Neo4j KG """
    from neo4j import GraphDatabase
    queries = cn_direct_queries + cn_complex_queries
    paths_list = []
    paths_dict = {}

    for query_def in queries:
        paths = []
        try:
            with driver.session() as session:
                results = session.run(query_def['query'])
                for record in results:
                    data = dict(record)
                    # Map to unified format expected by generate functions
                    obj_field = query_def.get('object_field', 'system')
                    evt_field = query_def.get('event_field', 'failure_mode')

                    path = {
                        'object_name': data.get(obj_field, ''),
                        'event_name': data.get(evt_field, ''),
                        'object_type': obj_field,
                        'valid': True,
                        'path_type': query_def.get('path_type', 'direct'),
                        # Additional Chinese FMEA fields
                        'system': data.get('system', ''),
                        'failure_mode': data.get('failure_mode', ''),
                        'cause': data.get('cause', ''),
                        'effect': data.get('effect', ''),
                        'prevention': data.get('prevention', ''),
                        'detection': data.get('detection', ''),
                        'function': data.get('function', ''),
                        'component': data.get('component', ''),
                    }
                    # Filter empty names
                    if path['object_name'] and path['event_name']:
                        paths.append(path)
        except Exception as e:
            print(f"ERROR running query {query_def['outfile']}: {e}")

        print(f"{len(paths)}\tpaths in {query_def['outfile']}")
        paths_dict[query_def['outfile']] = paths
        paths_list.extend(paths)

    print(f"Total number of CN paths: {len(paths_list)}")
    return paths_list, paths_dict

# Craft and return prompt for generating MWO sentences
def get_generate_prompt(prompt_variations, object, event):
    """ Craft and return prompt for generating MWO sentences.
        Prompt: Generate 5 different Maintenance Work Order (MWO) sentence describing 
                the following equipment undesirable event. 
                Equipment: {object}
                Undesirable Event: {event}
                You must use all terms given above and do not add new information.
                Avoid verbosity and use minimal stop words.
                Each sentence can have a maximum of 8 words.
                Do not use these terms: {blacklisted_words}.
    """
    # Randomly select base prompt and instruction prompt
    base_prompts, limit_words, limit_count = prompt_variations
    base = random.choice(base_prompts)
    words = random.choice(limit_words)
    count = random.choice(limit_count)
    blacklist = ["'"+word+"'" for word in BLACKLIST]
    blacklist = ', '.join(blacklist)
    prompt = f"{base}\nEquipment: {object}\nUndesirable Event: {event}"
    prompt += f"\nYou must use all terms given above and do not add new information.\n{words}\n{count}"
    prompt += f"Do not use these terms: {blacklist}."
    return prompt

# Get fewshot message from fewshot csv file
def get_generate_fewshot(prompt_variations):
    """ Get fewshot message from fewshot csv file """
    message = [{"role": "system", "content": "You are a technician recording maintenance work orders."}]
    with open("fewshot_messages/fewshot_generate.csv", encoding='utf-8') as f:
        fewshot_data = csv.reader(f)
        next(fewshot_data) # Ignore header
        for row in fewshot_data:
            object_name = row[0]
            event_name = f"{row[1]} {row[2]}".strip()
            prompt = get_generate_prompt(prompt_variations, object_name, event_name)
            user = {"role": "user", "content": prompt}
            example = f"1. {row[4]}\n2. {row[5]}\n3. {row[6]}\n4. {row[7]}\n5. {row[8]}"
            assistant = {"role": "assistant", "content": example}
            message.append(user)
            message.append(assistant)

    # Save fewshot message to json file
    with open("fewshot_messages/fewshot_generate.json", "w", encoding='utf-8') as f:
        json.dump(message, f, indent=4)

    return message

# Overall generation for MWO sentences
def generate_mwo(client, prompt_variations, path):
    """ Generate MWO sentences for each path """
    # Get prompt for current path's PhysicalObject and UndesirableEvent
    object = path['object_name']
    event = path['event_name']
    prompt = get_generate_prompt(prompt_variations, object, event)
    fewshot = get_generate_fewshot(prompt_variations)
    message = fewshot + [{"role": "user", "content": prompt}]
    
    # Generate 1 completion for path (max 5 sentences)
    response = client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=message,
                    temperature=0.9,
                    top_p=0.9,
                    n=1
            )
    sentences = process_mwo_response(response.choices[0].message.content)
    print(f"{object} {event} - {len(sentences)} sentences")
    return sentences

# Overall generation process for diversity
def generate_diverse_mwo(client, prompt_variations, path):
    """ Generate diverse MWO sentences for each path """
    num = 5
    # Get prompt for current path's PhysicalObject and UndesirableEvent
    object = path['object_name']
    event = path['event_name']
    prompt = get_generate_prompt(prompt_variations, object, event)

    # Get fewshot message
    fewshot = get_generate_fewshot(prompt_variations)

    # Generate 5 completions (max 5x5 sentences) for each path
    sentences = [] # Max 25 sentences (avg 10)
    for _ in range(num):
        message = fewshot + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
                        model=DEEPSEEK_MODEL,
                        messages=message,
                        temperature=0.9,
                        top_p=0.9,
                        n=1
                )
        response_sentences = process_mwo_response(response.choices[0].message.content)
        sentences.extend(response_sentences)
    sentences = list(set(sentences)) # Remove duplicates
    print(f"{object} {event} - {len(sentences)} sentences")
    return sentences

# ---- Chinese MWO Generation Functions ----

def get_cn_generate_prompt(prompt_variations, object_name, event_name):
    """ Craft Chinese prompt for generating MWO sentences. """
    base_prompts, limit_words, limit_count = prompt_variations
    base = random.choice(base_prompts)
    words = random.choice(limit_words)
    count = random.choice(limit_count)
    blacklist = ["\"" + word + "\"" for word in CN_BLACKLIST]
    blacklist_str = '、'.join(blacklist)
    prompt = f"{base}\n设备：{object_name}\n故障：{event_name}"
    prompt += f"\n必须使用上述所有术语，不添加额外信息。\n{words}\n{count}"
    prompt += f"不要使用这些词汇：{blacklist_str}。"
    return prompt

def get_cn_generate_fewshot(prompt_variations):
    """ Get Chinese few-shot examples for MWO generation. """
    message = [{"role": "system", "content": "你是一名维修技师，负责记录设备维护工单。使用简洁、含行业术语的语言。每条工单控制在20字以内，直接描述故障和处理措施。"}]
    # Try multiple paths for fewshot file
    possible_paths = [
        "fewshot_messages/fewshot_cn.csv",
        os.path.join(os.path.dirname(__file__), "fewshot_messages/fewshot_cn.csv"),
    ]
    found = False
    for fpath in possible_paths:
        if os.path.exists(fpath):
            with open(fpath, encoding='utf-8') as f:
                fewshot_data = csv.reader(f)
                next(fewshot_data)
                for row in fewshot_data:
                    object_name = row[0]
                    event_name = row[1].strip()
                    prompt = get_cn_generate_prompt(prompt_variations, object_name, event_name)
                    user = {"role": "user", "content": prompt}
                    examples = f"1. {row[2]}\n2. {row[3]}\n3. {row[4]}\n4. {row[5]}\n5. {row[6]}"
                    assistant = {"role": "assistant", "content": examples}
                    message.append(user)
                    message.append(assistant)
            found = True
            break
    if not found:
        print("WARNING: fewshot_cn.csv not found, using zero-shot mode")
    return message

def generate_cn_mwo(client, prompt_variations, path):
    """ Generate Chinese MWO sentences for a given equipment-failure path. """
    obj = path.get('object_name', '')
    evt = path.get('event_name', '')
    prompt = get_cn_generate_prompt(prompt_variations, obj, evt)
    fewshot = get_cn_generate_fewshot(prompt_variations)
    message = fewshot + [{"role": "user", "content": prompt}]

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=message,
        temperature=0.9,
        top_p=0.9,
        n=1
    )
    sentences = process_cn_mwo_response(response.choices[0].message.content)
    print(f"{obj} {evt} - {len(sentences)} 条工单")
    return sentences

def generate_diverse_cn_mwo(client, prompt_variations, path, rounds=5):
    """ Generate diverse Chinese MWO sentences. """
    obj = path.get('object_name', '')
    evt = path.get('event_name', '')
    fewshot = get_cn_generate_fewshot(prompt_variations)
    sentences = []
    for _ in range(rounds):
        prompt = get_cn_generate_prompt(prompt_variations, obj, evt)
        message = fewshot + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=message,
            temperature=0.9,
            top_p=0.9,
            n=1
        )
        response_sentences = process_cn_mwo_response(response.choices[0].message.content)
        sentences.extend(response_sentences)
    sentences = list(set(sentences))
    print(f"{obj} {evt} - {len(sentences)} 条工单 (diverse)")
    return sentences

def process_cn_mwo_response(response):
    """ Process LLM response for Chinese MWO sentences.
        No case folding (Chinese has no case). Keep punctuation minimal. """
    output = []
    for sentence in response.strip().split('\n'):
        processed = re.sub(r'^\d+[\.\)、\s]+', '', sentence).strip()
        processed = re.sub(r'[，,]\s*', '，', processed)
        processed = re.sub(r'\s+', '', processed)
        if processed and len(processed) >= 3:
            output.append(processed)
    return output

def paraphrase_cn_mwo(client, sentence, keywords=None, num_paraphrases=5):
    """ Paraphrase Chinese MWO sentences. """
    pp = f"将以下句子改写{num_paraphrases}个不同版本。\n{sentence}\n"
    if keywords:
        pp += "必须包含以下关键词：" + "、".join(keywords)
    pp += "\n可变换语序或替换同义词，保持原意不变。每句不超过20字。"
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": "你是中文句子改写助手，输出改写后的句子。"},
            {"role": "user", "content": pp},
        ],
        top_p=0.9, temperature=0.9, n=1
    )
    return process_cn_mwo_response(response.choices[0].message.content)

# Process LLM response and return list of MWO sentences
def process_mwo_response(response):
    """ Process LLM response and return list of MWO sentences """
    output = []
    sentences = response.split('\n')
    for sentence in sentences:
        processed = re.sub(r'^\d+\.\s*', '', sentence) # Remove numbering
        processed = re.sub(r',', '', processed)        # Remove commas
        processed = re.sub(r'\s+', ' ', processed)     # Remove extra spaces
        processed = processed.lower().strip()          # Case folding and strip
        output.append(processed)
    return output

# Get samples from different path types (num samples per path type)
def get_samples(paths_dict, num_samples=30, exclude=[]):
    """ Get samples from different path types """
    samples = []
    for key, paths in paths_dict.items():
        if key in exclude:
            continue
        if len(paths) < num_samples:
            paths = random.sample(paths, len(paths))
        else:
            paths = random.sample(paths, num_samples)
        samples.extend(paths)
    return samples

# Get LLM to paraphrase MWO sentences with PhysicalObject and UndesirableEvent
def paraphrase_mwo(client, sentence, keywords=None, num_paraphrases=5):
    """ GPT paraphrases MWO sentences. """
    # Paraphrase the MWO sentence num_paraphrases times
    paraphrase_prompt = f"Paraphrase the following sentence {num_paraphrases} times.\n{sentence}\n"
    if keywords:
        string_keywords = ", ".join(keywords)
        paraphrase_prompt += "Must include the following keywords: " + string_keywords
    paraphrase_prompt += "\nYou may change the sentence from passive to active voice or vice versa."
    paraphrase_prompt += "\nThe sentence can have a maximum of 8 words."
    response = client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a sentence paraphraser."},
                        {"role": "user", "content": paraphrase_prompt},
                    ],
                    top_p=0.9,
                    temperature=0.9,
                    n=1
                )
    output = process_mwo_response(response.choices[0].message.content)
    return output

if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("API_KEY")
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    # Check for --cn flag to use Chinese pipeline
    use_cn = '--cn' in sys.argv
    lang = 'cn' if use_cn else 'en'

    if use_cn:
        print("=== 中文 FMEA MWO 生成管线 ===")
        from neo4j import GraphDatabase
        from llm_prompt import initialise_cn_prompts

        neo4j_uri = os.getenv("NEO4J_URI")
        if not neo4j_uri:
            print("ERROR: NEO4J_URI not set in .env")
            sys.exit(1)

        driver = GraphDatabase.driver(neo4j_uri, auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))

        # Step 1: Extract paths from Neo4j
        print("\n[1/3] 从 Neo4j 提取中文 FMEA 路径...")
        paths_list, paths_dict = get_cn_paths_from_neo4j(driver)
        driver.close()

        # Step 2: Generate Chinese MWO
        print("\n[2/3] 生成中文 MWO...")
        prompt_variations = initialise_cn_prompts()
        paths = get_samples(paths_dict, num_samples=int(sys.argv[sys.argv.index('--samples')+1]) if '--samples' in sys.argv else 5)

        all_sentences = []
        out_logfile = "mwo_sentences/cn_log.txt"
        out_csvfile = "mwo_sentences/cn_synthetic.csv"

        for path in paths:
            sentences = generate_cn_mwo(client, prompt_variations, path)
            all_sentences.extend(sentences)

            with open(out_logfile, "a", encoding='utf-8') as f:
                f.write("="*60 + "\n")
                f.write(f"设备: {path.get('system','')} / {path['object_name']}\n")
                f.write(f"故障: {path['event_name']}\n")
                f.write(f"起因: {path.get('cause','')}\n")
                f.write(f"条数: {len(sentences)}\n")
                f.write("-"*60 + "\n")
                for s in sentences:
                    f.write(f"~ {s}\n")
                f.write("="*60 + "\n")

            with open(out_csvfile, "a", encoding='utf-8') as f:
                for s in sentences:
                    f.write(f"{s},{path.get('system','')},{path['object_name']},{path['event_name']}\n")

        # Step 3: Humanize
        print("\n[3/3] 中文人性化...")
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Humanise'))
            from humanise_cn import cn_humanise_sentence
            humanized = [cn_humanise_sentence(s) for s in all_sentences]
            changed = sum(1 for i in range(len(all_sentences)) if all_sentences[i] != humanized[i])
            print(f"  人性化: {changed}/{len(all_sentences)} 条发生变化 ({changed/len(all_sentences)*100:.0f}%)")

            with open(out_logfile.replace('.txt', '_humanised.txt'), "w", encoding='utf-8') as f:
                for i, (orig, hum) in enumerate(zip(all_sentences, humanized)):
                    f.write(f"{i+1}. ORIG: {orig}\n")
                    f.write(f"   HUM:  {hum}\n")
                    if orig != hum:
                        f.write(f"   DIFF: [已修改]\n")
                    f.write("\n")
        except ImportError:
            print("  (humanise_cn module not available, skipping)")

        print(f"\n完成! 生成 {len(all_sentences)} 条中文 MWO")

    else:
        # Original English pipeline
        print("=== English MaintIE MWO Generation ===")
        paths_list, paths_dict = get_all_paths(valid=True)
        prompt_variations = initialise_prompts(client, num_variants=5, num_examples=5)
        paths = get_samples(paths_dict, num_samples=1)

        out_logfile = "mwo_sentences/log.txt"
        out_csvfile = "mwo_sentences/order_synthetic.csv"

        for path in paths:
            sentences = generate_mwo(client, prompt_variations, path)
            with open(out_logfile, "a", encoding='utf-8') as f:
                f.write("="*60 + "\n")
                f.write(f"Object: {path['object_name']}\n")
                f.write(f"Event: {path['event_name']}\n")
                f.write(f"Number of sentences: {len(sentences)}\n")
                f.write("-"*60 + "\n")
                for sentence in sentences:
                    f.write(f"~ {sentence}\n")
                f.write("="*60 + "\n")
            with open(out_csvfile, "a", encoding='utf-8') as f:
                for sentence in sentences:
                    f.write(f"{sentence},{path.get('object_type','')},{path['object_name']},{path['event_name']}\n")

        print(f"Done! Generated {len(paths)} batches")
