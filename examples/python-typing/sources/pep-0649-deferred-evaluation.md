PEP: 649
Title: Deferred Evaluation Of Annotations Using Descriptors
Status: Final
Created: 11-Jan-2021
Python-Version: 3.14
Replaces: 563
Resolution: `08-May-2023 <https://discuss.python.org/t/pep-649-deferred-evaluation-of-annotations-tentatively-accepted/21331/43>`__

[...]

Abstract
********

Annotations are a Python technology that allows expressing
type information and other metadata about Python functions,
classes, and modules.  But Python's original semantics
for annotations required them to be eagerly evaluated,
at the time the annotated object was bound.  This caused
chronic problems for static type analysis users using
"type hints", due to forward-reference and circular-reference
problems.

Python solved this by accepting :pep:`563`, incorporating
a new approach called "stringized annotations" in which
annotations were automatically converted into strings by
Python.  This solved the forward-reference and circular-reference
problems, and also fostered intriguing new uses for annotation
metadata.  But stringized annotations in turn caused chronic
problems for runtime users of annotations.

This PEP proposes a new and comprehensive third approach
for representing and computing annotations.  It adds a new
internal mechanism for lazily computing annotations on demand,
via a new object method called ``__annotate__``.
This approach, when combined with a novel technique for
coercing annotation values into alternative formats, solves
all the above problems, supports all existing use cases,
and should foster future innovations in annotations.

[...]

********
Overview
********

This PEP adds a new dunder attribute to the objects that
support annotations--functions, classes, and modules.
The new attribute is called ``__annotate__``, and is
a reference to a function which computes and returns
that object's annotations dict.

At compile time, if the definition of an object includes
annotations, the Python compiler will write the expressions
computing the annotations into its own function.  When run,
the function will return the annotations dict.  The Python
compiler then stores a reference to this function in
``__annotate__`` on the object.

Furthermore, ``__annotations__`` is redefined to be a
"data descriptor" which calls this annotation function once
and caches the result.

This mechanism delays the evaluation of annotations expressions
until the annotations are examined, which solves many circular
reference problems.

[...]

If accepted, this PEP would *supersede* :pep:`563`,
and :pep:`563`'s behavior would be deprecated and
eventually removed.

[...]

Mistaken Rejection Of This Approach In November 2017
====================================================

During the early days of discussion around :pep:`563`,
in a November 2017 thread in ``comp.lang.python-dev``,
the idea of using code to delay the evaluation of
annotations was briefly discussed.  At the time the
technique was termed an "implicit lambda expression".

Guido van Rossum—Python's BDFL at the time—replied,
asserting that these "implicit lambda expression" wouldn't
work, because they'd only be able to resolve symbols at
module-level scope:

    IMO the inability of referencing class-level definitions
    from annotations on methods pretty much kills this idea.

https://mail.python.org/pipermail/python-dev/2017-November/150109.html

This led to a short discussion about extending lambda-ized
annotations for methods to be able to refer to class-level
definitions, by maintaining a reference to the class-level
scope.  This idea, too, was quickly rejected.

:pep:`PEP 563 summarizes the above discussion
<563#keeping-the-ability-to-use-function-local-state-when-defining-annotations>`

The approach taken by this PEP doesn't suffer from these
restrictions.  Annotations can access module-level definitions,
class-level definitions, and even local and free variables.

[...]

Motivation For This PEP
=======================

Python's original semantics for annotations made its use for
static type analysis painful due to forward reference problems.
:pep:`563` solved the forward reference problem, and many
static type analysis users became happy early adopters of it.
But its unconventional solution created new problems for two
of the above cited use cases: runtime annotation users,
and wrappers.

First, stringized annotations didn't permit referencing local or
free variables, which meant many useful, reasonable approaches
to creating annotations were no longer viable.  This was
particularly inconvenient for decorators that wrap existing
functions and classes, as these decorators often use closures.

Second, in order for ``eval`` to correctly look up globals in a
stringized annotation, you must first obtain a reference
to the correct module.
But class objects don't retain a reference to their globals.
:pep:`563` suggests looking up a class's module by name in
``sys.modules``—a surprising requirement for a language-level
feature.

