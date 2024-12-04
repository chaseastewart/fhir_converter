from io import BytesIO
from os import path as os_path
from os import PathLike
from os import remove as os_remove
from os import walk as os_walk
from pathlib import Path
from re import Pattern, sub as re_sub
from re import compile as re_compile
from typing import IO, Any, Dict, Final, Generator, List, Optional, Tuple, Union

from liquid import Undefined
from lxml import etree
from typing_extensions import TypeAlias

DataIn: TypeAlias = Union[IO[str], IO[bytes], str, bytes]
FileDataIn: TypeAlias = Union[DataIn, PathLike]

line_endings_pattern: Final[Pattern] = re_compile(r"\r\n?|\n")
sanitize_pattern: Final[Pattern] = re_compile(r"\s\s+|\r\n?|\n")


def sanitize_str(text: Optional[str], repl: str = " ") -> str:
    """sanitize_str trims leading / trailing spaces replacing line endings and
        consecutive whitespace characters with the specified replacement value

    Args:
        text (Optional[str]): the string
        repl (str): the replacement value. Defaults to " "

    Returns:
        str: the santized string or empty string
    """
    return sanitize_pattern.sub(repl, text.strip()) if text else ""


def join_strs(a: Optional[str], b: Optional[str], sep: str = "_") -> str:
    """join_strs conditionally joins two strings depending on if they are both
        not empty or None

    Args:
        a (Optional[str]): the first string
        b (Optional[str]): the second string

    Returns:
        str: either the joined strings, the first, second or empty string
    """
    if a and b:
        return a + sep + b
    return a if a else b if b else ""


def is_undefined_or_none(obj: Any) -> bool:
    """is_undefined_or_none returns whether the object is undefined or
    none

    Args:
        obj (Any): the object to check

    Returns:
        bool: returns True if the object is undefined or empty, otherwise, False
    """
    return obj is None or isinstance(obj, Undefined)


def is_undefined_none_or_blank(obj: Any) -> bool:
    """is_undefined_none_or_blank returns whether the object is undefined,
    none or blank

    Will return True for the following::
        - Undefined
        - None
        - '' (empty string)
        - ' ' (blank string)
        - [] (empty list)
        - () (empty tuple)
        - {} (empty dict)
        - set() (empty set)

    Args:
        obj (Any): the object to check

    Returns:
        bool: returns True if the object is undefined, none or empty, otherwise, False
    """
    if is_undefined_or_none(obj):
        return True
    elif type(obj) in (int, float, bool):
        return False

    if isinstance(obj, str):
        obj = blank_str_to_empty(obj)
    return not obj


def to_list_or_empty(obj: Any) -> List[Any]:
    """to_list_or_empty returns the object as a list if its a list or not empty
    or none, otherwise, []

    Args:
        obj (Any): the object to check

    Returns:
        list[Any]: returns the object as a list if its a list or not empty or none,
        otherwise, []
    """
    if isinstance(obj, list):
        return obj
    elif is_undefined_none_or_blank(obj):
        return []
    return [obj]


def blank_str_to_empty(obj: str) -> str:
    """blank_str_to_empty returns the given string if it's not blank, otherwise, empty

    Args:
        obj (str): the string to check

    Returns:
        str: returns the given string if it's not blank, otherwise, empty
    """
    return obj if obj and not obj.isspace() else ""


def merge_dict(a: Dict[Any, Any], b: Dict[Any, Any]) -> Dict[Any, Any]:
    """merge_dict Merges the key/value pair mappings similarly to
    newtonsoft Merge.

    See https://www.newtonsoft.com/json/help/html/MergeJson.htm

    Args:
        a (Dict[Any, Any]): the mappings to merge into
        b (Dict[Any, Any]): the mappings to merge

    Returns:
        Dict[Any, Any]: the merged mappings
    """
    for bk, bv in b.items():
        if bv is None:
            continue

        if bk not in a:
            a[bk] = bv
        else:
            av = a[bk]
            if type(av) != type(bv):
                a[bk] = bv
            elif isinstance(bv, dict):
                merge_dict(av, bv)
            elif isinstance(bv, list):
                for v in bv:
                    if v not in av:
                        av.append(v)
            else:
                a[bk] = bv
    return a


