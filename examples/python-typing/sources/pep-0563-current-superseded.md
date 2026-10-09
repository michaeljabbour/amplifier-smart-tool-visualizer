PEP: 563
Title: Postponed Evaluation of Annotations
Status: Superseded
Created: 08-Sep-2017
Python-Version: 3.7
Post-History: 01-Nov-2017, 21-Nov-2017
Superseded-By: 649, 749
Resolution: https://mail.python.org/pipermail/python-dev/2017-December/151042.html

[...]

Resolution
==========

The features proposed in this PEP never became the default behaviour,
and have been replaced with deferred evaluation of annotations,
as proposed by :pep:`649` and :pep:`749`.

[...]

Abstract
========

:pep:`3107` introduced syntax for function annotations, but the semantics
were deliberately left undefined.  :pep:`484` introduced a standard meaning
to annotations: type hints.  :pep:`526` defined variable annotations,
explicitly tying them with the type hinting use case.

This PEP proposes changing function annotations and variable annotations
so that they are no longer evaluated at function definition time.
Instead, they are preserved in ``__annotations__`` in string form.

This change is being introduced gradually, starting with a
``__future__`` import in Python 3.7.

[...]

Deprecation policy
------------------

Starting with Python 3.7, a ``__future__`` import is required to use the
described functionality.  No warnings are raised.

NOTE: Whether this will eventually become the default behavior is currently unclear
pending decision on :pep:`649`.  In any case, use of annotations that depend upon
their eager evaluation is incompatible with both proposals and is no longer
supported.
