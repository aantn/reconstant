import argparse
import os
import yaml
import textwrap
import inflection
from typing import Dict, List, TextIO, Union, Optional
from pydantic import BaseModel, PrivateAttr


class Enum (BaseModel):
    name: str
    values: List[str]


class Constant (BaseModel):
    name: str
    value: Union[int, str]


class Outputer (BaseModel):
    common_comment: Optional[str] = None
    path: str
    _output: TextIO = PrivateAttr()
    _comment_mark: str = PrivateAttr()
    _comment_indentation: int = PrivateAttr() # doesn't apply to the comment in output_header()

    def __init__(self, *args, comment_mark="#", comment_indentation=0, **kwargs):
        super().__init__(*args, **kwargs)
        dirname = os.path.dirname(self.path)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        self._output = open(self.path, "w")
        self._comment_mark = comment_mark
        self._comment_indentation = comment_indentation
    
    def __del__(self):
        self._output.close()

    def output_enum(self, enum: Enum, prefix="", assignment="=", suffix=""):
        for (i, value) in enumerate(enum.values):
            self._output.write(f"{prefix}{value} {assignment} {i}{suffix}\n")

    def output_comment(self, comment, start_with_newline=True):
        indent = '\t' * self._comment_indentation
        lines = [f"{indent}{self._comment_mark} {line}" for line in comment.splitlines()]
        self._output.write(('\n' if start_with_newline else '') + '\n'.join(lines) + '\n')
    
    def output_constant(self, constant: Constant, prefix="", assignment="=", suffix=""):
        if type(constant.value) == int:
            value = constant.value
        elif type(constant.value) == str:
            value = f'"{constant.value}"'
        else:
            raise Exception("Internal error - illegal constant type. %s", type(constant.value))
        self._output.write(f"{prefix}{constant.name} {assignment} {value}{suffix}\n")

    def output_header(self):
        if self.common_comment:
            self.output_comment(self.common_comment, start_with_newline=False)

    def output_footer(self):
        pass


class Python2Outputer (Outputer):

    def output_enum(self, constant : Constant):
        super().output_enum(constant, prefix=f"{inflection.underscore(constant.name).upper()}_")


class Python3Outputer (Outputer):
        
    def output_header(self):
        super().output_header()
        self._output.write("from enum import IntEnum\n")

    def output_enum(self, enum : Enum):
        self._output.write(f"class {enum.name}(IntEnum):\n")
        super().output_enum(enum, prefix=f"\t")
        self._output.write(f"\n")


class JavascriptOutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", *args, **kwargs)

    def output_enum(self, enum : Enum):
        self._output.write(f"export const {enum.name} = {{\n")
        super().output_enum(enum, prefix=f"\t", assignment=":", suffix=",")
        self._output.write(f"}}\n")

    def output_constant(self, constant: Constant):
        return super().output_constant(constant, prefix="export const ")


class JavaOutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", comment_indentation=1, *args, **kwargs)

    def output_header(self):
        super().output_header()
        class_name = self._get_class_name()
        self._output.write(textwrap.dedent(f"""\
            public final class {class_name} {{
            """))

    def output_footer(self):
        super().output_footer()
        self._output.write("\n}")

    def _get_class_name(self):
        return os.path.basename(self.path).replace(".java", "")

    def output_enum(self, enum : Enum):
        separator = ', \n\t\t'
        self._output.write(f"\tpublic enum {enum.name} {{\n\t\t{separator.join([val for val in enum.values])}\n\t}}\n")

    def output_constant(self, constant: Constant):
        name = inflection.underscore(constant.name).upper()
        if type(constant.value) == str:
            self._output.write(f'\tpublic static final String {name} = "{constant.value}";\n')
        else:
            self._output.write(f'\tpublic static final {type(constant.value).__name__} {name} = {constant.value};\n')


class RustOutputer (Outputer):

    def __init__(self, *args, **kwargs):
        super().__init__(comment_mark="//", *args, **kwargs)

    def output_enum(self, enum : Enum):
        separator = ', \n\t'
        self._output.write(f"pub enum {enum.name} {{\n\t{separator.join([val for val in enum.values])}\n}}\n")

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

    def output_enum(self, enum : Enum):
        self._output.write(f"typedef enum {{ {', '.join([val for val in enum.values])} }} {enum.name};\n")

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

    def output_enum(self, constant : Constant):
        super().output_enum(constant, assignment="<-", prefix=f"{inflection.underscore(constant.name).upper()}_")

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

    def output_enum(self, enum: Enum):
        self._output.write(f"enum {enum.name} {{\n")
        # Convert enum values to lowercase for more Dart-like style
        values = ",\n  ".join([val.lower() for val in enum.values])
        self._output.write(f"  {values}\n}}\n")

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


class RootConfig (BaseModel):
    common_comment: Optional[str] = None
    enums : List[Enum] = []
    constants : List[Constant] = []
    outputs: AllOutputs


def process_input(config: RootConfig):
    outputers = [getattr(config.outputs, x) for x in config.outputs.__fields_set__]

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
        if python_obj.get('common_comment'):
            for output in python_obj['outputs']:
                python_obj['outputs'][output]['common_comment'] = python_obj['common_comment']
        config = RootConfig.parse_obj(python_obj)
        process_input(config)

if __name__ == "__main__":
    main()
