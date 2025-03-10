from typing import TYPE_CHECKING, Any, Dict, Type

from pydantic import BaseModel

from starlite.exceptions import MissingDependencyException
from starlite.openapi.spec.schema import SchemaDataContainer
from starlite.plugins import OpenAPISchemaPluginProtocol, SerializationPluginProtocol

__all__ = ("PiccoloORMPlugin",)

try:
    import piccolo  # noqa: F401
except ImportError as e:
    raise MissingDependencyException("piccolo orm is not installed") from e

from piccolo.table import Table, TableMetaclass
from piccolo.utils.pydantic import create_pydantic_model

if TYPE_CHECKING:
    from typing_extensions import TypeGuard

    from starlite.openapi.spec import Schema


class PiccoloORMPlugin(SerializationPluginProtocol[Table, BaseModel], OpenAPISchemaPluginProtocol[Table]):
    """Support (de)serialization and OpenAPI generation for Piccolo ORM types."""

    _models_map: Dict[Type[Table], Type["BaseModel"]] = {}
    _data_models_map: Dict[Type[Table], Type["BaseModel"]] = {}

    def to_data_container_class(self, model_class: Type[Table], **kwargs: Any) -> Type["BaseModel"]:
        """Given a piccolo model_class instance, convert it to a subclass of the piccolo "BaseModel".

        Since incoming request body's cannot and should not include values for
        related fields, pk fields and read only fields in piccolo-orm, we generate two different kinds of pydantic models here:
        - the first is a regular pydantic model, and the other is for the "data" kwarg only, which is further sanitized.

        This function uses memoization to ensure we don't recompute unnecessarily.
        """
        parameter_name = kwargs.get("parameter_name")
        if parameter_name == "data":
            if model_class not in self._data_models_map:
                self._data_models_map[model_class] = create_pydantic_model(
                    table=model_class, model_name=f"{model_class.__name__}RequestBody"
                )
            return self._data_models_map[model_class]
        if model_class not in self._models_map:
            self._models_map[model_class] = create_pydantic_model(
                table=model_class, model_name=model_class.__name__, nested=True, include_default_columns=True
            )
        return self._models_map[model_class]

    @staticmethod
    def is_plugin_supported_type(value: Any) -> "TypeGuard[Table]":
        """Given a value of indeterminate type, determine if this value is supported by the plugin."""
        return isinstance(value, (Table, TableMetaclass))

    def from_data_container_instance(self, model_class: Type[Table], data_container_instance: "BaseModel") -> Table:
        """Given an instance of a pydantic model created using the plugin's ``to_data_container_class``, return an
        instance of the class from which that pydantic model has been created.

        This class is passed in as the ``model_class`` kwarg.
        """
        return self.from_dict(model_class=model_class, **data_container_instance.dict())

    def to_dict(self, model_instance: Table) -> Dict[str, Any]:
        """Given an instance of a model supported by the plugin, return a dictionary of serializable values."""
        return model_instance.to_dict()

    def from_dict(self, model_class: Type[Table], **kwargs: Any) -> Table:
        """Given a class supported by this plugin and a dict of values, create an instance of the class."""
        instance = model_class()
        for column in instance.all_columns():
            meta = column._meta
            if meta.name in kwargs:
                setattr(instance, meta.name, kwargs[meta.name])
        return instance

    def to_openapi_schema(self, model_class: Type[Table]) -> "Schema":
        """Given a model class, transform it into an OpenAPI schema class.

        Args:
            model_class: A table class.

        Returns:
            An :class:`OpenAPI <starlite.openapi.spec.schema.Schema>` instance.
        """
        return SchemaDataContainer(data_container=self.to_data_container_class(model_class=model_class))