def read_text(data: DataIn, encoding: str = "utf-8") -> str:
    """read_text Reads the given data using the supplied encoding if the data
    is not already a string

    Args:
        data (DataIn): the data to read
        encoding (str, optional): the character encoding to use. Defaults to "utf-8"

    Returns:
        str: the text content
    """
    if isinstance(data, str):
        return data

    if not isinstance(data, (bytes, memoryview, bytearray)):
        content = data.read()
        if isinstance(content, str):
            return content
        data = content
    return str(data, encoding=encoding)


def join_subpath(path: Path, parent: Path, child: Path) -> Path:
    """join_subpath Joins the parts from the child relative to the parent
    path to the supplied path. the final file part from child will be
    excluded if child is a file

    Args:
        path (Path): the path to join the parts to
        parent (Path): the parent path
        child (Path): the child within the parent path

    Returns:
        Path: the new path
    """
    if not parent.is_dir():
        raise ValueError("parent must be a directory")
    child_parts = list(child.parts if child.is_dir() else child.parts[:-1])
    for parent_part in parent.parts:
        child_part = child_parts.pop(0) if child_parts else None
        if parent_part != child_part:
            raise ValueError("child must be a subdirectory of parent")
    return path.joinpath(*child_parts)


def del_empty_dirs_quietly(path: Path) -> None:
    """del_empty_dirs_quietly Quietly deletes any empty sub directories within
    the path ignoring any errors that may have occurred

    Args:
        path (Path): the path to scan
    """
    for dir, dirs, filenames in walk_path(path):
        if not dirs and not filenames and dir != path:
            del_path_quietly(dir)


def del_path_quietly(path: Path) -> None:
    """del_path_quietly Quietly deletes a path ignoring any errors that
    may have occurred

    Allows callers to attempt to delete a path while not having to worry
    about file system errors

    Args:
        path (Path): the path to delete
    """
    try:
        if path.is_dir():
            path.rmdir()
        else:
            os_remove(path)
    except OSError:
        pass


def mkdir(path: Path, **kwargs) -> bool:
    """mkdir wrapper around Path.mkdir forwarding additional keyword args

    Allows callers to discern between a directory existing, an actual error
    while creating the directory and a successful creation aka the directory
    didn't exist previously

    Args:
        path (Path): the path

    Returns:
        bool: True if the directory was created, otherwise, False to indicate the
        directory already exists
    """
    if not path.is_dir():
        path.mkdir(**kwargs)
        return True
    return False


def walk_path(
    path: Path,
) -> Generator[Tuple[Path, List[str], List[str]], Any, None]:
    """walk_path wrapper around os.walk to semi bridge the gap of path.walk
    added in 3.12.

    Args:
        path (Path): the path to walk

    Yields:
        Generator[Tuple[Path, List[str], List[str]], Any, None]: the directory
        tree generator
    """
    for dir, dirs, filenames in os_walk(path):
        yield (Path(dir), dirs, filenames)


def tail(buffer: IO, last_n: int = 25, encoding: str = "utf-8") -> str:
    """tail Reads the tail from the given file like object

    Args:
        buffer (IO): the file like object to read from
        last_n (int, optional): the last n to read up to. Defaults to 25.
        encoding (str, optional): the character encoding to use. Defaults to "utf-8"

    Returns:
        str: up to the last n from the file like object or empty string if
        the object is empty
    """
    pos = buffer.tell()
    if pos <= 0:
        return ""
    buffer.seek(pos - min(pos, last_n))
    return read_text(buffer, encoding)


def parse_etree(
    xml_in: FileDataIn, encoding: str = "utf-8", resolve_entities: bool = False, **kwargs
) -> etree._ElementTree:
    """parse_etree Parses the provided xml into a document tree

    Args:
        xml_in (FileDataIn): the xml in
        encoding (str, optional): the character encoding to use. Defaults to "utf-8"
        resolve_entities (bool, optional): Whether to replace entities. Defaults to False
    Returns:
        etree._ElementTree: the document tree
    """
    if isinstance(xml_in, (str, bytes)):
        if isinstance(xml_in, str):
            xml_in = xml_in.encode(encoding)
        xml_in = BytesIO(xml_in)
    return etree.parse(
        xml_in,
        etree.XMLParser(
            encoding=encoding,
            resolve_entities=resolve_entities,
            **kwargs,
        ),
    )


