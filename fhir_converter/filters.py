from base64 import b64encode
from datetime import datetime, timezone
from functools import partial, wraps
from hashlib import sha1, sha256
from re import Match, Pattern
from re import compile as re_compile
from re import findall as re_findall
from typing import Any, Callable, Final, Iterable, List, Mapping, Sequence, Tuple
from uuid import UUID
from zlib import compress as z_compress

from dateutil import parser
from frozendict import frozendict
from isodate import isotzinfo, parse_datetime
from liquid import Environment
from liquid.builtin.filters.misc import date as liquid_date
from liquid.context import Context
from liquid.exceptions import FilterArgumentError
from liquid.filter import (
    flatten,
    liquid_filter,
    sequence_filter,
    string_filter,
    with_context,
    with_environment,
)
from pyjson5 import dumps as json_dumps

from fhir_converter.hl7 import (
    Hl7DtmPrecision,
    get_ccda_section,
    get_template_id_key,
    hl7_to_fhir_dtm,
    to_fhir_dtm,
)
from fhir_converter.utils import is_undefined_none_or_blank, tail, to_list_or_empty

FilterT = Callable[..., Any]
"""Callable[..., Any]: A liquid filter function"""

date_format_map: Final[Mapping[str, str]] = frozendict(
    {
        "yyyy": "%Y",
        "MM": "%m",
        "dd": "%d",
        "HH": "%H",
        "mm": "%M",
        "ss": "%S",
        "%K": "zzz",  # map directive to format code
    }
)
"""Mapping[str, str]: C# reference format to Python format map"""

