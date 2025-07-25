#!/usr/bin/env python3
"""
chaptermode.py
Split long MKV files into episodes by detecting chapters whose
duration repeats ≥2 times and using the *next* chapter as an
episode start.  The user first specifies the expected number of
episodes; if any repeating-length group has exactly that count,
it is used automatically (or the user is prompted to pick among
ties).
"""

import os
import subprocess
import argparse
import sys
from collections import Counter
import xml.etree.ElementTree as ET

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"

# ------------------------------------------------------------------
# Chapter extraction
# ------------------------------------------------------------------
def extract_chapters(mkv_path: str, xml_path: str = "chapters.xml") -> list:
    with open(xml_path, "w", encoding="utf-8") as f:
        subprocess.run(["mkvextract", "chapters", mkv_path], stdout=f, stderr=subprocess.DEVNULL)

    tree = ET.parse(xml_path)
    root = tree.getroot()
    chapters = []

    chapter_num = 1
    for atom in root.findall(".//ChapterAtom"):
        t = atom.find("ChapterTimeStart").text
        h, m, s = map(float, t.replace(",", ".").split(":"))
        sec = h * 3600 + m * 60 + s
        chapters.append({
            'number': chapter_num,
            'label': t,
            'start_time': sec,
            'duration': None
        })
        chapter_num += 1

    for i, ch in enumerate(chapters):
        if i < len(chapters) - 1:
            ch['duration'] = chapters[i + 1]['start_time'] - ch['start_time']
        else:
            ch['duration'] = None

    os.remove(xml_path)
    return chapters

# ------------------------------------------------------------------
# NEW length-mode helpers
# ------------------------------------------------------------------
def build_repeating_groups(chapters: list) -> dict:
    usable = [c for c in chapters if c['duration'] is not None]
    rounded = [round(c['duration'], 1) for c in usable]
    counts = Counter(rounded)
    repeating = {dur for dur, cnt in counts.items() if cnt >= 2}

    groups = {}
    for ch in usable:
        key = round(ch['duration'], 1)
        if key in repeating:
            groups.setdefault(key, []).append(ch['number'])
    return groups

def pick_group_by_episode_count(groups: dict) -> list:
    if not groups:
        return []

    while True:
        try:
            expected = input("\nHow many episodes do you expect? (number / q to quit): ").strip()
            if expected.lower() == 'q':
                return []
            expected = int(expected)
            if expected <= 0:
                raise ValueError
            break
        except ValueError:
            print("❌ Please enter a positive integer.")

    # Filter groups whose length == expected
    candidates = {dur: chaps for dur, chaps in groups.items() if len(chaps) == expected}
    if len(candidates) == 1:
        return list(candidates.values())[0]

    # 0 or >1 matches → show relevant groups
    pool = candidates if candidates else groups
    if not pool:
        return []

    print("\n📊 Repeating chapter-length groups:")
    print("-" * 60)
    group_list = sorted(pool.items(), key=lambda kv: (len(kv[1]), kv[0]), reverse=True)
    for idx, (dur, chaps) in enumerate(group_list, 1):
        matches = " (👉 matches your count)" if dur in candidates else ""
        print(f"{idx:2d}. {len(chaps):2d} chapters @ {dur:.1f}s  –  chapters {', '.join(map(str, chaps))}{matches}")
    print("-" * 60)

    while True:
        try:
            choice = input(f"Select ending-marker group (1-{len(group_list)}) or q to quit: ").strip().lower()
            if choice == 'q':
                return []
            idx = int(choice) - 1
            if 0 <= idx < len(group_list):
                return group_list[idx][1]
        except ValueError:
            pass
        print("❌ Invalid choice.")

def analyze_chapter_lengths(chapters: list) -> list:
    groups = build_repeating_groups(chapters)
    chosen_group = pick_group_by_episode_count(groups)

    max_ch = max(c['number'] for c in chapters)
    episode_candidates = {ch + 1 for ch in chosen_group if ch + 1 <= max_ch}

    # Do NOT split if the last marker would leave only one final chapter
    episode_candidates = {c for c in episode_candidates
                          if c != max_ch or max_ch != len(chapters)}

    return sorted(episode_candidates)

