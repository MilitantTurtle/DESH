#!/usr/bin/env python3
"""
launch.py
Simple launcher that asks the user whether to run
audiomode.py  or  chaptermode.py
"""
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_SCRIPT  = os.path.join(SCRIPT_DIR, "audiomode.py")
CHAPTER_SCRIPT = os.path.join(SCRIPT_DIR, "chaptermode.py")

def script_exists(path):
    return os.path.isfile(path)

def main():
    if not script_exists(AUDIO_SCRIPT):
        sys.exit("❌ audiomode.py not found beside this launcher.")
    if not script_exists(CHAPTER_SCRIPT):
        sys.exit("❌ chaptermode.py not found beside this launcher.")

    print("\n🎬 Choose detection mode:")
    print("  1. Audio fingerprint (audiomode.py)")
    print("  2. Chapter length   (chaptermode.py)")
    print("  q. Quit")

    while True:
        choice = input("\nEnter 1, 2 or q: ").strip().lower()
        if choice == 'q':
            sys.exit("👋 Cancelled.")
        if choice == '1':
            subprocess.run([sys.executable, AUDIO_SCRIPT])
            break
        if choice == '2':
            subprocess.run([sys.executable, CHAPTER_SCRIPT])
            break
        print("❌ Please enter 1, 2 or q.")

if __name__ == "__main__":
    main()
