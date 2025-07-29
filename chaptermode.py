#!/usr/bin/env python3
"""
DESH chaptermode.py (v2.1 - Tolerance-Based Grouping)
Split long MKV files into episodes by detecting chapters whose
duration repeats ≥2 times, using a tolerance for grouping.
The user first specifies the expected number of episodes.
If any repeating-length group has exactly that count, it is used automatically.
Enhancement (v2.0): Better handling of "N episodes = N-1 splits" logic.
Fix (v2.0): Improved auto-detection for N episodes = N splits (Outro-style).
Enhancement (v2.1): Use tolerance-based grouping to find more accurate repeating patterns.
"""
import os
import subprocess
import argparse
import sys
from collections import Counter, defaultdict
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
# NEW length-mode helpers (v2.1 - Tolerance-Based)
# ------------------------------------------------------------------
def build_repeating_groups(chapters: list, tolerance: float = 2.0) -> dict:
    """
    Groups chapters by duration using a tolerance.
    This is more robust than simple rounding for finding repeating patterns.
    """
    usable = [c for c in chapters if c['duration'] is not None]
    if not usable:
        return {}

    groups = defaultdict(list)
    used = set()

    # Sort chapters by duration to group similar ones
    sorted_chapters = sorted(usable, key=lambda x: x['duration'])

    for i, ch1 in enumerate(sorted_chapters):
        if ch1['number'] in used:
            continue

        # Use rounded duration as a representative key for the group
        group_key = round(ch1['duration'])
        current_group = [ch1['number']]
        used.add(ch1['number'])

        # Check subsequent chapters for potential inclusion in this group
        # based on the provided tolerance
        for j in range(i + 1, len(sorted_chapters)):
            ch2 = sorted_chapters[j]
            if ch2['number'] in used:
                continue

            if abs(ch2['duration'] - ch1['duration']) <= tolerance:
                current_group.append(ch2['number'])
                used.add(ch2['number'])

        # Only keep groups with 2 or more chapters (repeating pattern)
        if len(current_group) >= 2:
            groups[group_key] = sorted(current_group)

    # Convert defaultdict to regular dict for clarity
    return dict(groups)

def pick_group_by_episode_count(groups: dict, expected_episodes: int, total_chapters: int) -> (list, str):
    """
    Picks the best group based on expected episode count.
    Handles N episodes = N-1 splits logic.
    Returns (chosen_chapters_list, reasoning_string).
    """
    if not groups:
        return [], "No repeating groups found."
    # --- v2.0 Enhancement Logic ---
    # 1. Calculate potential episode counts for each group
    group_info = {}
    for dur, chaps in groups.items():
        num_splits = len(chaps)
        # Scenario A: Splits mark the END of an episode (e.g., Outros)
        episodes_if_outro_style = num_splits
        # Scenario B: Splits mark the START of an episode (e.g., Intros)
        episodes_if_intro_style = num_splits + 1
        group_info[dur] = {
            'chapters': chaps,
            'splits': num_splits,
            'episodes_outro': episodes_if_outro_style,
            'episodes_intro': episodes_if_intro_style
        }
    # 2. Find the best matching group
    best_candidates = []
    for dur, info in group_info.items():
        # Prioritize exact match for expected_episodes
        # Prefer Outro-style match if both styles match, as it's common for DVD structures
        if info['episodes_outro'] == expected_episodes:
             # Outro style: Split at end, next chapter is start.
             # Important: Do not propose a split after the last chapter.
            episode_starts = [ch + 1 for ch in info['chapters'] if ch + 1 <= total_chapters]
            best_candidates.append((episode_starts, f"Outro-style match (N splits = N episodes) for duration {dur}s"))
        elif info['episodes_intro'] == expected_episodes:
            # Intro style: Split at start
            episode_starts = info['chapters']
            best_candidates.append((episode_starts, f"Intro-style match (N splits = N-1 episodes) for duration {dur}s"))
    # 3. Auto-select if there's one clear winner, prioritizing Outro-style
    if len(best_candidates) == 1:
        return best_candidates[0]
    # 4. If multiple or no exact matches, fall back to original logic for user prompt
    # Filter groups whose length matches the expected number of *splits* (N-1)
    # We assume user thinks in terms of episodes, so N splits implies N+1 episodes.
    # Let's prompt based on potential episode counts.
    print(f"\n📊 Repeating chapter-length groups (considering {expected_episodes} episodes):")
    print("-" * 70)
    group_list = []
    idx = 1
    # Prioritize groups that could plausibly match
    plausible_groups = {k: v for k, v in group_info.items() if v['episodes_outro'] == expected_episodes or v['episodes_intro'] == expected_episodes or abs(v['episodes_outro'] - expected_episodes) <= 1 or abs(v['episodes_intro'] - expected_episodes) <= 1}
    if not plausible_groups:
        plausible_groups = group_info # Fallback to all
    # Sort by how close they are to the expected count, preferring Outro-style closeness
    sorted_plausible = sorted(plausible_groups.items(), key=lambda item: (
        not (item[1]['episodes_outro'] == expected_episodes), # Exact Outro match first
        not (item[1]['episodes_intro'] == expected_episodes), # Exact Intro match next
        min(abs(item[1]['episodes_outro'] - expected_episodes), abs(item[1]['episodes_intro'] - expected_episodes)), # Then by min diff
        abs(item[1]['episodes_outro'] - expected_episodes) - abs(item[1]['episodes_intro'] - expected_episodes) # Prefer Outro if ties
    ))
    for dur, info in sorted_plausible:
        matches_outro = " (👉 Outro-style)" if info['episodes_outro'] == expected_episodes else ""
        matches_intro = " (👉 Intro-style)" if info['episodes_intro'] == expected_episodes else ""
        mismatch_info = ""
        if not matches_outro and not matches_intro:
            # Indicate which count it's closer to
            if abs(info['episodes_outro'] - expected_episodes) < abs(info['episodes_intro'] - expected_episodes):
                mismatch_info = f" (Closest: Outro-style {info['episodes_outro']} eps)"
            else:
                mismatch_info = f" (Closest: Intro-style {info['episodes_intro']} eps)"
        print(f"{idx:2d}. {info['splits']:2d} chapters @ {dur:.1f}s  –  chapters {', '.join(map(str, info['chapters']))} [{info['episodes_outro']} or {info['episodes_intro']} episodes]{matches_outro}{matches_intro}{mismatch_info}")
        group_list.append((dur, info))
        idx += 1
    print("-" * 70)
    while True:
        try:
            choice = input(f"Select ending-marker group (1-{len(group_list)}) or q to quit: ").strip().lower()
            if choice == 'q':
                return [], "User quit selection."
            idx = int(choice) - 1
            if 0 <= idx < len(group_list):
                chosen_dur, chosen_info = group_list[idx]
                # Default to Outro-style interpretation if ambiguous, or ask?
                # For simplicity in prompt, let's stick to "next chapter is start"
                episode_starts = [ch + 1 for ch in chosen_info['chapters'] if ch + 1 <= total_chapters]
                reasoning = f"User selected group with duration {chosen_dur}s (chapters {', '.join(map(str, chosen_info['chapters']))}). Assuming outro-style (end of ep -> start of next)."
                return episode_starts, reasoning
        except ValueError:
            pass
        print("❌ Invalid choice.")

