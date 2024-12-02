from base64 import b64decode
from datetime import datetime, timezone
from unittest import TestCase
from zlib import decompress

from liquid import BoundTemplate, DictLoader, Environment
from liquid.exceptions import (
    FilterArgumentError,
    NoSuchFilterFunc,
    OutputStreamLimitError,
    TemplateNotFound,
)
from pytest import fixture, raises

from fhir_converter.filters import all_filters, register_filters
from fhir_converter.hl7 import Hl7DtmPrecision

from fhir_converter.parsers import Hl7v2Data, Hl7v2Segment, Hl7v2Field, Hl7v2Component
from fhir_converter.filters import _component_to_dict, _field_to_dict, _segment_to_dict, _get_segment_lists_internal

class FilterTest:
    """Base Test that doesn't extend TestCase to avoid the generic
    test(s) from being executed on the base"""

    template: str
    bound_template: BoundTemplate

    def setup_template(self, **kwargs) -> None:
        Environment.output_stream_limit = None
        env = Environment(**kwargs)
        register_filters(env, all_filters, replace=True)
        self.bound_template = env.from_string(self.template)

    def test_unregistered(self) -> None:
        with raises(NoSuchFilterFunc):
            env = Environment()
            env.filters.clear()
            env.from_string(self.template).render()


class ToJsonStringTest(TestCase, FilterTest):
    template = """{{ content | to_json_string }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_empty_content(self) -> None:
        result = self.bound_template.render(content="")
        self.assertEqual(result, "")

        result = self.bound_template.render(content={})
        self.assertEqual(result, "")

    def test_content(self) -> None:
        result = self.bound_template.render(content={"key": "val"})
        self.assertEqual(result, """{"key":"val"}""")


class ToArrayTest(TestCase, FilterTest):
    template = """
        {% assign keys = el.key | to_array -%}
        {% for key in keys -%}{{key}},{% endfor -%}
        """.strip()

    def setUp(self) -> None:
        self.setup_template()

    def test_list(self) -> None:
        result = self.bound_template.render(el={"key": ["one", "two", "three"]})
        self.assertEqual(result, "one,two,three,")

    def test_wrap(self) -> None:
        result = self.bound_template.render(el={"key": "one"})
        self.assertEqual(result, "one,")

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")


class MatchTest(TestCase, FilterTest):
    template = """{{data | match: "[0123456789.]+" | join}}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_match(self) -> None:
        result = self.bound_template.render(data="2.16.840.1.113883.6.1")
        self.assertEqual(result, "2.16.840.1.113883.6.1")

        result = self.bound_template.render(data="2.16,840.1.113883,6.1")
        self.assertEqual(result, "2.16 840.1.113883 6.1")

    def test_does_not_match(self) -> None:
        result = self.bound_template.render(data="nonumbers")
        self.assertEqual(result, "")

    def test_empty_string(self) -> None:
        result = self.bound_template.render(data="")
        self.assertEqual(result, "")

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")


class GzipTest(TestCase, FilterTest):
    template = """{{ content | gzip }}"""

    def setUp(self) -> None:
        self.setup_template()

    @staticmethod
    def decode(result: str = "") -> str:
        return decompress(b64decode(result)).decode()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual("", result)

    def test_empty_content(self) -> None:
        result = self.bound_template.render(content="")
        self.assertEqual("", result)

    def test_content(self) -> None:
        result = self.bound_template.render(content="test")
        self.assertEqual("test", self.decode(result))


