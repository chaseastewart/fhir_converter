from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import IntEnum
from math import copysign
from re import Pattern
from re import compile as re_compile
from re import sub as re_sub
from typing import Any, Dict, Final, Mapping, NamedTuple, Optional, Sequence

from fhir_converter.parsers import parse_json
from fhir_converter.utils import merge_dict, to_list_or_empty

dtm_pattern: Final[Pattern] = re_compile(r"(\d+(?:\.\d*)?)(?:([+-]\d{2})(\d{2}))?")
"""Final[Pattern]: The HL7 DTM REGEX for parsing date / times """

zero_time_delta: Final[timedelta] = timedelta(0)
"""Final[timedelta]: Timedelta of zero"""


class FhirDtmPrecision(IntEnum):
    """FhirDtmPrecision A precision associated with a FHIR DTM"""

    YEAR = 4
    MONTH = 7
    DAY = 10
    HOUR = 13
    MIN = 16
    SEC = 19
    MILLIS = 21

    @property
    def timespec(self) -> str:
        """timespec The timespec for the precision

        See datetime.isoformat

        Returns:
            str: The timespec
        """
        return "milliseconds" if self > FhirDtmPrecision.SEC else "seconds"


class Hl7DtmPrecision(IntEnum):
    """FhirDtmPrecision A precision associated with a HL7 DTM"""

    YEAR = 4
    MONTH = 6
    DAY = 8
    HOUR = 10
    MIN = 12
    SEC = 14
    MILLIS = 16

    @property
    def fhir_precision(self) -> FhirDtmPrecision:
        """fhir_precision The corresponding FHIR precision

        Returns:
            FhirDtmPrecision: The precision
        """
        return FhirDtmPrecision[self.name]

    @staticmethod
    def from_dtm(dtm: str) -> Hl7DtmPrecision:
        """from_dtm Gets the precision for the DTM

        Args:
            dtm (str): The hl7 DTM

        Raises:
            ValueError: If the dtm is malformed

        Returns:
            Hl7DtmPrecision: The precision of the DTM
        """
        _len = len(dtm)
        if _len >= Hl7DtmPrecision.MILLIS:
            return Hl7DtmPrecision.MILLIS
        elif _len == Hl7DtmPrecision.SEC:
            return Hl7DtmPrecision.SEC
        elif _len == Hl7DtmPrecision.MIN:
            return Hl7DtmPrecision.MIN
        elif _len == Hl7DtmPrecision.HOUR:
            return Hl7DtmPrecision.HOUR
        elif _len == Hl7DtmPrecision.DAY:
            return Hl7DtmPrecision.DAY
        elif _len == Hl7DtmPrecision.MONTH:
            return Hl7DtmPrecision.MONTH
        elif _len == Hl7DtmPrecision.YEAR:
            return Hl7DtmPrecision.YEAR
        raise ValueError("Malformed HL7 datetime {0}".format(dtm))


class Hl7ParsedDtm(NamedTuple):
    """Hl7ParsedDtm The parsed DTM

    Attributes:
        precision (Hl7DtmPrecision): The precision
        dt (datetime): The datetime
    """

    precision: Hl7DtmPrecision
    dt: datetime


