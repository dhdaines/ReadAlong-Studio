#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#######################################################################
#
# cli.py
#
#   Initializes a Command Line Interface with Click.
#   The main purpose of the cli is to align input files.
#
#   CLI commands implemented in this file:
#    - align  : main command to align text and audio
#    - epub   : convert aligned file to epub format
#    - prepare: prepare XML input for align from plain text
#
#   Default CLI commands provided by Flask:
#    - routes : show available routes in the this readalongs Flask app
#    - run    : run the readalongs Flask app
#    - shell  : open a shell within the readalongs Flask application context
#
#######################################################################

import io
import json
import os
import shutil
import sys
from tempfile import TemporaryFile

import click
from flask.cli import FlaskGroup
from lxml import etree

from readalongs._version import __version__
from readalongs.align import (
    align_audio,
    convert_to_xhtml,
    create_input_tei,
    return_words_and_sentences,
    write_to_subtitles,
    write_to_text_grid,
)
from readalongs.app import app
from readalongs.audio_utils import read_audio_from_file
from readalongs.epub.create_epub import create_epub
from readalongs.log import LOGGER
from readalongs.text.make_package import create_web_component_html
from readalongs.text.make_smil import make_smil
from readalongs.text.tokenize_xml import tokenize_xml
from readalongs.text.util import save_minimal_index_html, save_txt, save_xml, write_xml
from readalongs.views import LANGS


def create_app():
    """ Returns the app
    """
    return app


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.version_option(version=__version__, prog_name="readalongs")
@click.group(cls=FlaskGroup, create_app=create_app, context_settings=CONTEXT_SETTINGS)
def cli():
    """Management script for Read Along Studio."""


