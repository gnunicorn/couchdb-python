#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2007 Christopher Lenz
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.

"""Implementation of a view server for functions written in Python."""

import os
import simplejson as json
import sys
import traceback
from types import FunctionType

__all__ = ['main', 'run']
__docformat__ = 'restructuredtext en'

def run(input=sys.stdin, output=sys.stdout):
    r"""CouchDB view function handler implementation for Python.

    >>> from StringIO import StringIO

    >>> output = StringIO()
    >>> run(input=StringIO('["reset"]\n'), output=output)
    >>> print output.getvalue()
    true
    <BLANKLINE>

    >>> output = StringIO()
    >>> run(input=StringIO('["add_fun", "def fun(doc): yield None, doc"]\n'),
    ...     output=output)
    >>> print output.getvalue()
    true
    <BLANKLINE>

    >>> output = StringIO()
    >>> run(input=StringIO('["add_fun", "def fun(doc): yield None, doc"]\n'
    ...                    '["map_doc", {"foo": "bar"}]\n'),
    ...     output=output)
    >>> print output.getvalue()
    true
    [[[null, {"foo": "bar"}]]]
    <BLANKLINE>

    :param input: the readable file-like object to read input from
    :param output: the writable file-like object to write output to
    """
    functions = []

    def reset():
        del functions[:]
        return True

    def add_fun(string):
        string = '\xef\xbb\xbf' + string.encode('utf-8')
        globals_ = {}
        try:
            exec string in {}, globals_
        except Exception, e:
            return {'error': {'id': 'map_compilation_error', 'reason': e.args[0]}}
        err = {'error': {
            'id': 'map_compilation_error',
            'reason': 'string must eval to a function (ex: "def(doc): return 1")'
        }}
        if len(globals_) != 1:
            return err
        function = globals_.values()[0]
        if type(function) is not FunctionType:
            return err
        functions.append(function)
        return True

    def map_doc(doc):
        results = []
        for function in functions:
            try:
                results.append([[key, value] for key, value in function(doc)])
            except Exception, e:
                results.append([])
                output.write(json.dumps({'log': e.args[0]}))
        return results

    handlers = {'reset': reset, 'add_fun': add_fun, 'map_doc': map_doc}

    try:
        while True:
            line = input.readline()
            if not line:
                break
            try:
                cmd = json.loads(line)
            except ValueError, e:
                sys.stderr.write('error: %s\n' % e)
                sys.stderr.flush()
                exit(1)
            else:
                retval = handlers[cmd[0]](*cmd[1:])
                output.write(json.dumps(retval))
                output.write('\n')
                output.flush()
    except KeyboardInterrupt:
        exit(0)

_VERSION = """%(name)s - CouchDB Python %(version)s

Copyright (C) 2007 Christopher Lenz <cmlenz@gmx.de>.
"""
_HELP = """Usage: %(name)s [OPTION]

The %(name)s command runs the CouchDB Python view server.

The exit status is 0 for success or 1 for failure.

Options:

  --version          display version information and exit
  -h, --help         display a short help message and exit

Report bugs via the web at <http://code.google.com/p/couchdb-python>.
"""

def main():
    """Command-line entry point for running the view server."""
    import getopt
    from couchdb import __version__ as VERSION
    try:
        option_list, argument_list = getopt.gnu_getopt(
            sys.argv[1:], 'h', ['version', 'help'])
        message = None
        for option, value in option_list:
            if option in ('--version'):
                message = _VERSION % dict(name=os.path.basename(sys.argv[0]),
                                      version=VERSION)
            elif option in ('-h', '--help'):
                message = _HELP % dict(name=os.path.basename(sys.argv[0]))
        if message:
            sys.stdout.write(message)
            sys.stdout.flush()
            exit(0)
    except getopt.GetoptError, error:
        message = '%s\n\nTry `%s --help` for more information.\n' % (
            str(error), os.path.basename(sys.argv[0])
        )
        sys.stderr.write(message)
        sys.stderr.flush()
        exit(1)
    run()

if __name__ == '__main__':
    main()
