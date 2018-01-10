# -*- coding: utf-8 -*-

"""Implements the Parameters class that encapsulates the user's command-line
choices"""

import optparse


class Parameters(object):
    """Takes an arg list, does command-line processing on it, and stores the
    results in this object, for more convenient access from python.
    """
    def __init__(self, progname, args):
        super(Parameters, self).__init__()
        self.progname = progname
        self.args = args

        parser = self.configure_parser()
        parsed_options, parsed_args = parser.parse_args(self.args)

        if len(parsed_args) > 2:
            parser.error('Unexpected arguments: {0}'.format(parsed_args[2:]))
        elif len(parsed_args) == 2:
            self.directory = parsed_args[1]
        else:
            self.directory = "."

        self.prune_errors = parsed_options.prune_errors
        self.add_log_to_git = parsed_options.add_log_to_git
        self.use_git = parsed_options.use_git
        self.only_staged = parsed_options.only_staged
        self.logfile_name = parsed_options.logfile_name
        self.write_log = parsed_options.logfile_name != ""
        if parsed_options.require_bfx:
            self.required_namespace = "bfx"
        else:
            self.required_namespace = ""

    def configure_parser(self):
        parser = optparse.OptionParser(
            "\n" +
            "    1: %prog\n" +
            "    2: %prog DIRECTORY -l LOGFILE [--option]\n" +
            "    3: %prog -h\n" +
            "\n" +
            "Usage 1 runs a violations check on the local directory, with no git behavior.\n" +
            "Usage 2 runs the violations check in a custom directory, and outputs to a custom log file.\n" +
            "Usage 3 gives help about CLI options.", prog=self.progname)
        parser.add_option('--all', action='store_false', dest="prune_errors", default=True,
                          help='Do not prune ignored errors')
        parser.add_option('--add', action="store_true", dest="add_log_to_git", default=True,
                          help='Add the logfile to git')
        parser.add_option('--git', action="store_true", dest="use_git", default=False,
                          help='Run checks on the files currently active in git')
        parser.add_option('--bfx', action="store_true", dest="require_bfx", default=False,
                          help='Only run checks if this project is in the bfx namespace')
        parser.add_option('--staged', action="store_true", dest="only_staged", default=False,
                          help='Only check files currently staged in git')
        parser.add_option('--log', '-l', action="store", dest="logfile_name", default="",
                          help='LOGFILE is the name of the generated log file')
        return parser

    def __str__(self):
        """Human readable representation of Parameter"""
        return "Parameter ({0})".format(", ".join([
            str(self.progname),
            str(self.args),
        ]))
