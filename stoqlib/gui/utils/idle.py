# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2013 Async Open Source
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU Lesser General Public License
## as published by the Free Software Foundation; either version 2
## of the License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##

"""
This modules has one function :func:`get_idle_seconds` that returns
the number of the seconds since the user has used the keyboard or mouse.
"""

# Based on Pidgin's gtkidle.c

import ctypes
import ctypes.util
import platform

from gi.repository import Gtk, Gdk, GLib, GIRepository


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint),
        ('dwTime', ctypes.c_uint),
    ]


class XScreenSaverInfo(ctypes.Structure):
    _fields_ = [('window', ctypes.c_long),
                ('state', ctypes.c_int),
                ('kind', ctypes.c_int),
                ('til_or_since', ctypes.c_ulong),
                ('idle', ctypes.c_ulong),
                ('eventMask', ctypes.c_ulong)]


class IdleXScreenSaver(object):
    def __init__(self):
        self.xss = self._get_library('Xss')

        # FIXME: We could use gi.repository.GdkX11 here but then we would
        # not be able to pass the python objects to xss.
        repo = GIRepository.Repository.get_default()
        # This is probably libgdk-3.so
        gdk_path = repo.get_shared_library('GdkX11').split(',')[0]
        self.gdk_ = ctypes.cdll.LoadLibrary(gdk_path)

        self.gdk_.gdk_display_get_default.restype = ctypes.c_void_p
        # GDK_DISPLAY_XDISPLAY expands to gdk_x11_display_get_xdisplay
        self.gdk_.gdk_x11_display_get_xdisplay.restype = ctypes.c_void_p
        self.gdk_.gdk_x11_display_get_xdisplay.argtypes = [ctypes.c_void_p]
        # GDK_ROOT_WINDOW expands to gdk_x11_get_default_root_xwindow
        self.gdk_.gdk_x11_get_default_root_xwindow.restype = ctypes.c_void_p

        self.xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
        self.xss.XScreenSaverQueryExtension.restype = ctypes.c_int
        self.xss.XScreenSaverQueryExtension.argtypes = [ctypes.c_void_p,
                                                        ctypes.POINTER(ctypes.c_int),
                                                        ctypes.POINTER(ctypes.c_int)]
        self.xss.XScreenSaverQueryInfo.restype = ctypes.c_int
        self.xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p,
                                                   ctypes.c_void_p,
                                                   ctypes.POINTER(XScreenSaverInfo)]

        # has_extension = XScreenSaverQueryExtension(
        #     GDK_DISPLAY_XDISPLAY(gdk_display_get_default()),
        #     &event_base, &error_base);
        event_base = ctypes.c_int()
        error_base = ctypes.c_int()
        gtk_display = self.gdk_.gdk_display_get_default()
        self.dpy = self.gdk_.gdk_x11_display_get_xdisplay(gtk_display)
        available = self.xss.XScreenSaverQueryExtension(self.dpy,
                                                        ctypes.byref(event_base),
                                                        ctypes.byref(error_base))
        if available == 1:
            self.xss_info = self.xss.XScreenSaverAllocInfo()
        else:
            self.xss_info = None

    def _get_library(self, libname):
        path = ctypes.util.find_library(libname)
        if not path:
            raise ImportError('Could not find library "%s"' % (libname, ))
        lib = ctypes.cdll.LoadLibrary(path)
        assert lib
        return lib

    def get_idle(self):
        if not self.xss_info:
            return 0

        # XScreenSaverQueryInfo(GDK_DISPLAY_XDISPLAY(gdk_display_get_default()),
        #                       GDK_ROOT_WINDOW(), mit_info);
        drawable = self.gdk_.gdk_x11_get_default_root_xwindow()
        self.xss.XScreenSaverQueryInfo(self.dpy, drawable, self.xss_info)
        # return (mit_info->idle) / 1000;
        return self.xss_info.contents.idle / 1000


class IdleEventHandler(object):
    def __init__(self):
        Gdk.event_handler_set(self._filter_callback)
        GLib.timeout_add_seconds(1, self._increase_idle)
        self._idle = 0

    def _filter_callback(self, event):
        if event.type in [Gdk.EventType.BUTTON_PRESS,
                          Gdk.EventType.BUTTON_RELEASE,
                          Gdk.EventType.KEY_PRESS,
                          Gdk.EventType.KEY_RELEASE,
                          Gdk.EventType.MOTION_NOTIFY,
                          Gdk.EventType.SCROLL]:
            self._idle = 0
        Gtk.main_do_event(event)

    def _increase_idle(self):
        self._idle += 1
        return True

    def get_idle(self):
        return self._idle

_idle = None
_system = None


def get_idle_seconds():
    """
    Returns the number of seconds the current user has been idle.

    :returns: idle seconds
    :rtype: int
    """
    global _idle, _system
    if _system is None:
        _system = platform.system()

    if _system == 'Linux':
        if _idle is None:
            _idle = IdleXScreenSaver()

            # For X servers such as XMing which lacks the
            # the screen saver extension
            if _idle.xss_info is None:
                _idle = IdleEventHandler()

    elif _system == 'Windows':
        # Same as pidgin:
        # http://stackoverflow.com/questions/911856/detecting-idle-time-in-python
        lastInputInfo = LASTINPUTINFO()
        lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo))
        millis = ctypes.windll.kernel32.GetTickCount() - lastInputInfo.dwTime
        return int(millis / 1000.0)

    else:
        raise NotImplementedError(_system)

    return _idle.get_idle()
