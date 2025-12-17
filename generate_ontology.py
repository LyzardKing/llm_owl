import argparse
import os
import re
import sys

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pyparsing.helpers import Iterable

from validator import log_report, validate_ttl, validate_with_competency_questions_file

load_dotenv()

# Initialize OpenAI client
client = None

LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_API_KEY = os.getenv("LLM_API_KEY")

prefix_part = """# Prefixes
@prefix : <http://example.org/highway_code#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def get_client():
    """Get or initialize the OpenAI client configured for local LLM."""
    global client
    if client is None:
        client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return client


def load_system_prompt(path="system_step-by-step.md"):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def call_llm(system_prompt, text, dest, model=None):
    client = get_client()
    model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
    messages: Iterable[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Please follow the system step-by-step instructions exactly. "
                "Given the following legal text, produce two outputs in this order:\n"
                "1) A JSON array of extracted sentence-level objects as described in the system prompt.\n"
                "3) A section `## OWL` containing the OWL representation in Turtle (ttl).\n\n"
                "Legal text:\n\n" + text
            ),
        },
    ]

    with open(os.path.join(dest, "LLM_prompt.md"), "a+", encoding="utf-8") as f:
        for msg in messages:
            f.write(f"# {msg['role'].upper()}\n{msg['content']}\n\n")

    resp = client.chat.completions.create(
        model=model, messages=messages# temperature=0.0, max_tokens=4000
    )
    return resp.choices[0].message.content


def split_response(content):
    splitter = "## OWL"
    if splitter in content:
        left, right = content.split(splitter, 1)
        # return left.strip(), right.strip()
        code_block_match = re.search(
            r"```(?:ttl|turtle)\n([\s\S]+?)\n```", right.strip(), re.IGNORECASE
        )
        if code_block_match:
            # Assume JSON is before code block
            # parts = re.split(r"```(?:json)?\n[\s\S]+?\n```", content)
            # # fallback: take first JSON-like and the code block
            # json_part = parts[0].strip()
            ttl_part = code_block_match.group(1).strip()
            return ttl_part
    return ""


def save_outputs(json_text, ttl_text, dest="dest", out_prefix="output"):
    jpath = os.path.join(dest, f"{out_prefix}.md")
    tpath = os.path.join(dest, f"{out_prefix}.ttl")
    with open(jpath, "w", encoding="utf-8") as f:
        f.write(json_text)
    with open(tpath, "w", encoding="utf-8") as f:
        f.write(ttl_text)
    return jpath, tpath


def validate_output(tpath: str, dest: str) -> str | None:
    print("Validating Turtle file:", tpath)
    if not validate_ttl(tpath):
        print("Generated Turtle file is invalid.")
        return "Failed to load Turtle file."
    print("Turtle syntax is valid.")
    success, cq_validation = validate_with_competency_questions_file(
        tpath, "cqs_example.json"
    )
    if not success:
        print("Some competency questions failed.")
        error_msg = log_report(cq_validation, dest)
        print(error_msg)
        return error_msg
    print("All competency questions passed.")
    return None
    # if not validate_with_competency_questions_file(tpath, "cqs_example.json"):
    #     print("Some competency questions failed.")
    #     exit(-1)
    # print("All validations passed.")


def llm_fix_and_validate(content, dest, error_msg, step=0, max_steps=3):
    print(f"LLM fix step {step}...")
    # system_prompt = load_system_prompt("system_fixing.md")
    system_prompt = """
Your task is to fix the provided OWL Turtle code based on the following error message from a validator:"""
    user_prompt = f"""
Here is the original Turtle code:
{content}
The Turtle code has the following issues:
{error_msg}
Please provide a corrected version of the OWL Turtle code that resolves these issues.
"""
    try:
        fixed_content = call_llm(system_prompt, user_prompt, dest, model=LLM_MODEL)
    except Exception as e:
        print("LLM call failed during fixing:", str(e))
        sys.exit(1)

    print("LLM fix response received.")

    ttl_part = f"{prefix_part}\n\n# Generated code\n\n{split_response(fixed_content)}"

    jpath, tpath = save_outputs(fixed_content, ttl_part, dest=dest, out_prefix="fixed_output")
    print("Saved fixed output to:", jpath)
    if not ttl_part:
        print("No OWL Turtle detected in fixed response; check the raw output below:\n")
    else:
        print("Saved fixed OWL Turtle to:", tpath)
    error_msg = validate_output(tpath, dest)
    if error_msg and step < max_steps:
        step += 1
        print("Recursively calling LLM to fix issues...")
        llm_fix_and_validate(fixed_content, dest, error_msg, step, max_steps)


def llm_setup_and_validate(args):
    if not args.file and not args.text:
        print("Provide --file or --text with the legal text to convert.")
        sys.exit(2)

    text = ""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text

    system_prompt = load_system_prompt(args.system)
    try:
        content = call_llm(system_prompt, text, dest=args.dest, model=args.model)
    except Exception as e:
        print("LLM call failed:", str(e))
        sys.exit(1)

    print("LLM response received: ", content)

    ttl_part = f"{prefix_part}\n\n# Generated code\n\n{split_response(content)}"

    jpath, tpath = save_outputs(content, ttl_part, dest=args.dest, out_prefix=args.name)
    print("Saved output to:", jpath)
    if not ttl_part:
        print("No OWL Turtle detected in response; check the raw output below:\n")
    else:
        print("Saved OWL Turtle to:", tpath)
    error_msg = validate_output(tpath, args.dest)
    if error_msg and args.recursive:
        print("Recursively calling LLM to fix issues...")
        llm_fix_and_validate(ttl_part, args.dest, error_msg)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", "-f", help="Path to a text file containing legal text")
    p.add_argument("--text", "-t", help="Legal text directly as an argument")
    p.add_argument(
        "--system",
        "-s",
        default="system_step-by-step.md",
        help="System prompt file path",
    )
    p.add_argument(
        "--model", "-m", help="LLM model to use (overrides LLM_MODEL env var)"
    )
    p.add_argument(
        "--name", "-n", default="output", help="Prefix for output files (json, ttl)"
    )
    p.add_argument(
        "--validate-only", action="store_true", help="Only validate existing TTL file"
    )
    p.add_argument("--dest", action="store", help="Destination folder")
    p.add_argument(
        "--cq-file",
        help="Path to competency questions JSON file",
        default="cqs_example.json",
    )
    p.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively validate until all CQs pass",
    )
    args = p.parse_args()

    if not args.dest:
        args.dest = os.path.join("dest", f"dest_{LLM_MODEL}_{args.name}")
    if os.path.exists(args.dest) and not args.validate_only:
        # If the destination exists, create a new unique folder
        base_dest = args.dest
        i = 1
        while os.path.exists(args.dest):
            args.dest = f"{base_dest}_{i}"
            i += 1
        
    os.makedirs(args.dest, exist_ok=True)

    if not args.validate_only:
        print("Calling LLM...")
        llm_setup_and_validate(args)

    tpath = os.path.join(args.dest, f"{args.name}.ttl")
    print("Validating existing TTL file:", tpath)

    validate_output(tpath, args.dest)


if __name__ == "__main__":
    main()
