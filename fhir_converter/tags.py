from functools import partial
from sys import intern
from typing import Any, Iterable, List, Mapping, Optional, Sequence, TextIO, Tuple, Type

from liquid import Environment
from liquid.ast import BlockNode, ChildNode, Node
from liquid.context import Context
from liquid.exceptions import LiquidSyntaxError
from liquid.expression import Expression
from liquid.expressions import TokenStream as ExprTokenStream
from liquid.expressions.filtered.lex import tokenize
from liquid.lex import _compile_rules, _tokenize, include_expression_rules
from liquid.parse import expect, get_parser
from liquid.stream import TokenStream
from liquid.tag import Tag
from liquid.token import (
    TOKEN_BLANK,
    TOKEN_COLON,
    TOKEN_COMMA,
    TOKEN_EMPTY,
    TOKEN_EOF,
    TOKEN_EXPRESSION,
    TOKEN_FALSE,
    TOKEN_IDENTIFIER,
    TOKEN_NIL,
    TOKEN_NULL,
    TOKEN_TAG,
    TOKEN_TRUE,
    Token,
)
from liquid.undefined import is_undefined

from fhir_converter.expressions.common import parse_unchained_identifier, parse_string_or_identifier, parse_obj

from pyjson5 import encode_io
from pyjson5 import loads as json_loads

TAG_MERGE_DIFF = intern("mergeDiff")
TAG_ENDMERGE_DIFF = intern("endmergeDiff")
ENDMERGE_DIFFBLOCK = frozenset((TAG_ENDMERGE_DIFF, TOKEN_EOF))

TAG_EVALUATE = intern("evaluate")
TOKEN_USING = intern("using")

evaluate_expression_keywords = frozenset(
    [
        TOKEN_TRUE,
        TOKEN_FALSE,
        TOKEN_NIL,
        TOKEN_NULL,
        TOKEN_EMPTY,
        TOKEN_BLANK,
        TOKEN_USING,
    ]
)

tokenize_evaluate_expression = partial(
    _tokenize,
    rules=_compile_rules(include_expression_rules),
    keywords=evaluate_expression_keywords,
)


class MergeDiffNode(Node):
    """Parse tree node for the "mergeDiff" tag."""

    __slots__ = ("tok", "identifier", "block")

    def __init__(self, tok: Token, identifier: str, block: BlockNode) -> None:
        self.tok = tok
        self.identifier = identifier
        self.block = block

    def __str__(self) -> str:
        return f"mergeDiff {self.identifier} {{ {self.block} }}"

    def __repr__(self) -> str:
        return f"MergeDiff(tok={self.tok!r} identifier={self.identifier})"

    @staticmethod
    def __merge(a: Any, b: Any) -> Any:
        if isinstance(a, dict) and isinstance(b, dict):
            for k, v in b.items():
                if isinstance(k, str) and k.endswith("[x]"):
                    choice_name = k[:-3]
                    choices = [ak for ak in a.keys() if ak.startswith(choice_name)]
                    if choices:
                        a[choices[0]] = v
                else:
                    a[k] = v
        return a

    def render_to_output(self, context: Context, buffer: TextIO) -> Optional[bool]:
        original = context.resolve(self.identifier)
        if not is_undefined(original):
            buf = context.get_buffer(buffer)
            if self.block.render(context, buf):
                val = buf.getvalue()
                if val and not val.isspace():
                    self.__merge(original, json_loads(val))

        encode_io(
            original,
            fp=buffer,  # type: ignore
            supply_bytes=False,
        )
        return True

    def children(self) -> List[ChildNode]:
        return self.block.children()


class MergeDiffTag(Tag):
    """The "mergeDiff" tag."""

    name = TAG_MERGE_DIFF
    end = TAG_ENDMERGE_DIFF
    node_class = MergeDiffNode

    def __init__(self, env: Environment) -> None:
        super().__init__(env)
        self.parser = get_parser(self.env)

    def parse(self, stream: TokenStream) -> Node:
        expect(stream, TOKEN_TAG, value=TAG_MERGE_DIFF)
        tok = stream.current
        stream.next_token()

        expect(stream, TOKEN_EXPRESSION)
        identifier = parse_unchained_identifier(
            ExprTokenStream(tokenize(stream.current.value))
        )
        stream.next_token()

        block = self.parser.parse_block(stream, ENDMERGE_DIFFBLOCK)
        expect(stream, TOKEN_TAG, value=TAG_ENDMERGE_DIFF)
        return self.node_class(
            tok=tok,
            identifier=str(identifier),
            block=block,
        )


