PEP: 604
Title: Allow writing union types as ``X | Y``
Status: Final
Created: 28-Aug-2019
Python-Version: 3.10
Post-History: 28-Aug-2019, 05-Aug-2020

[...]

Abstract
========

This PEP proposes overloading the ``|`` operator on types to allow
writing ``Union[X, Y]`` as ``X | Y``, and allows it to appear in
``isinstance`` and ``issubclass`` calls.

[...]

Motivation
==========

:pep:`484` and :pep:`526` propose a generic syntax to add typing to variables,
parameters and function returns. :pep:`585` proposes to :pep:`expose
parameters to generics at runtime
<585#parameters-to-generics-are-available-at-runtime>`.
Mypy [1]_ accepts a syntax which looks like::

    annotation: name_type
    name_type: NAME (args)?
    args: '[' paramslist ']'
    paramslist: annotation (',' annotation)* [',']

- To describe a disjunction (union type), the user must use ``Union[X, Y]``.

The verbosity of this syntax does not help with type adoption.

[...]

Proposal
========

Inspired by Scala [2]_ and Pike [3]_, this proposal adds operator
``type.__or__()``.  With this new operator, it is possible to write
``int | str`` instead of ``Union[int, str]``. In addition to
annotations, the result of this expression would then be valid in
``isinstance()`` and ``issubclass()``::

    isinstance(5, int | str)
    issubclass(bool, int | float)

We will also be able to write ``t | None`` or ``None | t`` instead of
``Optional[t]``::

    isinstance(None, int | None)
    isinstance(42, None | int)

[...]

Specification
=============

The new union syntax should be accepted for function, variable and parameter annotations.

Simplified Syntax
-----------------
::

    # Instead of
    # def f(list: List[Union[int, str]], param: Optional[int]) -> Union[float, str]
    def f(list: List[int | str], param: int | None) -> float | str:
        pass

    f([1, "abc"], None)

    # Instead of typing.List[typing.Union[str, int]]
    typing.List[str | int]
    list[str | int]

    # Instead of typing.Dict[str, typing.Union[int, float]]
    typing.Dict[str, int | float]
    dict[str, int | float]

The existing ``typing.Union`` and ``|`` syntax should be equivalent.

::

  int | str == typing.Union[int, str]

  typing.Union[int, int] == int
  int | int == int
