import json
import os
import re
import subprocess
import tempfile
import shutil
import sys

import flake8.engine as flake8_engine

from StringIO import StringIO
from collections import namedtuple
from contextlib import contextmanager
from .internal import InternalStandardsChecker


@contextmanager
def create_temp_dir():
    """
    This helper function is meant to automate the deletion of a temp directory

    example:

    with create_temp_dir() as temp_dir:
        # Do whatever you like to the local files in "temp_dir"
    """
    tempdir = tempfile.mkdtemp()
    try:
        yield tempdir
    finally:
        shutil.rmtree(tempdir)


# This is a context manager class, and should be named like a function because of the usage.
# Ignore N801 PEP-8 standards violation
class capture_output(list):
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        sys.stdout = self._stdout


def system(*args, **kwargs):
    kwargs.setdefault('stdout', subprocess.PIPE)
    proc = subprocess.Popen(args, **kwargs)
    out, err = proc.communicate()
    return out, proc.returncode


def smartsort(a, b):
    a_list = a.split(":")
    b_list = b.split(":")

    length = max(len(a_list), len(b_list))

    for i in range(0, length):
        try:
            a_part = int(a_list[i])
            b_part = int(b_list[i])

            if a_part > b_part:
                return 1
            if b_part > a_part:
                return -1
        except ValueError:
            if a_list[i] > b_list[i]:
                return 1
            if b_list[i] > a_list[i]:
                return -1
    return 0


class CheckResult:
    def __init__(self, type, output, num_violations, return_code):
        self.type = type
        self.output = output
        self.num_violations = num_violations
        self.return_code = return_code


LineErrorEntry = namedtuple(
    "LineErrorEntry", "code string")


