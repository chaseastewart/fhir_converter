from __future__ import annotations

from abc import ABC, abstractmethod
from io import StringIO
from pathlib import Path
from typing import (
    IO,
    Any,
    AnyStr,
    Callable,
    Final,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    TextIO,
    TypedDict,
    Union,
)

from frozendict import frozendict
from liquid import Environment
from liquid.loaders import BaseLoader, PackageLoader
from lxml.etree import QName
from pyjson5 import encode_io
from pyjson5 import loads as json_loads

from fhir_converter.exceptions import RenderingError, fail
from fhir_converter.filters import all_filters, register_filters
from fhir_converter.hl7 import parse_fhir, post_process_fhir
from fhir_converter.loaders import make_template_system_loader, read_text
from fhir_converter.parsers import ParseXmlOpts, parse_json, parse_xml, parse_xml_filter, Hl7v2DataParser
from fhir_converter.tags import all_tags, register_tags
from fhir_converter.utils import (
    del_empty_dirs_quietly,
    del_path_quietly,
    etree_element_to_str,
    etree_to_str,
    join_subpath,
    load_xslt,
    mkdir,
    sanitize_str,
    walk_path,
    read_text as reader,
)

from fhir_converter.expressions import (
    parse_loop_expression,
    parse_boolean_expression,
    parse_filtered_expression
)

from liquid.mode import Mode

DataInput = Union[IO, AnyStr]
""" Union[str, IO]: The rendering data input types"""

DataOutput = TextIO
"""TextIO: The rendering data output type"""

DataRenderer = Callable[[DataInput, DataOutput, str], None]
"""Callable[[DataInput, DataOutput, str], None]: Data renderer function"""

RenderErrorHandler = Callable[[Exception], None]
"""Callable[[Exception], None]: Rendering error handling function"""

ccda_default_loader: Final[PackageLoader] = PackageLoader(
    package="fhir_converter.templates", package_path="ccda"
)
"""PackageLoader: The default loader for the ccda templates"""

stu3_default_loader: Final[PackageLoader] = PackageLoader(
    package="fhir_converter.templates", package_path="stu3"
)
"""PackageLoader: The default loader for the stu3 templates"""

hl7v2_default_loader: Final[PackageLoader] = PackageLoader(
    package="fhir_converter.templates", package_path="hl7v2"
)
"""PackageLoader: The default loader for the hl7v2 templates"""


class FhirRendererDefaults(TypedDict):
    """The Renderer Defaults"""

    loader: BaseLoader


class BaseFhirRenderer(ABC):
    """Base renderer. Supports rendering data to FHIR

    Filters:
        The module provides builtin filters to support the default templates provided
        within the module. Custom filters may be added for user defined templates.
        Consumers must provide the rendering environment with the custom filters
        registered. The builtin filters will be added unless a filter with the same
        name has already been registered. This includes filters provided by liquid
        that are overridden. These overrides are not made since its unknown if the
        filter is provided by liquid or is custom. See get_environment

    Tags:
        The module provides builtin tags to support the default templates provided
        within the module. Custom tags may be added for user defined templates.
        Consumers must provide the rendering environment with the custom tag(s)
        registered. The builtin tag(s) will be added unless a tag with the same name
        has already been registered.

    Args:
        env (Environment, optional): Optional rendering environment. A rendering
            environment will be constructed with builtin defaults when env is None.
            Defaults to None.
    """

    def __init__(
        self,
        env: Optional[Environment] = None,
    ) -> None:
        if not env:
            env = make_environment(**self.defaults())
        else:
            register_filters(env, all_filters)
            register_tags(env, all_tags)
        self.env = env

    @staticmethod
    @abstractmethod
    def defaults() -> FhirRendererDefaults:
        """defaults The rendering defaults for the renderer

        Returns:
            FhirRendererDefaults: The rendering defaults for the renderer
        """
        pass

    def render_fhir_string(
        self, template_name: str, data_in: DataInput, encoding: str = "utf-8"
    ) -> str:
        """render_fhir_string Renders the given data to a FHIR

        Args:
            template_name (str): The rendering template
            data_in (DataInput): The data input. Either a string or file like object
            encoding (str, optional): The encoding to use when parsing the data input.
                Defaults to "utf-8".

        Returns:
            str: The rendered FHIR as a string
        """
        with StringIO() as buffer:
            self.render_fhir(template_name, data_in, buffer, encoding)
            return buffer.getvalue()

    def render_fhir(
        self,
        template_name: str,
        data_in: DataInput,
        data_out: DataOutput,
        encoding: str = "utf-8",
    ) -> None:
        """render_fhir Renders the given data to FHIR writing the generated output
        to the supplied file like object

        Args:
            template_name (str): The rendering template
            data_in (DataInput): The data input. Either a string or file like object
            data_out (DataOutput): The file like object to write the rendered output
            encoding (str, optional): The encoding to use when parsing the data input.
                Defaults to "utf-8".

        Raises:
            RenderingError: when an error occurs while rendering the input data
        """
        fhir = self.render_to_fhir(template_name, data_in, encoding)
        try:
            encode_io(
                fhir,
                fp=data_out,  # type: ignore
                supply_bytes=False,
            )
        except Exception as e:
            raise RenderingError("Failed to serialize FHIR", e)

    def render_to_fhir(
        self, template_name: str, data_in: DataInput, encoding: str = "utf-8"
    ) -> MutableMapping:
        """render_to_fhir Renders the given data to FHIR

        Args:
            template_name (str): The rendering template
            data_in (DataInput): The data input. Either a string or file like object
            encoding (str, optional): The encoding to use when parsing the JSON input.
                Defaults to "utf-8".

        Returns:
            MutableMapping: The rendered FHIR mappings

        Raises:
            RenderingError: when an error occurs while rendering the input data
        """
        try:
            return self._render(template_name, data_in, encoding)
        except Exception as e:
            raise RenderingError("Failed to render FHIR", e)

    @abstractmethod
    def _render(
        self, template_name: str, data_in: DataInput, encoding: str = "utf-8"
    ) -> MutableMapping:
        """render Renders the given data to FHIR

        Args:
            template_name (str): The rendering template
            data_in (DataInput): The data input. Either a string or file like object
            encoding (str, optional): The encoding to use when parsing the JSON input.
                Defaults to "utf-8".

        Returns:
            MutableMapping: The rendered FHIR
        """
        pass


