from typing import Dict, Iterable, Iterator, List, Tuple
from itertools import islice

from liquid.expressions.filtered.lex import tokenize
from liquid.expressions.filtered.parse import (
    Expression,
    TOKEN_MAP,
    TOKEN_IDENTIFIER,
    TOKEN_STRING,
    TOKEN_EOF,
    TOKEN_COLON,
    TokenStream,
    FilteredExpression,
    Filter,
    split_at_comma,
    split_at_first_pipe,
    split_at_pipe,
    Token,
)

from fhir_converter.expressions.common import (
    parse_identifier,
    parse_string_literal,
    LiquidSyntaxError
)

TOKEN_MAP.update({
    TOKEN_IDENTIFIER: parse_identifier,
    TOKEN_STRING: parse_string_literal,
})

def parse_obj(stream: TokenStream) -> Expression:
    """Parse an object from the stream of tokens.

    An object could be a constant, like `true` or `nil`, a range literal or an
    identifier. An identifier could be chained, possibly with nested identifiers
    between square brackets.
    """
    try:
        return TOKEN_MAP[stream.current[1]](stream)
    except KeyError as err:
        raise LiquidSyntaxError(
            f"unexpected {stream.current[2]!r}", linenum=stream.current[0]
        ) from err

def bucket_args(
    arguments: Iterable[Tuple[str, Expression]]
) -> Tuple[List[Expression], Dict[str, Expression]]:  # pragma: no cover
    """Split filter arguments into positional and keyword arguments."""
    args = []
    kwargs = {}
    for name, expr in arguments:
        if not name:
            args.append(expr)
        else:
            kwargs[name] = expr
    return args, kwargs


def parse_filter(tokens: List[Token], linenum: int = 1) -> Filter:  # pragma: no cover
    """Parse a Liquid filter from a list of tokens."""
    if not tokens:
        raise LiquidSyntaxError(
            "unexpected pipe or missing filter name", linenum=linenum
        )

    name = tokens[0][2]

    if len(tokens) > 1:
        if tokens[1][1] != TOKEN_COLON:
            raise LiquidSyntaxError(
                f"expected a colon after {name!r}",
                linenum=tokens[1][0],
            )
        return Filter(name, *bucket_args(parse_args(islice(tokens, 2, None))))
    return Filter(name, [])


def parse_args(
    tokens: Iterator[Token],
) -> Iterator[Tuple[str, Expression]]:  # pragma: no cover
    """Parse a filter's arguments from the given token iterator."""
    for arg_tokens in split_at_comma(tokens):
        yield parse_arg(arg_tokens)


def parse_arg(tokens: List[Token]) -> Tuple[str, Expression]:  # pragma: no cover
    """Parse a single argument from a list of tokens."""
    if len(tokens) > 1 and tokens[1][1] == TOKEN_COLON:
        # A named/keyword parameter/argument
        return tokens[0][2], parse_obj(TokenStream(islice(tokens, 2, None)))
    return "", parse_obj(TokenStream(iter(tokens)))


def parse_from_tokens(tokens: Iterator[Token], linenum: int = 1) -> FilteredExpression:
    """Parse an expression with zero or more filters from a token iterator."""
    parts = tuple(split_at_first_pipe(tokens))
    stream = TokenStream(iter(parts[0]))
    left = parse_obj(stream)

    if stream.peek[1] != TOKEN_EOF:
        raise LiquidSyntaxError(
            f"expected a filter or end of expression, found {stream.peek[2]!r}",
            linenum=stream.current[0],
        )

    if len(parts) == 1:
        return FilteredExpression(left)

    filters = [parse_filter(_tokens, linenum) for _tokens in split_at_pipe(parts[1])]
    return FilteredExpression(left, filters)


def parse(expr: str, linenum: int = 1) -> FilteredExpression:
    """Parse an expression string with zero or more filters."""
    return parse_from_tokens(tokenize(expr, linenum))