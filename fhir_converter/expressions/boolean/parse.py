from liquid.expressions.boolean.lex import tokenize

from liquid.expressions.boolean.parse import (
    BooleanExpression,
    Expression,
    PRECEDENCE_LOWEST,
    PRECEDENCES,
    TOKEN_EOF,
    TOKEN_MAP,
    BINARY_OPERATORS,
    TOKEN_IDENTIFIER,
    TOKEN_STRING,
    TOKEN_LBRACKET,
    InfixExpression
)

from liquid.expressions.stream import TokenStream

from fhir_converter.expressions.common import (
    parse_identifier,
    parse_string_literal,
    LiquidSyntaxError,
)

TOKEN_MAP.update({
    TOKEN_IDENTIFIER: parse_identifier,
    TOKEN_STRING: parse_string_literal,
    TOKEN_LBRACKET: parse_identifier,
})

def parse(expr: str, linenum: int = 1) -> BooleanExpression:
    """Parse a string as a "standard" boolean expression."""
    return BooleanExpression(parse_obj(TokenStream(tokenize(expr, linenum))))

def parse_obj(
    stream: TokenStream,
    precedence: int = PRECEDENCE_LOWEST,
) -> Expression:
    """Parse the next object from the stream of tokens.

    This object parser is for "standard" boolean expressions. It does not
    handle logical `not` or grouping with parentheses.
    """
    try:
        left = TOKEN_MAP[stream.current[1]](stream)
    except KeyError as err:
        raise LiquidSyntaxError(
            f"unexpected {stream.current[2]!r}",
            linenum=stream.current[0],
        ) from err

    while True:
        peek_typ = stream.peek[1]
        if (
            peek_typ == TOKEN_EOF
            or PRECEDENCES.get(peek_typ, PRECEDENCE_LOWEST) < precedence
        ):
            break

        if peek_typ not in BINARY_OPERATORS:
            return left

        next(stream)
        left = parse_infix_expression(stream, left)

    return left

def parse_infix_expression(stream: TokenStream, left: Expression) -> InfixExpression:
    """Parse an infix expression from a stream of tokens."""
    tok = stream.current
    precedence = PRECEDENCES.get(tok[1], PRECEDENCE_LOWEST)
    stream.next_token()
    return InfixExpression(
        left=left,
        operator=tok[2],
        right=parse_obj(stream, precedence),
    )