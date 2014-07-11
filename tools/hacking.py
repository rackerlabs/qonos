#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012, Cloudscaling
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""HACKING file compliance testing

Built on top of pep8.py
"""

import inspect
import logging
import os
import re
import subprocess
import sys
import tokenize
import warnings

import pep8

# Don't need this for testing
logging.disable('LOG')

#H1xx comments
#H2xx except
#H3xx imports
#H4xx docstrings
#H5xx dictionaries/lists
#H6xx calling methods
#H7xx localization
#H8xx git commit messages

IMPORT_EXCEPTIONS = ['sqlalchemy', 'migrate']
START_DOCSTRING_TRIPLE = ['u"""', 'r"""', '"""', "u'''", "r'''", "'''"]
END_DOCSTRING_TRIPLE = ['"""', "'''"]
VERBOSE_MISSING_IMPORT = os.getenv('HACKING_VERBOSE_MISSING_IMPORT', 'False')

_missingImport = set([])


# Monkey patch broken excluded filter in pep8
# See https://github.com/jcrocholl/pep8/pull/111
def excluded(self, filename):
    """Check if options.exclude contains a pattern that matches filename."""
    basename = os.path.basename(filename)
    return any((pep8.filename_match(filename, self.options.exclude,
                               default=False),
                pep8.filename_match(basename, self.options.exclude,
                               default=False)))


def input_dir(self, dirname):
    """Check all files in this directory and all subdirectories."""
    dirname = dirname.rstrip('/')
    if self.excluded(dirname):
        return 0
    counters = self.options.report.counters
    verbose = self.options.verbose
    filepatterns = self.options.filename
    runner = self.runner
    for root, dirs, files in os.walk(dirname):
        if verbose:
            print('directory ' + root)
        counters['directories'] += 1
        for subdir in sorted(dirs):
            if self.excluded(os.path.join(root, subdir)):
                dirs.remove(subdir)
        for filename in sorted(files):
            # contain a pattern that matches?
            if ((pep8.filename_match(filename, filepatterns) and
                 not self.excluded(filename))):
                runner(os.path.join(root, filename))


def is_import_exception(mod):
    return (mod in IMPORT_EXCEPTIONS or
            any(mod.startswith(m + '.') for m in IMPORT_EXCEPTIONS))


def import_normalize(line):
    # convert "from x import y" to "import x.y"
    # handle "from x import y as z" to "import x.y as z"
    split_line = line.split()
    if ("import" in line and line.startswith("from ") and "," not in line and
           split_line[2] == "import" and split_line[3] != "*" and
           split_line[1] != "__future__" and
           (len(split_line) == 4 or
           (len(split_line) == 6 and split_line[4] == "as"))):
        return "import %s.%s" % (split_line[1], split_line[3])
    else:
        return line


def hacking_todo_format(physical_line, tokens):
    """Check for 'TODO()'.

    HACKING guide recommendation for TODO:
    Include your name with TODOs as in "#TODO(termie)"

    Okay: #TODO(sdague)
    H101: #TODO fail
    H101: #TODO (jogo) fail
    """
    # TODO(sdague): TODO check shouldn't fail inside of space
    pos = physical_line.find('TODO')
    pos1 = physical_line.find('TODO(')
    pos2 = physical_line.find('#')  # make sure it's a comment
    if (pos != pos1 and pos2 >= 0 and pos2 < pos and len(tokens) == 0):
        return pos, "H101: Use TODO(NAME)"


def hacking_except_format(logical_line):
    r"""Check for 'except:'.

    HACKING guide recommends not using except:
    Do not write "except:", use "except Exception:" at the very least

    Okay: except Exception:
    H201: except:
    """
    if logical_line.startswith("except:"):
        yield 6, "H201: no 'except:' at least use 'except Exception:'"


def hacking_except_format_assert(logical_line):
    r"""Check for 'assertRaises(Exception'.

    HACKING guide recommends not using assertRaises(Exception...):
    Do not use overly broad Exception type

    Okay: self.assertRaises(QonosException)
    H202: self.assertRaises(Exception)
    """
    if logical_line.startswith("self.assertRaises(Exception"):
        yield 1, "H202: assertRaises Exception too broad"


def hacking_one_import_per_line(logical_line):
    r"""Check for import format.

    HACKING guide recommends one import per line:
    Do not import more than one module per line

    Examples:
    Okay: from qonos.common import exception
    H301: from qonos.common import exception, timeutils
    """
    pos = logical_line.find(',')
    parts = logical_line.split()
    if (pos > -1 and (parts[0] == "import" or
                      parts[0] == "from" and parts[2] == "import") and
        not is_import_exception(parts[1])):
        yield pos, "H301: one import per line"


