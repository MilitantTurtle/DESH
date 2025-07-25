import os
import subprocess
import numpy as np
import scipy.spatial.distance
import xml.etree.ElementTree as ET
import librosa
import argparse
import sys

def progress_bar(current, total, bar_length=50):
    """Display a progress bar."""
    percent = float(current) / total
    filled_length = int(bar_length * percent)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    sys.stdout.write(f'\r[{bar}] {percent:.1%} ({current}/{total})')
    sys.stdout.flush()

def extract_audio(mkv_path: str, wav_path: str, sr: int = 22050) -> None:
    """Extract audio from MKV file using ffmpeg."""
    print("Extracting audio from MKV...")
    subprocess.run([
        "ffmpeg", "-y", "-i", mkv_path, "-vn", "-ac", "1", "-ar", str(sr), wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def extract_chapters(mkv_path: str, xml_path: str = "chapters.xml") -> list:
    """Extract chapter start times using mkvextract."""
    print("Extracting chapters...")
    with open(xml_path, "w", encoding="utf-8") as f:
        subprocess.run(["mkvextract", "chapters", mkv_path], stdout=f, stderr=subprocess.DEVNULL)
    
    tree = ET.parse(xml_path)
    root = tree.getroot()
    chapters = []
    
    chapter_num = 1
    for chapter in root.findall(".//ChapterAtom"):
        time_start = chapter.find("ChapterTimeStart").text
        h, m, s = map(float, time_start.replace(",", ".").split(":"))
        seconds = h * 3600 + m * 60 + s
        chapters.append({
            'number': chapter_num,
            'label': time_start,
            'start_time': seconds
        })
        chapter_num += 1
    
    # Filter out chapters shorter than 10 seconds
    filtered_chapters = []
    for i, chapter in enumerate(chapters):
        # Calculate chapter duration
        if i < len(chapters) - 1:
            # Duration is the time until the next chapter
            duration = chapters[i + 1]['start_time'] - chapter['start_time']
        else:
            # Last chapter - assume it's long enough (we can't know the total duration easily)
            duration = 11  # Just assume it's longer than 10 seconds
        
        if duration >= 10:
            filtered_chapters.append(chapter)
        else:
            print(f"Skipping Chapter #{chapter['number']} (duration: {duration:.1f}s < 10s)")
    
    print(f"Filtered to {len(filtered_chapters)} chapters with duration ≥ 10 seconds")
    
    os.remove(xml_path)
    return filtered_chapters

def create_fingerprint(audio_segment: np.ndarray, sr: int = 22050) -> np.ndarray:
    """Create audio fingerprint from 10-second segment."""
    # Extract MFCC features (most common for audio similarity)
    mfcc = librosa.feature.mfcc(y=audio_segment, sr=sr, n_mfcc=13)
    # Use mean of MFCC coefficients as fingerprint
    fingerprint = np.mean(mfcc, axis=1)
    return fingerprint

def analyze_chapters(audio_path: str, chapters: list, sr: int = 22050) -> list:
    """Analyze first 10 seconds of each chapter and create fingerprints."""
    print("Loading audio file...")
    y, _ = librosa.load(audio_path, sr=sr)
    
    samples = []
    segment_duration = 10  # seconds
    segment_samples = sr * segment_duration
    
    print(f"Analyzing first 10 seconds of {len(chapters)} chapters...")
    
    for i, chapter in enumerate(chapters):
        progress_bar(i + 1, len(chapters))
        
        start_sample = int(chapter['start_time'] * sr)
        
        # Skip if chapter extends beyond audio
        if start_sample + segment_samples > len(y):
            continue
            
        # Extract 10-second segment
        segment = y[start_sample:start_sample + segment_samples]
        
        # Skip if segment is too quiet (likely silence)
        if np.sqrt(np.mean(segment**2)) < 0.005:
            continue
        
        # Create fingerprint
        fingerprint = create_fingerprint(segment, sr)
        
        samples.append({
            'chapter_number': chapter['number'],
            'chapter_label': chapter['label'], 
            'start_time': chapter['start_time'],
            'fingerprint': fingerprint
        })
    
    print()  # New line after progress bar
    print(f"Created fingerprints for {len(samples)} chapters (skipped silence)")
    return samples

def find_similar_samples(samples: list, similarity_threshold: float = 0.005) -> list:
    """Find samples that match with high similarity (default 99.5%)."""
    if len(samples) < 2:
        return []
    
    similarity_percent = (1 - similarity_threshold) * 100
    print(f"Comparing {len(samples)} samples for {similarity_percent:.1f}% similarity...")
    
    # Extract fingerprints for comparison
    fingerprints = np.array([sample['fingerprint'] for sample in samples])
    
    # Calculate pairwise cosine distances
    distances = scipy.spatial.distance.pdist(fingerprints, metric='cosine')
    distance_matrix = scipy.spatial.distance.squareform(distances)
    
    matches = []
    total_comparisons = len(samples) * (len(samples) - 1) // 2
    comparisons_done = 0
    
    # Find all pairs with similarity >= threshold
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            comparisons_done += 1
            if comparisons_done % 100 == 0:
                progress_bar(comparisons_done, total_comparisons)
            
            similarity_score = distance_matrix[i][j]
            
            # Cosine distance < threshold means high similarity
            if similarity_score < similarity_threshold:
                similarity_percent = (1 - similarity_score) * 100
                matches.append({
                    'sample1': samples[i],
                    'sample2': samples[j],
                    'similarity': similarity_percent
                })
    
    print()  # New line after progress bar
    print(f"Found {len(matches)} pairs with ≥{(1-similarity_threshold)*100:.1f}% similarity")
    
    return matches

def find_intro_sequences(matches: list, min_group_size: int = 3, similarity_threshold: float = 99.9) -> list:
    """Find the most likely intro sequences by identifying tightly connected chapter groups."""
    if not matches:
        return []
    
    # Only use very high similarity matches
    high_quality_matches = [m for m in matches if m['similarity'] >= similarity_threshold]
    
    if not high_quality_matches:
        return []
    
    # Count how many high-quality matches each chapter has
    chapter_match_counts = {}
    chapter_similarities = {}
    
    for match in high_quality_matches:
        ch1 = match['sample1']['chapter_number']
        ch2 = match['sample2']['chapter_number']
        similarity = match['similarity']
        
        # Track match counts
        chapter_match_counts[ch1] = chapter_match_counts.get(ch1, 0) + 1
        chapter_match_counts[ch2] = chapter_match_counts.get(ch2, 0) + 1
        
        # Track average similarities
        if ch1 not in chapter_similarities:
            chapter_similarities[ch1] = []
        if ch2 not in chapter_similarities:
            chapter_similarities[ch2] = []
        
        chapter_similarities[ch1].append(similarity)
        chapter_similarities[ch2].append(similarity)
    
    # Find chapters that have many high-quality matches (likely intro sequences)
    candidate_chapters = []
    for chapter, count in chapter_match_counts.items():
        if count >= min_group_size - 1:  # At least N-1 matches for a group of N
            avg_similarity = sum(chapter_similarities[chapter]) / len(chapter_similarities[chapter])
            candidate_chapters.append((chapter, count, avg_similarity))
    
    # Sort by match count and similarity
    candidate_chapters.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    if not candidate_chapters:
        return []
    
    # Build groups using only the most connected chapters
    # Start with the chapter that has the most high-quality matches
    best_chapters = set()
    for chapter, count, avg_sim in candidate_chapters:
        # Only include chapters that match with other candidates
        matches_with_candidates = 0
        for match in high_quality_matches:
            ch1 = match['sample1']['chapter_number']
            ch2 = match['sample2']['chapter_number']
            
            if (ch1 == chapter and any(ch2 == c[0] for c in candidate_chapters)) or \
               (ch2 == chapter and any(ch1 == c[0] for c in candidate_chapters)):
                matches_with_candidates += 1
        
        # If this chapter matches well with other candidates, include it
        if matches_with_candidates >= min_group_size - 1:
            best_chapters.add(chapter)
    
    if len(best_chapters) >= min_group_size:
        return [sorted(list(best_chapters))]
    
    return []

def display_results(matches: list, max_results: int = 10):
    """Display matching samples grouped by intro sequences."""
    if not matches:
        print("\n❌ No matching samples found")
        print("Try using a lower similarity threshold (e.g., --similarity 0.01 for 99%)")
        return
    
    # Find intro sequences with stricter criteria
    intro_sequences = find_intro_sequences(matches, min_group_size=4, similarity_threshold=99.95)
    
    print(f"\n🎯 Found {len(matches)} total matching pairs")
    
    if not intro_sequences:
        print("📊 No clear intro sequences found with high similarity")
        print("💡 Showing top individual matches instead:")
        
        # Fall back to showing top matches
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        displayed_matches = matches[:max_results]
        
        def format_time(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
        
        for i, match in enumerate(displayed_matches, 1):
            sample1 = match['sample1']
            sample2 = match['sample2']
            similarity = match['similarity']
            
            print(f"\n{i:2d}. Similarity: {similarity:.3f}%")
            print(f"    Chapter #{sample1['chapter_number']:2d} at {format_time(sample1['start_time'])} ({sample1['start_time']:.1f}s)")
            print(f"    Chapter #{sample2['chapter_number']:2d} at {format_time(sample2['start_time'])} ({sample2['start_time']:.1f}s)")
        
        return
    
    print(f"📊 Identified {len(intro_sequences)} intro sequence(s):")
    print("=" * 60)
    
    # Get sample info for timestamps
    all_samples = {}
    for match in matches:
        ch1 = match['sample1']['chapter_number']
        ch2 = match['sample2']['chapter_number']
        all_samples[ch1] = match['sample1']
        all_samples[ch2] = match['sample2']
    
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    for i, sequence in enumerate(intro_sequences, 1):
        print(f"\nIntro Sequence #{i}:")
        
        # Calculate average similarity for this sequence
        sequence_similarities = []
        for match in matches:
            ch1 = match['sample1']['chapter_number']
            ch2 = match['sample2']['chapter_number']
            if ch1 in sequence and ch2 in sequence:
                sequence_similarities.append(match['similarity'])
        
        if sequence_similarities:
            avg_similarity = sum(sequence_similarities) / len(sequence_similarities)
            print(f"Average similarity: {avg_similarity:.3f}%")
        
        # Display chapters in the requested format
        print(f"Chapters: {', '.join(map(str, sequence))}")
        
        # Show detailed timestamps
        print("Episode start times:")
        for chapter_num in sequence:
            if chapter_num in all_samples:
                sample = all_samples[chapter_num]
                timestamp = format_time(sample['start_time'])
                print(f"  Chapter #{chapter_num:2d}: {timestamp} ({sample['start_time']:.1f}s)")

def prompt_for_splitting(mkv_path: str, intro_sequences: list):
    """Prompt user to generate and run mkvtoolnix split command."""
    if not intro_sequences:
        return
    
    print("\n" + "="*60)
    print("🎬 MKV SPLITTING OPTIONS")
    print("="*60)
    
    for i, sequence in enumerate(intro_sequences, 1):
        print(f"\nIntro Sequence #{i}:")
        print(f"Episode start chapters: {', '.join(map(str, sequence))}")
        
        # Generate the split command
        chapter_list = ','.join(map(str, sequence))
        output_name = mkv_path.rsplit('.', 1)[0] + '_episodes.mkv'
        command = f"mkvmerge -o \"{output_name}\" --split chapters:{chapter_list} \"{mkv_path}\""
        
        print(f"\nGenerated command:")
        print(f"  {command}")
        
        # Ask user what to do
        while True:
            print(f"\nOptions for sequence #{i}:")
            print("  1. Run the command now")
            print("  2. Copy command to clipboard (display only)")
            print("  3. Skip this sequence")
            
            choice = input("Enter your choice (1-3): ").strip()
            
            if choice == '1':
                print(f"\n🚀 Running mkvmerge command...")
                try:
                    result = subprocess.run(command, shell=True, capture_output=True, text=True)
                    if result.returncode == 0:
                        print(f"✅ Successfully split MKV! Output: {output_name}")
                    else:
                        print(f"❌ Error running command:")
                        print(f"   {result.stderr}")
                        print(f"\n💡 You can run this command manually:")
                        print(f"   {command}")
                except Exception as e:
                    print(f"❌ Error: {e}")
                    print(f"\n💡 You can run this command manually:")
                    print(f"   {command}")
                break
                
            elif choice == '2':
                print(f"\n📋 Command to copy:")
                print(f"   {command}")
                print(f"\n💡 Copy the above command and run it in your terminal")
                break
                
            elif choice == '3':
                print(f"⏭️  Skipping sequence #{i}")
                break
                
            else:
                print("❌ Invalid choice. Please enter 1, 2, or 3.")
    
    print(f"\n✨ Done!")

def find_mkv_files() -> list:
    """Find all MKV files in the current directory."""
    mkv_files = []
    for file in os.listdir('.'):
        if file.lower().endswith('.mkv'):
            mkv_files.append(file)
    return sorted(mkv_files)

def select_mkv_file() -> str:
    """Prompt user to select an MKV file from the current directory."""
    mkv_files = find_mkv_files()
    
    if not mkv_files:
        print("❌ No MKV files found in the current directory")
        sys.exit(1)
    
    if len(mkv_files) == 1:
        print(f"📁 Found 1 MKV file: {mkv_files[0]}")
        confirm = input(f"Process '{mkv_files[0]}'? (y/n): ").strip().lower()
        if confirm in ['y', 'yes']:
            return mkv_files[0]
        else:
            print("❌ Cancelled by user")
            sys.exit(1)
    
    # Multiple files found
    print(f"📁 Found {len(mkv_files)} MKV files:")
    print("-" * 50)
    
    for i, file in enumerate(mkv_files, 1):
        # Get file size for display
        try:
            size_bytes = os.path.getsize(file)
            if size_bytes > 1024*1024*1024:  # > 1GB
                size_str = f"{size_bytes / (1024*1024*1024):.1f} GB"
            elif size_bytes > 1024*1024:  # > 1MB
                size_str = f"{size_bytes / (1024*1024):.0f} MB"
            else:
                size_str = f"{size_bytes / 1024:.0f} KB"
        except:
            size_str = "unknown size"
        
        print(f"{i:2d}. {file} ({size_str})")
    
    print("-" * 50)
    
    while True:
        try:
            choice = input(f"Select file to process (1-{len(mkv_files)}) or 'q' to quit: ").strip()
            
            if choice.lower() == 'q':
                print("❌ Cancelled by user")
                sys.exit(1)
            
            file_index = int(choice) - 1
            if 0 <= file_index < len(mkv_files):
                selected_file = mkv_files[file_index]
                print(f"✅ Selected: {selected_file}")
                return selected_file
            else:
                print(f"❌ Invalid choice. Please enter 1-{len(mkv_files)} or 'q'")
                
        except ValueError:
            print(f"❌ Invalid input. Please enter a number 1-{len(mkv_files)} or 'q'")

def main():
    parser = argparse.ArgumentParser(description="Find recurring intro music in MKV chapters")
    parser.add_argument("--mkv", help="Path to the MKV file (optional - will auto-detect if not provided)")
    parser.add_argument("--similarity", type=float, default=0.005, 
                       help="Similarity threshold (0.005 = 99.5%% similarity, default)")
    parser.add_argument("--max-results", type=int, default=10,
                       help="Maximum number of results to display (default: 10)")
    parser.add_argument("--auto-split", action="store_true",
                       help="Automatically prompt for MKV splitting after analysis")
    args = parser.parse_args()
    
    # Auto-detect MKV file if not provided
    if args.mkv:
        mkv_path = args.mkv
        if not os.path.exists(mkv_path):
            print(f"❌ File not found: {mkv_path}")
            sys.exit(1)
    else:
        mkv_path = select_mkv_file()
    
    wav_path = "temp_audio.wav"
    
    print(f"\n🎬 Processing: {mkv_path}")
    print("=" * 60)
    
    try:
        # Step 1: Extract audio
        extract_audio(mkv_path, wav_path)
        
        # Step 2: Extract chapters
        chapters = extract_chapters(mkv_path)
        print(f"Found {len(chapters)} chapters")
        
        # Step 3: Analyze first 10 seconds of each chapter
        samples = analyze_chapters(wav_path, chapters)
        
        # Step 4: Find similar samples
        matches = find_similar_samples(samples, args.similarity)
        
        # Step 5: Display results and get intro sequences
        intro_sequences = find_intro_sequences(matches, min_group_size=4, similarity_threshold=99.95)
        display_results(matches, args.max_results)
        
        # Step 6: Optional splitting prompt
        if args.auto_split or intro_sequences:
            if not args.auto_split:
                # Always ask if intro sequences were found
                ask_split = input(f"\n🎬 Found intro sequences. Generate MKV split commands? (y/n): ").strip().lower()
                if ask_split in ['y', 'yes']:
                    prompt_for_splitting(mkv_path, intro_sequences)
            else:
                prompt_for_splitting(mkv_path, intro_sequences)
        
    finally:
        # Clean up
        if os.path.exists(wav_path):
            os.remove(wav_path)

if __name__ == "__main__":
    main()
