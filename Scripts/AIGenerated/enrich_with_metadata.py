#!/usr/bin/env python3
"""
Enrich YAML slokas with semantic metadata using Claude AI
Extracts headwords, pratipadikas, and genders from Sanskrit dictionary slokas
"""

import sys
import argparse
import json
from pathlib import Path
import yaml
from anthropic import AnthropicVertex


def parse_sloka_with_claude(sloka_text, client):
    """
    Use Claude to parse a kosha sloka and extract semantic structure

    Args:
        sloka_text: The sloka to parse
        client: Anthropic Vertex AI client

    Returns:
        Dictionary with parsed entries
    """
    prompt = f"""You are a Sanskrit kosha (synonym dictionary) expert. Parse this sloka from a classical Sanskrit kosha and extract dictionary entries.

Sloka: {sloka_text}

Instructions:
1. Identify groups of synonyms (words with the same meaning)
2. For each group, determine:
   - The headword (main word for that concept)
   - All words in the group with their prātipadika (stem/root form)
   - The gender: m (masculine/पुं), f (feminine/स्त्री), n (neuter/नपुं)
3. Note any qualifiers or contextual information

Rules:
- Words ending in ः are typically masculine (m)
- Words ending in आ/ई are typically feminine (f)
- Words ending in म्‌ are typically neuter (n)
- Look for sandhi and vibhakti to identify word boundaries
- Group words that are synonyms (have the same meaning)
- Use ONLY these gender codes: m, f, n

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "entries": [
    {{
      "head": "prātipadika_of_headword",
      "gender": "m/f/n",
      "syns": [
        {{"prati": "word1", "gender": "m/f/n"}},
        {{"prati": "word2", "gender": "m/f/n"}}
      ]
    }}
  ]
}}

Example for: नागा बहुफणाः सर्पास्तेषां भोगवती पुरी॥
{{
  "entries": [
    {{
      "head": "सर्प",
      "gender": "m",
      "syns": [
        {{"prati": "नाग", "gender": "m"}},
        {{"prati": "बहुफण", "gender": "m"}},
        {{"prati": "सर्प", "gender": "m"}}
      ]
    }},
    {{
      "head": "भोगवती",
      "gender": "f",
      "qual": "तेषां",
      "syns": [
        {{"prati": "पुरी", "gender": "f"}}
      ]
    }}
  ]
}}

Now parse the given sloka and return JSON:"""

    try:
        message = client.messages.create(
            model="claude-3-5-haiku@20241022",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]

        response_text = response_text.strip()

        # Parse JSON
        parsed = json.loads(response_text)
        return parsed

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from Claude: {e}")
        print(f"Response was: {response_text[:200]}...")
        return {"entries": []}
    except Exception as e:
        print(f"Error parsing sloka: {e}")
        return {"entries": []}


def enrich_yaml(input_yaml, output_yaml, project_id, region):
    """
    Read YAML with slokas and enrich with semantic metadata
    """
    print(f"Reading YAML from: {input_yaml}")

    with open(input_yaml, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    print(f"Found {len(data)} slokas to enrich")
    print(f"Initializing Vertex AI client (region: {region})...")

    try:
        client = AnthropicVertex(region=region, project_id=project_id)
    except Exception as e:
        print(f"\nError: Failed to initialize Vertex AI client: {e}")
        print("\nMake sure you have:")
        print("1. Authenticated: gcloud auth application-default login")
        print("2. Enabled Claude models in Vertex AI Model Garden")
        sys.exit(1)

    # Enrich each sloka
    enriched_data = {}
    for i, (sloka, metadata) in enumerate(data.items(), 1):
        print(f"Parsing sloka {i}/{len(data)}...")

        parsed = parse_sloka_with_claude(sloka, client)

        # Add verify: false right after head for proofreading tracking
        for entry in parsed.get('entries', []):
            if 'head' in entry:
                # Create ordered dict with verify right after head
                new_entry = {'head': entry['head'], 'verify': False}
                # Add remaining fields
                for key, value in entry.items():
                    if key != 'head':
                        new_entry[key] = value
                # Replace entry with ordered version
                entry.clear()
                entry.update(new_entry)

        # Store enriched data
        enriched_data[sloka] = parsed

    print(f"\nCompleted parsing of {len(data)} slokas")

    # Ensure output directory exists
    output_path = Path(output_yaml)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write enriched YAML
    print(f"\nWriting enriched YAML to: {output_yaml}")
    with open(output_yaml, 'w', encoding='utf-8') as f:
        yaml.dump(enriched_data, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, indent=2, width=float('inf'))

    print(f"\n✓ Successfully enriched and saved to: {output_yaml}")


def main():
    parser = argparse.ArgumentParser(
        description='Enrich Sanskrit kosha YAML with semantic metadata using Claude AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enrich a corrected YAML file with metadata
  python enrich_with_metadata.py \\
    Output/Vaijayanti_Kosha/4_PaatalaKhanda/1_SarpaSwarupaAdyayah.yaml \\
    -o Output/Vaijayanti_Kosha/4_PaatalaKhanda/1_SarpaSwarupaAdyayah_enriched.yaml \\
    --project-id anetorg-sinaraya-kartik

This will parse each sloka and extract:
- Headwords (head)
- Synonyms with pratipadika (syns.prati)
- Gender for each word (gen)
        """
    )

    parser.add_argument('input_yaml', help='Input YAML file with corrected slokas')
    parser.add_argument('-o', '--output', required=True,
                        help='Output enriched YAML file path')
    parser.add_argument('--project-id', required=True,
                        help='Google Cloud project ID')
    parser.add_argument('--region', default='us-east5',
                        help='Vertex AI region (default: us-east5)')

    args = parser.parse_args()

    # Check if input file exists
    if not Path(args.input_yaml).exists():
        print(f"Error: Input file not found: {args.input_yaml}")
        sys.exit(1)

    enrich_yaml(args.input_yaml, args.output, args.project_id, args.region)


if __name__ == '__main__':
    main()