def hacking_import_module_only(logical_line):
    r"""Check for import module only.

    HACKING guide recommends importing only modules:
    Do not import objects, only modules

    Okay: from os import path
    Okay: import os.path
    H302: from os.path import dirname as dirname2
    H303  from os.path import *
    H304  import flakes
    """
    # H302 import only modules
    # H303 Invalid Import
    # H304 Relative Import

    # TODO(sdague) actually get these tests working
    # TODO(jogo) simplify this code
    def import_module_check(mod, parent=None, added=False):
        """Checks for relative, modules and invalid imports.

        If can't find module on first try, recursively check for relative
        imports.
        When parsing 'from x import y,' x is the parent.
        """
        current_path = os.path.dirname(pep8.current_file)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', DeprecationWarning)
                valid = True
                if parent:
                    parent_mod = __import__(parent, globals(), locals(),
                        [mod], -1)
                    valid = inspect.ismodule(getattr(parent_mod, mod))
                else:
                    __import__(mod, globals(), locals(), [], -1)
                    valid = inspect.ismodule(sys.modules[mod])
                if not valid:
                    if added:
                        sys.path.pop()
                        added = False
                        return logical_line.find(mod), ("H304: No "
                            "relative imports. '%s' is a relative import"
                            % logical_line)
                    return logical_line.find(mod), ("H302: import only "
                        "modules. '%s' does not import a module"
                        % logical_line)

        except (ImportError, NameError) as exc:
            if not added:
                added = True
                sys.path.append(current_path)
                return import_module_check(mod, parent, added)
            else:
                name = logical_line.split()[1]
                if name not in _missingImport:
                    if VERBOSE_MISSING_IMPORT != 'False':
                        print >> sys.stderr, ("ERROR: import '%s' in %s "
                                              "failed: %s" %
                            (name, pep8.current_file, exc))
                    _missingImport.add(name)
                added = False
                sys.path.pop()
                return

        except AttributeError:
            # Invalid import
            if "import *" in logical_line:
                # TODO(jogo): handle "from x import *, by checking all
                #           "objects in x"
                return
            return logical_line.find(mod), ("H303: Invalid import, "
                "%s" % mod)

    split_line = logical_line.split()
    if (", " not in logical_line and
            split_line[0] in ('import', 'from') and
            (len(split_line) in (2, 4, 6)) and
            split_line[1] != "__future__"):
        if is_import_exception(split_line[1]):
            return
        if "from" == split_line[0]:
            rval = import_module_check(split_line[3], parent=split_line[1])
        else:
            rval = import_module_check(split_line[1])
        if rval is not None:
            yield rval


#TODO(jogo): import template: H305


def hacking_import_alphabetical(logical_line, blank_lines, previous_logical,
                             indent_level, previous_indent_level):
    r"""Check for imports in alphabetical order.

    HACKING guide recommendation for imports:
    imports in human alphabetical order

    Okay: import os\nimport sys\n\nimport qonos\nfrom qonos import tests
    H306: import sys\nimport os
    """
    # handle import x
    # use .lower since capitalization shouldn't dictate order
    split_line = import_normalize(logical_line.strip()).lower().split()
    split_previous = import_normalize(previous_logical.strip()).lower().split()

    if blank_lines < 1 and indent_level == previous_indent_level:
        length = [2, 4]
        if (len(split_line) in length and len(split_previous) in length and
            split_line[0] == "import" and split_previous[0] == "import"):
            if split_line[1] < split_previous[1]:
                yield (0, "H306: imports not in alphabetical order (%s, %s)"
                       % (split_previous[1], split_line[1]))


def in_docstring_position(previous_logical):
    return (previous_logical.startswith("def ") or
        previous_logical.startswith("class "))


def hacking_docstring_start_space(physical_line, previous_logical):
    r"""Check for docstring not start with space.

    HACKING guide recommendation for docstring:
    Docstring should not start with space

    Okay: def foo():\n    '''This is good.'''
    H401: def foo():\n    ''' This is not.'''
    """
    # short circuit so that we don't fail on our own fail test
    # when running under external pep8
    if physical_line.find("H401: def foo()") != -1:
        return

    # it's important that we determine this is actually a docstring,
    # and not a doc block used somewhere after the first line of a
    # function def
    if in_docstring_position(previous_logical):
        pos = max([physical_line.find(i) for i in START_DOCSTRING_TRIPLE])
        if pos != -1 and len(physical_line) > pos + 4:
            if physical_line[pos + 3] == ' ':
                return (pos, "H401: docstring should not start with"
                        " a space")


