# Python FHIR Converter Change Log

## Version 0.4.0
- Add support for HL7v2 to FHIR conversion. See [#12](https://github.com/chaseastewart/fhir-converter/pull/12)

## Version 0.3.0
- Render narrative text from the CDA to xhtml to include in the Composition resource. See [#11](https://github.com/chaseastewart/fhir-converter/issues/11)
- Fix bug in CDA to R4 Immunization template to correctly map lotNumberText to lotNumber.

## Version 0.2.0
- Map C-CDA Allergy to FHIR Allergy Intolerance Category. See [#6](https://github.com/chaseastewart/fhir-converter/issues/6)
- Renamed `render_to_fhir_internal` to `render` to simplify `BaseFhirRenderer` API.

## Version 0.1.0
- Fixed missing required AllergyIntolerance.reaction.manifestation for CDA->FHIR conversion. [_AllergyIntolerance.liquid](https://github.com/chaseastewart/fhir-converter/blob/69ca8f81cade9a480e624e09bfa3c4aa1663a2bf/fhir_converter/templates/ccda/Resource/_AllergyIntolerance.liquid#L23) incorrectly created an additional reaction for the severity. See [#3](https://github.com/chaseastewart/fhir-converter/issues/3)
- Remove time when timezone is not present in CDA datetime to conform with FHIR datetime.  See [#2](https://github.com/chaseastewart/fhir-converter/issues/2)
- Added `CachingTemplateSystemLoader`. `TemplateSystemLoader` now extends `ChoiceLoader` to better align with `python-liquid`.
- Added `make_template_system_loader()`, a factory function that returns a `TemplateSystemLoader` or `CachingTemplateSystemLoader` depending on its arguments.
- Renamed `get_environment` factory function to `make_environment` to align with a consistent naming convention.
- Moved `RenderingError` and `fail` to exceptions.py.
- Removed deprecated `ResourceLoader` and `CachedChoiceLoader`. 
- Now depends on [python-liquid](https://pypi.org/project/python-liquid/) = 1.12.1.

## Version 0.0.22
- `ResourceLoader` and `CachedChoiceLoader` are depreciated and will be removed in 0.1.0. Use `PackageLoader` and `CachingChoiceLoader` instead.
- Run tests on mac, windows and ubuntu.
- Now depends on [python-liquid](https://pypi.org/project/python-liquid/) = 1.11.0.