class CcdaRenderer(BaseFhirRenderer):
    """Consolidated CDA document renderer"""

    __slots__ = ("env", "template_globals")

    def __init__(
        self,
        env: Optional[Environment] = None,
        template_globals: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(env)
        self.template_globals = self._make_globals(template_globals)

    @staticmethod
    def defaults() -> FhirRendererDefaults:
        return {"loader": ccda_default_loader}

    def _make_globals(self, globals: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
        template_globals = dict(globals or {})
        if "code_mapping" not in template_globals:
            value_set = json_loads(read_text(self.env, filename="ValueSet/ValueSet.json"))
            template_globals["code_mapping"] = frozendict(value_set.get("Mapping", {}))

        self.render_narrative = template_globals.get("render_narrative", False)
        if bool(self.render_narrative):
            template_globals["narrative_xslt"] = load_xslt(
                read_text(
                    self.env,
                    filename="cda_narrative.xsl",
                )
            )
        return frozendict(template_globals)

    def _parse_cda(self, data_in: DataInput, encoding: str = "utf-8"):
        def parse_ccda_filter(element, parent, opts):
            filtered_out = parse_xml_filter(element, parent, opts)
            if self.render_narrative is False:
                return filtered_out

            if filtered_out is None and QName(element.tag).localname == "text":
                if parent is not None and QName(parent.tag).localname == "section":
                    return {
                        "_originalData": sanitize_str(
                            etree_element_to_str(
                                parent,
                                encoding=opts.encoding,
                                standalone=True,
                            )
                        )
                    }
            return filtered_out

        def after_parse_ccda(parsed_dict, tree, opts):
            parsed_dict["_originalData"] = sanitize_str(
                etree_to_str(
                    tree,
                    encoding=opts.encoding,
                    standalone=True,
                )
            )
            return parsed_dict

        return parse_xml(
            data_in,
            parse_opts=ParseXmlOpts(encoding=encoding),
            parse_filter=parse_ccda_filter,
            after_parse_xml=after_parse_ccda,
        )

    def _render(
        self, template_name: str, data_in: DataInput, encoding: str = "utf-8"
    ) -> MutableMapping:
        template = self.env.get_template(template_name, globals=self.template_globals)
        return parse_fhir(
            json_input=template.render({"msg": self._parse_cda(data_in, encoding)}),
        )


class Stu3FhirRenderer(BaseFhirRenderer):
    """Stu3 Fhir to Fhir renderer"""

    __slots__ = "env"

    def __init__(self, env: Optional[Environment] = None) -> None:
        super().__init__(env)

    @staticmethod
    def defaults() -> FhirRendererDefaults:
        return {"loader": stu3_default_loader}

    @staticmethod
    def _parse_stu3(data_in: DataInput, encoding: str = "utf-8"):
        return parse_json(data_in, encoding, ignore_empty_fields=False)

    def _render(
        self, template_name: str, data_in: DataInput, encoding: str = "utf-8"
    ) -> MutableMapping:
        template = self.env.get_template(template_name)
        return parse_fhir(
            json_input=template.render({"msg": self._parse_stu3(data_in, encoding)}),
        )
    
class Hl7v2Renderer(BaseFhirRenderer):
    """HL7v2 to FHIR renderer"""

    __slots__ = ("env", "template_globals")

    def __init__(
            self, env: Optional[Environment] = None,
            template_globals: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(env)
        # TODO: Remove this mode setting when the liquid library is updated
        self.env.mode = Mode.WARN
        self.env.parse_loop_expression_value = parse_loop_expression
        self.env.parse_boolean_expression_value = parse_boolean_expression
        self.env.parse_filtered_expression_value = parse_filtered_expression
        self.template_globals = self._make_globals(template_globals)


    @staticmethod
    def defaults() -> FhirRendererDefaults:
        return {"loader": hl7v2_default_loader}

    def _make_globals(self, globals: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
        template_globals = dict(globals or {})
        if "code_mapping" not in template_globals:
            value_set = json_loads(read_text(self.env, filename="CodeSystem/CodeSystem.json"))
            template_globals["code_mapping"] = frozendict(value_set.get("Mapping", {}))

        return frozendict(template_globals)

    @staticmethod
    def _parse_hl7v2(data_in: DataInput, encoding: str = "utf-8"):

        return Hl7v2DataParser().parse(reader(data_in, encoding))

    def _render(
        self, template_name: str, data_in: DataInput, encoding: str = "utf-8"
    ) -> MutableMapping:
        template = self.env.get_template(template_name, globals=self.template_globals)
        return post_process_fhir(
            template.render({"hl7v2Data": self._parse_hl7v2(data_in, encoding)})
        )
        


def make_environment(
    loader: BaseLoader,
    auto_reload: bool = False,
    cache_size: int = 300,
    additional_loaders: Optional[Sequence[BaseLoader]] = None,
    **kwargs,
) -> Environment:
    """Factory for creating rendering environments with builtin configurations.
    Keyword arguments will be forwarded to the rendering environment. Filters provided
    by liquid are overridden by builtin filters as necessary

    Args:
        loader (BaseLoader): The loader to use when loading the rendering temples
        auto_reload (bool, optional): If `True`, loaders that have an `uptodate`
            callable will reload template source data automatically. Defaults to False
        cache_size (int, optional): The capacity of the template cache in number of
            templates. cache_size less than 1 disables caching. Defaults to 300
        additional_loaders (Optional[Sequence[BaseLoader]], optional): The additional
            loaders to use when a template is not found by the loader. Defaults to None

    Returns:
        Environment: The rendering environment
    """
    env = Environment(
        loader=make_template_system_loader(
            loader,
            auto_reload=auto_reload,
            cache_size=cache_size,
            additional_loaders=additional_loaders,
        ),
        cache_size=cache_size,
        **kwargs,
    )
    register_filters(env, all_filters, replace=True)
    register_tags(env, all_tags)
    return env


def render_files_to_dir(
    render: DataRenderer,
    from_dir: Path,
    to_dir: Path,
    flatten: bool = False,
    extension: str = ".json",
    encoding: str = "utf-8",
    onerror: RenderErrorHandler = fail,
    path_filter: Optional[Callable[[Path], bool]] = None,
) -> None:
    """render_files_to_dir Renders the files from the given directory to the specified output
    directory using the supplied data renderer.

    Args:
        render (DataRenderer): the renderer to use
        from_dir (Path): the directory to render
        to_dir (Path): the output directory
        flatten (bool, optional): whether to flatten, ignore, the source directory structure and write
            all files to the root of the output directory. Defaults to False.
        extension (str, optional): the file extension for the rendered output file. Defaults to ".json".
        encoding (str, optional): the character encoding to use. Defaults to "utf-8".
        onerror (RenderErrorHandler, optional): the error handler. Defaults to fail.
        path_filter (Optional[Callable[[Path], bool]], optional): the filter to use when scaning the
            source directory. Defaults to None.

    Raises:
        RenderingError: When the error handler determines an exception should be raised. By default
        all errors are raised. See fail
    """
    try:
        for dir, _, filenames in walk_path(from_dir):
            files: Iterable[Path] = map(lambda fn: dir.joinpath(fn), filenames)
            if path_filter:
                files = filter(path_filter, files)
            for file in files:
                if not flatten and from_dir != dir:
                    to_file_dir = join_subpath(to_dir, parent=from_dir, child=file)
                    mkdir(to_file_dir, parents=True, exist_ok=True)
                else:
                    to_file_dir = to_dir
                render_to_dir(render, file, to_file_dir, extension, encoding, onerror)
    except Exception as e:
        onerror(RenderingError(f"Failed to render {from_dir}", e))
    finally:
        if not flatten:
            del_empty_dirs_quietly(to_dir)


def render_to_dir(
    render: DataRenderer,
    from_file: Path,
    to_dir: Path,
    extension: str = ".json",
    encoding: str = "utf-8",
    onerror: RenderErrorHandler = fail,
) -> None:
    """render_to_dir Renders the given file to the specified output directory using the
    supplied data renderer.

    Args:
        render (DataRenderer): the renderer to use
        from_file (Path): the file to render
        to_dir (Path): the output directory
        extension (str, optional): the file extension for the rendered output file. Defaults to ".json".
        encoding (str, optional): the character encoding to use. Defaults to "utf-8".
        onerror (RenderErrorHandler, optional): the error handler. Defaults to fail.

    Raises:
        RenderingError: When the error handler determines an exception should be raised. By default
        all errors are raised. See fail
    """
    try:
        with from_file.open(encoding=encoding) as data_in:
            to_file: Path = to_dir.joinpath(from_file.with_suffix(extension).name)
            try:
                with to_file.open("w", encoding=encoding) as data_out:
                    render(data_in, data_out, encoding)
            except Exception as e:
                del_path_quietly(to_file)
                raise e
    except Exception as e:
        onerror(RenderingError(f"Failed to render {from_file}", e))