class Sha1HashTest(TestCase, FilterTest):
    template = """{{ content | sha1_hash }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual("", result)

    def test_empty_content(self) -> None:
        result = self.bound_template.render(content="")
        self.assertEqual("", result)

    def test_content(self) -> None:
        result = self.bound_template.render(content="test")
        self.assertEqual(result, "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3")


class AddHyphensDateTest(TestCase, FilterTest):
    template = """{{ date | add_hyphens_date }}"""

    @fixture(autouse=True, scope="function")
    def hl7_to_fhir_dtm_mock(self, mocker):
        mocked = mocker.patch(
            "fhir_converter.filters.hl7_to_fhir_dtm",
            return_value="2024-01-10",
        )
        self._hl7_to_fhir_dtm_mock = mocked
        return mocked

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")
        self._hl7_to_fhir_dtm_mock.assert_not_called()

    def test_empty_date(self) -> None:
        result = self.bound_template.render(date="")
        self.assertEqual(result, "")
        self._hl7_to_fhir_dtm_mock.assert_not_called()

    def test_date(self) -> None:
        result = self.bound_template.render(date="20240110063457.920+0000")
        self.assertEqual(result, "2024-01-10")
        self._hl7_to_fhir_dtm_mock.assert_called_once_with(
            "20240110063457.920+0000", precision=Hl7DtmPrecision.DAY
        )


class FormatAsDateTimeTest(TestCase, FilterTest):
    template = """{{ date | format_as_date_time }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_empty_date(self) -> None:
        result = self.bound_template.render(date="")
        self.assertEqual(result, "")

    def test(self) -> None:
        result = self.bound_template.render(date="20240110063557.920+0000")
        self.assertEqual(result, "2024-01-10T06:35:57.920Z")


class DateTest(TestCase, FilterTest):
    template = """{{ dt | date: format }}"""
    iso_datetime_complete = "2014-10-09T11:58:10.001981+08:00"

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_format_undefined(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete)
        self.assertEqual(result, self.iso_datetime_complete)

    def test_format_empty_str(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="")
        self.assertEqual(result, self.iso_datetime_complete)

    def test_format_not_str(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format=[])
        self.assertEqual(result, self.iso_datetime_complete)

    def test_liquid_date_str(self) -> None:
        result = self.bound_template.render(dt="March 14, 2016", format="%b %d, %y")
        self.assertEqual(result, "Mar 14, 16")

    def test_liquid_date_datetime(self) -> None:
        result = self.bound_template.render(
            dt=datetime(2002, 1, 1, 11, 45, 13), format="%a, %b %d, %y"
        )
        self.assertEqual(result, "Tue, Jan 01, 02")

    def test_liquid_date_now(self) -> None:
        result = self.bound_template.render(dt="now", format="%Y")
        self.assertEqual(result, datetime.now().strftime("%Y"))

    def test_liquid_date_today(self) -> None:
        result = self.bound_template.render(dt="today", format="%Y")
        self.assertEqual(result, datetime.now().strftime("%Y"))

    def test_liquid_date_unsupported_format(self) -> None:
        result = self.bound_template.render(dt="today", format="YYYY")
        self.assertEqual(result, "YYYY")

    def test_unsupported_format(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="ffff")
        self.assertEqual(result, "ffff")

    def test_year(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="yyyy")
        self.assertEqual(result, "2014")

    def test_year_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%Y")
        self.assertEqual(result, "2014")

    def test_without_century(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%y")
        self.assertEqual(result, "14")

    def test_month(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="MM")
        self.assertEqual(result, "10")

    def test_month_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%m")
        self.assertEqual(result, "10")

    def test_month_locale(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%b")
        self.assertEqual(result, "Oct")

    def test_month_locale_full(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%B")
        self.assertEqual(result, "October")

    def test_day(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="dd")
        self.assertEqual(result, "09")

    def test_day_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%d")
        self.assertEqual(result, "09")

    def test_hour(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="HH")
        self.assertEqual(result, "11")

    def test_hour_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%H")
        self.assertEqual(result, "11")

    def test_minute(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="mm")
        self.assertEqual(result, "58")

    def test_minute_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%M")
        self.assertEqual(result, "58")

    def test_second(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="ss")
        self.assertEqual(result, "10")

    def test_second_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%S")
        self.assertEqual(result, "10")

    def test_milli(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="fff")
        self.assertEqual(result, "001")

    def test_micro(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="ffffff"
        )
        self.assertEqual(result, "001981")

    def test_micro_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%f")
        self.assertEqual(result, "001981")

    def test_k_specifier_tz_undefined(self) -> None:
        result = self.bound_template.render(dt="2014-10-09T11:58:10", format="%K")
        self.assertEqual(result, "")

    def test_k_specifier_tz_offset(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%K")
        self.assertEqual(result, "+08:00")

    def test_k_specifier_tz_offset_zero(self) -> None:
        result = self.bound_template.render(dt="2014-10-09T11:58:10+00:00", format="%K")
        self.assertEqual(result, "Z")

    def test_k_specifier_tz_utc(self) -> None:
        result = self.bound_template.render(dt="2014-10-09T11:58:10Z", format="%K")
        self.assertEqual(result, "Z")

    def test_tz_hour_min_offset(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="zzz")
        self.assertEqual(result, "+08:00")

    def test_tz_hour_min_offset_python(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="%z")
        self.assertEqual(result, "+0800")

    def test_tz_hour_offset(self) -> None:
        result = self.bound_template.render(dt=self.iso_datetime_complete, format="zz")
        self.assertEqual(result, "+08")

    def test_year_month(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM"
        )
        self.assertEqual(result, "2014-10")

    def test_year_month_day(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-dd"
        )
        self.assertEqual(result, "2014-10-09")

    def test_year_month_day_python(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="%Y-%m-%d"
        )
        self.assertEqual(result, "2014-10-09")

    def test_year_month_day_hour(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH"
        )
        self.assertEqual(result, "2014-10-09T11")

    def test_year_month_day_hour_minute(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH:mm"
        )
        self.assertEqual(result, "2014-10-09T11:58")

    def test_year_month_day_hour_minute_second(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH:mm:ss"
        )
        self.assertEqual(result, "2014-10-09T11:58:10")

    def test_year_month_day_hour_minute_second_python(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="%Y-%m-%dT%H:%M:%S"
        )
        self.assertEqual(result, "2014-10-09T11:58:10")

    def test_year_month_day_hour_minute_second_k_specifier(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH:mm:ss%K"
        )
        self.assertEqual(result, "2014-10-09T11:58:10+08:00")

    def test_year_month_day_hour_minute_second_milli(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH:mm:ss.fff"
        )
        self.assertEqual(result, "2014-10-09T11:58:10.001")

    def test_year_month_day_hour_minute_second_milli_k_specifier(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH:mm:ss.fff%K"
        )
        self.assertEqual(result, "2014-10-09T11:58:10.001+08:00")

    def test_year_month_day_hour_minute_second_milli_micro(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH:mm:ss.ffffff"
        )
        self.assertEqual(result, "2014-10-09T11:58:10.001981")

    def test_year_month_day_hour_minute_second_milli_micro_python(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="%Y-%m-%dT%H:%M:%S.%f"
        )
        self.assertEqual(result, "2014-10-09T11:58:10.001981")

    def test_year_month_day_hour_minute_second_milli_micro_k_specifier(self) -> None:
        result = self.bound_template.render(
            dt=self.iso_datetime_complete, format="yyyy-MM-ddTHH:mm:ss.ffffff%K"
        )
        self.assertEqual(result, "2014-10-09T11:58:10.001981+08:00")


class NowTest(TestCase, FilterTest):
    template = """{{ "" | now }}"""

    @fixture(autouse=True, scope="function")
    def to_fhir_dtm_mock(self, mocker):
        mocked = mocker.patch(
            "fhir_converter.filters.to_fhir_dtm", return_value="2024-01-10T06:34:57.920Z"
        )
        self._to_fhir_dtm_mock = mocked
        return mocked

    def setUp(self) -> None:
        self.setup_template()

    def test(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "2024-01-10T06:34:57.920Z")
        self._to_fhir_dtm_mock.assert_called_once()

        args, kwargs = self._to_fhir_dtm_mock.call_args
        self.assertDictEqual({}, kwargs)
        self.assertEqual(1, len(args))
        self.assertEqual(timezone.utc, args[0].tzinfo)


class GenerateUuidTest(TestCase, FilterTest):
    template = """{{ data | generate_uuid }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_uuid(self) -> None:
        result = self.bound_template.render(data="This is a test.")
        self.assertEqual(result, "08b9a802-08d3-5a58-a0ff-ad195172929b")


class GetPropertTest(TestCase, FilterTest):
    template = """{{ status | get_property: key, property }}"""

    template_globals: dict = {
        "code_mapping": {
            "RequestStatus": {
                "fatal": {"code": "severe", "display": "very severe"},
                "retry": {"other": "retrying", "code": "", "display": ""},
                "unknown": {"other": ""},
                "timeout": {},
                "__default__": {
                    "code": "bad",
                    "display": "very bad",
                    "other": "could be worse",
                },
            }
        }
    }

    def setUp(self) -> None:
        self.setup_template(globals=self.template_globals)

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_undefined_valueset_code(self) -> None:
        result = self.bound_template.render(status="undefined", key="Undefined")
        self.assertEqual(result, "undefined")

    def test_undefined_valueset_display(self) -> None:
        result = self.bound_template.render(
            status="undefined", key="Undefined", property="display"
        )
        self.assertEqual(result, "undefined")

    def test_undefined_valueset_other(self) -> None:
        result = self.bound_template.render(
            status="undefined", key="Undefined", property="other"
        )
        self.assertEqual(result, "")

    def test_valueset_default_code(self) -> None:
        result = self.bound_template.render(status="aborted", key="RequestStatus")
        self.assertEqual(result, "bad")

    def test_valueset_default_display(self) -> None:
        result = self.bound_template.render(
            status="aborted", key="RequestStatus", property="display"
        )
        self.assertEqual(result, "very bad")

    def test_valueset_default_other(self) -> None:
        result = self.bound_template.render(
            status="aborted", key="RequestStatus", property="other"
        )
        self.assertEqual(result, "could be worse")

    def test_valueset_undefined(self) -> None:
        result = self.bound_template.render(
            status="aborted", key="RequestStatus", property="undefined"
        )
        self.assertEqual(result, "")

    def test_valueset_code(self) -> None:
        result = self.bound_template.render(status="fatal", key="RequestStatus")
        self.assertEqual(result, "severe")

    def test_valueset_display(self) -> None:
        result = self.bound_template.render(
            status="fatal", key="RequestStatus", property="display"
        )
        self.assertEqual(result, "very severe")

    def test_valueset_other(self) -> None:
        result = self.bound_template.render(
            status="retry", key="RequestStatus", property="other"
        )
        self.assertEqual(result, "retrying")

    def test_valueset_code_blank(self) -> None:
        result = self.bound_template.render(
            status="retry", key="RequestStatus", property="code"
        )
        self.assertEqual(result, "")

    def test_valueset_display_blank(self) -> None:
        result = self.bound_template.render(
            status="retry", key="RequestStatus", property="display"
        )
        self.assertEqual(result, "")

    def test_valueset_other_blank(self) -> None:
        result = self.bound_template.render(
            status="unknown", key="RequestStatus", property="other"
        )
        self.assertEqual(result, "")

    def test_valueset_code_undefined_default(self) -> None:
        result = self.bound_template.render(
            status="unknown", key="RequestStatus", property="code"
        )
        self.assertEqual(result, "bad")

    def test_valueset_display_undefined_default(self) -> None:
        result = self.bound_template.render(
            status="unknown", key="RequestStatus", property="display"
        )
        self.assertEqual(result, "very bad")

    def test_valueset_empty_default_code(self) -> None:
        result = self.bound_template.render(
            status="timeout", key="RequestStatus", property="code"
        )
        self.assertEqual(result, "bad")

    def test_valueset_empty_default_display(self) -> None:
        result = self.bound_template.render(
            status="timeout", key="RequestStatus", property="display"
        )
        self.assertEqual(result, "very bad")


class GetFirstCcdaSectionsByTemplateIdTest(TestCase, FilterTest):
    template = """{{ msg | get_first_ccda_sections_by_template_id: template_ids }}"""

    msg: dict = {
        "ClinicalDocument": {
            "component": {
                "structuredBody": {
                    "component": [
                        {"section": {"templateId": [{"root": "2.2"}, {"root": "2.2.1"}]}},
                        {"section": {"templateId": [{"root": "2.6"}]}},
                        {"section": {"templateId": [{"root": "2.5.1"}]}},
                    ]
                }
            }
        }
    }

    def setUp(self) -> None:
        self.setup_template()

    def test_invalid_argument(self) -> None:
        with raises(FilterArgumentError):
            self.bound_template.render(msg="Not a dict", template_ids="2.6")

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "{}")

    def test_undefined_object(self) -> None:
        result = self.bound_template.render(template_ids="2.6")
        self.assertEqual(result, "{}")

    def test_undefined_parameter(self) -> None:
        result = self.bound_template.render(msg=self.msg)
        self.assertEqual(result, "{}")

    def test_empty(self) -> None:
        result = self.bound_template.render(msg={}, template_ids="2.6")
        self.assertEqual(result, "{}")

    def test_not_found(self) -> None:
        result = self.bound_template.render(msg=self.msg, template_ids="2.5")
        self.assertEqual(result, "{}")

    def test_found(self) -> None:
        result = self.bound_template.render(msg=self.msg, template_ids="2.6")
        self.assertEqual(
            result,
            "{'2_6': {'templateId': [{'root': '2.6'}]}}",
        )

    def test_multiple_found(self) -> None:
        result = self.bound_template.render(msg=self.msg, template_ids="2.6|2.2.1|2.2")
        self.assertEqual(
            result,
            " ".join(
                (
                    "{'2_6': {'templateId': [{'root': '2.6'}]}, '2_2_1':",
                    "{'templateId': [{'root': '2.2'}, {'root': '2.2.1'}]},",
                    "'2_2': {'templateId': [{'root': '2.2'}, {'root': '2.2.1'}]}}",
                )
            ),
        )


class GetCcdaSectionByTemplateIdTest(TestCase, FilterTest):
    template = """{{ msg | get_ccda_section_by_template_id: id, id2, id3 }}"""

    msg: dict = {
        "ClinicalDocument": {
            "component": {
                "structuredBody": {
                    "component": [
                        {"section": {"templateId": [{"root": "2.2"}, {"root": "2.2.1"}]}},
                        {"section": {"templateId": [{"root": "2.6"}]}},
                        {"section": {"templateId": [{"root": "2.5.1"}]}},
                    ]
                }
            }
        }
    }

    def setUp(self) -> None:
        self.setup_template()

    def test_invalid_argument(self) -> None:
        with raises(FilterArgumentError):
            self.bound_template.render(msg="Not a dict", id="2.6")

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "{}")

    def test_undefined_object(self) -> None:
        result = self.bound_template.render(id="2.6")
        self.assertEqual(result, "{}")

    def test_undefined_parameter(self) -> None:
        result = self.bound_template.render(msg=self.msg)
        self.assertEqual(result, "{}")

    def test_empty(self) -> None:
        result = self.bound_template.render(msg={}, id="2.6")
        self.assertEqual(result, "{}")

    def test_not_found(self) -> None:
        result = self.bound_template.render(msg=self.msg, id="2.5")
        self.assertEqual(result, "{}")

    def test_found(self) -> None:
        result = self.bound_template.render(msg=self.msg, id="2.6")
        self.assertEqual(
            result,
            "{'templateId': [{'root': '2.6'}]}",
        )

    def test_found_multiple_ids(self) -> None:
        result = self.bound_template.render(msg=self.msg, id="2.5", id2="2.6", id3="2.7")
        self.assertEqual(
            result,
            "{'templateId': [{'root': '2.6'}]}",
        )

    def test_found_flatten_ids(self) -> None:
        result = self.bound_template.render(
            msg=self.msg, id=["2.5"], id2=["2.7"], id3=["2.6"]
        )
        self.assertEqual(
            result,
            "{'templateId': [{'root': '2.6'}]}",
        )


class BatchRenderTest(TestCase, FilterTest):
    template = """{{ batch | batch_render: template, 'data' }}"""
    inner_template = """{{ data }}"""

    def setUp(self) -> None:
        self.setup_template(loader=DictLoader({"__template__": self.inner_template}))

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_empty(self) -> None:
        result = self.bound_template.render(batch=[])
        self.assertEqual(result, "")

    def test_str_to_list(self) -> None:
        result = self.bound_template.render(batch="one", template="__template__")
        self.assertEqual(result, "one,")

    def test_batch(self) -> None:
        result = self.bound_template.render(
            batch=["one", "two", "three"], template="__template__"
        )
        self.assertEqual(result, "one,two,three,")

    def test_batch_with_trailing_comma(self) -> None:
        result = self.bound_template.render(
            batch=["one,", "two,", "three,"], template="__template__"
        )
        self.assertEqual(result, "one,two,three,")

    def test_batch_with_trailing_comma_blank_space_line_endings(self) -> None:
        result = self.bound_template.render(
            batch=["one, \n", "two,  \n\n", "three,   \n\n\n"], template="__template__"
        )
        self.assertEqual(result, "one, \ntwo,  \n\nthree,   \n\n\n")

    def test_template_not_found(self) -> None:
        with raises(TemplateNotFound):
            self.bound_template.render(batch=["one"], template="undefined")

    def test_output_limit_reached(self) -> None:
        Environment.output_stream_limit = 3
        with raises(OutputStreamLimitError):
            self.bound_template.render(batch=["one"], template="__template__")

    def test_output_limit_not_reached(self) -> None:
        Environment.output_stream_limit = 4
        result = self.bound_template.render(batch=["one"], template="__template__")
        self.assertEqual(result, "one,")

class GenerateIdInputTest(TestCase, FilterTest):
    template = """{{ datas | generate_id_input: resource_name, based_id_required, base_id }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_empty(self) -> None:
        result = self.bound_template.render(data="")
        self.assertEqual(result, "")

    def test_data(self) -> None:
        result = self.bound_template.render(
            datas="This is a test.",
            resource_name = "Patient",
            base_id = "123",
            based_id_required=True)
        self.assertEqual(result, "PatientThis is a test.123")

class SignTest(TestCase, FilterTest):
    template = """{{ data | sign }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_empty(self) -> None:
        result = self.bound_template.render(data="")
        self.assertEqual(result, "")

    def test_data_positif(self) -> None:
        result = self.bound_template.render(data="1")
        self.assertEqual(result, "1")

    def test_data_negatif(self) -> None:
        result = self.bound_template.render(data="-1")
        self.assertEqual(result, "-1")

    def test_data_float(self) -> None:
        result = self.bound_template.render(data="1.5")
        self.assertEqual(result, "1")

    def test_data_zero(self) -> None:
        result = self.bound_template.render(data="0")
        self.assertEqual(result, "0")

class DivideTest(TestCase, FilterTest):
    template = """{{ data | divide: divisor }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_empty(self) -> None:
        result = self.bound_template.render(data="")
        self.assertEqual(result, "")

    def test_data_divisor(self) -> None:
        result = self.bound_template.render(data="1", divisor="2")
        self.assertEqual(result, "0.5")

    def test_data_divisor_zero(self) -> None:
        result = self.bound_template.render(data="1", divisor="0")
        self.assertEqual(result, "0")

    def test_data_divisor_negatif(self) -> None:
        result = self.bound_template.render(data="1", divisor="-2")
        self.assertEqual(result, "-0.5")

    def test_data_float(self) -> None:
        result = self.bound_template.render(data="1.5", divisor="2")
        self.assertEqual(result, "0.75")

    def test_data_zero(self) -> None:
        result = self.bound_template.render(data="0", divisor="2")
        self.assertEqual(result, "0.0")

class TruncateNumberTest(TestCase, FilterTest):
    template = """{{ data | truncate_number }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_undefined(self) -> None:
        result = self.bound_template.render()
        self.assertEqual(result, "")

    def test_empty(self) -> None:
        result = self.bound_template.render(data="")
        self.assertEqual(result, "")

    def test_data_precision(self) -> None:
        result = self.bound_template.render(data="1.123456789")
        self.assertEqual(result, "1")

class GetFristSegmentsTest(TestCase, FilterTest):
    template = """{{ data | get_first_segments: segment_list }}"""
    hl7v2_data = Hl7v2Data('')
    hl7v2_data.meta.append('MSH')
    hl7v2_data.data.append(Hl7v2Segment('Field', []))

    def setUp(self) -> None:
        self.setup_template()

    def test_data(self) -> None:
        result = self.bound_template.render(data=self.hl7v2_data, segment_list="MSH")
        self.assertTrue(result.startswith(r"{'MSH': {'Value': 'Field'}}"))

class GetSegmentListsTest(TestCase, FilterTest):
    template = """{{ data | get_segment_lists: segment }}"""
    hl7v2_data = Hl7v2Data('')
    hl7v2_data.meta.append('MSH')
    hl7v2_data.data.append(Hl7v2Segment('Field', []))

    def setUp(self) -> None:
        self.setup_template()

    def test_data(self) -> None:
        result = self.bound_template.render(data=self.hl7v2_data, segment="MSH")
        self.assertTrue(result.startswith(r"{'MSH': [{'Value': 'Field'}]}"))

class GetRelatedSegmentListTest(TestCase, FilterTest):
    template = """{{ data | get_related_segment_list: segments, related_segment_name }}"""

    def setUp(self) -> None:
        self.setup_template()

    def test_empty_data(self) -> None:
        hl7v2_data = Hl7v2Data('')
        result = self.bound_template.render(
            data=hl7v2_data, 
            segments={"Value": "MSH"}, 
            related_segment_name="EVN"
        )
        self.assertEqual(result, "{}")

    def test_no_matching_parent(self) -> None:
        hl7v2_data = Hl7v2Data('')
        hl7v2_data.meta.extend(['MSH', 'EVN'])
        hl7v2_data.data.extend([
            Hl7v2Segment('MSH Field', []),
            Hl7v2Segment('EVN Field', [])
        ])
        result = self.bound_template.render(
            data=hl7v2_data,
            segments={"Value": "PID"},  # Non-existent parent
            related_segment_name="EVN"
        )
        self.assertEqual(result, "{}")

    def test_no_matching_child(self) -> None:
        hl7v2_data = Hl7v2Data('')
        hl7v2_data.meta.extend(['MSH', 'EVN'])
        hl7v2_data.data.extend([
            Hl7v2Segment('MSH Field', []),
            Hl7v2Segment('EVN Field', [])
        ])
        result = self.bound_template.render(
            data=hl7v2_data,
            segments={"Value": "MSH Field"},
            related_segment_name="PID"  # Non-existent child
        )
        self.assertEqual(result, "{}")

    def test_single_child_segment(self) -> None:
        hl7v2_data = Hl7v2Data('')
        hl7v2_data.meta.extend(['MSH', 'EVN'])
        hl7v2_data.data.extend([
            Hl7v2Segment('MSH Field', []),
            Hl7v2Segment('EVN Field', [])
        ])
        result = self.bound_template.render(
            data=hl7v2_data,
            segments={"Value": "MSH Field"},
            related_segment_name="EVN"
        )
        self.assertEqual(result, "{'EVN': [{'Value': 'EVN Field'}]}")

    def test_multiple_child_segments(self) -> None:
        hl7v2_data = Hl7v2Data('')
        hl7v2_data.meta.extend(['MSH', 'EVN', 'EVN'])
        hl7v2_data.data.extend([
            Hl7v2Segment('MSH Field', []),
            Hl7v2Segment('EVN Field 1', []),
            Hl7v2Segment('EVN Field 2', [])
        ])
        result = self.bound_template.render(
            data=hl7v2_data,
            segments={"Value": "MSH Field"},
            related_segment_name="EVN"
        )
        self.assertEqual(
            result, 
            "{'EVN': [{'Value': 'EVN Field 1'}, {'Value': 'EVN Field 2'}]}"
        )

    def test_case_insensitive_matching(self) -> None:
        hl7v2_data = Hl7v2Data('')
        hl7v2_data.meta.extend(['MSH', 'evn'])  # lowercase EVN
        hl7v2_data.data.extend([
            Hl7v2Segment('MSH Field', []),
            Hl7v2Segment('EVN Field', [])
        ])
        result = self.bound_template.render(
            data=hl7v2_data,
            segments={"Value": "MSH Field"},
            related_segment_name="EVN"  # uppercase EVN
        )
        self.assertEqual(result, "{'EVN': [{'Value': 'EVN Field'}]}")

class GetParentSegmentTest(TestCase, FilterTest):
    template = """{{ data | get_parent_segment: child_segment_id, child_index, parent_segment_id }}"""
    hl7v2_data = Hl7v2Data('')
    hl7v2_data.meta.append('MSH')
    hl7v2_data.meta.append('EVN')
    hl7v2_data.data.append(Hl7v2Segment('Field', []))
    hl7v2_data.data.append(Hl7v2Segment('EVN', []))

    def setUp(self) -> None:
        self.setup_template()

    def test_data_not_found(self) -> None:
        result = self.bound_template.render(data=self.hl7v2_data, child_segment_id="MSH", child_index=0, parent_segment_id="EVN")
        self.assertTrue(result.startswith(r"{}"))

    def test_data_found(self) -> None:
        result = self.bound_template.render(data=self.hl7v2_data, child_segment_id="EVN", child_index=0, parent_segment_id="MSH")
        self.assertTrue(result.startswith(r"{'MSH': {'Value': 'Field'}}"))

class HasSegmentsTest(TestCase, FilterTest):
    template = """{{ data | has_segments: segment_name }}"""
    hl7v2_data = Hl7v2Data('')
    hl7v2_data.meta.append('MSH')
    hl7v2_data.meta.append('EVN')
    hl7v2_data.data.append(Hl7v2Segment('Field', []))
    hl7v2_data.data.append(Hl7v2Segment('EVN', []))

    def setUp(self) -> None:
        self.setup_template()

    def test_data_not_found(self) -> None:
        result = self.bound_template.render(data=self.hl7v2_data, segment_name="PID")
        self.assertEqual(result, 'false')

    def test_data_found(self) -> None:
        result = self.bound_template.render(data=self.hl7v2_data, segment_name="EVN")
        self.assertEqual(result, 'true')


class Hl7v2DataToDictTest(TestCase):
    def test_component_to_dict_without_sub(self) -> None:
        hl7v2_component_0 = Hl7v2Component('Component0', None)
        result = _component_to_dict(hl7v2_component_0)
        self.assertEqual(result, {'Value': 'Component0'})

    def test_component_to_dict_with_sub(self) -> None:
        hl7v2_subcomponent_0 = 'SubComponent0'
        hl7v2_subcomponent_1 = 'SubComponent1'
        hl7v2_component_0 = Hl7v2Component('Component0', [hl7v2_subcomponent_0, hl7v2_subcomponent_1])
        result = _component_to_dict(hl7v2_component_0)
        self.assertEqual(result, {'Value': 'Component0', '0': 'SubComponent0', '1': 'SubComponent1'})
        
    def test_field_to_dict(self) -> None:
        hl7v2_component_0 = Hl7v2Component('Component0', None)
        hl7v2_field_0 = Hl7v2Field('Field0', [hl7v2_component_0])
        result = _field_to_dict(hl7v2_field_0)
        self.assertEqual(result, {'Value': 'Field0', '0': {'Value': 'Component0'}})

    def test_segment_to_dict(self) -> None:
        hl7v2_component_0 = Hl7v2Component('Component0', None)
        hl7v2_field_0 = Hl7v2Field('Field0', [hl7v2_component_0])
        hl7v2_segment_0 = Hl7v2Segment('Segment0', [hl7v2_field_0])
        result = _segment_to_dict(hl7v2_segment_0)
        self.assertEqual(result, {'Value': 'Segment0', '0': {'Value': 'Field0', '0': {'Value': 'Component0'}}})

    def test_get_segment_lists_internal(self) -> None:
        hl7v2_component_0 = Hl7v2Component('Component0', None)
        hl7v2_field_0 = Hl7v2Field('Field0', [hl7v2_component_0])
        hl7v2_segment_0 = Hl7v2Segment('Segment0', [hl7v2_field_0])
        hl7v2_data = Hl7v2Data('')
        hl7v2_data.meta.append('Segment0')
        hl7v2_data.data.append(hl7v2_segment_0)
        result = _get_segment_lists_internal(hl7v2_data, 'Segment0')
        self.assertEqual(result, {'Segment0': [{'Value': 'Segment0', '0': {'Value': 'Field0', '0': {'Value': 'Component0'}}}]})
