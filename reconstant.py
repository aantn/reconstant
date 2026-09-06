import argparse
import os
import re
import yaml
import textwrap
import inflection
from fastnumbers import isint
from typing import Dict, List, TextIO, Union
from pydantic import BaseModel, PrivateAttr, model_validator

class EnumValueReference (BaseModel):
    enum_name: str
    value_name: str
    _value: int | None = None

class EnumValue (BaseModel):
    name: str
    value: int | EnumValueReference | None = None
    
    @model_validator(mode="before")
    @classmethod
    def convert_string_to_dict(cls, data):
        if isinstance(data, str):
            match = re.search(r'^([\w\-_]+)(?::([\w\-_]+)(?:::([\w\-_]+))?)?$', data)
            if (not match):
                raise Exception("Enum value could not be parsed: " + data)
            result = { "name": match.group(1) }
            if match.group(2) is not None:
                if isint(match.group(2)):
                    if match.group(3) is not None:
                        raise Exception("Number was used as a Enum name: " + data)
                    # Set enum value to integer
                    result["value"] = int(match.group(2))
                else:
                    if match.group(3) is None:
                        raise Exception("Enum name was given, but no enum value: " + data)
                    # Set enum value to reference of another enum
                    result["value"] = {
                        "enum_name": match.group(2),
                        "value_name": match.group(3)
                    }
            return result
        return data

class Enum (BaseModel):
    name: str
    values: List[EnumValue]


class Constant (BaseModel):
    name: str
    value: Union[int, str]


class Outputer (BaseModel):
    path: str
    _buffered_enum_values: list[EnumValueReference] = []
    _output: TextIO = PrivateAttr()
    _comment_mark: str = PrivateAttr()
    _comment_indentation: int = PrivateAttr() # doesn't apply to the comment in output_header()

    def __init__(self, *args, comment_mark="#", comment_indentation=0, **kwargs):
        super().__init__(*args, **kwargs)
        self._output = open(self.path, "w")
        self._comment_mark = comment_mark
        self._comment_indentation = comment_indentation
    
    def __del__(self):
        self._output.close()

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
        return f"{value_identifier.enum_name}.{value_identifier.value_name}"

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        return ""

    def output_enum(self, enum: Enum):
        # The value that will be added to the last explicit value (or 0 in case there is no explicit)
        iterator_value: int = 0
        # The last value that was explicitly given by the user
        last_explicit_value : str | int | EnumValueReference | None = None
        for (i, value) in enumerate(enum.values):
            enum_value = value.value    # The value the enum value is supposed to represent
            output_value = 0
            if enum_value is None:
                if last_explicit_value is None:   # Set to iterator_value
                    output_value = iterator_value
                else:   # Set to the last specified value + iterator_value
                    if type(last_explicit_value) == int:
                        output_value = last_explicit_value + iterator_value
                    if type(last_explicit_value) == EnumValueReference:
                        output_value = self.getEnumValue(enum_value) + f' + {iterator_value}'
                iterator_value += 1
            else:
                if type(enum_value) == EnumValueReference:
                    find_res = [val._value for val in self._buffered_enum_values 
                                if val.enum_name == enum_value.enum_name and val.value_name == enum_value.value_name]
                    if len(find_res) > 0 and find_res[0] is not None:
                        output_value = find_res[0]
                        enum_value = find_res[0]
                    else:
                        output_value = self.getEnumValue(enum_value)
                else:
                    output_value = enum_value
                last_explicit_value = enum_value
                iterator_value = 1
            if type(output_value) == int:
                new_ref = EnumValueReference(enum_name=enum.name, value_name=value.name)
                new_ref._value = output_value
                self._buffered_enum_values.append(new_ref)
            self._output.write(
                self.formatEnumEntry(enum.name, value.name, output_value, i == 0, i == len(enum.values) - 1)
            )

    def output_comment(self, comment):
        indent = '\t' * self._comment_indentation
        self._output.write(f"\n{indent}{self._comment_mark} {comment}\n")
    
    def output_constant(self, constant: Constant, prefix="", assignment="=", suffix=""):
        if type(constant.value) == int:
            value = constant.value
        elif type(constant.value) == str:
            value = f'"{constant.value}"'
        else:
            raise Exception("Internal error - illegal constant type. %s", type(constant.value))
        self._output.write(f"{prefix}{constant.name} {assignment} {value}{suffix}\n")

    def output_header(self):
        self._output.write(f"{self._comment_mark} autogenerated by reconstant - do not edit!\n")

    def output_footer(self):
        pass


class Python2Outputer (Outputer):

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
        return f"{inflection.underscore(value_identifier.enum_name).upper()}_{value_identifier.value_name}"

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        enum_name = inflection.underscore(enum_name).upper()
        enum_value_name = inflection.underscore(enum_value_name).upper()
        return f"{enum_name}_{enum_value_name}={enum_value}\n"

