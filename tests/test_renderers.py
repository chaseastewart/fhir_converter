from collections.abc import Mapping
from io import StringIO
from json import loads
from pathlib import Path
from typing import List, cast
from unittest import TestCase

from liquid import FileExtensionLoader
from liquid.utils import LRUCache
from lxml.etree import XMLSyntaxError
from json5 import JSON5DecodeError
from pytest import raises

from fhir_converter.hl7 import get_ccda_section
from fhir_converter.loaders import CachingTemplateSystemLoader, TemplateSystemLoader
from fhir_converter.renderers import (
    CcdaRenderer,
    RenderingError,
    Stu3FhirRenderer,
    ccda_default_loader,
    make_environment,
    stu3_default_loader,
)
from fhir_converter.utils import sanitize_str


class MakeEnvironmentTest(TestCase):
    def test_defaults(self) -> None:
        env = make_environment(loader=ccda_default_loader)
        self.assertFalse(env.auto_reload)
        self.assertIsNone(env.cache)

        self.assertIsInstance(env.loader, CachingTemplateSystemLoader)
        loader = cast(CachingTemplateSystemLoader, env.loader)
        self.assertFalse(loader.auto_reload)
        self.assertEqual([ccda_default_loader], loader.loaders)

        self.assertIsInstance(loader.cache, LRUCache)
        self.assertEqual(loader.cache.capacity, 300)  # type: ignore

    def test_auto_reload(self) -> None:
        env = make_environment(loader=ccda_default_loader, auto_reload=True)
        self.assertFalse(env.auto_reload)
        self.assertIsNone(env.cache)

        loader = cast(CachingTemplateSystemLoader, env.loader)
        self.assertTrue(loader.auto_reload)

    def test_cache_size(self) -> None:
        env = make_environment(loader=ccda_default_loader, cache_size=1)
        self.assertFalse(env.auto_reload)
        self.assertIsNone(env.cache)

        loader = cast(CachingTemplateSystemLoader, env.loader)
        self.assertEqual(loader.cache.capacity, 1)  # type: ignore

    def test_cache_disabled(self) -> None:
        env = make_environment(loader=ccda_default_loader, cache_size=0)
        self.assertFalse(env.auto_reload)
        self.assertIsNone(env.cache)
        self.assertIsInstance(env.loader, TemplateSystemLoader)

    def test_additional_loaders(self) -> None:
        loader = FileExtensionLoader(search_path="data/templates/ccda")
        env = make_environment(
            loader,
            additional_loaders=[ccda_default_loader],
        )
        self.assertEqual([loader, ccda_default_loader], env.loader.loaders)  # type: ignore


