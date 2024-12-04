from typing import Union
from typing import TYPE_CHECKING

from liquid.expression import Expression
from liquid.expression import StringLiteral

from liquid.expressions.filtered.parse import TOKEN_MAP

from liquid.expressions.common import (
    parse_string_literal,
    reverse_operators,
    Identifier,
    IdentifierPath,
    IdentifierPathElement,
    to_int,
    LiquidSyntaxError,
    TOKEN_IDENTIFIER,
    TOKEN_INTEGER,
    TOKEN_STRING,
    TOKEN_IDENTINDEX,
    TOKEN_LBRACKET,
    TOKEN_FLOAT,
    TOKEN_DOT,
    TOKEN_RBRACKET,
)

if TYPE_CHECKING:
    from liquid.expressions.stream import TokenStream


def parse_identifier(stream: "TokenStream") -> Identifier:
    """Read an identifier from the token stream.

    An identifier might be chained with dots and square brackets, and might contain
    more, possibly chained, identifiers within those brackets.
    """
    path: IdentifierPath = []

    while True:
        pos, typ, val = stream.current
        if typ == TOKEN_IDENTIFIER or typ == TOKEN_INTEGER or typ == TOKEN_STRING:
            path.append(IdentifierPathElement(val))
        elif typ == TOKEN_IDENTINDEX:
            path.append(IdentifierPathElement(to_int(val)))
        elif typ == TOKEN_LBRACKET:
            stream.next_token()
            path.append(parse_identifier(stream))
            # Eat close bracket
            stream.next_token()
            stream.expect(TOKEN_RBRACKET)
        elif typ == TOKEN_FLOAT:
            raise LiquidSyntaxError(
                f"expected an identifier, found {val!r}",
                linenum=pos,
            )
        elif typ == TOKEN_DOT:
            pass
        else:
            stream.push(stream.current)
            break

        stream.next_token()

    return Identifier(path)

def parse_string_or_identifier(
    stream: "TokenStream",
) -> Union[StringLiteral, Identifier]:
    """Parse an expression from a stream of tokens.

    If the stream is not at a string or identifier expression, raise a syntax error.
    """
    typ = stream.current[1]
    if typ in (TOKEN_IDENTIFIER, TOKEN_LBRACKET):
        expr: Union[StringLiteral, Identifier] = parse_identifier(stream)
    elif typ == TOKEN_STRING:
        expr = parse_string_literal(stream)
    else:
        _typ = reverse_operators.get(typ, typ)
        msg = f"expected identifier or string, found {_typ}"
        raise LiquidSyntaxError(msg, linenum=stream.current[0])

    return expr


def parse_unchained_identifier(stream: "TokenStream") -> Identifier:
    """Parse an identifier from a stream of tokens.

    If the stream is not at an identifier or the identifier is chained, raise a syntax
    error.
    """
    tok = stream.current
    ident = parse_identifier(stream)
    if len(ident.path) != 1:
        raise LiquidSyntaxError(f"invalid identifier '{ident}'", linenum=tok[0])
    return ident

TOKEN_MAP[TOKEN_IDENTIFIER] = parse_identifier
TOKEN_MAP[TOKEN_LBRACKET] = parse_identifier

def parse_obj(stream: "TokenStream") -> Expression:
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
