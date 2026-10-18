"""Minimal X11 helpers (via ctypes) for window hints GTK 4 no longer exposes."""

from __future__ import annotations

import ctypes
import ctypes.util
import logging

logger = logging.getLogger(__name__)

_CLIENT_MESSAGE = 33
_SUBSTRUCTURE_NOTIFY_MASK = 1 << 19
_SUBSTRUCTURE_REDIRECT_MASK = 1 << 20
_NET_WM_STATE_ADD = 1
_SOURCE_APPLICATION = 1


class _ClientMessageData(ctypes.Union):
    _fields_ = [
        ("b", ctypes.c_char * 20),
        ("s", ctypes.c_short * 10),
        ("l", ctypes.c_long * 5),
    ]


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", _ClientMessageData),
    ]


class _XEvent(ctypes.Union):
    # XEvent is padded to 24 longs
    _fields_ = [("xclient", _XClientMessageEvent), ("pad", ctypes.c_long * 24)]


_xlib: ctypes.CDLL | None = None


def _load_xlib() -> ctypes.CDLL | None:
    global _xlib
    if _xlib is None:
        name = ctypes.util.find_library("X11")
        if not name:
            return None
        lib = ctypes.CDLL(name)
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        lib.XInternAtom.restype = ctypes.c_ulong
        lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XSendEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.POINTER(_XEvent),
        ]
        lib.XFlush.argtypes = [ctypes.c_void_p]
        _xlib = lib
    return _xlib


def set_keep_above(xid: int) -> bool:
    """Ask the window manager to keep a mapped X11 window above others (EWMH).

    Returns False when no X11 display is reachable.
    """
    lib = _load_xlib()
    if lib is None:
        return False
    display = lib.XOpenDisplay(None)
    if not display:
        return False
    try:
        event = _XEvent()
        msg = event.xclient
        msg.type = _CLIENT_MESSAGE
        msg.send_event = 1
        msg.display = display
        msg.window = xid
        msg.message_type = lib.XInternAtom(display, b"_NET_WM_STATE", 0)
        msg.format = 32
        msg.data.l[0] = _NET_WM_STATE_ADD
        msg.data.l[1] = lib.XInternAtom(display, b"_NET_WM_STATE_ABOVE", 0)
        msg.data.l[2] = 0
        msg.data.l[3] = _SOURCE_APPLICATION
        lib.XSendEvent(
            display,
            lib.XDefaultRootWindow(display),
            0,
            _SUBSTRUCTURE_REDIRECT_MASK | _SUBSTRUCTURE_NOTIFY_MASK,
            ctypes.byref(event),
        )
        lib.XFlush(display)
        return True
    finally:
        lib.XCloseDisplay(display)