class Python3Outputer (Outputer):
    enum_type: str = "Enum"
    
    def output_header(self):
        super().output_header()
        self._output.write(f"from enum import {self.enum_type}\n")

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
        return f"{value_identifier.enum_name}.{value_identifier.value_name}.value"

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        return f"\t{enum_value_name}={enum_value}\n"

    def output_enum(self, enum : Enum):
        self._output.write(f"class {enum.name}({self.enum_type}):\n")
        super().output_enum(enum)
        self._output.write(f"\n")


class JavascriptOutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", *args, **kwargs)

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        return f"\t{enum_value_name}:{enum_value},\n"

    def output_enum(self, enum : Enum):
        self._output.write(f"export const {enum.name} = {{\n")
        super().output_enum(enum)
        self._output.write(f"}}\n")

    def output_constant(self, constant: Constant):
        return super().output_constant(constant, prefix="export const ")


class JavaOutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", comment_indentation=1, *args, **kwargs)

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
            return f"{value_identifier.enum_name}.{value_identifier.value_name}.getValue()"

    def output_header(self):
        super().output_header()
        class_name = self._get_class_name()
        self._output.write(textwrap.dedent(f"""\
            public final class {class_name} {{
            """))

    def output_footer(self):
        super().output_footer()
        self._output.write("}")

    def _get_class_name(self):
        return os.path.basename(self.path).replace(".java", "")

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        return f"\t\t{enum_value_name}({enum_value}){';' if islast else ','}\n"

    def output_enum(self, enum : Enum):
        self._output.write(f"\tpublic enum {enum.name} {'{'}\n")
        super().output_enum(enum)
        self._output.write( """\t\tprivate final int value;\n"""
                           f"""\t\t{enum.name}""" """(int value) {\n"""
                            """\t\t\tthis.value = value;\n"""
                            """\t\t}\n"""
                            """\t\tpublic int getValue() {\n"""
                            """\t\t\treturn this.value;\n"""
                            """\t\t}\n"""
                            """\t}\n\n""")
        #self._output.write( {separator.join([val.name for val in enum.values])}\n\t}}\n")

    def output_constant(self, constant: Constant):
        name = inflection.underscore(constant.name).upper()
        if type(constant.value) == str:
            self._output.write(f'\tpublic static final String {name} = "{constant.value}";\n')
        else:
            self._output.write(f'\tpublic static final {type(constant.value).__name__} {name} = {constant.value};\n')


class RustOutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", *args, **kwargs)

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
        return f"{value_identifier.enum_name}::{value_identifier.value_name}"

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        return f"\t{enum_value_name}={enum_value},\n"

    def output_enum(self, enum : Enum):
        self._output.write(f"pub enum {enum.name} {'{'}\n")
        super().output_enum(enum)
        self._output.write("}\n")

    def output_constant(self, constant: Constant):
        name = inflection.underscore(constant.name).upper()
        t = {int: 'i32', float: 'f32', str: '&str'}.get(type(constant.value), type(constant.value).__name__)
        quotes = '"' if t == '&str' else ''
        self._output.write(f'pub const {name}: {t} = {quotes}{constant.value}{quotes};\n')


class COutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", *args, **kwargs)

    def output_header(self):
        super().output_header()
        guard_name = self._get_guard_name()
        self._output.write(textwrap.dedent(f"""\
            #ifndef {guard_name}
            #define {guard_name}
            """))

    def output_footer(self):
        super().output_footer()
        guard_name = self._get_guard_name()
        self._output.write(f"\n#endif /* {guard_name} */")

    def _get_guard_name(self):
        return self.path.replace('/', '_').replace(".", "_").upper()

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
        return f"{value_identifier.value_name}"

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        enum_name = inflection.underscore(enum_name).upper()
        enum_value_name = inflection.underscore(enum_value_name).upper()
        return f"\t{enum_name}_{enum_value_name}={enum_value},\n"

    def output_enum(self, enum : Enum):
        self._output.write("typedef enum {\n")
        super().output_enum(enum)
        self._output.write(f"{'}'}  {enum.name};\n")

    def output_constant(self, constant: Constant):
        name = inflection.underscore(constant.name).upper()
        if type(constant.value) == str:
            self._output.write(f'#define {name} "{constant.value}"\n')
        else:
            self._output.write(f'#define {name} {constant.value}\n')


# idea from https://stackoverflow.com/a/65734013/495995
class VueMixinOutputer (JavascriptOutputer):

    def output_enum(self, enum : Enum):
        super().output_enum(enum)
        name = enum.name
        self._output.write(textwrap.dedent(f"""\
            
            {name}.Mixin = {{
              created () {{
                  this.{name} = {name}
              }}
            }}
            """))


