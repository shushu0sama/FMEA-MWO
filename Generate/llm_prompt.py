import os
import re
import sys
from openai import OpenAI
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Initialise list of Chinese prompt variants (hand-written, no API needed)
def initialise_cn_prompts(num_variants=5, num_examples=5):
    """ Return Chinese prompt variations for MWO generation. """

    if num_examples == 1:
        base_prompts = [
            "根据以下设备故障信息，生成一条中文维护工单记录。",
            "你是维修技师，用简洁专业的中文写一条维护工单。",
            "为以下设备故障编写一条标准维护工单。",
            "用技术性语言描述以下故障的维修处理。",
            "写一条中文维护记录，包含故障现象和处理方式。",
        ]
    else:
        base_prompts = [
            f"根据以下设备故障信息，生成{num_examples}条不同的中文维护工单记录。",
            f"你是维修技师，用简洁专业的中文写{num_examples}条维护工单。",
            f"为以下设备故障编写{num_examples}条不同的标准维护工单。",
            f"用技术性语言描述以下故障，生成{num_examples}条维修处理记录。",
            f"写{num_examples}条中文维护记录，包含故障现象和处理方式。",
        ]

    limit_words = [
        "语言简洁，每句不超过20个字。",
        "避免冗长表述，控制在15-20字以内。",
        "使用短句，每句不超过20个汉字。",
        "简洁明了，20字以内。",
        "限制每条工单20字以内，直接描述。",
    ]

    limit_count = [
        "每条记录仅包含1-2句话。",
        "不添加多余解释，直接描述故障和处理。",
        "一条工单一句话即可，无需分段。",
        "直接输出工单内容，不加其他说明。",
        "一条故障对应一条工单，不要列举多种可能。",
    ]

    return (base_prompts[:num_variants], limit_words[:num_variants], limit_count[:num_variants])

# Initialise list of prompt variants
def initialise_prompts(openai, num_variants, num_examples):
    """ Initialise list of prompt variants. """

    # Base prompt for generating MWO sentences
    base_prompts = []
    while len(base_prompts) < num_variants:
        if num_examples == 1:
            base_prompt = "Generate a Maintenance Work Order (MWO) sentence describing the following equipment and undesirable event."
            keywords = ["Maintenance Work Order", "MWO", "equipment", "undesirable event", "sentence"]
        elif num_examples == 5:
            base_prompt = f"Generate {num_examples} different Maintenance Work Order (MWO) sentences describing the following equipment and undesirable event."
            keywords = [f"{num_examples}", "Maintenance Work Order", "MWO", "equipment", "undesirable event", "sentence"]
        base_prompts = paraphrase_prompt(openai, base_prompt, keywords, num_variants)
        similarity = check_similarity(base_prompt, base_prompts)
        for prompt, sim in zip(base_prompts, similarity):
            if sim > 0.9:
                base_prompts.append(prompt)
        base_prompts = list(set(base_prompts)) # Remove duplicates

    # Word verbose-limit instruction for generating MWO sentences
    limit_words = []
    while len(limit_words) < num_variants:
        instruction = "Avoid verbosity and use minimal stop words."
        keywords = ["verbosity", "stop words"]
        limit_words = paraphrase_prompt(openai, instruction, keywords, num_variants)
        similarity = check_similarity(instruction, limit_words)
        for prompt, sim in zip(limit_words, similarity):
            if sim > 0.9:
                limit_words.append(prompt)
        limit_words = list(set(limit_words)) # Remove duplicates

    # Word count-limit instruction for generating MWO sentences
    limit_count = []
    while len(limit_count) < num_variants:
        if num_examples == 1:
            instruction = "The sentence can have a maximum of 8 words."
        elif num_examples == 5:
            instruction = "Each sentence can have a maximum of 8 words."
        keywords = ["sentence", "8"]
        limit_count = paraphrase_prompt(openai, instruction, keywords, num_variants)
        similarity = check_similarity(instruction, limit_count)
        for prompt, sim in zip(limit_count, similarity):
            if sim > 0.9:
                limit_count.append(prompt)
        limit_count = list(set(limit_count)) # Remove duplicates

    # Make sure list has correct number of variants
    base_prompts = base_prompts[:num_variants]
    limit_words = limit_words[:num_variants]
    limit_count = limit_count[:num_variants]
    return (base_prompts, limit_words, limit_count)

# Check semantic similarity for the paraphrased sentences
def check_similarity(original, paraphrases):
    """ Check semantic similarity for the paraphrased sentences. """
    model = SentenceTransformer('sentence-transformers/paraphrase-MiniLM-L6-v2')
    original_embedding = model.encode(original)
    paraphrases_embeddings = model.encode(paraphrases)
    similarities = model.similarity(original_embedding, paraphrases_embeddings)
    
    # Uncomment this to print sentence and their similarity scores
    # for sentence, similarity in zip(paraphrases, similarities.tolist()[0]):
    #     print(f"{similarity:.4f} - {sentence}")
    return similarities.tolist()[0]

# Post-process LLM response of prompt paraphrases into a list of sentences
def process_prompt_response(response):
    """ Process the response from the LLM. """
    output = []
    sentences = response.split('\n')
    for sentence in sentences:
        processed = re.sub(r'^\d+\.\s*', '', sentence).strip() 
        output.append(processed)
    return output

# Get LLM to paraphrase prompts for generating more diverse responses
def paraphrase_prompt(openai, prompt, keywords=None, num_paraphrases=5):
    """ Paraphrase the prompt to generate more diverse responses. """
    # Paraphrase the prompt num_paraphrases times
    paraphrase_prompt = f"Paraphrase the following sentence {num_paraphrases} times.\n{prompt}\n"
    paraphrase_prompt += "\n" + "Do not add any new information or alter the meaning."
    if keywords:
        string_keywords = ", ".join(keywords)
        paraphrase_prompt += "Must include the following keywords: " + string_keywords
    response = openai.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                            {"role": "system", "content": "You are a sentence paraphraser."},
                            {"role": "user", "content": paraphrase_prompt},
                        ],
                    top_p=0.9,
                    temperature=0.9,
                    n=1
                )
    output = process_prompt_response(response.choices[0].message.content)
    return output

if __name__ == "__main__":
    # Set OpenAI API key
    load_dotenv()
    api_key = os.getenv("API_KEY")
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    
    # Test Paraphrase Instruction Prompt
    instruction = "The sentence can have a maximum of 8 words."
    instructions_dummy = [
        "The sentence can have a maximum of 8 words.",
        "Each sentence can have a maximum of 8 words.",
        "The sentence should have a maximum of 8 words.",
        "Each sentence should have a maximum of 8 words.",
        "The sentence must have a maximum of 8 words."
    ]
    similarity = check_similarity(instruction, instructions_dummy)
    for prompt, sim in zip(instructions_dummy, similarity):
        print(f"{sim:.4f} - {prompt}")