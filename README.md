# DESH
DVD Episode Splitter Helper

You know when you rip a DVD boxset but the episodes are in one long file rather then per episode?

This helps with that.

It fingerprints intro music based on chapter start times, and presents a list of possible episode start chapters to split by, using mkvmerge to process the output.

Currently Proof of Concept, only tested on 1 DVD so far, does not work on episodes with cold opens, outro music may throw off the script, but it should group by different music fingerprints, give it a try and let me know.

____________________________________________________

Usage:
Copy autosplit.py to the folder where your mkv is.
Open a commandline window in that folder.
Type autosplit.py

Requirements:
Python and mkvtoolnix in system path

python requirements:

numpy>=2.1.2

scipy>=1.16.0

librosa>=0.11.0

lxml>=6.0.0
