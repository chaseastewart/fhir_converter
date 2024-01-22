from functools import partial
from pathlib import Path

from liquid import FileExtensionLoader
from liquid.loaders import DictLoader

from fhir_converter.renderers import (
    CcdaRenderer,
    ccda_default_loader,
    get_environment,
    render_files_to_dir,
    render_to_dir,
)
from fhir_converter.utils import mkdir

templates_dir, sample_data_dir, data_out_dir = (
    Path("data/templates/ccda"),
    Path("data/sample/ccda"),
    Path("data/out"),
)

from_file = sample_data_dir.joinpath("CCD.ccda")
mkdir(data_out_dir)

# Render the file to string using the rendering defaults
with from_file.open() as xml_in:
    print(CcdaRenderer().render_fhir_string("CCD", xml_in))

# Create a renderer that will load the user defined templates into the rendering env
renderer = CcdaRenderer(
    # Since a default loader is not provided, the default location will be the module
    env=get_environment(
        loader=FileExtensionLoader(search_path=templates_dir),
        additional_loaders=[ccda_default_loader],
    )
)

# Render the file to the output directory using the default CCD template
render_to_dir(
    render=partial(renderer.render_fhir, "CCD"),
    from_file=from_file,
    to_dir=data_out_dir,
)

# Render all of the sample files to the output directory using the user defined
# pampi (problems, allergies, meds, procedures, immunizations) template
render_files_to_dir(
    render=partial(renderer.render_fhir, "Pampi"),
    from_dir=sample_data_dir,
    to_dir=data_out_dir,
    path_filter=lambda p: p.suffix in (".ccda", ".xml"),
)


# Static / Dictonary loader
static_templates = {
    "RESULTS": """{
    "resourceType": "Bundle",
    "type": "batch",
    "entry": [ {% include 'Section/Result' %} ]
}"""
}
renderer = CcdaRenderer(
    env=get_environment(
        loader=DictLoader(templates=static_templates),
        additional_loaders=[ccda_default_loader],
    )
)
with from_file.open() as xml_in:
    # Render the results section with no patient / header information
    print(renderer.render_fhir_string("RESULTS", xml_in))