class Stu3FhirRendererTest(TestCase):
    stu3_file = Path("tests/data/stu3/Immunization.json")

    def _validate(self, fhir: Mapping) -> None:
        self.assertEqual(fhir["resourceType"], "Immunization")
        self.assertEqual(fhir["status"], "completed")
        self.assertNotIn("notGiven", fhir)
        # TODO validation!

    def _validate_str(self, fhir_str: str) -> None:
        self._validate(loads(fhir_str))

    def _validate_parse_json(self, fhir: Mapping) -> None:
        self.assertEqual(fhir["resourceType"], "Immunization")
        self.assertEqual(fhir["status"], "completed")
        self.assertEqual(fhir["notGiven"], False)

    def test_render_fhir_string_json_error(self) -> None:
        with raises(RenderingError, match="Failed to render FHIR") as exc_info:
            Stu3FhirRenderer().render_fhir_string("Immunization", "")
        self.assertIsInstance(exc_info.value.__cause__, JSON5DecodeError)

    def test_render_fhir_string_text(self) -> None:
        self._validate_str(
            Stu3FhirRenderer().render_fhir_string(
                "Immunization", self.stu3_file.read_text(encoding="utf-8")
            )
        )

    def test_render_fhir_string_bytes(self) -> None:
        self._validate_str(
            Stu3FhirRenderer().render_fhir_string(
                "Immunization", self.stu3_file.read_bytes()
            )
        )

    def test_render_fhir_string_text_io(self) -> None:
        with self.stu3_file.open(encoding="utf-8") as fhir_in:
            self._validate_str(
                Stu3FhirRenderer().render_fhir_string("Immunization", fhir_in)
            )

    def test_render_fhir_string_binary_io(self) -> None:
        with self.stu3_file.open("rb") as fhir_in:
            self._validate_str(
                Stu3FhirRenderer().render_fhir_string("Immunization", fhir_in)
            )

    def test_render_to_fhir_json_error(self) -> None:
        with raises(RenderingError, match="Failed to render FHIR") as exc_info:
            Stu3FhirRenderer().render_to_fhir("Immunization", "")
        self.assertIsInstance(exc_info.value.__cause__, JSON5DecodeError)

    def test_render_to_fhir_text(self) -> None:
        self._validate(
            Stu3FhirRenderer().render_to_fhir(
                "Immunization", self.stu3_file.read_text(encoding="utf-8")
            )
        )

    def test_render_to_fhir_bytes(self) -> None:
        self._validate(
            Stu3FhirRenderer().render_to_fhir("Immunization", self.stu3_file.read_bytes())
        )

    def test_render_to_fhir_text_io(self) -> None:
        with self.stu3_file.open(encoding="utf-8") as fhir_in:
            self._validate(Stu3FhirRenderer().render_to_fhir("Immunization", fhir_in))

    def test_render_to_fhir_binary_io(self) -> None:
        with self.stu3_file.open("rb") as fhir_in:
            self._validate(Stu3FhirRenderer().render_to_fhir("Immunization", fhir_in))

    def test_render_fhir_serialize_error(self) -> None:
        buffer = StringIO()
        buffer.close()

        with raises(RenderingError, match="Failed to serialize FHIR") as exc_info:
            with self.stu3_file.open(encoding="utf-8") as fhir_in:
                Stu3FhirRenderer().render_fhir("Immunization", fhir_in, buffer)
        self.assertIsInstance(exc_info.value.__cause__, ValueError)
        self.assertEqual(str(exc_info.value.__cause__), "I/O operation on closed file")

    def test_render_fhir_text(self) -> None:
        buffer = StringIO()
        Stu3FhirRenderer().render_fhir(
            "Immunization", self.stu3_file.read_text(encoding="utf-8"), buffer
        )
        self._validate_str(buffer.getvalue())

    def test_render_fhir_bytes(self) -> None:
        buffer = StringIO()
        Stu3FhirRenderer().render_fhir(
            "Immunization", self.stu3_file.read_bytes(), buffer
        )
        self._validate_str(buffer.getvalue())

    def test_render_env_provided(self) -> None:
        renderer = Stu3FhirRenderer(make_environment(loader=stu3_default_loader))
        self._validate(
            renderer.render_to_fhir(
                "Immunization", self.stu3_file.read_text(encoding="utf-8")
            )
        )

    def test_parse_text(self) -> None:
        self._validate_parse_json(
            Stu3FhirRenderer()._parse_stu3(self.stu3_file.read_text())
        )

    def test_parse_bytes(self) -> None:
        self._validate_parse_json(
            Stu3FhirRenderer()._parse_stu3(self.stu3_file.read_bytes())
        )

    def test_parse_text_io(self) -> None:
        with self.stu3_file.open(encoding="utf-8") as stu3_in:
            self._validate_parse_json(
                Stu3FhirRenderer()._parse_stu3(stu3_in, encoding="utf-8")
            )

    def test_parse_binary_io(self) -> None:
        with self.stu3_file.open("rb") as stu3_in:
            self._validate_parse_json(Stu3FhirRenderer()._parse_stu3(stu3_in))