@app.cli.command(
    context_settings=CONTEXT_SETTINGS, short_help="Force align a text and a sound file."
)
@click.argument("textfile", type=click.Path(exists=True, readable=True))
@click.argument("audiofile", type=click.Path(exists=True, readable=True))
@click.argument("output-base", type=click.Path())
@click.option(
    "-b",
    "--bare",
    is_flag=True,
    help="Bare alignments do not split silences between words",
)
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True),
    help="Use ReadAlong-Studio configuration file (in JSON format)",
)
@click.option(
    "-C",
    "--closed-captioning",
    is_flag=True,
    help="Export sentences to WebVTT and SRT files",
)
@click.option("-d", "--debug", is_flag=True, help="Add debugging messages to logger")
@click.option(
    "-f", "--force-overwrite", is_flag=True, help="Force overwrite output files"
)
@click.option(
    "-i",
    "--text-input",
    is_flag=True,
    help="Input is plain text (assume paragraphs are separated by blank lines, pages are separated by two blank lines)",
)
@click.option(
    "-l",
    "--language",
    type=click.Choice(LANGS, case_sensitive=False),
    help="Set language for plain text input",
)
@click.option(
    "-u",
    "--unit",
    type=click.Choice(["w", "m"], case_sensitive=False),
    help="Unit (w = word, m = morpheme) to align to",
)
@click.option(
    "-s",
    "--save-temps",
    is_flag=True,
    help="Save intermediate stages of processing and temporary files (dictionary, FSG, tokenization etc)",
)
@click.option(
    "-t", "--text-grid", is_flag=True, help="Export to Praat TextGrid & ELAN eaf file"
)
@click.option("-H", "--html", is_flag=True, help="Export to WebComponent HTML")
@click.option(
    "-x", "--output-xhtml", is_flag=True, help="Output simple XHTML instead of XML"
)
def align(**kwargs):
    """Align TEXTFILE and AUDIOFILE and create output files as OUTPUT_BASE.* in directory
    OUTPUT_BASE/.

    TEXTFILE:    Input text file path (in XML, or plain text with -i)

    AUDIOFILE:   Input audio file path, in any format supported by ffmpeg

    OUTPUT_BASE: Base name for output files
    """
    config = kwargs.get("config", None)
    if config:
        if config.endswith("json"):
            try:
                with open(config) as f:
                    config = json.load(f)
            except json.decoder.JSONDecodeError:
                LOGGER.error(f"Config file at {config} is not valid json.")
        else:
            raise click.BadParameter(f"Config file '{config}' must be in JSON format")

    output_dir = kwargs["output_base"]
    if os.path.exists(output_dir):
        if not os.path.isdir(output_dir):
            raise click.UsageError(
                f"Output folder '{output_dir}' already exists but is a not a directory."
            )
        if not kwargs["force_overwrite"]:
            raise click.UsageError(
                f"Output folder '{output_dir}' already exists, use -f to overwrite."
            )
    else:
        os.mkdir(output_dir)

    # Make sure we can write to the output directory, for early error checking and user
    # friendly error messages.
    try:
        with TemporaryFile(dir=output_dir):
            pass
    except Exception:
        raise click.UsageError(
            f"Cannot write into output folder '{output_dir}'. Please verify permissions."
        )

    output_basename = os.path.basename(output_dir)
    output_base = os.path.join(output_dir, output_basename)
    temp_base = None
    if kwargs["save_temps"]:
        temp_dir = os.path.join(output_dir, "tempfiles")
        if not os.path.isdir(temp_dir):
            if os.path.exists(temp_dir) and kwargs["force_overwrite"]:
                os.unlink(temp_dir)
            os.mkdir(temp_dir)
        temp_base = os.path.join(temp_dir, output_basename)

    if kwargs["debug"]:
        LOGGER.setLevel("DEBUG")
    if kwargs["text_input"]:
        if not kwargs["language"]:
            LOGGER.warn("No input language provided, using undetermined mapping")
        tempfile, kwargs["textfile"] = create_input_tei(
            input_file_name=kwargs["textfile"],
            text_language=kwargs["language"],
            save_temps=temp_base,
        )
    if kwargs["output_xhtml"]:
        tokenized_xml_path = "%s.xhtml" % output_base
    else:
        _, input_ext = os.path.splitext(kwargs["textfile"])
        tokenized_xml_path = "%s%s" % (output_base, input_ext)
    if os.path.exists(tokenized_xml_path) and not kwargs["force_overwrite"]:
        raise click.BadParameter(
            "Output file %s exists already, use -f to overwrite." % tokenized_xml_path
        )
    smil_path = output_base + ".smil"
    if os.path.exists(smil_path) and not kwargs["force_overwrite"]:
        raise click.BadParameter(
            "Output file %s exists already, use -f to overwrite." % smil_path
        )
    _, audio_ext = os.path.splitext(kwargs["audiofile"])
    audio_path = output_base + audio_ext
    if os.path.exists(audio_path) and not kwargs["force_overwrite"]:
        raise click.BadParameter(
            "Output file %s exists already, use -f to overwrite." % audio_path
        )
    unit = kwargs.get("unit", "w")
    bare = kwargs.get("bare", False)
    if (
        not unit
    ):  # .get() above should handle this but apparently the way kwargs is implemented
        unit = "w"  # unit could still be None here.
    try:
        results = align_audio(
            kwargs["textfile"],
            kwargs["audiofile"],
            unit=unit,
            bare=bare,
            config=config,
            save_temps=temp_base,
        )
    except RuntimeError as e:
        LOGGER.error(e)
        exit(1)

    if kwargs["text_grid"]:
        audio = read_audio_from_file(kwargs["audiofile"])
        duration = audio.frame_count() / audio.frame_rate
        words, sentences = return_words_and_sentences(results)
        textgrid = write_to_text_grid(words, sentences, duration)
        textgrid.to_file(output_base + ".TextGrid")
        textgrid.to_eaf().to_file(output_base + ".eaf")

    if kwargs["closed_captioning"]:
        words, sentences = return_words_and_sentences(results)
        webvtt_sentences = write_to_subtitles(sentences)
        webvtt_sentences.save(output_base + "_sentences.vtt")
        webvtt_sentences.save_as_srt(output_base + "_sentences.srt")
        webvtt_words = write_to_subtitles(words)
        webvtt_words.save(output_base + "_words.vtt")
        webvtt_words.save_as_srt(output_base + "_words.srt")

    if kwargs["output_xhtml"]:
        convert_to_xhtml(results["tokenized"])

    if kwargs["html"]:
        html_out_path = output_base + ".html"
        html_out = create_web_component_html(tokenized_xml_path, smil_path, audio_path)
        with open(html_out_path, "w") as f:
            f.write(html_out)

    save_minimal_index_html(
        os.path.join(output_dir, "index.html"),
        os.path.basename(tokenized_xml_path),
        os.path.basename(smil_path),
        os.path.basename(audio_path),
    )

    save_xml(tokenized_xml_path, results["tokenized"])
    smil = make_smil(
        os.path.basename(tokenized_xml_path), os.path.basename(audio_path), results
    )
    shutil.copy(kwargs["audiofile"], audio_path)
    save_txt(smil_path, smil)


@app.cli.command(
    context_settings=CONTEXT_SETTINGS, short_help="Convert a smil document to epub."
)
@click.argument("input", type=click.Path(exists=True, readable=True))
@click.argument("output", type=click.Path(exists=False, readable=True))
@click.option(
    "-u",
    "--unpacked",
    is_flag=True,
    help="Output unpacked directory of files (for testing)",
)
def epub(**kwargs):
    """
    Convert INPUT smil document to epub with media overlay at OUTPUT

    INPUT:  The .smil document

    OUTPUT: Path to the .epub output
    """
    create_epub(kwargs["input"], kwargs["output"], kwargs["unpacked"])


