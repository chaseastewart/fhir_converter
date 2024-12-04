from fhir_converter.renderers import CcdaRenderer

with open("data/sample/ccda/CCD.ccda",mode="r",encoding="utf-8") as hl7v2_in:
    result = CcdaRenderer().render_fhir_string("CCD", hl7v2_in)
    print(result)