def parse_hl7_dtm(hl7_input: str) -> Hl7ParsedDtm:
    """parse_hl7_dtm Parse the given hl7 input string to a ``Hl7ParsedDtm``

    Args:
        hl7_input (str): The hl7 string to parse

    Raises:
        ValueError: when the provided hl7_input is malformed

    Returns:
        The parsed ``Hl7ParsedDtm``
    """
    dt_match = dtm_pattern.match(hl7_input.strip())
    if not dt_match:
        raise ValueError("Malformed HL7 datetime {0}".format(hl7_input))

    dtm = dt_match.group(1)
    tzh = dt_match.group(2)
    tzm = dt_match.group(3)
    if tzh and tzm:
        minutes = int(tzh) * 60.0
        minutes += copysign(int(tzm), minutes)
        tzinfo = timezone(timedelta(minutes=minutes))
    else:
        tzinfo = None

    precision = Hl7DtmPrecision.from_dtm(dtm)
    year = int(dtm[: Hl7DtmPrecision.YEAR])

    if precision >= Hl7DtmPrecision.MONTH:
        month = int(dtm[Hl7DtmPrecision.YEAR : Hl7DtmPrecision.MONTH])
    else:
        month = 1

    if precision >= Hl7DtmPrecision.DAY:
        day = int(dtm[Hl7DtmPrecision.MONTH : Hl7DtmPrecision.DAY])
    else:
        day = 1

    if precision >= Hl7DtmPrecision.HOUR:
        hour = int(dtm[Hl7DtmPrecision.DAY : Hl7DtmPrecision.HOUR])
    else:
        hour = 0

    if precision >= Hl7DtmPrecision.MIN:
        minute = int(dtm[Hl7DtmPrecision.HOUR : Hl7DtmPrecision.MIN])
    else:
        minute = 0

    if precision >= Hl7DtmPrecision.SEC:
        delta = timedelta(seconds=float(dtm[Hl7DtmPrecision.MIN :]))
        second, microsecond = delta.seconds, delta.microseconds
    else:
        second = 0
        microsecond = 0

    return Hl7ParsedDtm(
        precision,
        dt=datetime(year, month, day, hour, minute, second, microsecond, tzinfo=tzinfo),
    )


def hl7_to_fhir_dtm(dtm: str, precision: Optional[Hl7DtmPrecision] = None) -> str:
    """hl7_to_fhir_dtm Converts the given hl7 dtm to an ISO equivalent string optionally
    truncating the precision to the provided specifity as long as the dtm has precision
    greater than or equal to the provided specifity

    Precision:
    Hour, Minute and Second truncation is not implemented

    Args:
        dtm (str): The hl7 dtm
        precision (Optional[FhirDtmPrecision], optional): The output precision. When None
        is provided, the precision of the dtm is used. Defaults to None

    Returns:
        The ISO date time string
    """
    parsed_dtm = parse_hl7_dtm(dtm)
    if precision is None or precision > parsed_dtm.precision:
        precision = parsed_dtm.precision

    return to_fhir_dtm(
        dt=parsed_dtm.dt,
        precision=precision.fhir_precision,
    )


def to_fhir_dtm(dt: datetime, precision: Optional[FhirDtmPrecision] = None) -> str:
    """to_fhir_dtm Converts the given datetime to an ISO equivalent string optionally
    truncating the precision to the provided specifity

    Precision:
    Hour, Minute and Second truncation is not implemented

    Args:
        dt (datetime): The datetime
        precision (Optional[FhirDtmPrecision], optional): The FHIR precision. When None
        is provided, SEC will be used. Defaults to None

    Returns:
        The ISO date time string
    """
    if precision is None:
        precision = FhirDtmPrecision.DAY

    iso_dtm, offset = dt.isoformat(timespec=precision.timespec), dt.utcoffset()

    # if offset is zero, we must append Z instead of +00:00
    if offset == zero_time_delta:
        iso_dtm = iso_dtm[:-6] + "Z"

    # if precision is greater than day, and iso_dtm is midnight, we must append Z
    if precision > FhirDtmPrecision.DAY and iso_dtm.endswith("T00:00:00"):
        iso_dtm += "Z"
        
    # if precision is day, we must remove the time part
    if precision == FhirDtmPrecision.DAY:
        return iso_dtm[:precision]
    else:
        return iso_dtm

def post_process_fhir(json_data: str) -> Any:
    """post_process_fhir Post processes the FHIR object
    1/ if we have two concecutively entries with the same resourceType
    and the second entry has only extensions, we merge the extensions into the first entry

    Args:
        json_data (Any): The FHIR object

    Returns:
        The post processed FHIR object
    """
    init = parse_fhir(json_data)
    if isinstance(init, dict):
        entries = to_list_or_empty(init.get("entry", []))
        for i in range(1, len(entries)-1):
            if entries[i - 1].get("resource", {}).get("resourceType") == entries[i].get("resource", {}).get("resourceType"):
                if "extension" in entries[i].get("resource", {}):
                    merge_extension(entries[i - 1], entries[i])
                    del entries[i]
    return init