@app.cli.command(
    context_settings=CONTEXT_SETTINGS,
    short_help="Prepare XML input to align from plain text.",
)
@click.argument("plaintextfile", type=click.File("rb"))
@click.argument("xmlfile", type=click.Path(), required=False, default="")
@click.option("-d", "--debug", is_flag=True, help="Add debugging messages to logger")
@click.option(
    "-f", "--force-overwrite", is_flag=True, help="Force overwrite output files"
)
@click.option(
    "-l",
    "--language",
    type=click.Choice(LANGS, case_sensitive=False),
    required=True,
    help="Set language for input file",
)
def prepare(**kwargs):
    """Prepare XMLFILE for 'readalongs align' from PLAINTEXTFILE.
    PLAINTEXTFILE must be plain text encoded in utf-8, with one sentence per line,
    paragraph breaks marked by a blank line, and page breaks marked by two
    blank lines.

    PLAINTEXTFILE: Path to the plain text input file, or - for stdin

    XMLFILE:       Path to the XML output file, or - for stdout [default: PLAINTEXTFILE.xml]
    """

    if kwargs["debug"]:
        LOGGER.setLevel("DEBUG")
        LOGGER.info(
            "Running readalongs prepare(lang={}, force-overwrite={}, plaintextfile={}, xmlfile={}).".format(
                kwargs["language"],
                kwargs["force_overwrite"],
                kwargs["plaintextfile"],
                kwargs["xmlfile"],
            )
        )

    input_file = kwargs["plaintextfile"]

    out_file = kwargs["xmlfile"]
    if not out_file:
        try:
            out_file = input_file.name
        except Exception:  # For unit testing: simulated stdin stream has no .name attrib
            out_file = "<stdin>"
        if out_file == "<stdin>":  # actual intput_file.name when cli input is "-"
            out_file = "-"
        else:
            if out_file.endswith(".txt"):
                out_file = out_file[:-4]
            out_file += ".xml"

    if out_file == "-":
        filehandle, filename = create_input_tei(
            input_file_handle=input_file, text_language=kwargs["language"],
        )
        with io.open(filename) as f:
            sys.stdout.write(f.read())
    else:
        if not out_file.endswith(".xml"):
            out_file += ".xml"
        if os.path.exists(out_file) and not kwargs["force_overwrite"]:
            raise click.BadParameter(
                "Output file %s exists already, use -f to overwrite." % out_file
            )

        filehandle, filename = create_input_tei(
            input_file_handle=input_file,
            text_language=kwargs["language"],
            output_file=out_file,
        )

    LOGGER.info("Wrote {}".format(out_file))


@app.cli.command(
    context_settings=CONTEXT_SETTINGS,
    short_help="Tokenize XML file to align from XML file produced by prepare.",
)
@click.argument("xmlfile", type=click.File("rb"))
@click.argument("tokfile", type=click.Path(), required=False, default="")
@click.option("-d", "--debug", is_flag=True, help="Add debugging messages to logger")
@click.option(
    "-f", "--force-overwrite", is_flag=True, help="Force overwrite output files"
)
def tokenize(**kwargs):
    """Tokenize XMLFILE for 'readalongs align' into TOKFILE.
    XMLFILE should have been produce by 'readalongs prepare'.
    TOKFILE can be augmented with word-specific language codes.
    'readalongs align' can be called with either XMLFILE or TOKFILE as XML input.

    XMLFILE: Path to the XML file to tokenize, or - for stdin

    TOKFILE: Output path for the tok'd XML, or - for stdout [default: XMLFILE.tokenized.xml]
    """
    xmlfile = kwargs["xmlfile"]

    if kwargs["debug"]:
        LOGGER.setLevel("DEBUG")
        LOGGER.info(
            "Running readalongs tokenize(xmlfile={}, tokfile={}, force-overwrite={}).".format(
                kwargs["xmlfile"], kwargs["tokfile"], kwargs["force_overwrite"],
            )
        )

    if not kwargs["tokfile"]:
        try:
            output_tok_path = xmlfile.name
        except Exception:
            output_tok_path = "<stdin>"
        if output_tok_path == "<stdin>":
            output_tok_path = "-"
        else:
            if output_tok_path.endswith(".xml"):
                output_tok_path = output_tok_path[:-4]
            output_tok_path += ".tokenized.xml"
    else:
        output_tok_path = kwargs["tokfile"]
        if not output_tok_path.endswith(".xml") and not output_tok_path == "-":
            output_tok_path += ".xml"

    if os.path.exists(output_tok_path) and not kwargs["force_overwrite"]:
        raise click.BadParameter(
            "Output file %s exists already, use -f to overwrite." % output_tok_path
        )

    try:
        xml = etree.parse(xmlfile).getroot()
    except etree.XMLSyntaxError as e:
        raise click.BadParameter(
            "Error parsing input file %s as XML, please verify it. Parser error: %s"
            % (xmlfile, e)
        )

    xml = tokenize_xml(xml)

    if output_tok_path == "-":
        write_xml(sys.stdout.buffer, xml)
    else:
        save_xml(output_tok_path, xml)
    LOGGER.info("Wrote {}".format(output_tok_path))
