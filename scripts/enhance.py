#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "wn>=0.9.0",
#     "wn-edit @ git+https://github.com/bond-lab/wn_edit.git",
# ]
# ///
"""
Enhance WordNet with ChainNet metaphor and metonymy relations.

This script reads the ChainNet JSON data and adds metaphor/metonymy sense
relations to a WordNet lexicon using wn_edit.

Usage:
    uv run scripts/enhance.py [--wordnet LEXICON] [--chainnet PATH] [--output PATH]

Examples:
    # Use defaults (omw-en:1.4, data/chainnet.json)
    uv run scripts/enhance.py -v
    
    # Specify a different wordnet
    uv run scripts/enhance.py --wordnet oewn:2024 -v
    
    # Specify custom chainnet file and output
    uv run scripts/enhance.py --chainnet data/chainnet.json --output enhanced-wordnet.xml
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import wn
from wn.compat import sensekey

# Default paths
DEFAULT_WORDNET = 'omw-en:1.4'
DEFAULT_WN_DATA = 'wn_data'
DEFAULT_CHAINNET = Path(__file__).parent.parent / "data" / "chainnet_simple"

TROPES = ['metaphor', 'metonymy']
REVERSES = {'metaphor': 'has_metaphor',
            'metonym': 'has_metonym'}


def load_chainnet_tropes(path: Path) -> dict[str, Any]:
    """Load ChainNet JSON data."""
    data = {}
    for trope in TROPES:
        trope_path = path / f"chainnet_{trope}.json"
        with open(trope_path, "r", encoding="utf-8") as f:
            data[trope] = json.load(f)
    return data


def extract_relations(chainnet_data: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """
    Extract metaphor and metonymy relations from ChainNet data.
    
    Returns:
        List of (relation_type, word, source_sense_key, target_sense_key) tuples
        relation_type is either 'metaphor' or 'metonym'
    """
    relations = []
    
    for trope in chainnet_data:
        content = chainnet_data.get(trope, [])
        for e in content['content']:
            w = e['wordform']
            fr_s = e['from_sense']
            to_s = e['to_sense']
            rel = 'metonym' if trope=='metonymy' else 'metaphor'
            relations.append((rel,  w, fr_s, to_s))
    
    return relations


def enhance_wordnet(
    lexicon_spec: str,
    wn_data_dir: Path,
    chainnet_path: Path,
    output_path: Path,
    verbose: bool = False
) -> None:
    """
    Enhance a WordNet with ChainNet metaphor/metonymy relations.
    
    Args:
        lexicon_spec: WordNet lexicon specifier (e.g., 'omw-en:1.4', 'oewn:2024')
        wn_data_dir: Path to WN data directory
        chainnet_path: Path to ChainNet JSON file
        output_path: Path to write enhanced WordNet XML
        verbose: Print progress information
    """
    wn.config.data_directory = wn_data_dir

    try:
        from wn_edit import WordnetEditor
    except ImportError:
        print("Error: 'wn_edit' module not installed.", file=sys.stderr)
        print("Run: pip install git+https://github.com/bond-lab/wn_edit.git", file=sys.stderr)
        sys.exit(1)
  
    # Load ChainNet data
    if verbose:
        print(f"Loading ChainNet from {chainnet_path}...")
    chainnet_data = load_chainnet_tropes(chainnet_path)

    # Extract relations
    if verbose:
        print("Extracting metaphor and metonymy relations...")
    relations = extract_relations(chainnet_data)
    if verbose:
        print(f"Found {len(relations)} relations")
        metaphor_count = sum(1 for rel in relations if rel[0] == 'metaphor')
        metonym_count = sum(1 for rel in relations if rel[0] == 'metonym')
        print(f"  - {metaphor_count} metaphor relations")
        print(f"  - {metonym_count} metonym relations")
    
    # Download/load the wordnet if needed
    if verbose:
        print(f"Loading WordNet '{lexicon_spec}'...")
    
    # Try to download if not present
    try:
        # wn.Wordnet() takes the lexicon spec as a single string
        wordnet = wn.Wordnet(lexicon=lexicon_spec)
    except wn.Error:
        if verbose:
            print(f"Downloading {lexicon_spec}...")
        wn.download(lexicon_spec)
        wordnet = wn.Wordnet(lexicon=lexicon_spec)

    if verbose:
        print(f"Loading sense mapping from {lexicon_spec}...")
    try:
        get_sense = sensekey.sense_getter(lexicon_spec)
    except Exception as e:
        print(f"Error: Cannot create sense mapping for {lexicon_spec}: {e}", file=sys.stderr)
        sys.exit(1)

    # Load into editor
    if verbose:
        print("Loading lexicon into editor...")
    old_ver=wordnet.lexicons()[0].version
    old_label=wordnet.lexicons()[0].label
    editor = WordnetEditor(lexicon_spec,
                           version =  f"{old_ver}.cn",
                           label =  f"{old_label} with tropes from ChainNet",
                           lmf_version = '1.4',
    )


    # Add relations
    added_count = 0
    reverse_count = 0
    skipped_count = 0
    skipped_reverse = 0
    
    if verbose:
        print("Adding relations...")

    for rel_type, _, source_key, target_key in relations:
        # Resolve sense keys to wn sense IDs
        source_id = get_sense(source_key)
        if source_id:
            source_id = source_id.id
        target_id = get_sense(target_key)
        if target_id:
            target_id =  target_id.id 

        if source_id is None or target_id is None:
            skipped_count += 1
            if verbose and skipped_count <= 10:
                print(f"  Skipping: {source_key} -> {target_key} (sense not found)")
            continue
        
        try:
            editor.add_sense_relation(source_id, target_id,
                                      rel_type,
                                      validate=False)
            added_count += 1
        except Exception as e:
            skipped_count += 1
            if verbose:
                print(f"  Error adding {source_key} -{rel_type}-> {target_key}: {e}")
        ## reverse
        try:
            editor.add_sense_relation(target_id, source_id,
                                      REVERSES[rel_type],
                                      validate=False)
            reverse_count += 1
        except Exception as e:
            skipped_reverse += 1
            if verbose:
                print(f"  Error adding {target_key} -{REVERSES[rel_type]}-> {source_key}: {e}")



                
    if verbose:
        print(f"Added {added_count} relations, skipped {skipped_count}")
        print(f"Added {reverse_count} reverse relations, skipped {skipped_reverse}")
        
    # Export
    
    if verbose:
        print(f"Exporting to {output_path}...")
    editor.export(output_path)
    
    print(f"Enhanced WordNet written to {output_path}")




if __name__ == "__main__":
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enhance WordNet with ChainNet metaphor and metonymy relations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Use defaults (omw-en:1.4)
    uv run scripts/enhance.py -v
    
    # Use OEWN 2024
    uv run scripts/enhance.py --wordnet oewn:2024 -v
    
    # Specify all options
    uv run scripts/enhance.py --wordnet omw-en:1.4 --chainnet data/chainnet.json --output enhanced.xml
"""
    )
    
    parser.add_argument(
        "--wordnet", "-w",
        default=DEFAULT_WORDNET,
        help=f"WordNet lexicon specifier (default:  {DEFAULT_WORDNET})"
    )
    parser.add_argument(
        "--wn_data", "-d",
        default=DEFAULT_WN_DATA,
        help=f"directory to store the Wordnet data (default:  {DEFAULT_WN_DATA})"
    )
    
    parser.add_argument(
        "--chainnet", "-c",
        type=Path,
        default=DEFAULT_CHAINNET,
        help=f"Path to ChainNet JSON file (default: {DEFAULT_CHAINNET})"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output path for enhanced WordNet XML (default: <wordnet>.cn.xml)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress information"
    )
    
    args = parser.parse_args()
    
    # Set default output path if not specified
    if args.output is None:
        output_path = Path(f"{args.wordnet}.cn.xml")
    else:
        output_path = args.output
    
    # Check chainnet file exists
    if not args.chainnet.exists():
        print(f"Error: ChainNet file not found: {args.chainnet}", file=sys.stderr)
        print("Download from: https://raw.githubusercontent.com/rowanhm/ChainNet/main/data/chainnet.json")
        sys.exit(1)
    
    enhance_wordnet(
        lexicon_spec=args.wordnet,
        wn_data_dir=args.wn_data,
        chainnet_path=args.chainnet,
        output_path=output_path,
        verbose=args.verbose
    )