def parse_fhir(json_input: str) -> Any:
    """parse_fhir Parses the given json input string to a FHIR object. In
    the event of a FHIR bundle an attempt will be made to merge duplicate
    entries for the same entity

    See merge_dict for more information

    Args:
        json_input (str): The json input string

    Returns:
        The FHIR object
    """
    json_data = parse_json(json_input)
    if isinstance(json_data, dict):
        entries = to_list_or_empty(json_data.get("entry", []))
        if len(entries) > 1:
            unique_entrys: Dict[str, Dict] = {}
            for entry in entries:
                key = get_fhir_entry_key(entry)
                if key in unique_entrys:
                    merge_dict(unique_entrys[key], entry)
                else:
                    unique_entrys[key] = entry
            json_data["entry"] = list(unique_entrys.values())
    return json_data

def merge_extension(entry:dict, extension: dict) -> None:
    """merge_extension Merges the given extension into the FHIR entry

    Args:
        entry (Mapping): The FHIR entry
        extension (Mapping): The extension to merge
    """
    if "extension" in entry["resource"]:
        merge_dict(entry["resource"], extension["resource"])
    else:
        entry["resource"]["extension"] = extension["resource"]["extension"]

def get_fhir_entry_key(entry: Mapping[str, dict]) -> str:
    """get_fhir_entry_key Gets the unique key for the given FHIR
    bundle entry

    Key:
    Combination of resourceType, meta.versionId and id. Fields are
    allowed to be missing or empty

    Args:
        entry (Mapping): The FHIR bundle entry

    Returns:
        The unique key for the entry, otherwise, empty string
    """
    resource = entry.get("resource", {})
    return "_".join(
        filter(
            None,
            (
                resource.get("resourceType", ""),
                resource.get("meta", {}).get("versionId", ""),
                resource.get("id", ""),
            ),
        )
    )


def get_ccda_section(
    ccda: Mapping[Any, Any], search_template_ids: Sequence[str]
) -> Optional[Mapping[Any, Any]]:
    """get_ccda_section Gets the POCD_MT000040.Section
    from the ClinicalDocument that matches one of the templateIds

    See https://github.com/HL7/CDA-core-2.0/tree/master/schema

    Args:
        ccda (Mapping): The ccda document as a map
        search_template_ids (Sequence): The templateIds

    Returns:
        The section from the document if present
    """
    if search_template_ids:
        if isinstance(search_template_ids, str):
            search_template_ids = [search_template_ids]
        for component in get_ccda_component3(ccda):
            for id in get_component3_section_templateId(component):
                for template_id in search_template_ids:
                    if is_template_id(id, template_id):
                        return component["section"]
    return None


def get_ccda_component3(ccda: Mapping[Any, Any]) -> Sequence[Any]:
    """get_ccda_component3 Gets the POCD_MT000040.Component3
    from the ClinicalDocument.

    See https://github.com/HL7/CDA-core-2.0/tree/master/schema

    Args:
        ccda (Mapping): The ccda document as a map

    Returns:
        The Component3 elements from the document, otherwise []
    """
    return to_list_or_empty(
        ccda.get("ClinicalDocument", {})
        .get("component", {})
        .get("structuredBody", {})
        .get("component", [])
    )


def get_component3_section_templateId(component: Mapping[Any, Any]) -> Sequence[Any]:
    """get_component3_section_template_id Gets the templateId
    from the POCD_MT000040.Component3.

    See https://github.com/HL7/CDA-core-2.0/tree/master/schema

    Args:
        component (Mapping): The component3 as a map

    Returns:
        The templateId from the component3, otherwise []
    """
    return to_list_or_empty(component.get("section", {}).get("templateId", []))


def get_template_id_key(template_id: str) -> str:
    """get_template_id_key Gets a key for the given template id

    Args:
        template_id (str): The template id

    Returns:
        str: The key
    """
    return re_sub(r"[^A-Za-z0-9]", "_", template_id)


def is_template_id(id: Mapping[Any, Any], template_id: str) -> bool:
    """is_template_id Determines if the given id matches the specified template id

    Args:
        id (Mapping[Any, Any]): The id
        template_id (str): The template id

    Returns:
        bool: True if the id matches the template id, otherwise, False
    """
    return template_id == id.get("root", "").strip()
