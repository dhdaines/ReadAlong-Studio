#!/usr/bin/env python3

# Original Copyright and License from https://github.com/alexestes/SonoriPy:
#
# MIT License
#
# Copyright (c) 2016 Alex Estes and Christopher Hench
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Copyright for modifications at NRC:
#
# MIT License
#
# Copyright (c) 2021 National Research Council Canada (NRC)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Description of modifications by NRC
# - The original script by Estes&Hench provided the sonoropy() function
# - Fineed Davis 2020:
#   - adapt the script to Algonquin alphabet
#   - handle loading a readalongs tokenized XML file, syllabifying each word,
#     and writing the results back as a tokenized XML file for readalongs.
# - Eric Joanis 2021:
#   - add a basic command line interface
#   - reformat whole file with black and isort and and quiet flake8 on sonoripy()


import argparse
import codecs
import itertools
import unicodedata
import xml.etree.ElementTree
from io import BytesIO, StringIO

from lxml import etree

# -*- coding: utf-8 -*-
# created at UC Berkeley 2015
# Authors: Christopher Hench, Alex Estes

"""This program syllabifies words based on the Sonority Sequencing Principle (SSP)"""


def sonoripy(word):  # noqa: C901
    def no_syll_no_vowel(ss):
        # no syllable if no vowel
        nss = []
        front = ""
        for i, syll in enumerate(ss):
            # if following syllable doesn't have vowel,
            # add it to the current one
            if not any(char.lower() in vowels for char in syll):
                if len(nss) == 0:
                    front += syll
                else:
                    nss = nss[:-1] + [nss[-1] + syll]
            else:
                if len(nss) == 0:
                    nss.append(front + syll)
                else:
                    nss.append(syll)

        return nss

    # SONORITY HIERARCHY, MODIFY FOR LANGUAGE BELOW
    # categories can be collapsed into more general groups
    vowels = "aeiouyèùòìà"
    approximates = ""
    nasals = "lmnrw"  # resonants and nasals
    fricatives = "zvsf"
    affricates = ""
    stops = "bcdgtkpqxhj"  # rest of consonants

    vowelcount = 0  # if vowel count is 1, syllable is automatically 1
    sylset = []  # to collect letters and corresponding values
    for letter in word.strip(".:;?!)('" + '"'):
        if letter.lower() in vowels:
            sylset.append((letter, 5))
            vowelcount += 1  # to check for monosyllabic words
        elif letter.lower() in approximates:
            sylset.append((letter, 4))
        elif letter.lower() in nasals:
            sylset.append((letter, 3))
        elif letter.lower() in fricatives:
            sylset.append((letter, 2))
        elif letter.lower() in affricates:
            sylset.append((letter, 1))
        elif letter.lower() in stops:
            sylset.append((letter, 0))
        else:
            sylset.append((letter, 0))

    # below actually divides the syllables
    newsylset = []
    if vowelcount <= 1:  # finalize word immediately if monosyllabic
        newsylset.append(word)
    else:
        syllable = ""  # prepare empty syllable to build upon
        for i, tup in enumerate(sylset):
            if i == 0:  # if it's the first letter, append automatically
                syllable += tup[0]
            # lengths below are in order to not overshoot index
            # when it looks beyond
            else:
                # add whatever is left at end of word, last letter
                if i == len(sylset) - 1:
                    syllable += tup[0]
                    newsylset.append(syllable)

                # MAIN ALGORITHM BELOW
                # these cases DO NOT trigger syllable breaks
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] < sylset[i + 1][1]
                    and tup[1] > sylset[i - 1][1]
                ):
                    syllable += tup[0]
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] > sylset[i + 1][1]
                    and tup[1] < sylset[i - 1][1]
                ):
                    syllable += tup[0]
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] > sylset[i + 1][1]
                    and tup[1] > sylset[i - 1][1]
                ):
                    syllable += tup[0]
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] > sylset[i + 1][1]
                    and tup[1] == sylset[i - 1][1]
                ):
                    syllable += tup[0]
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] == sylset[i + 1][1]
                    and tup[1] > sylset[i - 1][1]
                ):
                    syllable += tup[0]
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] < sylset[i + 1][1]
                    and tup[1] == sylset[i - 1][1]
                ):
                    syllable += tup[0]

                # these cases DO trigger syllable break
                # if phoneme value is equal to value of preceding AND following
                # phoneme
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] == sylset[i + 1][1]
                    and tup[1] == sylset[i - 1][1]
                ):
                    syllable += tup[0]
                    # append and break syllable BEFORE appending letter at
                    # index in new syllable
                    newsylset.append(syllable)
                    syllable = ""

                # if phoneme value is less than preceding AND following value
                # (trough)
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] < sylset[i + 1][1]
                    and tup[1] < sylset[i - 1][1]
                ):
                    # append and break syllable BEFORE appending letter at
                    # index in new syllable
                    newsylset.append(syllable)
                    syllable = ""
                    syllable += tup[0]

                # if phoneme value is less than preceding value AND equal to
                # following value
                elif (
                    (i < len(sylset) - 1)
                    and tup[1] == sylset[i + 1][1]
                    and tup[1] < sylset[i - 1][1]
                ):
                    syllable += tup[0]
                    # append and break syllable BEFORE appending letter at
                    # index in new syllable
                    newsylset.append(syllable)
                    syllable = ""

        newsylset = no_syll_no_vowel(newsylset)

    return newsylset


### Modifications by Fineen Davis at National Research Council Canada

# Basic argument parser added by Eric Joanis to support this usage:
# syll_parse.py input.xml [output.xml]
parser = argparse.ArgumentParser(
    description="syllabify a readalongs tokenized XML file"
)
parser.add_argument(
    "input_file",
    type=argparse.FileType("r"),
    help="Input tokenized XML file to syllabify (use - for stdin)",
)
parser.add_argument(
    "output_file",
    type=str,
    default="-",
    nargs="?",
    help="Output syllabified tokenized XML file (use - for stdout)",
)
args = parser.parse_args()

# Load XML file and read it
equiv_text = unicodedata.normalize("NFC", args.input_file.read())

# root = etree.fromstring(equiv_text)
root = etree.fromstring(equiv_text.encode("UTF-8"))


# Find <w> elements in XML file
for word in root.findall(".//w"):
    if "id" in word.attrib:
        del word.attrib["id"]
    # get the text for each word
    word_text = word.text
    # remove text from word element
    word.text = ""

    word_sylls = sonoripy(word_text)  # word_sylls is a list of lists []

    # Adds sylls to <syll> elements which are children of the <w> element
    # for syll in word_sylls:
    # syll_element = etree.Element('syll')
    # syll_element.text = syll
    # word.append(syll_element)

    # Adds sylls as <w> elements for alignment purposes
    prev_word = word
    prev_word.text = word_sylls.pop(0)

    for syll in word_sylls:
        next_word = etree.Element("w")
        next_word.text = syll
        prev_word.addnext(next_word)
        prev_word = next_word


tree = etree.ElementTree(root)
tree.write(args.output_file, pretty_print=True)
