#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Components of the simulation system, namely blocks, wires and plugs.
"""
from abc import ABC, abstractmethod
from typing import Any, Iterable, List, Optional as Opt, Tuple, Union, TYPE_CHECKING
from typing_extensions import Literal

from bdsim.core import np
if TYPE_CHECKING:  # this lets us use type-hints without circular dependency
    from bdsim.core import BlockDiagram

from collections import UserDict

# type alias
SourceType = Union['Block', 'Plug']


class Struct(UserDict):
    """
    A dict like object that allows items to be added by attribute or by key.

    For example::

        >>> d = Struct('thing')
        >>> d.a = 1
        >>> d['b'] = 2
        >>> d.a
        1
        >>> d['a']
        1
        >>> d.b
        2
        >>> str(d)
        "thing {'a': 1, 'b': 2}"
    """

    def __init__(self, name='Struct'):
        super().__init__()
        self.name = name

    def __setattr__(self, name, value):
        if name in ['data', 'name']:
            super().__setattr__(name, value)
        else:
            self.data[name] = value

    def __getattr__(self, name):
        return self.data[name]

    def __str__(self):
        return self.name + ' ' + str(
            {k: v
             for k, v in self.data.items() if not k.startswith('_')})

    def __repr__(self):
        def fmt(k, v):
            if isinstance(v, np.ndarray):
                return '{:12s}| {:12s}'.format(
                    k,
                    type(v).__name__ + ' ' + str(v.shape))
            else:
                return '{:12s}| {:12s}'.format(k, type(v).__name__)

        return self.name + ':\n' + '\n'.join(
            [fmt(k, v) for k, v in self.data.items() if not k.startswith('_')])

# ------------------------------------------------------------------------- #


class Plug:
    """
    Create a plug.

    :param block: The block being plugged into
    :type block: Block
    :param port: The port on the block, defaults to 0
    :type port: int, optional
    :param type: 'start' or 'end', defaults to None
    :type type: str, optional
    :return: Plug object
    :rtype: Plug

    Plugs are the interface between a wire and block and have information
    about port number and wire end. Plugs are on the end of each wire, and connect a 
    Wire to a specific port on a Block.

    The ``type`` argument indicates if the ``Plug`` is at:
        - the start of a wire, ie. the port is an output port
        - the end of a wire, ie. the port is an input port

    A plug can specify a set of ports on a block.

    """

    def __init__(self, block: 'Block', port: Union[int, slice] = 0, type: Literal["start", "end"] = None):

        self.block = block
        self.port = port
        self.type = type  # start

    @property
    def isslice(self):
        """
        Test if port number is a slice.

        :return: Whether the port is a slice
        :rtype: bool

        Returns ``True`` if the port is a slice, eg. ``[0:3]``, and ``False``
        for a simple index, eg. ``[2]``.
        """
        return isinstance(self.port, slice)

    @property
    def portlist(self):
        """
        Return port numbers.

        :return: Port numbers
        :rtype: int or list of int

        If the port is a simple index, eg. ``[2]`` returns 2.

        If the port is a slice, eg. ``[0:3]``, returns [0, 1, 2].

        """
        if isinstance(self.port, slice):
            return list(range(self.port.start, self.port.stop, self.port.step or 1))
        else:
            return [self.port]

    @property
    def width(self):
        """
        Return number of ports connected.

        :return: Number of ports
        :rtype: int

        If the port is a simple index, eg. ``[2]`` returns 1.

        If the port is a slice, eg. ``[0:3]``, returns 3.
        """
        return len(self.portlist)

    def __mul__(self, right: SourceType):
        """
        Operator for implicit wiring.

        :param right: A block or plug to be wired to
        :type right: Block or Plug
        :return: ``right``
        :rtype: Block or Plug

        Implements implicit wiring, where the left-hand operator is a Plug, for example::

            a = bike[2] * bd.GAIN(3)

        will connect port 2 of ``bike`` to the input of the GAIN block.

        Note that::

           a = bike[2] * func[1]

        will connect port 2 of ``bike`` to port 1 of ``func``, and port 1 of ``func``
        will be assigned to ``a``.  To specify a different outport port on ``func``
        we need to use parentheses::

            a = (bike[2] * func[1])[0]

        which will connect port 2 of ``bike`` to port 1 of ``func``, and port 0 of ``func``
        will be assigned to ``a``.

        :seealso: Block.__mul__
        """

        # called for the cases:
        # block * block
        # block * plug
        s = self.block.bd
        #assert isinstance(right, Block), 'arguments to * must be blocks not ports (for now)'
        s.connect(self, right)  # add a wire
        #print('plug * ' + str(w))
        return right

    def __setitem__(self, port: Union[int, slice], src: SourceType):
        """
        Convert a LHS block slice reference to a wire.

        :param port: Port number
        :type port: int | slice
        :param src: the RHS
        :type src: Block or Plug

        Used to create a wired connection by assignment, for example::

            c = bd.CONSTANT(1)

            c[0] = x

        Ths method is invoked to create a wire from ``x`` to input port 0 of
        the constant block ``c``.
        """
        # b[port] = src
        # src --> b[port]
        print('Plug connecting', src, self, port)
        self.block.bd.connect(src, self.block[port])

    def __repr__(self):
        """
        Display plug details.

        :return: Plug description
        :rtype: str

        String format::

            bicycle.0[1]

        """
        return str(self.block) + "[" + str(self.port) + "]"


# ------------------------------------------------------------------------- #

class Wire:
    """
    Create a wire.

    :param start: Plug at the start of a wire, defaults to None
    :type start: Plug, optional
    :param end: Plug at the end of a wire, defaults to None
    :type end: Plug, optional
    :param name: Name of wire, defaults to None
    :type name: str, optional
    :return: A wire object
    :rtype: Wire

    A Wire object connects two block ports.  A Wire has a reference to the
    start and end ports.

    A wire records all the connections defined by the user.  At compile time
    wires are used to build inter-block references.

    Between two blocks, a wire can connect one or more ports, ie. it can connect
    a set of output ports on one block to a same sized set of input ports on 
    another block.
    """

    def __init__(self, start: Plug = None, end: Plug = None, name: str = None):

        self.name = name
        self.id = None
        self.start = start
        self.end = end
        self.value = None
        self.type = None
        self.name = None

    @property
    def info(self):
        """
        Interactive display of wire properties.

        Displays all attributes of the wire for debugging purposes.

        """
        print("wire:")
        for k, v in self.__dict__.items():
            print("  {:8s}{:s}".format(k + ":", str(v)))

    def send(self, value):
        """
        Send a value to the port at end of this wire.

        :param value: A port value
        :type value: float, numpy.ndarray, etc.

        The value is sent to the input port connected to the end of this wire.
        """
        # dest is a Wire
        return self.end.block.setinput(self.end.port, value)

    def __repr__(self):
        """
        Display wire with name and connection details.

        :return: Long-form wire description
        :rtype: str

        String format::

            wire.5: d2goal[0] --> Kv[0]

        """
        return str(self) + ": " + self.fullname

    @property
    def fullname(self):
        """
        Display wire connection details.

        :return: Wire name
        :rtype: str

        String format::

            d2goal[0] --> Kv[0]

        """
        return "{:s}[{:d}] --> {:s}[{:d}]".format(str(self.start.block),
                                                  self.start.port,
                                                  str(self.end.block),
                                                  self.end.port)

    def __str__(self):
        """
        Display wire name.

        :return: Wire name
        :rtype: str

        String format::

            wire.5

        """
        s = "wire."
        if self.name is not None:
            s += self.name
        elif self.id is not None:
            s += str(self.id)
        else:
            s += '??'
        return s


# ------------------------------------------------------------------------- #

blocklist = []


def block(cls):
    """
    Decorator for block classes

    :param cls: A block to be registered for the simulator
    :type cls: subclass of Block
    :return: the class
    :rtype: subclass of Block

    @block
    class MyBlock:

    The modules in ``./blocks`` uses the ``block`` decorator to declare
    that they are a block which will be made available as a method of the
    ``BlockDiagram`` instance.  The method name is a capitalized version of
    the class name.
    """

    if issubclass(cls, Block):
        blocklist.append(cls)  # append class to a global list
    else:
        raise ValueError('@block used on non Block subclass')
    return cls


# ------------------------------------------------------------------------- #


class Block(ABC):
    """
    Construct a new block object.

    :param name: Name of the block, defaults to None
    :type name: str, optional
    :param inames: Names of input ports, defaults to None
    :type inames: list of str, optional
    :param onames: Names of output ports, defaults to None
    :type onames: list of str, optional
    :param snames: Names of states, defaults to None
    :type snames: list of str, optional
    :param pos: Position of block on the canvas, defaults to None
    :type pos: 2-element tuple or list, optional
    :param bd: Parent block diagram, defaults to None
    :type bd: BlockDiagram, optional
    :param nin: Number of inputs, defaults to None
    :type nin: int, optional
    :param nout: Number of outputs, defaults to None
    :type nout: int, optional
    :param ``*inputs``: Optional incoming connections
    :type ``*inputs``: Block or Plug
    :param ``**kwargs``: Unknow arguments
    :return: A Block superclass
    :rtype: Block

    A block object is the superclass of all blocks in the simulation environment.

    This is the top-level initializer, and handles most options passed to
    the superclass initializer for each block in the library.

    """

    type: str  # a string holding the name of a concrete block. Usually the lowercase
    # name of the block's class definition
    blockclass: Literal['source', 'sink', 'function', 'transfer', 'subsystem']

    def __new__(cls, *args, bd=None, **kwargs):
        """
        Construct a new Block object.

        :param cls: The class to construct
        :type cls: class type
        :param *args: positional args passed to constructor
        :type *args: list
        :param **kwargs: keyword args passed to constructor
        :type **kwargs: dict
        :return: new Block instance
        :rtype: Block instance
        """
        # print('Block __new__', args,bd, kwargs)
        block = super(Block, cls).__new__(cls)  # create a new instance

        # we overload setattr, so need to know whether it is being passed a port
        # name.  Add this attribute now to allow proper operation.
        block.__dict__['portnames'] = []  # must be first, see __setattr__

        block.bd = bd
        block.nin = 0
        block.nout = 0
        block.nstates = 0
        return block

    _latex_remove = str.maketrans({
        '$': '',
        '\\': '',
        '{': '',
        '}': '',
        '^': '',
        '_': ''
    })

    def __init__(self,
                 name: str = None,
                 inames: List[str] = None,
                 onames: List[str] = None,
                 snames: List[str] = None,
                 pos: Tuple[int, int] = None,
                 nin: int = None,
                 nout: int = None,
                 bd: 'BlockDiagram' = None,
                 *inputs: Union['Block', Plug],
                 **kwargs):

        # print('Block constructor, bd = ', bd)
        if name is not None:
            self.name_tex = name
            self.name = self._fixname(name)
        else:
            self.name = None

        self.pos = pos
        self.id = None
        self.out = []
        self.updated = False
        self.shape = 'block'  # for box
        self._inport_names = None
        self._outport_names = None
        self._state_names = None
        self.initd = True
        self.bd = self.bd or bd
        self.nstates = self.nstates

        # appease pylint
        self.portnames = self.portnames  # this gets set in Block.__new__()

        # these get set in BlockDiagram.compile() They are None until wired..?
        self.inports: List[Opt[Wire]] = []
        self.outports: List[List[Wire]] = []

        if nin is not None:
            self.nin = nin
        if nout is not None:
            self.nout = nout

        if inames is not None:
            self.inport_names(inames)
        if onames is not None:
            self.outport_names(onames)
        if snames is not None:
            self.state_names(snames)

        for i, input in enumerate(inputs):
            self.bd.connect(input, Plug(self, port=i))

        if len(kwargs) > 0:
            print('WARNING: unused arguments', kwargs.keys())

    @property
    def info(self):
        """
        Interactive display of block properties.

        Displays all attributes of the block for debugging purposes.

        """
        print("block: " + type(self).__name__)
        for k, v in self.__dict__.items():
            if k != 'sim':
                print("  {:11s}{:s}".format(k + ":", str(v)))
        self.inputs

    # for use in unit testing
    def _eval(self, *inputs: Any, t=None):
        """
        Evaluate a block for unit testing.

        :param *inputs: List of input port values
        :type *inputs: list
        :param t: Simulation time, defaults to None
        :type t: float, optional
        :return: Block output port values
        :rtype: list

        The output ports of the block are evaluated for a given set of input
        port values and simulation time. Input and output port values are treated
        as lists.

        Mostly used for making concise unit tests.

        """
        assert len(inputs) == self.nin, 'wrong number of inputs provided'
        self.inputs = list(inputs)
        out = self.output(t=t)
        assert isinstance(out, list), 'result must be a list'
        assert len(out) == self.nout, 'result list is wrong length'
        return out

    def __getitem__(self, port: int):
        """
        Convert a block slice reference to a plug.

        :param port: Port number
        :type port: int
        :return: A port plug
        :rtype: Plug

        Invoked whenever a block is referenced as a slice, for example::

            c = bd.CONSTANT(1)

            bd.connect(x, c[0])
            bd.connect(c[0], x)

        In both cases ``c[0]`` is converted to a ``Plug`` by this method.
        """
        # block[i] is a plug object
        #print('getitem called', self, port)
        return Plug(self, port)

    def __setitem__(self, port: int, src: SourceType):
        """
        Convert a LHS block slice reference to a wire.

        :param port: Port number
        :type port: int
        :param src: the RHS
        :type src: Block or Plug

        Used to create a wired connection by assignment, for example::

            c = bd.CONSTANT(1)

            c[0] = x

        Ths method is invoked to create a wire from ``x`` to port 0 of
        the constant block ``c``.
        """
        # b[port] = src
        # src --> b[port]
        #print('connecting', src, self, port)
        self.bd.connect(src, self[port])

    def __setattr__(self, name: str, value: SourceType):
        """
        Convert a LHS block name reference to a wire.

        :param name: Port name
        :type port: str
        :param value: the RHS
        :type value: Block or Plug

        Used to create a wired connection by assignment, for example::

            c = bd.CONSTANT(1, inames=['u'])

            c.u = x

        Ths method is invoked to create a wire from ``x`` to port 'u' of
        the constant block ``c``.

        Notes:

            - this overloaded method handles all instances of ``setattr`` and
              implements normal functionality as well, only creating a wire
              if ``name`` is a known port name.
        """

        # b[port] = src
        # src --> b[port]
        # gets called for regular attribute settings, as well as for wiring

        if name in self.portnames:
            # we're doing wiring
            #print('in __setattr___', self, name, value)
            self.bd.connect(value, getattr(self, name))
        else:
            #print('in __setattr___', self, name, value)
            # regular case, add attribute to the instance's dictionary
            self.__dict__[name] = value

    def __mul__(self, right: SourceType):
        """
        Operator for implicit wiring.

        :param right: A block or plugto be wired to
        :type right: Block or Plug
        :return: ``right``
        :rtype: Block or Plug

        Implements implicit wiring, for example::

            a = bd.CONSTANT(1) * bd.GAIN(2)

        will connect the output of the CONSTANT block to the input of the
        GAIN block.  The result will be GAIN block, whose output in this case
        will be assigned to ``a``.

        Note that::

           a = bd.CONSTANT(1) * func[1]

        will connect port 0 of CONSTANT to port 1 of ``func``, and port 1 of ``func``
        will be assigned to ``a``.  To specify a different outport port on ``func``
        we need to use parentheses::

            a = (bd.CONSTANT(1) * func[1])[0]

        which will connect port 0 of CONSTANT ` to port 1 of ``func``, and port 0 of ``func``
        will be assigned to ``a``.

        :seealso: Plug.__mul__

        """
        # called for the cases:
        # block * block
        # block * plug
        s = self.bd
        #assert isinstance(right, Block), 'arguments to * must be blocks not ports (for now)'
        w = s.connect(self, right)  # add a wire
        #print('block * ' + str(w))
        return right

        # make connection, return a plug

    def __str__(self):
        if hasattr(self, 'name') and self.name is not None:
            return self.name
        else:
            return self.blockclass + '.??'

    def __repr__(self):
        return self.__str__()

    def _fixname(self, s):
        return s.translate(self._latex_remove)

    def inport_names(self, names: Iterable[str]):
        """
        Set the names of block input ports.

        :param names: List of port names
        :type names: list of str

        Invoked by the ``inames`` argument to the Block constructor.

        The names can include LaTeX math markup.  The LaTeX version is used
        where appropriate, but the port names are a de-LaTeXd version of the
        given string with backslash, underscore, caret, braces and dollar signs
        removed.
        """
        self._inport_names = names

        for port, name in enumerate(names):
            fn = self._fixname(name)
            setattr(self, fn, self[port])
            self.portnames.append(fn)

    def outport_names(self, names: Iterable[str]):
        """
        Set the names of block output ports.

        :param names: List of port names
        :type names: list of str

        Invoked by the ``onames`` argument to the Block constructor.

        The names can include LaTeX math markup.  The LaTeX version is used
        where appropriate, but the port names are a de-LaTeXd version of the
        given string with backslash, underscore, caret, braces and dollar signs
        removed.

        """
        self._outport_names = names
        for port, name in enumerate(names):
            fn = self._fixname(name)
            setattr(self, fn, self[port])
            self.portnames.append(fn)

    def state_names(self, names: Iterable[str]):
        self._state_names = names

    def sourcename(self, port: int):
        """
        Get the name of output port driving this input port.

        :param port: Input port
        :type port: int
        :return: Port name
        :rtype: str

        Return the name of the output port that drives the specified input
        port. The name can be:

            - a LaTeX string if provided
            - block name with port number given in square brackets.  The block
              name will the one optionally assigned by the user using the ``name``
              keyword, otherwise a systematic default name.

        :seealso: outport_names

        """

        w = self.inports[port]
        if w.name is not None:
            return w.name
        src = w.start.block
        srcp = w.start.port
        if src._outport_names is not None:
            return src._outport_names[srcp]
        return str(w.start)

    # @property
    # def fullname(self):
    #     return self.blockclass + "." + str(self)

    def reset(self):
        if self.nin > 0:
            self.inputs: List[Any] = [None] * self.nin
        self.updated = False

    def add_outport(self, w: Wire):
        port = w.start.port
        assert port < len(self.outports), 'port number too big'
        self.outports[port].append(w)

    def add_inport(self, w: Wire):
        port = w.end.port
        assert self.inports[
            port] is None, 'attempting to connect second wire to an input'
        self.inports[port] = w

    def setinput(self, port: int, value: Any):
        """
        Receive input from a wire

        :param self: Block to be updated
        :type wire: Block
        :param port: Input port to be updated
        :type port: int
        :param value: Input value
        :type val: any
        :return: If all inputs have been received
        :rtype: bool

        """
        # stash it away
        self.inputs[port] = value

        # check if all inputs have been assigned
        if all([x is not None for x in self.inputs]):
            self.updated = True
            # self.update()
        return self.updated

    def setinputs(self, *pos):
        assert len(pos) == self.nin, 'mismatch in number of inputs'
        self.reset()
        for i, val in enumerate(pos):
            self.inputs[i] = val

    def check(self):  # check validity of block parameters at start
        assert self.nin > 0 or self.nout > 0, 'no inputs or outputs specified'
        assert hasattr(
            self, 'initd'
        ) and self.initd, 'Block superclass not initalized. was super().__init__ called?'

    def start(self, **kwargs): ...  # begin of a simulation

    def output(self, t: float): ...

    def step(self): ...  # to be deprecated; replaced solely by output()

    def done(self, **kwargs): ...  # end of simulation


class SinkBlock(Block):
    """
    A SinkBlock is a subclass of Block that represents a block that has inputs
    but no outputs. Typically used to save data to a variable, file or 
    graphics.
    """
    blockclass = 'sink'

    def __init__(self, **kwargs):
        # print('Sink constructor')
        super().__init__(**kwargs)
        self.nout = 0
        self.nstates = 0


class SourceBlock(Block):
    """
    A SourceBlock is a subclass of Block that represents a block that has outputs
    but no inputs.  Its output is a function of parameters and time.
    """
    blockclass = 'source'

    def __init__(self, **kwargs):
        # print('SourceType constructor')
        super().__init__(**kwargs)
        self.nin = 0
        self.nstates = 0


class TransferBlock(Block):
    """
    A TransferBlock is a subclass of Block that represents a block with inputs
    outputs and states. Typically used to describe a continuous time dynamic
    system, either linear or nonlinear.
    """
    blockclass = 'transfer'

    def __init__(self, **kwargs):
        # print('Transfer constructor')
        super().__init__(**kwargs)
        self._x0 = ()

    def reset(self):
        super().reset()
        self._x = self._x0
        return self._x

    def setstate(self, x):
        self._x = x[:self.nstates]  # take as much state vector as we need
        return x[self.nstates:]  # return the rest

    def getstate(self):
        return self._x0

    def check(self):
        assert len(
            self._x0) == self.nstates, 'incorrect length for initial state'
        assert self.nin > 0 or self.nout > 0, 'no inputs or outputs specified'

    @abstractmethod
    def deriv(self) -> np.ndarray: ...


class FunctionBlock(Block):
    """
    A FunctionBlock is a subclass of Block that represents a block that has inputs
    and outputs but no state variables.  Typically used to describe operations
    such as gain, summation or various mappings.
    """
    blockclass = 'function'

    def __init__(self, **kwargs):
        # print('Function constructor')
        super().__init__(**kwargs)
        self.nstates = 0


class SubsystemBlock(Block):
    """
    A Subsystem is a subclass of block thafrom bdsim. import npt contains a group of blocks within it
    and a predefined set of inputs and outputs. It is synonymous to Simulink's groups.

    When Subclassing SubsystemBlock, all connections between blocks within should be
    performed in the constructor.
    """
    blockclass = 'subsystem'

    def __init__(self, ssvar: str = None, **kwargs):
        # print('Subsystem constructor')
        super().__init__(**kwargs)
        self.ssvar = ssvar

    # def _run(self, sub_block, inputs, t=None):
    #     "helper function to make processing internal blocks less cumbersome"
    #     sub_block.inputs = inputs
    #     return sub_block.output(t)

    # def _sequential(self, sub_blocks, inputs, t=None):
    #     "helper function to run blocks sequentially"
    #     for block in sub_blocks:
    #         inputs = self._run(block, inputs, t)
    #     return inputs


# module exports
__all__ = ('block', 'Block', 'Wire', 'Plug', 'FunctionBlock', 'SinkBlock',
           'SourceBlock', 'SubsystemBlock', 'Struct', 'TransferBlock', 'blocklist',
           'SourceType')
