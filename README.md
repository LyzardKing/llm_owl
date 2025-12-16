# Owl-LLM

Owl-LLM is a small toolkit to convert legal or regulatory text into OWL (Turtle) using a local LLM endpoint, validate the generated ontology with competency questions, and run additional consistency and pitfall checks.

## Features
- **Convert text to OWL**: `generate_ontology.py` calls an LLM with a step-by-step system prompt and extracts an OWL Turtle fragment.
- **Validate OWL**: `validator.py` validates Turtle syntax, runs an OWL consistency check and evaluates competency questions (CQ) expressed as SPARQL.

## Requirements
- **Python**: >= 3.13
- **Libraries**: see `pyproject.toml` (python-dotenv, openai, rdflib, pyyaml, lxml, owlready2, requests)

## Configuration
- Copy or create a `.env` file with your LLM endpoint configuration (if using an OpenAI compatible API):

```text
LLM_BASE_URL=openai_compatible_endpoint_url
LLM_MODEL=model_name
LLM_API_KEY=your_api_key_if_needed
```

- The system prompt used by the generator is `system_step-by-step.md` and can be edited to tune extraction and OWL generation.

## Quick Start

- Convert a text file to OWL (writes outputs to `dest/output.*` by default):

```bash
python generate_ontology.py --file example_rule.txt --name my_output --dest dest
```

- Provide text directly:

```bash
python generate_ontology.py --text "You MUST stop behind the line at a junction..." --name quick --dest dest
```

- Validate an existing Turtle file with competency questions:

```bash
python validator.py --ttl-file dest/output.ttl --cqs-file cqs_example.json --log-file validation_steps.jsonl
```