class CcdaRendererTest(TestCase):
    ccda_file = Path("tests/data/ccda/History_and_Physical.ccda")

    @staticmethod
    def _get_resource(entries: List[Mapping], resource_type: str) -> Mapping:
        for entry in entries:
            resource = entry.get("resource", {})
            if resource and resource.get("resourceType", "") == resource_type:
                return resource
        return {}

    @staticmethod
    def _get_section(resource: Mapping, title: str) -> Mapping:
        for section in resource.get("section", []):
            if section.get("title", "") == title:
                return section
        return {}

    def _validate(self, fhir: Mapping, render_narrative: bool = False) -> None:
        self.assertEqual(fhir["resourceType"], "Bundle")
        self.assertEqual(fhir["type"], "batch")
        self.assertIsInstance(fhir["entry"], list)

        # TODO additional validation

        # immunizations
        immunization = self._get_resource(fhir["entry"], "Immunization")
        self.assertNotEqual(immunization, {})
        self.assertEqual(immunization["status"], "completed")
        self.assertEqual(immunization["lotNumber"], "1")

        # composition
        composition = self._get_resource(fhir["entry"], "Composition")
        self.assertNotEqual(composition, {})

        section = self._get_section(composition, "ALLERGIES, ADVERSE REACTIONS, ALERTS")
        self.assertNotEqual(section, {})

        self.assertEqual(
            section["code"],
            {
                "coding": [
                    {
                        "code": "48765-2",
                        "system": "http://loinc.org",
                    }
                ]
            },
        )

        if render_narrative:
            self.assertEqual(
                section["text"],
                {
                    "div": sanitize_str(
                        """<div xmlns="http://www.w3.org/1999/xhtml">
                        <table cellspacing="1" cellpadding="1" width="100%" border="1">
                            <thead>
                                <tr>
                                    <th>Substance</th>
                                    <th>Reaction</th>
                                    <th>Severity</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td>ALLERGENIC EXTRACT, PENICILLIN</td>
                                    <td><span id="reaction1">Nausea</span></td>
                                    <td><span id="severity1">Moderate to severe</span></td>
                                    <td>Inactive</td>
                                </tr>
                                <tr>
                                    <td>Codeine</td>
                                    <td><span id="reaction2">Wheezing</span></td>
                                    <td><span id="severity2">Moderate</span></td>
                                    <td>Active</td>
                                </tr>
                                <tr>
                                    <td>Aspirin</td>
                                    <td><span id="reaction3">Hives</span></td>
                                    <td><span id="severity3">Mild to moderate</span></td>
                                    <td>Active</td>
                                </tr>
                            </tbody>
                        </table></div>""",
                        repl="",
                    ),
                    "_status": {
                        "extension": [
                            {
                                "url": "http://hl7.org/fhir/StructureDefinition/data-absent-reason",
                                "valueCode": "unknown",
                            }
                        ]
                    },
                },
            )
        else:
            self.assertEqual(
                section["text"],
                {
                    "status": "generated",
                    "div": '<div xmlns="http://www.w3.org/1999/xhtml">ALLERGIES, ADVERSE REACTIONS, ALERTS</div>',
                },
            )

    def _validate_str(self, fhir_str: str) -> None:
        self._validate(loads(fhir_str))

    def _validate_parse_cda(self, xml: Mapping) -> None:
        self.assertIn("ClinicalDocument", xml)
        allergies = get_ccda_section(
            xml, search_template_ids="2.16.840.1.113883.10.20.22.2.6"
        )
        self.assertIsNotNone(allergies)
        self.assertEqual(
            allergies.get("code"),  # type: ignore
            {
                "code": "48765-2",
                "codeSystem": "2.16.840.1.113883.6.1",
                "codeSystemName": "LOINC",
            },
        )
        meds = get_ccda_section(
            xml, search_template_ids="2.16.840.1.113883.10.20.22.2.1.1"
        )
        self.assertIsNotNone(meds)
        self.assertEqual(
            meds.get("code"),  # type: ignore
            {
                "code": "10160-0",
                "codeSystem": "2.16.840.1.113883.6.1",
                "codeSystemName": "LOINC",
                "displayName": "HISTORY OF MEDICATION USE",
            },
        )
        # TODO additional validation

    def test_render_fhir_string_xml_error(self) -> None:
        with raises(RenderingError, match="Failed to render FHIR") as exc_info:
            CcdaRenderer().render_fhir_string("CCD", "")
        self.assertIsInstance(exc_info.value.__cause__, XMLSyntaxError)

    def test_render_fhir_string_text(self) -> None:
        self._validate_str(
            CcdaRenderer().render_fhir_string(
                "CCD", self.ccda_file.read_text(encoding="utf-8")
            )
        )

    def test_render_fhir_string_bytes(self) -> None:
        self._validate_str(
            CcdaRenderer().render_fhir_string("CCD", self.ccda_file.read_bytes())
        )

    def test_render_fhir_string_text_io(self) -> None:
        with self.ccda_file.open(encoding="utf-8") as xml_in:
            self._validate_str(CcdaRenderer().render_fhir_string("CCD", xml_in))

    def test_render_fhir_string_binary_io(self) -> None:
        with self.ccda_file.open("rb") as xml_in:
            self._validate_str(CcdaRenderer().render_fhir_string("CCD", xml_in))

    def test_render_to_fhir_xml_error(self) -> None:
        with raises(RenderingError, match="Failed to render FHIR") as exc_info:
            CcdaRenderer().render_to_fhir("CCD", "")
        self.assertIsInstance(exc_info.value.__cause__, XMLSyntaxError)
        self.assertEqual(
            str(exc_info.value.__cause__),
            "Document is empty, line 1, column 1 (<string>, line 1)",
        )

    def test_render_to_fhir_text(self) -> None:
        self._validate(
            CcdaRenderer().render_to_fhir(
                "CCD", self.ccda_file.read_text(encoding="utf-8")
            )
        )

    def test_render_to_fhir_bytes(self) -> None:
        self._validate(CcdaRenderer().render_to_fhir("CCD", self.ccda_file.read_bytes()))

    def test_render_to_fhir_text_io(self) -> None:
        with self.ccda_file.open(encoding="utf-8") as xml_in:
            self._validate(CcdaRenderer().render_to_fhir("CCD", xml_in))

    def test_render_to_fhir_binary_io(self) -> None:
        with self.ccda_file.open("rb") as xml_in:
            self._validate(CcdaRenderer().render_to_fhir("CCD", xml_in))

    def test_render_fhir_serialize_error(self) -> None:
        buffer = StringIO()
        buffer.close()

        with raises(RenderingError, match="Failed to serialize FHIR") as exc_info:
            with self.ccda_file.open(encoding="utf-8") as xml_in:
                CcdaRenderer().render_fhir("CCD", xml_in, buffer)
        self.assertIsInstance(exc_info.value.__cause__, ValueError)
        self.assertEqual(str(exc_info.value.__cause__), "I/O operation on closed file")

    def test_render_fhir_text(self) -> None:
        buffer = StringIO()
        CcdaRenderer().render_fhir(
            "CCD", self.ccda_file.read_text(encoding="utf-8"), buffer
        )
        self._validate_str(buffer.getvalue())

    def test_render_fhir_bytes(self) -> None:
        buffer = StringIO()
        CcdaRenderer().render_fhir("CCD", self.ccda_file.read_bytes(), buffer)
        self._validate_str(buffer.getvalue())

    def test_render_env_provided(self) -> None:
        self._validate(
            CcdaRenderer(make_environment(loader=ccda_default_loader)).render_to_fhir(
                "CCD", self.ccda_file.read_text(encoding="utf-8")
            )
        )

    def test_render_narrative_falsy(self) -> None:
        cda_xml = self.ccda_file.read_text(encoding="utf-8")

        self._validate(
            CcdaRenderer(template_globals={"render_narrative": False}).render_to_fhir(
                template_name="CCD", data_in=cda_xml
            ),
            render_narrative=False,
        )

        self._validate(
            CcdaRenderer(template_globals={"render_narrative": ""}).render_to_fhir(
                template_name="CCD", data_in=cda_xml
            ),
        )

        self._validate(
            CcdaRenderer(template_globals={"render_narrative": 0}).render_to_fhir(
                template_name="CCD", data_in=cda_xml
            ),
        )

    def test_render_narrative_truthy(self) -> None:
        cda_xml = self.ccda_file.read_text(encoding="utf-8")
        self._validate(
            CcdaRenderer(template_globals={"render_narrative": True}).render_to_fhir(
                template_name="CCD", data_in=cda_xml
            ),
            render_narrative=True,
        )

        self._validate(
            CcdaRenderer(template_globals={"render_narrative": 1}).render_to_fhir(
                template_name="CCD", data_in=cda_xml
            ),
            render_narrative=True,
        )

    def test_parse_cda_path(self) -> None:
        self._validate_parse_cda(CcdaRenderer()._parse_cda(data_in=self.ccda_file))

    def test_parse_cda_text(self) -> None:
        self._validate_parse_cda(
            CcdaRenderer()._parse_cda(data_in=self.ccda_file.read_text(encoding="utf-8"))
        )

    def test_parse_cda_bytes(self) -> None:
        self._validate_parse_cda(
            CcdaRenderer()._parse_cda(data_in=self.ccda_file.read_bytes())
        )

    def test_parse_cda_text_io(self) -> None:
        with self.ccda_file.open(encoding="utf-8") as xml_in:
            self._validate_parse_cda(
                CcdaRenderer()._parse_cda(data_in=xml_in, encoding="utf-8")
            )

    def test_parse_cda_binary_io(self) -> None:
        with self.ccda_file.open("rb") as xml_in:
            self._validate_parse_cda(CcdaRenderer()._parse_cda(data_in=xml_in))
