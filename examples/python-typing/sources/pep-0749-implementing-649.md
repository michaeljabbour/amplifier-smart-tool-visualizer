PEP: 749
Title: Implementing PEP 649
Status: Final
Requires: 649
Created: 28-May-2024
Python-Version: 3.14
Resolution: `05-May-2025 <https://discuss.python.org/t/pep-749-implementing-pep-649/54974/66>`__

[...]

Abstract
========

This PEP supplements :pep:`649` by providing various tweaks and additions to its
specification:

* ``from __future__ import annotations`` (:pep:`563`) will continue to exist with
  its current behavior at least until Python 3.13 reaches its end-of-life. Subsequently,
  it will be deprecated and eventually removed.
* A new standard library module, ``annotationlib``, is added to provide tooling for
  annotations. It will include the ``get_annotations()`` function, an enum for annotation
  formats, a ``ForwardRef`` class, and a helper function for calling ``__annotate__`` functions.
* Annotations in the REPL are lazily evaluated, just like other module-level annotations.
* We specify the behavior of wrapper objects that provide annotations, such as :py:func:`classmethod`
  and code that uses :py:func:`functools.wraps`.
* There will not be a code flag for marking ``__annotate__`` functions
  that can be run in a "fake globals" environment. Instead, we add a fourth format,
  ``VALUE_WITH_FAKE_GLOBALS``, to allow third-party implementors of annotate functions to
  indicate what formats they support.
* Deleting the ``__annotations__`` attribute directly will also clear ``__annotate__``.
* We add functionality to allow evaluating type alias values and type parameter bounds and defaults
  (which were added by :pep:`695` and :pep:`696`) using PEP 649-like semantics.
* The ``SOURCE`` format is renamed to ``STRING`` to improve clarity and reduce the risk of
  user confusion.
* Conditionally defined class and module annotations are handled correctly.
* If annotations are accessed on a partially executed module, the annotations executed so far
  are returned, but not cached.

[...]

Motivation
==========

:pep:`649` provides an excellent framework for creating better semantics for
annotations in Python. It solves a common pain point for users of annotations,
including those using static type hints as well as those using runtime typing,
and it makes the language more elegant and powerful.
The PEP was originally proposed in 2021 for Python 3.10,
and it was accepted in 2023. However, the implementation took longer than anticipated,
and now the PEP is expected to be implemented in Python 3.14.

I have started working on the implementation of the PEP in CPython. I found that
the PEP leaves some areas underspecified, and some
of its decisions in corner cases are questionable. This new PEP proposes several
changes and additions to the specification to address these issues.

This PEP supplements rather than supersedes PEP 649. The changes proposed here
should make the overall user experience better, but they do not change the
general framework of the earlier PEP.

[...]

The future of ``from __future__ import annotations``
====================================================

:pep:`563` previously introduced the future import ``from __future__ import annotations``,
which changes all annotations to strings. :pep:`649` proposes an alternative approach
that does not require this future import, and states:

    If this PEP is accepted, PEP 563 will be deprecated and eventually removed.

However, the PEP does not provide a detailed plan for this deprecation.

There is some previous discussion of this topic `on Discourse <https://discuss.python.org/t/pep-649-deferred-evaluation-of-annotations-tentatively-accepted/21331/44>`__
(note that in the linked post I proposed something different from what is proposed here).

Specification
-------------

We suggest the following deprecation plan:

- In Python 3.14, ``from __future__ import annotations`` will continue to work as it
  did before, converting annotations into strings.

  - If the future import is active, the ``__annotate__`` function of objects with
    annotations will return the annotations as strings when called with the ``VALUE``
    format, reflecting the behavior of ``__annotations__``.

- Sometime after the last release that did not support :pep:`649` semantics (expected to be 3.13)
  reaches its end-of-life, ``from __future__ import annotations`` is deprecated. Compiling
  any code that uses the future import will emit a :py:exc:`DeprecationWarning`. This will
  happen no sooner than the first release after Python 3.13 reaches its end-of-life, but
  the community may decide to wait longer.
- After at least two releases, the future import is removed, and annotations are always
  evaluated as per :pep:`649`. Code that continues to use the future import will raise
  a :py:exc:`SyntaxError`, similar to any other undefined future import.

Rejected alternatives
---------------------

*Immediately make the future import a no-op*: We considered applying :pep:`649` semantics
to all code in Python 3.14, making the future import a no-op. However, this would break
code that works in 3.13 under the following set of conditions:

* ``__future__ import annotations`` is active
* There are annotations that rely on forward references
* Annotations are eagerly evaluated at import time, for example by a metaclass or
  class or function decorator. For example, this currently applies to the
  released version of ``typing_extensions.TypedDict``.

This is expected to be a common pattern, so we cannot afford to break such code during
the upgrade from 3.13 to 3.14.

Such code would still break when the future import is eventually removed. However, this
is many years in the future, giving affected libraries plenty of time to update their code.

*Immediately deprecate the future import*: Instead of waiting until Python 3.13 reaches
its end-of-life, we could immediately start emitting warnings when the future import is
used. However, many libraries are already using ``from __future__ import annotations`` as
an elegant way to enable unrestricted forward references in their annotations. If we deprecate
the future import immediately, it would be impossible for these libraries to use unrestricted
forward references on all supported Python versions while avoiding deprecation warnings:
unlike other features deprecated from the standard library, a ``__future__`` import must
be the first statement in a given module, meaning it would be impossible to only
conditionally import ``__future__.annotations`` on Python 3.13 and lower. (The necessary
``sys.version_info`` check would count as a statement preceding the ``__future__`` import.)

*Keep the future import around forever*: We could also decide to keep the future import
indefinitely. However, this would permanently bifurcate the behavior of the Python
language. This is undesirable; the language should have only a single set of semantics,
not two permanently different modes.

*Make the future import a no-op in the future*: Instead of eventually making
``from __future__ import annotations`` a ``SyntaxError``, we could make it do nothing
instead at some point after Python 3.13 reaches its end-of-life. This still has some
of the same issues outlined above around making it a no-op now, although the ecosystem
would have had much longer to adapt. It is better to have users explicitly remove
the future import from their code in the future once they have confirmed they do not
rely on stringized annotations.

[...]

Renaming ``SOURCE`` to ``STRING``
=================================

The ``SOURCE`` format is meant for tools that need to show a human-readable
format that is close to the original source code. However, we cannot retrieve
the original source in ``__annotate__`` functions, and in some cases, we have
``__annotate__`` functions in Python code that do not have access to the original
code. For example, this applies to :py:func:`dataclasses.make_dataclass`
and the call-based syntax for :py:class:`typing.TypedDict`.

This makes the name ``SOURCE`` a bit of a misnomer. The goal of the format
should indeed be to recreate the source, but the name is likely to mislead
users in practice. A more neutral name would emphasize that the format returns
an annotation dictionary with only strings. We suggest ``STRING``.

Specification
-------------

The ``SOURCE`` format is renamed to ``STRING``. To reiterate the changes in this
PEP, the four supported formats are now:

- ``VALUE``: the default format, which evaluates the annotations and returns the
  resulting values.
- ``VALUE_WITH_FAKE_GLOBALS``: for internal use; should be handled like ``VALUE``
  by annotate functions that support execution with fake globals.
- ``FORWARDREF``: replaces undefined names with ``ForwardRef`` objects.
- ``STRING``: returns strings, attempts to recreate code close to the original source.
