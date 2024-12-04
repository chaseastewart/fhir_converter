# new command to be complient with Microsoft FHIR Converter
# command example:
# fhir-convert convert -d /path/to/template -r root_template_name -n /path/to/file -f /path/to/resultfile -t

import argparse

from liquid import FileExtensionLoader

from fhir_converter.renderers import (
    Hl7v2Renderer,
    make_environment,
    hl7v2_default_loader
)

def parse_args():
    # fhir-convert convert -d /path/to/template -r root_template_name -n /path/to/file -f /path/to/resultfile -t
    parser = argparse.ArgumentParser(description="FHIR Converter CLI")
    # add argument convert without double dash or single dash
    parser.add_argument(
        "convert",
        nargs='*'
    )
    parser.add_argument(
        "-d",
        "--template-dir",
        type=str,
        metavar="<Path>",
        help="The user defined liquid template directory",
    )
    parser.add_argument(
        "-r",
        "--root-template-name",
        metavar="<str>",
        help="The liquid template to use when rendering the file",
        required=True,
    )
    parser.add_argument(
        "-n",
        "--from-file",
        type=str,
        metavar="<Path>",
        help="The file to render",
    )
    parser.add_argument(
        "-f",
        "--to-file",
        type=str,
        metavar="<Path>",
        help="The file to store the rendered output",
        required=True,
    )
    parser.add_argument(
        "-t",
        action='store_true'
    )
    return parser

def main():
    parser = parse_args()
    args = parser.parse_args()

    renderer = Hl7v2Renderer(
        env=make_environment(
            loader=FileExtensionLoader(search_path=args.template_dir),
            additional_loaders=[hl7v2_default_loader],
        )
    )
    with open(args.from_file, mode="r", encoding="utf-8") as hl7v2_in:
        result = renderer.render_fhir_string(args.root_template_name, hl7v2_in)
        with open(args.to_file, mode="w", encoding="utf-8") as fhir_out:
            fhir_out.write(result)

if __name__ == "__main__":
    main()