Additionally, complex but legitimate constructions can make it
difficult to determine the correct globals and locals dicts to
give to  ``eval`` to properly evaluate a stringized annotation.
Even worse, in some situations it may simply be infeasible.

For example, some libraries (e.g. ``typing.TypedDict``, :mod:`dataclasses`)
wrap a user class, then merge all the annotations from all that
class's base classes together into one cumulative annotations dict.
If those annotations were stringized, calling ``eval`` on them later
may not work properly, because the globals dictionary used for the
``eval`` will be the module where the *user class* was defined,
which may not be the same module where the *annotation* was
defined.  However, if the annotations were stringized because
of forward-reference problems, calling ``eval`` on them early
may not work either, due to the forward reference not being
resolvable yet.  This has proved to be difficult to reconcile;
of the three bug reports linked to below, only one has been
marked as fixed.

* https://github.com/python/cpython/issues/89687
* https://github.com/python/cpython/issues/85421
* https://github.com/python/cpython/issues/90531

Even with proper globals *and* locals, ``eval`` can be unreliable
on stringized annotations.
``eval`` can only succeed if all the symbols referenced in
an annotations are defined.  If a stringized annotation refers
to a mixture of defined and undefined symbols, a simple ``eval``
of that string will fail.  This is a problem for libraries with
that need to examine the annotation, because they can't reliably
convert these stringized annotations into real values.

* Some libraries (e.g. :mod:`dataclasses`) solved this by foregoing real
  values and performing lexical analysis of the stringized annotation,
  which requires a lot of work to get right.

* Other libraries still suffer with this problem,
  which can produce surprising runtime behavior.
  https://github.com/python/cpython/issues/97727

Also, ``eval()`` is slow, and it isn't always available; it's
sometimes removed for space reasons on certain platforms.
``eval()`` on MicroPython doesn't support the ``locals``
argument, which makes converting stringized annotations
into real values at runtime even harder.

Finally, :pep:`563` requires Python implementations to
stringize their annotations.  This is surprising behavior—unprecedented
for a language-level feature, with a complicated implementation,
that must be updated whenever a new operator is added to the
language.

These problems motivated the research into finding a new
approach to solve the problems facing annotations users,
resulting in this PEP.

[...]

Backwards Compatibility With PEP 563 Semantics
==============================================

:pep:`563` changed the semantics of annotations.  When its semantics
are active, annotations must assume they will be evaluated in
*module-level* or *class-level* scope.  They may no longer refer directly
to local variables in the current function or an enclosing function.
This PEP removes that restriction, and annotations may refer any
local variable.

:pep:`563` requires using ``eval`` (or a helper function like
``typing.get_type_hints`` or ``inspect.get_annotations`` that
uses ``eval`` for you) to convert stringized annotations into
their "real" values.  Existing code that activates stringized
annotations, and calls ``eval()`` directly to convert the strings
back into real values, can simply remove the ``eval()`` call.
Existing code using a helper function would continue to work
unchanged, though use of those functions may become optional.

[...]

Finally, the warnings about using the ``if / else`` ternary
operator in annotations apply equally to users of :pep:`563`.
It currently works for them, but could produce incorrect
results when requesting some formats from the helper functions.

If this PEP is accepted, :pep:`563` will be deprecated and
eventually removed.  To facilitate this transition for early
adopters of :pep:`563`, who now depend on its semantics,
``inspect.get_annotations`` and ``typing.get_type_hints`` will
implement a special affordance.

The Python compiler won't generate annotation code objects
for objects defined in a module where :pep:`563` semantics are
active, even if this PEP is accepted.  So, under normal
circumstances, requesting ``inspect.SOURCE`` format from a
helper function would return an empty dict.  As an affordance,
to facilitate the transition, if the helper functions detect
that an object was defined in a module with :pep:`563` active,
and the user requests ``inspect.SOURCE`` format, they'll return
the current value of the ``__annotations__`` dict, which in
this case will be the stringized annotations.  This will allow
:pep:`563` users who lexically analyze stringized annotations
to immediately change over to requesting ``inspect.SOURCE`` format
from the helper functions, which will hopefully smooth their
transition away from :pep:`563`.
