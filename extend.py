import logging
import os
import warnings
from argparse import ArgumentError, ArgumentParser, Namespace
from pathlib import Path
from typing import Literal

import ffmpeg
from mtools.metacopy import copy_metadata
from mtools.utils import UnsupportedFormat
from pymusiclooper.handler import LoopExportHandler
from utils_python import copy_filedate, get_platform, setup_root_logger

LOGGER = logging.getLogger(__name__)


class ProgramArgsNamespace(Namespace):
    input_file_path: Path
    extended_length: float
    output_dir: Path
    min_duration_multiplier: float = 0.35
    fade_length: float | None = None
    brute_force: bool = False
    show_progress_bar: bool = False
    format: str = "M4A"
    interactive: bool = False


def get_args() -> ProgramArgsNamespace:
    parser = ArgumentParser()
    parser.add_argument(
        "input_file_path",
        type=Path,
        metavar="INPUT_FILE_PATH",
        help="Path of file to extend",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Default: <directory containing INPUT_FILE_PATH>",
    )
    parser.add_argument(
        "-l",
        "--extended-length",
        type=float,
        help="Length (seconds) to extend to",
        required=True,
    )
    parser.add_argument(
        "--min-duration-multiplier",
        type=float,
        help=(
            "The minimum loop duration as a multiplier of the "
            "audio track's total duration. Default: %(default)s"
        ),
        default=ProgramArgsNamespace.min_duration_multiplier,
    )
    fade_length_arg = parser.add_argument(
        "--fade-length",
        type=float,
        help=(
            "Desired length of the loop fade out in seconds."
            " If not provided, extend the track with all its sections"
            " (intro/loop/outro) without fading out."
            " --extended-length will be treated as an 'at least' constraint."
        ),
    )
    parser.add_argument(
        "--brute-force",
        action="store_true",
        help="Check the entire audio track instead of just the detected beats."
        " (Warning: may take several minutes to complete.)",
    )
    parser.add_argument(
        "--show-progress-bar",
        action="store_true",
    )
    format_arg = parser.add_argument(
        "-f",
        "--format",
        choices=("WAV", "FLAC", "OGG", "MP3", "M4A"),
        default=ProgramArgsNamespace.format,
        dest="format",
        type=lambda s: s.upper(),
        help="Audio format to use for the output audio file. [default: %(default)s]",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
    )

    args = parser.parse_args(namespace=ProgramArgsNamespace())

    if args.output_dir is None:
        args.output_dir = args.input_file_path.parent

    if args.fade_length == 0:
        raise ArgumentError(
            fade_length_arg, "PyMusicLooper does not support fade_length==0"
        )

    if args.format == "OGG" and get_platform() == "windows":
        raise ArgumentError(
            format_arg,
            "format 'OGG' is not supported on Windows: see https://github.com/arkrow/PyMusicLooper/issues/35",
        )

    if args.interactive:
        os.environ["PML_INTERACTIVE_MODE"] = "1"
    return args


def main(args: ProgramArgsNamespace) -> None:
    input_path = args.input_file_path
    disable_fade_out = args.fade_length is None
    format_: Literal["WAV", "FLAC", "OGG", "MP3"]
    if args.format in ["WAV", "FLAC", "OGG", "MP3"]:
        format_ = args.format
    else:
        format_ = "WAV"
    loop_export_handler = LoopExportHandler(
        path=str(input_path),
        output_dir=str(args.output_dir),
        min_duration_multiplier=args.min_duration_multiplier,
        extended_length=args.extended_length,
        fade_length=args.fade_length or 0,
        disable_fade_out=disable_fade_out,
        batch_mode=not args.show_progress_bar,
        brute_force=args.brute_force,
        format=format_,
    )
    raw_output_path = loop_export_handler.extend_track_runner()
    if args.format == "M4A":
        LOGGER.info(f"Converting '{raw_output_path}' to M4A")
        output_path = raw_output_path.with_suffix("." + args.format.lower())

        LOGGER.info(f"'{raw_output_path}' -> '{output_path}'")

        cmd = ffmpeg.input(raw_output_path)
        cmd = cmd.output(
            str(output_path),
            acodec="aac",
            map="0:a",
        )
        LOGGER.info(" ".join(str(c) for c in cmd.compile()))
        try:
            _stdout, _stderr = cmd.run()
        except Exception as _exc:
            LOGGER.error("    " + " ".join(str(c) for c in cmd.compile()))
            raise
    else:
        output_path = raw_output_path

    try:
        LOGGER.info(
            f"Attempting to copy metadata from '{input_path}' to '{output_path}'"
        )
        copy_metadata(input_path, output_path)
    except UnsupportedFormat as exc:
        LOGGER.info(f"Failed to copy metadata: {exc!r}")

    LOGGER.info(f"Copying file dates from '{input_path}' to '{output_path}'")
    copy_filedate(input_path, output_path)

    if output_path != raw_output_path:
        LOGGER.info(f"Deleting '{raw_output_path}'")
        raw_output_path.unlink()


if __name__ == "__main__":
    warnings.filterwarnings("ignore")

    _args = get_args()
    setup_root_logger()
    main(_args)