strf_map: Final[Mapping[str, Callable[[datetime], str]]] = frozendict(
    {
        "ffffff": lambda dt: "%06d" % dt.microsecond,
        "fff": lambda dt: "%03d" % (dt.microsecond // 1000),
        "zzz": lambda dt: isotzinfo.tz_isoformat(dt, "%Z"),
        "zz": lambda dt: isotzinfo.tz_isoformat(dt, "%h"),
    }
)
"""Mapping[str, Callable[[datetime], str]]: Format to strf formatting map"""

format_pattern: Final[Pattern] = re_compile(
    "|".join(["y+", "M+", "d+", "H+", "m+", "s+", "%K"])
)
"""C# Date Format Regex Pattern"""

iso_format_pattern: Final[Pattern] = re_compile("|".join(["f+", "z+"]))
"""ISO format Regex Pattern"""


def _repl_format(m: Match) -> str:
    return date_format_map.get(m.group(0), m.group(0))


def _repl_strf_format(dt: datetime, m: Match) -> str:
    format_f = strf_map.get(m.group(0), None)
    if format_f is not None:
        return format_f(dt)
    return m.group(0)


def str_arg(val: Any, default: str = "") -> str:
    """Return `val` as an str or `default` if `val` is none or empty"""
    if is_undefined_none_or_blank(val):
        return default
    return str(val)


def mapping_filter(_filter: FilterT) -> FilterT:
    """Raise a `FilterValueError` if the left value is not mapping-like."""

    @wraps(_filter)
    def wrapper(val: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(val, Mapping):
            raise FilterArgumentError(f"expected a mapping, found {type(val).__name__}")
        return _filter(val, *args, **kwargs)

    return wrapper


@liquid_filter
def to_json_string(obj: Any) -> str:
    """Serialize the given object to json"""
    if is_undefined_none_or_blank(obj):
        return ""
    return json_dumps(obj)


@liquid_filter
def to_array(obj: Any) -> List[Any]:
    """Convert the given object to a list"""
    return to_list_or_empty(obj)


@string_filter
def match(data: str, regex: Any) -> List[str]:
    """Find all / match the regex in data"""
    if is_undefined_none_or_blank(data):
        return []
    return re_findall(str_arg(regex), data)


@string_filter
def gzip(data: str) -> str:
    """Compress the string using zlib base64 encoding the output"""
    if is_undefined_none_or_blank(data):
        return ""
    return b64encode(z_compress(data.encode())).decode()


@string_filter
def sha1_hash(data: str) -> str:
    """Compute the sha1 hash for the string"""
    if is_undefined_none_or_blank(data):
        return ""
    return sha1(data.encode()).hexdigest()


@string_filter
def add_hyphens_date(dtm: str) -> str:
    """Convert the hl7 v2 dtm to a FHIR hl7 v3 dtm with day precision"""
    if is_undefined_none_or_blank(dtm):
        return ""
    return hl7_to_fhir_dtm(dtm, precision=Hl7DtmPrecision.DAY)


@string_filter
def format_as_date_time(dtm: str) -> str:
    """Convert the hl7 v2 dtm to a FHIR hl7 v3 dtm"""
    if is_undefined_none_or_blank(dtm):
        return ""
    return hl7_to_fhir_dtm(dtm)


@string_filter
def now(_: str) -> str:
    """The current date time in UTC as a FHIR hl7 v3 dtm"""
    return to_fhir_dtm(datetime.now(timezone.utc))


@with_environment
@liquid_filter
def date(
    input: Any,
    format: Any,
    *,
    environment: Environment,
) -> str:
    """date Format the given input date with the provided format

    Compatibility:
    This filter losely attempts to bridge templates migrating from DotLiquid
    that use the C# date format codes. This only works for strings that
    can be parsed to a datetime. The special strings such as today or int
    values are suppported. Not all possible C# format codes are supported

    Args:
        input (Any): The input date to format
        format (Any): The format string
        environment (Environment): The rendering environment

    Returns:
        str: the formatted date
    """
    if is_undefined_none_or_blank(input):
        return input

    format = str_arg(format)
    if not format:
        return input
    format = format_pattern.sub(_repl_format, format)

    dat = input
    if isinstance(dat, str):
        if dat in ("now", "today"):
            dat = datetime.now()
        else:
            try:
                dat = parse_datetime(dat)  # strictly iso8601
            except Exception:
                try:
                    dat = parser.parse(dat)  # a bit more flexibility
                except Exception:
                    pass

    formatted = liquid_date(dat, format, environment=environment)
    if not isinstance(dat, datetime):
        return formatted
    return iso_format_pattern.sub(
        partial(_repl_strf_format, dat),
        formatted,
    )


@string_filter
def generate_uuid(data: str) -> str:
    """Generate a UUID using the sha256 hash of the given data string"""
    if is_undefined_none_or_blank(data):
        return ""
    return str(UUID(bytes=sha256(data.encode()).digest()[:16]))


@with_context
@string_filter
def get_property(
    code: str, mapping_key: Any, property_name: Any = None, *, context: Context
) -> str:
    """get_property Get the codified property mapping from the ``code_mapping`` global in
    the supplied context. ``mapping_key`` indicates the type of mapping.  Mappings may be
    provided for specific codes and or at a default / global level. Mappings for the code
    are prefered over the default mappings. In the event a mapping is not available, the
    original code will be used when property_name is code or display, otherwise, ""


    Args:
        code (str): the codified value
        mapping_key (Any): the type of mappings
        property_name (Any): the mapped property to retrieve. Defaults to code.
        context (Context): the rendering context

    Returns:
        str: the property or ""
    """
    property = str_arg(property_name, default="code")
    mapping = context.resolve("code_mapping", default={}).get(str_arg(mapping_key), None)
    if mapping:
        code_mapping = mapping.get(code, None)
        if not code_mapping or property not in code_mapping:
            code_mapping = mapping.get("__default__", {})

        mapped_code = code_mapping.get(property, None)
        if mapped_code is not None:
            return mapped_code

    return code if property in ("code", "display") else ""


@liquid_filter
@mapping_filter
def get_first_ccda_sections_by_template_id(msg: Mapping, template_ids: Any) -> Mapping:
    """get_first_ccda_sections_by_template_id Get the sections that match the given
    template_ids. All matches will be returned

    Key/value pairs will be returned where the key is the template_id that matched and the
    value is the corresponding section

    Args:
        msg (Mapping[Any, Any]): the msg / ccda document to search
        template_ids (Any): the template_id(s) delimited by | to search the document with

    Returns:
        Mapping[Any, Any]: the sections, otherwise, empty
    """
    sections, search_template_ids = {}, str_arg(template_ids).split("|")
    for template_id in search_template_ids:
        section = get_ccda_section(msg, search_template_ids=[template_id])
        if section:
            sections[get_template_id_key(template_id)] = section
    return sections


@liquid_filter
@mapping_filter
def get_ccda_section_by_template_id(
    msg: Mapping[Any, Any], template_id: Any, *template_ids: Any
) -> Mapping[Any, Any]:
    """get_ccda_section_by_template_id Get the section that matches one
    of the given template_ids. The first section found will be returned

    Args:
        msg (Mapping[Any, Any]): the msg / ccda document to search
        template_id (Any): the template_id(s) to search the document with

    Returns:
        Mapping[Any, Any]: the section, otherwise, empty
    """
    search_template_ids = [template_id]
    if template_ids:
        search_template_ids += template_ids
    search_template_ids = list(map(str_arg, flatten(search_template_ids)))
    section = get_ccda_section(msg, search_template_ids)
    return section or {}


@with_context
@sequence_filter
def batch_render(
    batch: Sequence[Any], template_name: Any, arg_name: Any, *, context: Context
) -> str:
    """batch_render Render the given batch data with the supplied template passing
    the data in the batch as the specified arg / parameter name to the template

    This function is similar to ``{% render template_name for batch as arg_name %}``

    See https://shopify.dev/docs/api/liquid/tags/render for more information

    Args:
        batch (Sequence): the array to render
        template_name (Any): the template to use
        arg_name (Any): the argument / parameter name
        context (Context): the rendering context

    Returns:
        str: the rendered output
    """
    if is_undefined_none_or_blank(batch):
        return ""
    template = context.get_template_with_context(str_arg(template_name))
    with context.get_buffer() as buffer:
        for data in batch:
            with context.extend(namespace={str_arg(arg_name): data}, template=template):
                template.render_with_context(context, buffer, partial=True)
            last_n = tail(buffer).rstrip()
            if last_n and not last_n.endswith(","):
                buffer.write(",")
        return buffer.getvalue()


all_filters: Sequence[Tuple[str, FilterT]] = [
    ("to_json_string", to_json_string),
    ("to_array", to_array),
    ("match", match),
    ("gzip", gzip),
    ("sha1_hash", sha1_hash),
    ("add_hyphens_date", add_hyphens_date),
    ("format_as_date_time", format_as_date_time),
    ("now", now),
    ("date", date),
    ("generate_uuid", generate_uuid),
    ("get_property", get_property),
    ("get_first_ccda_sections_by_template_id", get_first_ccda_sections_by_template_id),
    ("get_ccda_section_by_template_id", get_ccda_section_by_template_id),
    ("batch_render", batch_render),
]
"""Sequence[tuple[str, FilterT]]: All of the filters provided by the module"""


def register_filters(
    env: Environment, filters: Iterable[Tuple[str, FilterT]], replace: bool = False
) -> None:
    """register_filters Registers the given filters with the supplied Environment. Will not
    replace a filter with the same name already registered with the environment.

    Args:
        env (Environment): the environment
        filters (Iterable[tuple[str, FilterT]]): the filters to register
        replace (bool, optional): whether to replace existing filters. Defaults to False
    """
    it = filters if replace else filter(lambda f: f[0] not in env.filters, filters)
    for name, func in it:
        env.add_filter(name, func)
