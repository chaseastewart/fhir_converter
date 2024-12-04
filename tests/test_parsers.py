from pathlib import Path
from unittest import TestCase

from lxml import etree
from json5 import JSON5DecodeError
from pytest import raises

from fhir_converter.parsers import ParseXmlOpts, parse_json, parse_xml, Hl7v2DataParser


class ParseJsonTest(TestCase):
    empty_file = Path("tests/data/empty.json")
    simple_file = Path("tests/data/simple.json")

    def test_empty_text(self) -> None:
        with raises(JSON5DecodeError):
            parse_json("")

    def test_blank_text(self) -> None:
        with raises(JSON5DecodeError):
            parse_json(" ")

    def test_empty_bytes(self) -> None:
        with raises(JSON5DecodeError):
            parse_json(bytes())

    def test_empty_text_io(self) -> None:
        with raises(JSON5DecodeError):
            with self.empty_file.open() as json_in:
                parse_json(json_in)

    def test_empty_binary_io(self) -> None:
        with raises(JSON5DecodeError):
            with self.empty_file.open("rb") as json_in:
                parse_json(json_in)

    def test_simple(self) -> None:
        self.assertEqual({"test": "ok"}, parse_json('{"test": "ok"}'))

    def test_simple_bytes(self) -> None:
        self.assertEqual({"test": "ok"}, parse_json(b'{"test": "ok"}'))

    def test_simple_text_io(self) -> None:
        with self.simple_file.open() as json_in:
            self.assertEqual(parse_json(json_in), {"test": "ok"})

    def test_simple_binary_io(self) -> None:
        with self.simple_file.open("rb") as json_in:
            self.assertEqual(parse_json(json_in), {"test": "ok"})

    def test_bytearray(self) -> None:
        self.assertEqual({"test": "ok"}, parse_json(bytearray(b'{"test": "ok"}')))

    def test_memoryview(self) -> None:
        self.assertEqual({"test": "ok"}, parse_json(memoryview(b'{"test": "ok"}')))

    def test_list_empty(self) -> None:
        self.assertEqual([], parse_json("[]"))

    def test_list_bool(self) -> None:
        self.assertEqual([True, False], parse_json("[true, false]"))

    def test_list_str(self) -> None:
        self.assertEqual(["ok"], parse_json("['', ' ', 'ok']"))

    def test_list_dict(self) -> None:
        self.assertEqual([{"test": "ok"}], parse_json('[{}, {"test": "ok"}]'))

    def test_list_nested_empty(self) -> None:
        self.assertEqual([], parse_json("[[[],[]]]"))

    def test_dict_empty(self) -> None:
        self.assertEqual({}, parse_json("{}"))

    def test_dict_bool(self) -> None:
        self.assertEqual({"test": False}, parse_json('{"test": false}'))

    def test_dict_str_empty(self) -> None:
        self.assertEqual({}, parse_json('{"test": ""}'))

    def test_dict_list_empty(self) -> None:
        self.assertEqual({}, parse_json('{"test": []}'))

    def test_dict_list_bool(self) -> None:
        self.assertEqual({"test": [True, False]}, parse_json('{"test": [true, false]}'))

    def test_dict_list_str(self) -> None:
        self.assertEqual({"test": ["ok"]}, parse_json('{"test": ["", " ", "ok"]}'))

    def test_dict_list_dict(self) -> None:
        self.assertEqual(
            {"test": [{"test": "ok"}]}, parse_json('{"test": [{}, {"test": "ok"}]}')
        )

    def test_dict_nested_empty(self) -> None:
        self.assertEqual({}, parse_json('{"test": {"test": {"test": {}}}}'))

    def test_dict_nested_str_empty(self) -> None:
        self.assertEqual({}, parse_json('{"name": [{"family": "","given": [""]}]}'))

    def test_dict_ignore_trailing_comma(self) -> None:
        expected = {"name": [{"family": "Relative", "given": ["Ralph"]}]}
        self.assertEqual(
            expected,
            parse_json('{"name": [{"family": "Relative","given": ["Ralph"]}],}'),
        )

    def test_dict_ignore_lead_trail_spaces(self) -> None:
        expected = {"name": [{"family": "Relative", "given": ["Ralph"]}]}
        self.assertEqual(
            expected,
            parse_json('   {"name": [{"family": "Relative","given": ["Ralph"]}]}   '),
        )

    def test_include_empty_fields(self) -> None:
        self.assertEqual(
            {"name": [{"family": "", "given": [""]}]},
            parse_json(
                '{"name": [{"family": "","given": [""]}]}', ignore_empty_fields=False
            ),
        )

    def test_include_empty_fields_nested(self) -> None:
        self.assertEqual(
            {},
            parse_json(
                '{"name": [{"family": "","given": [""]}]}', ignore_empty_fields=True
            ),
        )


