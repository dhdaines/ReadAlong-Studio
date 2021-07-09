## Misc Utils

This directory contains miscellaneous utility scripts that are not part of the
core of ReadAlongs Studio, but help with specific tasks in the perifery.

Their Copyrights are different from the rest of the repo, and declared with
license in each file, along with a documentation of the original provenance of
the files.

### `syll_parse.py`

Syllabify a tokenized readalongs XML file, so that highlighting can happen
syllable by syllable instead of word by word. This script should work reasonably
well for languages in the latin script where syllabification follows the
Sonority Sequencing Principle (SSP). For example, this works on Algonquin, and
is currently setup to support Algonquin spelling. Modify the sets of letter by
categories under "Sonority Hierarchy" to support other languages.

Must be called manually after
readalongs tokenize and before readalongs align or readalong g2p:

    readalongs prepare -l my_lang file.txt file.xml
    readalongs tokenize file.xml file-tok.xml
    ./syll_parse.py file-tok.xml file-tok-syll.xml

and then either:

    readalongs align file-tok-syll.xml file.wav output

or

    readalongs g2p file-tok-syll.xml file-g2p.xml
    readalongs align file-g2p.xml file.wav output

### `non-caching-server.py`

This script is intended to mitigate an issue with Mac's where the client might
cache files and refuse to fetch them again even if they were modified on disk,
even with a hard reload. This is an issue when, for example, testing a read
along that you just created using

    cd read-alongs-dir && python3 -m http.server

If you modify the read along and want to reload it without having to restart the
http server, on some OS's that works fine, but not on all OS's. If you encouter
this problem, using this command instead:

    cd read-alongs-dir && non-caching-server.py
