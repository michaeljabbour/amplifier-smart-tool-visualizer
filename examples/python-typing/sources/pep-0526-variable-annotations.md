PEP: 526
Title: Syntax for Variable Annotations
Status: Final
Created: 09-Aug-2016
Python-Version: 3.6
Post-History: 30-Aug-2016, 02-Sep-2016
Resolution: https://mail.python.org/pipermail/python-dev/2016-September/146282.html

[...]

Status
======

This PEP has been provisionally accepted by the BDFL.
See the acceptance message for more color:
https://mail.python.org/pipermail/python-dev/2016-September/146282.html

[...]

Abstract
========

:pep:`484` introduced type hints, a.k.a. type annotations.  While its
main focus was function annotations, it also introduced the notion of
type comments to annotate variables::

  # 'primes' is a list of integers
  primes = []  # type: List[int]

  # 'captain' is a string (Note: initial value is a problem)
  captain = ...  # type: str

  class Starship:
      # 'stats' is a class variable
      stats = {}  # type: Dict[str, int]

This PEP aims at adding syntax to Python for annotating the types of variables
(including class variables and instance variables),
instead of expressing them through comments::

  primes: List[int] = []

  captain: str  # Note: no initial value!

  class Starship:
      stats: ClassVar[Dict[str, int]] = {}

:pep:`484` explicitly states that type comments are intended to help with
type inference in complex cases, and this PEP does not change this
intention.  However, since in practice type comments have also been
adopted for class variables and instance variables, this PEP also
discusses the use of type annotations for those variables.

[...]

Rationale
=========

Although type comments work well enough, the fact that they're
expressed through comments has some downsides:

- Text editors often highlight comments differently from type annotations.

- There's no way to annotate the type of an undefined variable; one needs to
  initialize it to ``None`` (e.g. ``a = None # type: int``).

- Variables annotated in a conditional branch are difficult to read::

    if some_value:
        my_var = function() # type: Logger
    else:
        my_var = another_function() # Why isn't there a type here?

- Since type comments aren't actually part of the language, if a Python script
  wants to parse them, it requires a custom parser instead of just using
  ``ast``.

- Type comments are used a lot in typeshed. Migrating typeshed to use
  the variable annotation syntax instead of type comments would improve
  readability of stubs.

- In situations where normal comments and type comments are used together, it is
  difficult to distinguish them::

    path = None  # type: Optional[str]  # Path to module source

- It's impossible to retrieve the annotations at runtime outside of
  attempting to find the module's source code and parse it at runtime,
  which is inelegant, to say the least.

The majority of these issues can be alleviated by making the syntax
a core part of the language. Moreover, having a dedicated annotation syntax
for class and instance variables (in addition to method annotations) will
pave the way to static duck-typing as a complement to nominal typing defined
by :pep:`484`.

[...]

Runtime Effects of Type Annotations
===================================

Annotating a local variable will cause
the interpreter to treat it as a local, even if it was never assigned to.
Annotations for local variables will not be evaluated::

  def f():
      x: NonexistentName  # No error.

However, if it is at a module or class level, then the type *will* be
evaluated::

  x: NonexistentName  # Error!
  class X:
      var: NonexistentName  # Error!

In addition, at the module or class level, if the item being annotated is a
*simple name*, then it and the annotation will be stored in the
``__annotations__`` attribute of that module or class (mangled if private)
as an ordered mapping from names to evaluated annotations.