class ROutputer (Outputer):
    """R-language Outputer"""

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="#", *args, **kwargs)

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
        return f"{inflection.underscore(value_identifier.enum_name).upper()}_{value_identifier.value_name}"

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        enum_name = inflection.underscore(enum_name).upper()
        enum_value_name = inflection.underscore(enum_value_name).upper()
        return f"{enum_name}_{enum_value_name} <- {enum_value}\n"

    def output_enum(self, constant : Constant):
        super().output_enum(constant)

    def output_constant(self, constant: Constant, prefix="", assignment="<-", suffix=""):
        if type(constant.value) == int:
            value = constant.value
        elif type(constant.value) == str:
            value = f'"{constant.value}"'
        else:
            raise Exception("Internal error - illegal constant type. %s", type(constant.value))
        self._output.write(f"{prefix}{constant.name} {assignment} {value}{suffix}\n")


class DartOutputer (Outputer):
    """Dart-language Outputer"""

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", *args, **kwargs)

    def output_header(self):
        super().output_header()
        self._output.write("library constants;\n\n")

    def getEnumValue(self, value_identifier: EnumValueReference) -> str:
            return f"{value_identifier.enum_name}.{value_identifier.value_name.lower()}.code"

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        # Convert enum values to lowercase for more Dart-like style
        return f"\t{enum_value_name.lower()}({enum_value}){';' if islast else ','}\n"

    def output_enum(self, enum: Enum):
        self._output.write(f"enum {enum.name} {{\n")
        super().output_enum(enum)
        self._output.write(f"\n\tfinal int code;\n\tconst {enum.name}(this.code);\n}}\n")

    def output_constant(self, constant: Constant):
        # Convert constant names to camelCase for Dart conventions
        # First convert to lowercase, then camelize to get proper camelCase
        dart_name = constant.name.lower()
        dart_name = inflection.camelize(dart_name, uppercase_first_letter=False)
        if type(constant.value) == int:
            self._output.write(f'const {dart_name} = {constant.value};\n')
        elif type(constant.value) == str:
            # Escape any special characters in strings
            escaped_value = constant.value.replace('"', '\\"').replace('\n', '\\n')
            self._output.write(f'const {dart_name} = "{escaped_value}";\n')
        else:
            raise Exception(f"Internal error - unsupported constant type: {type(constant.value)}")


class VhdlOutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="--", comment_indentation=1, *args, **kwargs)

    def output_header(self):
        super().output_header()
        pkg_name = os.path.splitext(os.path.basename(self.path))[0]
        self._output.write(f"\npackage {pkg_name} is\n")

    def output_footer(self):
        super().output_footer()
        self._output.write("\nend package;\n")

    def formatEnumEntry(self, enum_name: str, enum_value_name: str, enum_value: int | str, isfirst:bool, islast:bool):
        # Convert enum values to lowercase for more Dart-like style
        return f"\t\t{enum_value_name}{'' if islast else ','}\n"

    def output_enum(self, enum : Enum):
        self._output.write(f"\ttype {enum.name} is (\n")
        super().output_enum(enum)
        self._output.write(f"\t);\n")

    def output_constant(self, constant: Constant):
        name = inflection.underscore(constant.name).upper()
        if type(constant.value) == str:
            self._output.write(f'\tconstant {name} : string := "{constant.value}";\n')
        elif type(constant.value) == int:
            self._output.write(f'\tconstant {name} : integer := {constant.value};\n')
        else:
            raise Exception(f"Internal error - unsupported constant type: {type(constant.value)}")


class AllOutputs (BaseModel):
    python: Python3Outputer = None
    python2: Python2Outputer = None
    javascript: JavascriptOutputer = None
    vue: VueMixinOutputer = None
    c: COutputer = None
    java: JavaOutputer = None
    rust: RustOutputer = None
    r: ROutputer = None
    dart: DartOutputer = None
    vhdl: VhdlOutputer = None


class RootConfig (BaseModel):
    enums : List[Enum] = []
    constants : List[Constant] = []
    outputs: AllOutputs


def process_input(config: RootConfig):
    outputers = [getattr(config.outputs, x) for x in config.outputs.model_fields_set]

    for outputer in outputers:
        outputer.output_header()
        outputer.output_comment("constants")
        for constant in config.constants:
            outputer.output_constant(constant)
        outputer.output_comment("enums")
        for enum in config.enums:
            outputer.output_enum(enum)
        outputer.output_footer()
    

def main():
    parser = argparse.ArgumentParser(description='Reconstant - Share constant definitions between programming languages and make your constants constant again.')
    parser.add_argument('input', type=str, help='input file in yaml format')
    args = parser.parse_args()

    with open(args.input, "r") as yaml_input:
        python_obj = yaml.safe_load(yaml_input)
        config = RootConfig.model_validate(python_obj)
        process_input(config)

if __name__ == "__main__":
    main()