class CodeChecker:

    CHECKS_FLAKE8 = "flake8"
    CHECKS_BFX = "bfx"
    IGNORED_CODES = "W291,W292,W293,W391,E501"

    def __init__(self,
                 checks=(CHECKS_FLAKE8, CHECKS_BFX),
                 directory=".",
                 use_git=False,
                 only_staged=False,
                 write_log=False,
                 print_log=True,
                 add_log_to_git=False,
                 logfile_name=".violations",
                 ignorefile_name=".violations.ignore",
                 prune_errors=True,
                 required_namespace=""):

        self.checks = checks
        self.directory = directory
        self.use_git = use_git
        self.only_staged = only_staged
        self.write_log = write_log
        self.print_log = print_log
        self.add_log_to_git = add_log_to_git
        self.logfile_name = logfile_name
        self.ignorefile_name = ignorefile_name
        self.log = "Checks have not yet been run"
        self.prune_errors = prune_errors
        self.required_namespace = required_namespace
        self.results = []

        ignorefile_path = os.path.join(self.directory, ignorefile_name)
        if ignorefile_name and os.path.exists(ignorefile_path):
            with open(ignorefile_path, 'r') as ignorefile:
                self.ignore = json.loads(ignorefile.read())
        else:
            self.ignore = None

    def __run_check(self, check_type, directory):
        output = []
        num_violations = 0

        if check_type == CodeChecker.CHECKS_FLAKE8:
            with capture_output() as captured_output:
                flake8_style = flake8_engine.get_style_guide()
                flake8_style.check_files(paths=[directory])
            output = []
            for line in captured_output:
                output.append(line.replace(directory, "."))
            num_violations = len(output)
        elif check_type == CodeChecker.CHECKS_BFX:
            internal_checker = InternalStandardsChecker(directory)
            output = internal_checker.run_checks()
            num_violations = len(output)

        return_code = 1 if num_violations else 0
        return CheckResult(check_type, output, num_violations, return_code)

    @staticmethod
    def __get_comment_string(line_dict, line_number):
        """
        Gets the comment string data of a line of code, together with that of the previous and next lines.

        :param self:
        :param line_dict: a dictionary containing the lines of code from a file
        :param line_number: the line number we are looking for
        :return:
        """
        comment_string = ""
        line_numbers = (line_number - 2, line_number - 1, line_number)
        for i in line_numbers:
            if i in line_dict:
                line = line_dict[i].split("#")
                if len(line) > 1:
                    comment_string += "#".join(line[1:])

        return comment_string

    def __should_ignore_file(self, file_path):
        if not self.ignore:
            return False

        file_path = os.path.normpath(file_path)
        path, name = os.path.split(file_path)

        try:
            if name in self.ignore["files"]:
                return True
        except KeyError:
            pass

        try:
            if file_path in self.ignore["files"]:
                return True
        except KeyError:
            pass

        try:
            for directory in self.ignore["directories"]:
                if os.path.normpath(directory + "/") in path:
                    return True
        except KeyError:
            pass

        try:
            for pattern in self.ignore["patterns"]:
                if re.search(pattern, file_path):
                    return True
        except KeyError:
            pass

        return False

    def __remove_exceptions(self, results, directory):
        """
        Removes entries from the result list that we have agreed to add an exception for.

        :param results: a list of CheckResult objects
        :param directory: working directory for the purpose of looking up exception comments.
        :return: the amended results file
        """

        # Set up list of ignored error codes
        ignored_codes = CodeChecker.IGNORED_CODES.split(",")

        try:
            ignored_codes += self.ignore["codes"]
        except (TypeError, KeyError):
            pass

        # Begin by building a dictionary for parsing the files with the following structure:
        # {
        #     "./file1.py":
        #     {
        #         3: [("BE001", <original_error_output>), ("BE002", <original_error_output>)],
        #         54: [("N321", <original_error_output>)]
        #     },
        #     "./file2.py":
        #     {
        #         78: [("F321", <original_error_output>)]
        #     }
        # }

        file_dict = {}
        for result in results:
            for line in result.output:
                # Parse the line error data from the output string
                values = line.split(":")
                filename = values[0]
                line_number = values[1]
                error_code = values[3].split(" ")[1]

                # Ignore project-level errors
                if filename == '':
                    continue

                # Add the file and line dictionary entries if they don't yet exist
                if filename not in file_dict:
                    file_dict[filename] = {}
                line_dict = file_dict[filename]
                if int(line_number) not in line_dict:
                    line_dict[int(line_number)] = []
                error_codes = line_dict[int(line_number)]

                # Add the entry for the current error code
                error_codes.append(LineErrorEntry(error_code, line))

        # Load each file and look for approval commpents for the offending lines
        ignored_errors = []
        for filename in file_dict:
            # build a dictionary of the lines for the file, so we can do fast random access of the lines. Please note
            # that this will NOT work for insanely huge files, as we are storing the entire file in memory.
            file_lines = {}
            with open(os.path.join(self.directory, filename), 'r') as offending_file:
                for number, line in enumerate(offending_file):
                    file_lines[number] = line

            # Go through each offending line, and if there is a comment mentioning the error code nearby, add it
            # to the list of approved lines
            offending_lines = file_dict[filename]
            for line_number in offending_lines:
                error_entries = offending_lines[line_number]
                comment_string = self.__get_comment_string(file_lines, line_number)

                for line_entry in error_entries:
                    if line_entry.code in comment_string:
                        ignored_errors.append(line_entry.string)

        # Doctor the results to exclude approved lines
        for result in results:
            new_output = []
            for line in result.output:
                values = line.split(":")
                filepath = values[0]
                code = values[3].split(" ")[1]

                if line not in ignored_errors and not self.__should_ignore_file(filepath) and code not in ignored_codes:
                    new_output.append(line)

            result.output = new_output
            result.num_violations = len(new_output)

        return results

    def __run_checks(self, directory):
        results = []
        for check in self.checks:
            results.append(self.__run_check(check, directory))

        if self.prune_errors:
            results = self.__remove_exceptions(results, directory)
        return results

    def __run_git_checks(self):
        if self.only_staged:
            modified = re.compile('^[AM]+\s+(?P<name>.*\.(?:py|gitignore|violations.ignore))\n', re.MULTILINE)
            files, code = system('git', 'status', '--porcelain', cwd=self.directory)
            files = modified.findall(files)
        else:
            modified = re.compile('^(?P<name>.*\.(?:py|gitignore|violations.ignore))\n', re.MULTILINE)
            files, code = system('git', 'ls-files', cwd=self.directory)
            files = modified.findall(files)

        with create_temp_dir() as tempdir:
            for name in files:
                filename = os.path.join(tempdir, name)
                filepath = os.path.dirname(filename)
                if not os.path.exists(filepath):
                    os.makedirs(filepath)
                with file(filename, 'w') as f:
                    system('git', 'show', ':' + name, stdout=f, cwd=self.directory)

            return self.__run_checks(tempdir)

    @property
    def namespace(self):
        url, error = system('git', 'config', "--get", "remote.origin.url", cwd=self.directory)
        # get the namespace
        try:
            url = url.split("/")[-2]
            namespace = url.split(":")[-1]
            return namespace
        except IndexError:
            pass
        return ""

    def run_checks(self):
        # Do the actual analysis
        if self.use_git:
            if self.required_namespace and self.namespace != self.required_namespace:
                return
            results = self.__run_git_checks()
        else:
            results = self.__run_checks(self.directory)

        # Log the results
        self.log = CodeChecker.__create_log(results)
        if self.print_log:
            print self.log
        if self.write_log:
            with open(os.path.join(self.directory, self.logfile_name), 'w') as log_file:
                log_file.write(self.log)
        if self.use_git and self.write_log and self.add_log_to_git:
            system('git', 'add', self.logfile_name, cwd=self.directory)

        return results

    @staticmethod
    def __create_log(results):
        lines = []

        lines.append("Code Standards Violation Report")
        lines.append("")

        violations = []
        for result in results:
            violations += result.output

        violations.sort(cmp=smartsort)

        if len(violations):
            lines += violations
            lines.append("")

        total_violations = 0

        for result in results:
            lines.append("{0} violations: {1}".format(result.type, result.num_violations))
            total_violations += result.num_violations

        lines.append("total violations: {0}".format(total_violations))

        return "\n".join(lines)
















