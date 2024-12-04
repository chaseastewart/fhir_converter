from typing import Optional
from unittest import TestCase

from liquid import BoundTemplate, DictLoader, Environment
from liquid.ast import ChildNode
from liquid.exceptions import LiquidSyntaxError, TemplateNotFound
from liquid.expression import Identifier, IdentifierPathElement, StringLiteral
from liquid.loaders import BaseLoader
from pyjson5 import Json5Exception
from pytest import raises

from fhir_converter.tags import EvaluateNode, MergeDiffNode, all_tags, register_tags
from fhir_converter.expressions import parse_loop_expression

def get_template(
    source: str,
    register: bool = True,
    loader: Optional[BaseLoader] = None,
) -> BoundTemplate:
    env = Environment(loader=loader)
    if register:
        register_tags(env, all_tags)
    return env.from_string(source)


class MergeDiffTest(TestCase):
    missing_endmerge = "{% mergeDiff var -%}"
    missing_identifier = "{% mergeDiff -%}{% endmergeDiff -%}"
    block = "{% mergeDiff var -%}{{block}}{% endmergeDiff -%}"

    def test_unregistered(self) -> None:
        with raises(LiquidSyntaxError, match="unexpected tag 'mergeDiff'"):
            get_template(source=self.block, register=False).render()

    def test_missing_endmerge(self) -> None:
        with raises(LiquidSyntaxError, match="expected tag with value 'endmergeDiff'"):
            get_template(source=self.missing_endmerge).render()

    def test_missing_identifier(self) -> None:
        with raises(LiquidSyntaxError, match="expected 'expression', found 'tag'"):
            get_template(source=self.missing_identifier).render()

    def test_invalid(self) -> None:
        with raises(Json5Exception):
            template = get_template(source=self.block)
            template.render(var={"test": "ok"}, block="{test:ok}")

    def test_empty(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(template.render(var={"test": "ok"}, block=""), '{"test":"ok"}')

    def test_space(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(template.render(var={"test": "ok"}, block=" "), '{"test":"ok"}')

    def test_empty_quote(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(template.render(var={"test": "ok"}, block='""'), '{"test":"ok"}')

    def test_str(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(var={"test": "ok"}, block='"failed"'),
            '{"test":"ok"}',
        )

    def test_variable_undefined(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(template.render(block={"test": "ok"}), "{}")

    def test_variable_str(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(template.render(var="ok", block={"test": "ok"}), '"ok"')

    def test_add(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(len(template.tree.statements), 1)

        node = template.tree.statements[0]
        self.assertIsInstance(node, MergeDiffNode)

        self.assertEqual(
            repr(node),
            "MergeDiff(tok=Token(linenum=1, type='tag', value='mergeDiff') identifier=var)",
        )
        self.assertEqual(str(node), "mergeDiff var { `block` }")
        self.assertTrue(len(node.children()) > 0)
        self.assertEqual(template.render(var={}, block={"test": "add"}), '{"test":"add"}')

    def test_update(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(var={"test": "ok"}, block={"test": "update"}),
            '{"test":"update"}',
        )

    def test_remove(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(var={"test": "ok"}, block={"test": ""}), '{"test":""}'
        )

    def test_empty_dict(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(template.render(var={"test": "ok"}, block={}), '{"test":"ok"}')

    def test_empty_dicts(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(template.render(var={}, block={}), "{}")

    def test_choice_update(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(var={"test_first": "ok"}, block={"test[x]": "update"}),
            '{"test_first":"update"}',
        )

    def test_choice_update_first(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(
                var={"test_first": "ok", "test_second": "failed"},
                block={"test[x]": "update"},
            ),
            '{"test_first":"update","test_second":"failed"}',
        )

    def test_choice_remove(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(var={"test_first": "ok"}, block={"test[x]": ""}),
            '{"test_first":""}',
        )

    def test_choice_remove_first(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(
                var={"test_first": "ok", "test_second": "failed"}, block={"test[x]": ""}
            ),
            '{"test_first":"","test_second":"failed"}',
        )

    def test_choice_remove_multiple(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(
                var={"test_first": "ok", "test_second": "failed"},
                block={"test_f[x]": "", "test_s[x]": ""},
            ),
            '{"test_first":"","test_second":""}',
        )

    def test_choice_ignore(self) -> None:
        template = get_template(source=self.block)
        self.assertEqual(
            template.render(var={"other": "unknown"}, block={"test[x]": "ok"}),
            '{"other":"unknown"}',
        )


class EvaluateTest(TestCase):
    missing_keyword = "{% evaluate var 'nosuchthing' -%}"
    not_found = "{% evaluate var using 'nosuchthing' -%}"
    no_arg = "{% evaluate var using 'no_arg' -%}{{ var }}"
    single_arg = "{% evaluate var using 'single_arg' arg1: val -%}{{ var }}"
    missing_comma = "{% evaluate var using 'multi_arg' arg1: val1 arg2: val2 -%}"
    multi_arg = "{% evaluate var using 'multi_arg' arg1: val1, arg2: val2 -%}{{ var }}"
    hl7v2_arg = "{% evaluate var using 'hl7v2' arg1: val.\"10\" -%}{{ var }}"

    loader = DictLoader(
        {
            "no_arg": "ok",
            "single_arg": "{{ arg1 }}",
            "multi_arg": "{{ arg1 }}, {{ arg2 }}",
            "hl7v2": "{{ arg1 }}"
        }
    )

    def test_unregistered(self) -> None:
        with raises(LiquidSyntaxError):
            get_template(source=self.no_arg, register=False).render()

    def test_template_not_found(self) -> None:
        with raises(TemplateNotFound):
            get_template(source=self.not_found).render()

    def test_missing_keyword(self) -> None:
        with raises(LiquidSyntaxError):
            get_template(source=self.missing_keyword).render()

    def test_missing_comma(self) -> None:
        with raises(LiquidSyntaxError):
            get_template(source=self.missing_comma).render(val1="test", val2="ok")

    def test_no_arg(self) -> None:
        template = get_template(source=self.no_arg, loader=self.loader)
        self.assertEqual(len(template.tree.statements), 2)

        node = template.tree.statements[0]
        self.assertIsInstance(node, EvaluateNode)
        self.assertEqual(
            repr(node),
            "EvaluateNode(tok=Token(linenum=1, type='tag', value='evaluate'), name=var)",
        )
        self.assertEqual(str(node), "evaluate(var using 'no_arg')")
        self.assertEqual(
            node.children(),
            [
                ChildNode(
                    linenum=1,
                    expression=StringLiteral(value="no_arg"),
                    template_scope=["var"],
                    block_scope=[],
                    load_mode="include",
                    load_context={"tag": "evaluate"},
                )
            ],
        )

        self.assertEqual(template.render(), "ok")

    def test_single_arg(self) -> None:
        template = get_template(source=self.single_arg, loader=self.loader)
        self.assertEqual(len(template.tree.statements), 2)

        node = template.tree.statements[0]
        self.assertIsInstance(node, EvaluateNode)
        self.assertEqual(str(node), "evaluate(var using 'single_arg', arg1=val)")
        self.assertEqual(
            node.children(),
            [
                ChildNode(
                    linenum=1,
                    expression=StringLiteral(value="single_arg"),
                    template_scope=["var"],
                    block_scope=["arg1"],
                    load_mode="include",
                    load_context={"tag": "evaluate"},
                ),
                ChildNode(
                    linenum=1,
                    expression=Identifier(path=[IdentifierPathElement(value="val")]),
                ),
            ],
        )

        self.assertEqual(template.render(val="test"), "test")

    def test_multiple_args(self) -> None:
        template = get_template(source=self.multi_arg, loader=self.loader)
        self.assertEqual(len(template.tree.statements), 2)

        node = template.tree.statements[0]
        self.assertIsInstance(node, EvaluateNode)
        self.assertEqual(
            str(node),
            "evaluate(var using 'multi_arg', arg1=val1, arg2=val2)",
        )
        self.assertEqual(
            node.children(),
            [
                ChildNode(
                    linenum=1,
                    expression=StringLiteral(value="multi_arg"),
                    template_scope=["var"],
                    block_scope=["arg1", "arg2"],
                    load_mode="include",
                    load_context={"tag": "evaluate"},
                ),
                ChildNode(
                    linenum=1,
                    expression=Identifier(path=[IdentifierPathElement(value="val1")]),
                ),
                ChildNode(
                    linenum=1,
                    expression=Identifier(path=[IdentifierPathElement(value="val2")]),
                ),
            ],
        )

        self.assertEqual(template.render(val1="test", val2="ok"), "test, ok")

    def test_hl7v2_arg(self) -> None:
        template = get_template(source=self.hl7v2_arg, loader=self.loader)
        self.assertEqual(len(template.tree.statements), 2)

        node = template.tree.statements[0]
        self.assertIsInstance(node, EvaluateNode)
        self.assertEqual(
            str(node),
            "evaluate(var using 'hl7v2', arg1=val.10)",
        )
        self.assertEqual(
            node.children(),
            [
                ChildNode(
                    linenum=1,
                    expression=StringLiteral(value="hl7v2"),
                    template_scope=["var"],
                    block_scope=["arg1"],
                    load_mode="include",
                    load_context={"tag": "evaluate"},
                ),
                ChildNode(
                    linenum=1,
                    expression=Identifier(
                        path=[
                            IdentifierPathElement(value="val"),
                            IdentifierPathElement(value="10"),
                        ]
                    ),
                ),
            ],
        )

        self.assertEqual(template.render(val={'10':'test'}), "test")

class HL7v2LoopTest(TestCase):

    
    
    def get_hl7v2_template(
        self,
        source: str,
        register: bool = True,
        loader: Optional[BaseLoader] = None,
    ) -> BoundTemplate:
        env = Environment(loader=loader)
        env.parse_loop_expression_value = parse_loop_expression
        if register:
            register_tags(env, all_tags)
        return env.from_string(source)
    
