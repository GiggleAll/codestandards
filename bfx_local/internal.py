import ast
import os
from collections import namedtuple

import re

Violation = namedtuple("Violation", "code line column value")


class InternalStandardsChecker:
    class NodeVisitor(ast.NodeVisitor):
        def __init__(self, module):
            self.violations = []
            self.module = module

        # N802 We need to override a parent method, ignore PEP-8 violation
        def visit_Str(self, node):
            found = re.search(r"(^[a-zA-Z]:[/\\])|(^[/\\][a-zA-Z])", node.s)
            if found:
                self.violations.append(Violation("BE001", node.lineno, node.col_offset, node.s))

        # N802 We need to override a parent method, ignore PEP-8 violation
        def visit_Call(self, node):
            try:
                if node.func.id == "reload":
                    self.violations.append(Violation("BE004", node.lineno, node.col_offset, "reload"))
            except AttributeError:
                pass

            # Not parsing string literals in argments automatically, so do it manually
            try:
                for arg in node.args:
                    self.visit_Str(arg)
            except AttributeError:
                pass

        def visit_Import(self, node):  # Ignore N802: overriding function
            for alias in node.names:
                if alias.name and self.module and alias.name.startswith(self.module):
                    self.violations.append(Violation("BE006", node.lineno, node.col_offset, alias.name))

        def visit_ImportFrom(self, node):  # Ignore N802: overriding function
            # Ignore future modules and relative imports
            if node.module and self.module and node.module.startswith(self.module):
                self.violations.append(Violation("BE006", node.lineno, node.col_offset, node.module))

    def __init__(self, directory=".", ignore=""):
        self.directory = directory
        self.ignore = ignore.split(",")
        self.errors = []
        self.module_dict = {}

    def __add_dir_to_modules(self, dir):
        parent, dirname = os.path.split(dir)
        if parent in self.module_dict:
            self.module_dict[dir] = self.module_dict[parent] + "." + dirname
        else:
            self.module_dict[dir] = dirname

    def run_checks(self):
        rootdir = self.directory
        if os.path.isfile(rootdir):
            self.__check_file(rootdir)
        else:
            if rootdir == ".":
                rootdir = os.getcwd()

            for subdir, dirs, files in os.walk(rootdir):
                if "__init__.py" in files:
                    self.__add_dir_to_modules(subdir)

                for file in files:
                    name, extension = os.path.splitext(file)
                    if extension.lower() == ".py":
                        filepath = os.path.join(subdir, file)
                        self.__check_file(filepath)
            self.__check_root()
        return self.errors

    def __add_error(self, type, filepath, line=0, column=0):
        if type in self.ignore:
            return

        text = ""
        if type == "BE001":
            text = "string contains absolute path"
        elif type == "BE002":
            text = "code does not compile"
        elif type == "BE003":
            text = "line longer than 120 characters"
        elif type == "BE004":
            text = "reloading modules in production code"
        elif type == "BE005":
            text = 'file does not contain encoding header: "# -*- coding: utf-8 -*-"'
        elif type == "BE006":
            text = 'local imports should be relative, not absolute'
        elif type == "BE100":
            text = "project does not contain .gitignore file"
        elif type == "BE101":
            text = ".gitignore file not ignoring *.pyc files"
        elif type == "BE102":
            text = ".gitignore file not ignoring .*.swp files"
        elif type == "BE103":
            text = ".gitignore file not ignoring .idea files (pycharm project files)"
        elif type == "BE104":
            text = ".gitignore file not ignoring files ending in '~'"
        else:
            text = "unknown error"

        relative_filepath = ""
        if filepath:
            relative_filepath = os.path.join(".", os.path.relpath(filepath, self.directory))

        self.errors.append(
            "{0}:{1}:{2}: {3} {4}".format(relative_filepath, line, column, type, text))

    def __check_file(self, filepath):
        module = self.module_dict.get(os.path.dirname(filepath))
        with open(filepath, 'r') as source_file:
            try:
                contents = source_file.read()
                lines = contents.split("\n")
                line_number = 0
                # check for line length errors
                for line in lines:
                    if len(line) > 120:
                        self.__add_error("BE003", filepath, line_number + 1)
                    line_number += 1
                # check for UTF-8 encoding
                has_encoding = False
                for line in lines[:2]:
                    if "# -*- coding: utf-8 -*-" in line:
                        has_encoding = True

                if not has_encoding and len(lines) > 1 and lines[0] == "":
                    self.__add_error("BE005", filepath, 1)

                # check for other bfx errors
                node = ast.parse(contents)
                self.__find_errors(node, filepath, module)
            except Exception:
                # report compile errors
                self.__add_error("BE002", filepath)

    def __check_root(self):

        gitignore_path = os.path.join(self.directory, ".gitignore")

        if os.path.exists(gitignore_path):
            with open(gitignore_path) as gitignore_file:
                lines = gitignore_file.read().split("\n")
                if "*.pyc" not in lines:
                    self.__add_error("BE101", "")
                if ".*.swp" not in lines:
                    self.__add_error("BE102", "")
                if ".idea" not in lines:
                    self.__add_error("BE103", "")
                if "*~" not in lines:
                    self.__add_error("BE104", "")
        else:
            self.__add_error("BE100", "")

    def __find_errors(self, node, filepath, module=""):
        module = self.module_dict.get(os.path.dirname(filepath))
        visitor = InternalStandardsChecker.NodeVisitor(module)
        visitor.visit(node)
        violations = visitor.violations

        for violation in violations:
            self.__add_error(violation.code, filepath, violation.line, violation.column)