def analyze_chapter_lengths(chapters: list, expected_episodes: int) -> (list, str):
    """Analyzes chapters and returns episode starts based on length."""
    # Use tolerance-based grouping (v2.1 enhancement)
    groups = build_repeating_groups(chapters, tolerance=2.0)
    # Pass total chapters for boundary checks
    episode_starts, reason = pick_group_by_episode_count(groups, expected_episodes, len(chapters))
    # --- Post-processing to refine results (from v2.0 - Corrected) ---
    # Do NOT split if the last marker would leave only one final chapter
    # This also handles the case where the last proposed split is the last chapter itself.
    max_ch = max(c['number'] for c in chapters) if chapters else 0
    # Convert to set to remove potential duplicates, then back to list for filtering
    unique_starts = list(set(episode_starts))
    # Filter out any start point that is beyond the last chapter
    filtered_starts = [c for c in unique_starts if c <= max_ch] 
    # Crucially, remove the split point that is the last chapter number itself
    final_filtered_starts = [c for c in filtered_starts if c != max_ch] 
    final_starts = sorted(final_filtered_starts)
    # Handle missing first episode if the first suggested start is > 2
    # This is a simple heuristic, can be refined.
    if final_starts and final_starts[0] > 2:
         # Check if adding chapter 1 makes sense (e.g., closer to expected count)
         # A simple check: if we have N-1 starts, adding the first makes it N.
         if len(final_starts) == expected_episodes - 1:
              final_starts = [1] + final_starts
              reason += " Inferred missing first episode start at chapter 1."
    # Ensure we don't return a list longer than expected_episodes due to logic errors
    if len(final_starts) > expected_episodes:
        final_starts = final_starts[:expected_episodes]
        reason += " (Note: Truncated to match expected episode count.)"
        
    return final_starts, reason

def display_results(episode_starts: list, reason: str=""):
    """Displays the results."""
    if not episode_starts:
        print("\n❌ No suitable repeating chapter-length patterns found for the given episode count.\n")
        if reason:
            print(f"Reason: {reason}")
        return
    print("\n🎯 Episode start chapters:")
    print("=" * 60)
    if reason:
        print(f"Logic: {reason}")
    print("Chapters:", ", ".join(map(str, episode_starts)))
    print()

# ------------------------------------------------------------------
# Splitting prompt
# ------------------------------------------------------------------
def prompt_for_splitting(mkv_path: str, episode_starts: list):
    """Prompts the user to run the mkvmerge command."""
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
    """Finds MKV files in the current directory."""
    return sorted([f for f in os.listdir('.') if f.lower().endswith('.mkv')])

def select_mkv_file() -> str:
    """Prompts the user to select an MKV file."""
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
    """Main function."""
    parser = argparse.ArgumentParser(description="Split MKV by chapter-length pattern (v2.1 - Tolerance-Based Grouping)")
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
    # --- Get expected episodes ---
    while True:
        try:
            expected_input = input("\nHow many episodes do you expect? (number / q to quit): ").strip()
            if expected_input.lower() == 'q':
                print("👋 Quitting.")
                sys.exit(0)
            expected_episodes = int(expected_input)
            if expected_episodes > 0:
                break
            else:
                print("❌ Please enter a positive integer.")
        except ValueError:
            print("❌ Please enter a valid number.")
    episode_starts, reason = analyze_chapter_lengths(chapters, expected_episodes)
    display_results(episode_starts, reason)
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