def display_results(episode_starts: list):
    if not episode_starts:
        print("\n❌ No repeating chapter-length patterns found.\n")
        return
    print("\n🎯 Episode start chapters (after selected ending markers):")
    print("=" * 60)
    print("Chapters:", ", ".join(map(str, episode_starts)))
    print()

# ------------------------------------------------------------------
# Splitting prompt
# ------------------------------------------------------------------
def prompt_for_splitting(mkv_path: str, episode_starts: list):
    if not episode_starts:
        return
    print("\n" + "=" * 60)
    print("🎬 MKV SPLITTING OPTIONS")
    print("=" * 60)
    chapter_list = ','.join(map(str, episode_starts))
    output_name = mkv_path.rsplit('.', 1)[0] + '_episodes.mkv'
    command = f'mkvmerge -o "{output_name}" --split chapters:{chapter_list} "{mkv_path}"'
    print(f"\nGenerated command:\n  {command}\n")
    while True:
        print("Options:")
        print("  1. Run the command now")
        print("  2. Copy command to clipboard (display only)")
        print("  3. Skip")
        choice = input("Enter choice (1-3): ").strip()
        if choice == '1':
            print("\n🚀 Running mkvmerge...")
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ Success! Output: {output_name}")
            else:
                print("❌ Error:", result.stderr)
                print("💡 Run manually:", command)
            break
        elif choice == '2':
            print("\n📋 Command to copy:\n   ", command)
            break
        elif choice == '3':
            print("⏭️  Skipping")
            break
        else:
            print("❌ Invalid choice.")

# ------------------------------------------------------------------
# File discovery
# ------------------------------------------------------------------
def find_mkv_files() -> list:
    return sorted([f for f in os.listdir('.') if f.lower().endswith('.mkv')])

def select_mkv_file() -> str:
    mkv_files = find_mkv_files()
    if not mkv_files:
        print("❌ No MKV files in current directory")
        sys.exit(1)
    if len(mkv_files) == 1:
        f = mkv_files[0]
        print(f"📁 Found: {f}")
        return f if input("Process it? (y/n): ").strip().lower() in ('y', 'yes') else sys.exit(1)
    print(f"📁 Found {len(mkv_files)} MKV files:")
    for i, f in enumerate(mkv_files, 1):
        try:
            sz = os.path.getsize(f)
            sz = f"{sz/1024/1024/1024:.1f} GB" if sz > 1024**3 else f"{sz/1024/1024:.0f} MB"
        except:
            sz = "unknown size"
        print(f"{i:2d}. {f} ({sz})")
    while True:
        choice = input(f"Select file (1-{len(mkv_files)}) or 'q' to quit: ").strip()
        if choice.lower() == 'q':
            sys.exit(1)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(mkv_files):
                return mkv_files[idx]
        except ValueError:
            pass
        print("❌ Invalid choice.")

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Split MKV by chapter-length pattern")
    parser.add_argument("--mkv", help="Path to MKV file (optional – auto-detect)")
    parser.add_argument("--auto-split", action="store_true",
                        help="Skip prompts and generate split commands")
    args = parser.parse_args()

    if args.mkv:
        mkv_path = args.mkv
        if not os.path.exists(mkv_path):
            print(f"❌ File not found: {mkv_path}")
            sys.exit(1)
    else:
        mkv_path = select_mkv_file()

    print(f"\n🎬 Processing: {mkv_path}")
    print("=" * 60)

    chapters = extract_chapters(mkv_path)
    print(f"Found {len(chapters)} chapters")

    episode_starts = analyze_chapter_lengths(chapters)
    display_results(episode_starts)

    if args.auto_split or (episode_starts and not args.auto_split):
        if not args.auto_split:
            ans = input("\n🎬 Generate MKV split commands? (y/n): ").strip().lower()
            if ans not in ('y', 'yes'):
                print("\n👋 All done!")
                return
        prompt_for_splitting(mkv_path, episode_starts)

    print("\n👋 All done!")

if __name__ == "__main__":
    main()