class EvaluateNode(Node):
    """Parse tree node for the built-in "evaluate" tag."""

    __slots__ = ("tok", "name", "template_name", "args")
    tag = TAG_EVALUATE

    def __init__(
        self,
        tok: Token,
        name: str,
        template_name: Expression,
        args: Optional[Mapping[str, Expression]] = None,
    ) -> None:
        self.tok = tok
        self.name = name
        self.template_name = template_name
        self.args = args or {}

    def __str__(self) -> str:
        buf = [f"{self.name}", f" using {self.template_name}"]

        if self.args:
            buf.append(", ")
        args = (f"{key}={val}" for key, val in self.args.items())
        buf.append(", ".join(args))

        return f"{self.tag}({''.join(buf)})"

    def __repr__(self) -> str:
        return f"EvaluateNode(tok={self.tok!r}, name={self.name})"

    def render_to_output(self, context: Context, _: TextIO) -> Optional[bool]:
        template_name = str(self.template_name.evaluate(context))
        template = context.get_template_with_context(template_name, tag=self.tag)

        namespace = {}
        for _key, _val in self.args.items():
            namespace[_key] = _val.evaluate(context)

        with context.get_buffer() as buffer:
            with context.extend(namespace, template=template):
                template.render_with_context(context, buffer, partial=True)
                context.assign(key=self.name, val=buffer.getvalue().strip())

        return False

    def children(self) -> List[ChildNode]:
        block_scope = list(self.args.keys())
        _children = [
            ChildNode(
                linenum=self.tok.linenum,
                node=None,
                expression=self.template_name,
                template_scope=[self.name],
                block_scope=block_scope,
                load_mode="include",
                load_context={"tag": "evaluate"},
            )
        ]
        for expr in self.args.values():
            _children.append(ChildNode(linenum=self.tok.linenum, expression=expr))
        return _children


class EvaluateTag(Tag):
    """The "evaluate" tag."""

    name = TAG_EVALUATE
    block = False
    node_class = EvaluateNode

    @staticmethod
    def __parse_argument(stream: ExprTokenStream) -> Tuple[str, Expression]:
        key = str(parse_unchained_identifier(stream))
        stream.next_token()
        stream.expect(TOKEN_COLON)
        stream.next_token()  # Eat colon
        val = parse_obj(stream)
        stream.next_token()
        return key, val

    def parse(self, stream: TokenStream) -> Node:
        """Read an EvaluateNode from the given stream of tokens."""
        tok = next(stream)
        expect(stream, TOKEN_EXPRESSION)

        expr_stream = ExprTokenStream(tokenize_evaluate_expression(stream.current.value))
        name = str(parse_string_or_identifier(expr_stream))
        next(expr_stream)

        if expr_stream.current[1] != TOKEN_USING:
            raise LiquidSyntaxError(
                f'invalid evaluate expression "{stream.current.value}"',
                linenum=stream.current.linenum,
            )
        next(expr_stream)

        template_name = parse_string_or_identifier(expr_stream)
        next(expr_stream)

        args = {}
        if expr_stream.current[1] == TOKEN_IDENTIFIER:
            key, val = self.__parse_argument(expr_stream)
            args[key] = val

        while expr_stream.current[1] != TOKEN_EOF:
            if expr_stream.current[1] == TOKEN_COMMA:
                next(expr_stream)  # Eat comma
                key, val = self.__parse_argument(expr_stream)
                args[key] = val
            else:
                typ = expr_stream.current[1]
                raise LiquidSyntaxError(
                    f"expected a comma separated list of arguments, found {typ}",
                    linenum=tok.linenum,
                )

        return self.node_class(tok, name=name, template_name=template_name, args=args)


all_tags: Sequence[Type[Tag]] = [EvaluateTag, MergeDiffTag]
"""Sequence[type[Tag]]: All of the tags provided by the module"""


def register_tags(env: Environment, tags: Iterable[Type[Tag]]) -> None:
    """register_tags Adds the given tags to the Environment as long as a tag
    with the same name has not already been added

    Args:
        env (Environment): The rendering environment
        tags (Iterable[type[Tag]]): The tags to register / add
    """
    for tag in filter(lambda tag: tag.name not in env.tags, tags):
        env.add_tag(tag)
