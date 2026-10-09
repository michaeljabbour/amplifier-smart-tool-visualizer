PEP: 484
Title: Type Hints
Status: Final
Type: Standards Track
Topic: Typing
Created: 29-Sep-2014
Python-Version: 3.5
Post-History: 16-Jan-2015, 20-Mar-2015, 17-Apr-2015, 20-May-2015, 22-May-2015
Resolution: https://mail.python.org/pipermail/python-dev/2015-May/140104.html

[...]

Abstract
========

:pep:`3107` introduced syntax for function annotations, but the semantics
were deliberately left undefined.  There has now been enough 3rd party
usage for static type analysis that the community would benefit from
a standard vocabulary and baseline tools within the standard library.

This PEP introduces a provisional module to provide these standard
definitions and tools, along with some conventions for situations
where annotations are not available.

Note that this PEP still explicitly does NOT prevent other uses of
annotations, nor does it require (or forbid) any particular processing
of annotations, even when they conform to this specification.  It
simply enables better coordination, as :pep:`333` did for web frameworks.

For example, here is a simple function whose argument and return type
are declared in the annotations::

  def greeting(name: str) -> str:
      return 'Hello ' + name

While these annotations are available at runtime through the usual
``__annotations__`` attribute, *no type checking happens at runtime*.
Instead, the proposal assumes the existence of a separate off-line
type checker which users can run over their source code voluntarily.
Essentially, such a type checker acts as a very powerful linter.
(While it would of course be possible for individual users to employ
a similar checker at run time for Design By Contract enforcement or
JIT optimization, those tools are not yet as mature.)

The proposal is strongly inspired by `mypy <mypy_>`_.  For example, the
type "sequence of integers" can be written as ``Sequence[int]``.  The
square brackets mean that no new syntax needs to be added to the
language.  The example here uses a custom type ``Sequence``, imported
from a pure-Python module ``typing``.  The ``Sequence[int]`` notation
works at runtime by implementing ``__getitem__()`` in the metaclass
(but its significance is primarily to an offline type checker).

The type system supports unions, generic types, and a special type
named ``Any`` which is consistent with (i.e. assignable to and from) all
types.  This latter feature is taken from the idea of gradual typing.
Gradual typing and the full type system are explained in :pep:`483`.

Other approaches from which we have borrowed or to which ours can be
compared and contrasted are described in :pep:`482`.

[...]

Rationale and Goals
===================

:pep:`3107` added support for arbitrary annotations on parts of a
function definition.  Although no meaning was assigned to annotations
then, there has always been an `implicit goal to use them for type
hinting <gvr-artima_>`_, which is listed as the first possible use case
in said PEP.

This PEP aims to provide a standard syntax for type annotations,
opening up Python code to easier static analysis and refactoring,
potential runtime type checking, and (perhaps, in some contexts)
code generation utilizing type information.

Of these goals, static analysis is the most important.  This includes
support for off-line type checkers such as mypy, as well as providing
a standard notation that can be used by IDEs for code completion and
refactoring.

Non-goals
---------

While the proposed typing module will contain some building blocks for
runtime type checking -- in particular the ``get_type_hints()``
function -- third party packages would have to be developed to
implement specific runtime type checking functionality, for example
using decorators or metaclasses.  Using type hints for performance
optimizations is left as an exercise for the reader.

It should also be emphasized that **Python will remain a dynamically
typed language, and the authors have no desire to ever make type hints
mandatory, even by convention.**

[...]

Forward references
------------------

When a type hint contains names that have not been defined yet, that
definition may be expressed as a string literal, to be resolved later.

A situation where this occurs commonly is the definition of a
container class, where the class being defined occurs in the signature
of some of the methods.  For example, the following code (the start of
a simple binary tree implementation) does not work::

  class Tree:
      def __init__(self, left: Tree, right: Tree):
          self.left = left
          self.right = right

To address this, we write::

  class Tree:
      def __init__(self, left: 'Tree', right: 'Tree'):
          self.left = left
          self.right = right

The string literal should contain a valid Python expression (i.e.,
``compile(lit, '', 'eval')`` should be a valid code object) and it
should evaluate without errors once the module has been fully loaded.
The local and global namespace in which it is evaluated should be the
same namespaces in which default arguments to the same function would
be evaluated.

Moreover, the expression should be parseable as a valid type hint, i.e.,
it is constrained by the rules from the section `Acceptable type hints`_
above.
