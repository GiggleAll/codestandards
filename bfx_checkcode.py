import sys
from bfx_local.checker import CodeChecker
from bfx_local.cli_parameters import Parameters


if __name__ == '__main__':
    parameters = Parameters(__file__, sys.argv)
    checker = CodeChecker(
        directory=parameters.directory,
        use_git=parameters.use_git,
        only_staged=parameters.only_staged,
        print_log=False,
        write_log=parameters.write_log,
        add_log_to_git=parameters.add_log_to_git,
        logfile_name=parameters.logfile_name,
        prune_errors=parameters.prune_errors,
        required_namespace=parameters.required_namespace)

    results = checker.run_checks()

    # If there are no results, then the required namespace is not present and we should do nothing
    if not results:
        sys.exit(0)

    total_violations = 0
    for result in results:
        total_violations += result.num_violations

    if total_violations:
        print checker.log
        if parameters.write_log:
            print "\nCode standards violations have been written to the violations log."
        else:
            print "\nCode standards violations found."
        print 'If possible, please fix them with "git commit --amend" before pushing to the server.\n'
    else:
        print "No code standards violations detected.\n"

    sys.exit(0)