def hacking_docstring_one_line(physical_line):
    r"""Check one line docstring end.

    HACKING guide recommendation for one line docstring:
    A one line docstring looks like this and ends in punctuation.

    Okay: '''This is good.'''
    Okay: '''This is good too!'''
    Okay: '''How about this?'''
    H402: '''This is not'''
    H402: '''Bad punctuation,'''
    """
    #TODO(jogo) make this apply to multi line docstrings as well
    line = physical_line.lstrip()

    if line.startswith('"') or line.startswith("'"):
        pos = max([line.find(i) for i in START_DOCSTRING_TRIPLE])  # start
        end = max([line[-4:-1] == i for i in END_DOCSTRING_TRIPLE])  # end

        if pos != -1 and end and len(line) > pos + 4:
            if line[-5] not in ['.', '?', '!']:
                return pos, "H402: one line docstring needs punctuation."


def hacking_docstring_multiline_end(physical_line, previous_logical):
    r"""Check multi line docstring end.

    HACKING guide recommendation for docstring:
    Docstring should end on a new line

    Okay: '''foobar\nfoo\nbar\n'''
    H403: def foo():\n'''foobar\nfoo\nbar\n   d'''\n\n
    """
    if in_docstring_position(previous_logical):
        pos = max(physical_line.find(i) for i in END_DOCSTRING_TRIPLE)
        if pos != -1 and len(physical_line) == pos + 4:
            if physical_line.strip() not in START_DOCSTRING_TRIPLE:
                return (pos, "H403: multi line docstring end on new line")


def hacking_docstring_multiline_start(physical_line, previous_logical, tokens):
    r"""Check multi line docstring start with summary.

    HACKING guide recommendation for docstring:
    A multi line docstring should start with a one-line summary

    Okay: '''foobar\nfoo\nbar\n'''
    H404: def foo():\n'''\nfoo\nbar\n''' \n\n
    """
    if in_docstring_position(previous_logical):
        pos = max([physical_line.find(i) for i in START_DOCSTRING_TRIPLE])
        # start of docstring when len(tokens)==0
        if len(tokens) == 0 and pos != -1 and len(physical_line) == pos + 4:
            if physical_line.strip() in START_DOCSTRING_TRIPLE:
                return (pos, "H404: multi line docstring "
                        "should start with a summary")


def hacking_no_cr(physical_line):
    r"""Check that we only use newlines not cariage returns.

    Okay: import os\nimport sys
    # pep8 doesn't yet replace \r in strings, will work on an
    # upstream fix
    H901 import os\r\nimport sys
    """
    pos = physical_line.find('\r')
    if pos != -1 and pos == (len(physical_line) - 2):
        return (pos, "H901: Windows style line endings not allowed in code")


FORMAT_RE = re.compile("%(?:"
                            "%|"           # Ignore plain percents
                            "(\(\w+\))?"   # mapping key
                            "([#0 +-]?"    # flag
                             "(?:\d+|\*)?"  # width
                             "(?:\.\d+)?"   # precision
                             "[hlL]?"       # length mod
                             "\w))")        # type


class LocalizationError(Exception):
    pass


def check_i18n():
    """Generator that checks token stream for localization errors.

    Expects tokens to be ``send``ed one by one.
    Raises LocalizationError if some error is found.
    """
    while True:
        try:
            token_type, text, _, _, line = yield
        except GeneratorExit:
            return

        if (token_type == tokenize.NAME and text == "_" and
            not line.startswith('def _(msg):')):

            while True:
                token_type, text, start, _, _ = yield
                if token_type != tokenize.NL:
                    break
            if token_type != tokenize.OP or text != "(":
                continue  # not a localization call

            format_string = ''
            while True:
                token_type, text, start, _, _ = yield
                if token_type == tokenize.STRING:
                    format_string += eval(text)
                elif token_type == tokenize.NL:
                    pass
                else:
                    break

            if not format_string:
                raise LocalizationError(start,
                    "H701: Empty localization string")
            if token_type != tokenize.OP:
                raise LocalizationError(start,
                    "H701: Invalid localization call")
            if text != ")":
                if text == "%":
                    raise LocalizationError(start,
                        "H702: Formatting operation should be outside"
                        " of localization method call")
                elif text == "+":
                    raise LocalizationError(start,
                        "H702: Use bare string concatenation instead"
                        " of +")
                else:
                    raise LocalizationError(start,
                        "H702: Argument to _ must be just a string")

            format_specs = FORMAT_RE.findall(format_string)
            positional_specs = [(key, spec) for key, spec in format_specs
                                            if not key and spec]
            # not spec means %%, key means %(smth)s
            if len(positional_specs) > 1:
                raise LocalizationError(start,
                    "H703: Multiple positional placeholders")


