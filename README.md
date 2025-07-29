# DESH
DVD Episode Splitter Helper

You know when you rip a DVD boxset but the episodes are in one long file rather than per episode?

This helps with that, as long as your input mkv (DVD) has chapter markers.

Currently Proof of Concept, Chaptermode is currently the most reliable.

There are 2 Methods:

____________________________________________________


Audio Mode: Experimental (Intros MUST be the same length and Audio)

Fingerprints intro music based on chapter start times, and presents a list of possible episode start chapters to split by.

The benefit of doing it this way, is if the intro music is always the same, we can correctly identify the intro chapter.

The downside of this is that audio mode does not work on episodes with cold opens, or shortened intro music, plus outro music may throw off the script, but it should group by different music fingerprints.

____________________________________________________

Chapter Mode:

Detects chapters that are the same length, and uses them as end markers.

The benefit of doing it this way is for cold opens and different intro music or different intro lengths (like shortened intros).

The downside of this is that episode chapters (intro/outro) must be within a similar length.

____________________________________________________

Usage:
Copy python (.py) files to the folder where your mkv is.

Open a commandline window in that folder.

Type launch.py

____________________________________________________

Requirements:
Python and mkvtoolnix in system path

python requirements:

numpy>=2.1.2

scipy>=1.16.0

librosa>=0.11.0

lxml>=6.0.0