def etree_to_str(tree: etree._ElementTree, encoding: str = "utf-8", **kwargs) -> str:
    """etree_to_str Serializes the document tree to a string

    Args:
        tree ( etree._ElementTree): the document tree
        encoding (str, optional): the character encoding to use. Defaults to "utf-8"
    Returns:
        str: the xml string
    """
    buffer = BytesIO()
    if isinstance(tree, etree._XSLTResultTree):
        tree.write_output(
            buffer,
            **kwargs,
        )
    else:
        tree.write(
            buffer,
            encoding=encoding,
            **kwargs,
        )
    return buffer.getvalue().decode(encoding)


def etree_element_to_str(
    element: etree._Element, encoding: str = "utf-8", **kwargs
) -> str:
    """etree_element_to_str Serializes the document node to a string

    Args:
        element (etree._Element): the document node
        encoding (str, optional): the character encoding to use. Defaults to "utf-8"
    Returns:
        str: the xml string
    """
    return etree.tostring(
        element,
        encoding=encoding,
        **kwargs,
    ).decode(encoding)


def load_xslt(stylesheet_in: DataIn, encoding: str = "utf-8") -> etree.XSLT:
    """load_xslt Loads the provided xslt stylesheet

    Args:
        stylesheet_in (DataIn): the stylesheet to load
        encoding (str, optional): the character encoding to use. Defaults to "utf-8"
    Returns:
        etree.XSLT: the xslt object
    """
    return etree.XSLT(
        parse_etree(
            read_text(stylesheet_in, encoding),
            encoding,
        ),
    )


def transform_xml_str(xslt: etree.XSLT, xml: str) -> str:
    """transform_xml_str Transforms the provided xml string using the specified xslt object
    parsing the provided xml using the specified parser options passing any additional arguments
    to the xslt transformation

    Args:
        xslt (str): the xml to transform
        encoding (str, optional): the character encoding to use. Defaults to "utf-8"
    Returns:
        str: the output of the transformation
    """
    return etree_to_str(
        xslt(
            parse_etree(
                xml,
                remove_blank_text=True,
                remove_comments=True,
            )
        )
    )

def escape_liquid_variable(value: Path) -> str:
    """escape_liquid_variable Escapes with quotes the integer in variables name

    Args:
        value (Path): the file to read

    Returns:
        str: the escaped integer
    """
    with open(value, mode="r", encoding="utf-8") as file:
        to_process = file.read()
    # for each line in the file
    # if the line contains a variable name with an integer ( e.g. a number prefixed with a . (dot) )
    # escape the integer with quotes (e.g. .1 -> . "1")
    return re_sub(r"\.(\d+)", r'."\1"', to_process)

def process_liquid_folder_escape_variable(folder_in: Path, folder_out: Path) -> None:
    """process_liquid_folder_escape_variable Processes the liquid files 
    by walking all sub directory from the input folder and escaping the 
    integer in the variable name and writes the output to the output folder
    if the output folder does not exist it will be created, it will keep the
    same directory structure as the input

    Args:
        folder_in (Path): the input folder
        folder_out (Path): the output folder
    """

    for full_paths, dirs, filenames in walk_path(folder_in):
        for filename in filenames:
            in_file = full_paths.joinpath(filename)
            out_file = Path(os_path.join(folder_out, os_path.relpath(in_file, folder_in)))
            if not out_file.parent.is_dir():
                out_file.parent.mkdir(parents=True)
            with open(out_file, mode="w", encoding="utf-8") as out:
                out.write(escape_liquid_variable(in_file))


if __name__ == '__main__':
    process_liquid_folder_escape_variable(Path("fhir_converter/templates/hl7v2_orgi"), Path("fhir_converter/templates/hl7v2"))
    print("Done")