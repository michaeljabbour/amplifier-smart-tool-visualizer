PEP: 585
Title: Type Hinting Generics In Standard Collections
Status: Final
Created: 03-Mar-2019
Python-Version: 3.9
Resolution: https://mail.python.org/archives/list/python-dev@python.org/thread/HW2NFOEMCVCTAFLBLC3V7MLM6ZNMKP42/

[...]

Abstract
========

Static typing as defined by PEPs 484, 526, 544, 560, and 563 was built
incrementally on top of the existing Python runtime and constrained by
existing syntax and runtime behavior.  This led to the existence of
a duplicated collection hierarchy in the ``typing`` module due to
generics (for example ``typing.List`` and the built-in ``list``).

This PEP proposes to enable support for the generics syntax in all
standard collections currently available in the ``typing`` module.


Rationale and Goals
===================

This change removes the necessity for a parallel type hierarchy in the
``typing`` module, making it easier for users to annotate their programs
and easier for teachers to teach Python.

[...]

Backwards compatibility
=======================

Tooling, including type checkers and linters, will have to be adapted to
recognize standard collections as generics.

On the source level, the newly described functionality requires
Python 3.9.  For use cases restricted to type annotations, Python files
with the "annotations" future-import (available since Python 3.7) can
parameterize standard collections, including builtins.  To reiterate,
that depends on the external tools understanding that this is valid.

[...]

Implementation
==============

Starting with Python 3.7, when ``from __future__ import annotations`` is
used, function and variable annotations can parameterize standard
collections directly.  Example::

    from __future__ import annotations

    def find(haystack: dict[str, list[int]]) -> int:
        ...

Usefulness of this syntax before :pep:`585` is limited as external tooling
like Mypy does not recognize standard collections as generic.  Moreover,
certain features of typing like type aliases or casting require putting
types outside of annotations, in runtime context.  While these are
relatively less common than type annotations, it's important to allow
using the same type syntax in all contexts.  This is why starting with
Python 3.9, the following collections become generic using
``__class_getitem__()`` to parameterize contained types:

* ``tuple``  # typing.Tuple
* ``list``  # typing.List
* ``dict``  # typing.Dict
* ``set``  # typing.Set
* ``frozenset``  # typing.FrozenSet

[...]

* ``contextlib.AbstractAsyncContextManager``  # typing.AsyncContextManager
* ``re.Pattern``  # typing.Pattern, typing.re.Pattern
* ``re.Match``  # typing.Match, typing.re.Match

Importing those from ``typing`` is deprecated.  Due to :pep:`563` and the
intention to minimize the runtime impact of typing, this deprecation
will not generate DeprecationWarnings.  Instead, type checkers may warn
about such deprecated usage when the target version of the checked
program is signalled to be Python 3.9 or newer.  It's recommended to
allow for those warnings to be silenced on a project-wide basis.

The deprecated functionality may eventually be removed from the ``typing``
module. Removal will occur no sooner than Python 3.9's end of life,
scheduled for October 2025.