def hacking_localization_strings(logical_line, tokens):
    r"""Check localization in line.

    Okay: _("This is fine")
    Okay: _("This is also fine %s")
    H701: _('')
    H702: _("Bob" + " foo")
    H702: _("Bob %s" % foo)
    # H703 check is not quite right, disabled by removing colon
    H703 _("%s %s" % (foo, bar))
    """
    # TODO(sdague) actually get these tests working
    gen = check_i18n()
    next(gen)
    try:
        map(gen.send, tokens)
        gen.close()
    except LocalizationError as e:
        yield e.args

#TODO(jogo) Dict and list objects

current_file = ""


def readlines(filename):
    """Record the current file being tested."""
    pep8.current_file = filename
    return open(filename).readlines()


def add_hacking():
    """Monkey patch in HACKING guidelines.

    Look for functions that start with hacking_ and have arguments
    and add them to pep8 module
    Assumes you know how to write pep8.py checks
    """
    for name, function in globals().items():
        if not inspect.isfunction(function):
            continue
        args = inspect.getargspec(function)[0]
        if args and name.startswith("hacking_"):
            exec("pep8.%s = %s" % (name, name))


def once_git_check_commit_title():
    """Check git commit messages.

    HACKING recommends not referencing a bug or blueprint in first line,
    it should provide an accurate description of the change
    H801
    H802 Title limited to 50 chars
    """
    #Get title of most recent commit

    subp = subprocess.Popen(['git', 'log', '--no-merges', '--pretty=%s', '-1'],
            stdout=subprocess.PIPE)
    title = subp.communicate()[0]
    if subp.returncode:
        raise Exception("git log failed with code %s" % subp.returncode)

    #From https://github.com/openstack/openstack-ci-puppet
    #       /blob/master/modules/gerrit/manifests/init.pp#L74
    #Changeid|bug|blueprint
    git_keywords = (r'(I[0-9a-f]{8,40})|'
                    '([Bb]ug|[Ll][Pp])[\s\#:]*(\d+)|'
                    '([Bb]lue[Pp]rint|[Bb][Pp])[\s\#:]*([A-Za-z0-9\\-]+)')
    GIT_REGEX = re.compile(git_keywords)

    error = False
    #NOTE(jogo) if match regex but over 3 words, acceptable title
    if GIT_REGEX.search(title) is not None and len(title.split()) <= 3:
        print ("H801: git commit title ('%s') should provide an accurate "
               "description of the change, not just a reference to a bug "
               "or blueprint" % title.strip())
        error = True
    if len(title.decode('utf-8')) > 72:
        print ("H802: git commit title ('%s') should be under 50 chars"
                % title.strip())
        error = True
    return error

imports_on_separate_lines_H301_compliant = r"""
    Imports should usually be on separate lines.

    Okay: import os\nimport sys
    E401: import sys, os

    H301: from subprocess import Popen, PIPE
    Okay: from qonos import api
    Okay: from qonos.common import exception
    Okay: import qonos
    Okay: import qonos.db.migration
    """

if __name__ == "__main__":
    #include current path
    sys.path.append(os.getcwd())
    #Run once tests (not per line)
    once_error = once_git_check_commit_title()
    #HACKING error codes start with an H
    pep8.SELFTEST_REGEX = re.compile(r'(Okay|[EWH]\d{3}):\s(.*)')
    pep8.ERRORCODE_REGEX = re.compile(r'[EWH]\d{3}')
    add_hacking()
    pep8.current_file = current_file
    pep8.readlines = readlines
    pep8.StyleGuide.excluded = excluded
    pep8.StyleGuide.input_dir = input_dir
    # we need to kill this docstring otherwise the self tests fail
    pep8.imports_on_separate_lines.__doc__ = \
        imports_on_separate_lines_H301_compliant

    try:
        pep8._main()
        sys.exit(once_error)
    finally:
        if len(_missingImport) > 0:
            print >> sys.stderr, ("%i imports missing in this test environment"
                    % len(_missingImport))