class ParseXmlTest(TestCase):
    empty_file = Path("tests/data/empty.xml")
    simple_file = Path("tests/data/simple.xml")

    def test_empty_text(self) -> None:
        with raises(etree.XMLSyntaxError):
            parse_xml("")

    def test_blank_text(self) -> None:
        with raises(etree.XMLSyntaxError):
            parse_xml(" ")

    def test_empty_bytes(self) -> None:
        with raises(etree.XMLSyntaxError):
            parse_xml(bytes())

    def test_empty_text_io(self) -> None:
        with raises(etree.XMLSyntaxError):
            with self.empty_file.open() as xml_in:
                parse_xml(xml_in)

    def test_empty_binary_io(self) -> None:
        with raises(etree.XMLSyntaxError):
            with self.empty_file.open("rb") as xml_in:
                parse_xml(xml_in)

    def test_bytearray(self) -> None:
        with raises(TypeError):
            parse_xml(bytearray(b"<a>data</a>"))

    def test_memoryview(self) -> None:
        with raises(TypeError):
            parse_xml(memoryview(b"<a>data</a>"))

    def test_minimal(self) -> None:
        self.assertEqual(parse_xml("<a/>"), {"a": {}})

    def test_simple(self) -> None:
        self.assertEqual(parse_xml("<a>data</a>"), {"a": {"_": "data"}})

    def test_simple_bytes(self) -> None:
        self.assertEqual(parse_xml(b"<a>data</a>"), {"a": {"_": "data"}})

    def test_simple_path(self) -> None:
        self.assertEqual(parse_xml(self.simple_file), {"a": {"_": "data"}})

    def test_simple_text_io(self) -> None:
        with self.simple_file.open() as xml_in:
            self.assertEqual(parse_xml(xml_in), {"a": {"_": "data"}})

    def test_simple_binary_io(self) -> None:
        with self.simple_file.open("rb") as xml_in:
            self.assertEqual(parse_xml(xml_in), {"a": {"_": "data"}})

    def test_cdata_key(self) -> None:
        self.assertEqual(
            parse_xml("<a>data</a>", parse_opts=ParseXmlOpts(cdata_key="#text")),
            {"a": {"#text": "data"}},
        )

    def test_parse_filter(self) -> None:
        def filter_parse(element, parent, opts):
            return {} if element.tag == "b" else None

        self.assertEqual(
            parse_xml("<a><b>ignore</b><c>include</c></a>", parse_filter=filter_parse),
            {"a": {"c": {"_": "include"}}},
        )

    def test_after_parse(self) -> None:
        def after_parse(parsed_dict, tree, opts):
            a_dict = parsed_dict["a"]
            a_dict["after"] = "parse"
            return parsed_dict

        self.assertEqual(
            parse_xml("<a>data</a>", after_parse_xml=after_parse),
            {"a": {"_": "data", "after": "parse"}},
        )

    def test_list(self) -> None:
        self.assertEqual(
            parse_xml("<a><b>1</b><b>2</b><b>3</b></a>"),
            {"a": {"b": [{"_": "1"}, {"_": "2"}, {"_": "3"}]}},
        )

    def test_attrib(self) -> None:
        self.assertEqual(parse_xml('<a href="xyz"/>'), {"a": {"href": "xyz"}})

    def test_attrib_and_cdata(self) -> None:
        self.assertEqual(
            parse_xml('<a href="xyz">123</a>'), {"a": {"href": "xyz", "_": "123"}}
        )

    def test_semi_structured(self) -> None:
        self.assertEqual(parse_xml("<a>abc<b/>def</a>"), {"a": {"_": "abcdef"}})

    def test_nested_semi_structured(self) -> None:
        self.assertEqual(
            parse_xml("<a>abc<b>123<c/>456</b>def</a>"),
            {"a": {"_": "abcdef", "b": {"_": "123456"}}},
        )

    def test_sanitize_text(self) -> None:
        xml = """
        <root>  This text spans
            multiple lines, that should be sanitized.
            Line with trailing space </root>
        """
        self.assertEqual(
            parse_xml(xml),
            {
                "root": {
                    "_": "This text spans multiple lines, that should be sanitized. Line with trailing space"
                }
            },
        )

    def test_ignore_whitespace(self) -> None:
        xml = """
        <root>


          <emptya>           </emptya>
          <emptyb attr="attrvalue">


          </emptyb>
          <value>hello</value>
        </root>
        """
        self.assertEqual(
            parse_xml(xml),
            {"root": {"emptyb": {"attr": "attrvalue"}, "value": {"_": "hello"}}},
        )

    def test_keep_empty_root(self) -> None:
        self.assertEqual(parse_xml("<root></root>"), {"root": {}})

    def test_keep_blank_root(self) -> None:
        self.assertEqual(parse_xml("<root>      </root>"), {"root": {}})

    def test_namespace(self) -> None:
        xml = """
        <root xmlns="http://defaultns.com/"
              xmlns:a="http://a.com/"
              xmlns:b="http://b.com/"
              version="1.00">
          <x>1</x>
          <a:y>2</a:y>
          <b:z>3</b:z>
        </root>
        """
        d = {
            "root": {
                "xmlns": "http://defaultns.com/",
                "xmlns_a": "http://a.com/",
                "xmlns_b": "http://b.com/",
                "version": "1.00",
                "x": {"_": "1"},
                "a_y": {"_": "2"},
                "b_z": {"_": "3"},
            },
        }
        self.assertEqual(parse_xml(xml), d)

    def test_ignores_xmlbomb(self) -> None:
        xml = """
        <!DOCTYPE xmlbombz [
            <!ENTITY a "1234567890" >
            <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
        ]>
        <bomb>&b;</bomb>
        """
        self.assertEqual(parse_xml(xml), {"bomb": {}})

    def test_ignores_external_dtd(self) -> None:
        xml = """
        <!DOCTYPE external [
            <!ENTITY ee SYSTEM "http://www.python.org/">
        ]>
        <root>&ee;</root>
        """
        self.assertEqual(parse_xml(xml), {"root": {}})

    def test_ignores_xml_declaration(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><root/>"""
        self.assertEqual(parse_xml(xml), {"root": {}})

    def test_ignores_xml_stylesheet(self) -> None:
        xml = """<?xml-stylesheet type="text/xsl" href="CDA.xsl"?><root/>"""
        self.assertEqual(parse_xml(xml), {"root": {}})

    def test_ignores_comments(self) -> None:
        xml = """
        <!-- pre comment -->
        <a>
          <b>
            <!-- b comment -->
            <c>
                1
                <!-- c comment -->
            </c>
            <d><!-- d comment -->2</d>
            <e>3<!-- e comment -->4<!-- e comment -->5</e>
            <f><!-- f comment --></f>
          </b>
        </a>
        <!-- post comment -->
        """
        self.assertEqual(
            parse_xml(xml),
            {
                "a": {
                    "b": {
                        "c": {"_": "1"},
                        "d": {"_": "2"},
                        "e": {"_": "345"},
                    }
                }
            },
        )

class Hl7v2DataParserTest(TestCase):
    def test_parse_hl7v2(self) -> None:
        simple_file = Path("tests/data/hl7v2/ADT-A01-02.hl7")
        with simple_file.open() as hl7v2_in:
            hl7v2_str = hl7v2_in.read()
        hl7v2_parser = Hl7v2DataParser()
        hl7v2_data = hl7v2_parser.parse(hl7v2_str)

        self.assertEqual(hl7v2_str, hl7v2_data.message)
        # assert meta data = [MSH, EVN, PID, PV1]
        meta_data = ["MSH", "EVN", "PID", "PV1"]
        self.assertEqual(meta_data, hl7v2_data.meta)

        # assert encoding_chars = ["^", "~", "&", "\\", "|"]
        self.assertEqual("^", hl7v2_data.encoding_characters.component_separator)
        self.assertEqual("~", hl7v2_data.encoding_characters.repetition_separator)
        self.assertEqual("\\", hl7v2_data.encoding_characters.escape_character)
        self.assertEqual("&", hl7v2_data.encoding_characters.subcomponent_separator)

        # TODO: assert message_header = MSH
