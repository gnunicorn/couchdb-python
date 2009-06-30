# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2009 Christopher Lenz
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.

"""Support for streamed reading and writing of multipart MIME content."""

from cgi import parse_header
import sys

__all__ = ['read_multipart', 'write_multipart']
__docformat__ = 'restructuredtext en'


EOL = '\r\n'


def read_multipart(fileobj, boundary=None):
    """Simple streaming MIME multipart parser.
    
    This function takes a file-like object reading a MIME envelope, and yields
    a ``(headers, is_multipart, payload)`` tuple for every part found, where
    ``headers`` is a dictionary containing the MIME headers of that part (with
    names lower-cased), ``is_multipart`` is a boolean indicating whether the
    part is itself multipart, and ``payload`` is either a string (if
    ``is_multipart`` is false), or an iterator over the nested parts.
    
    Note that the iterator produced for nested multipart payloads MUST be fully
    consumed, even if you wish to skip over the content.
    
    :param fileobj: a file-like object
    :param boundary: the part boundary string, will generally be determined
                     automatically from the headers of the outermost multipart
                     envelope
    :return: an iterator over the parts
    :since: 0.5
    """
    headers = {}
    buf = []
    outer = in_headers = boundary is None

    next_boundary = boundary and '--' + boundary + EOL or None
    last_boundary = boundary and '--' + boundary + '--' + EOL or None

    def _current_part():
        payload = ''.join(buf)
        if payload.endswith(EOL):
            payload = payload[:-1]
        return headers, False, payload

    for line in fileobj:
        if in_headers:
            if line != EOL:
                name, value = line.split(':', 1)
                headers[name.lower().strip()] = value.strip()
            else:
                in_headers = False
                mimetype, params = parse_header(headers.get('content-type'))
                if mimetype.startswith('multipart/'):
                    sub_boundary = params['boundary']
                    sub_parts = read_multipart(fileobj, boundary=sub_boundary)
                    if boundary is not None:
                        yield headers, True, sub_parts
                        headers.clear()
                        del buf[:]
                    else:
                        for part in sub_parts:
                            yield part
                        return

        elif line == next_boundary:
            # We've reached the start of a new part, as indicated by the
            # boundary
            if headers:
                if not outer:
                    yield _current_part()
                else:
                    outer = False
                headers.clear()
                del buf[:]
            in_headers = True

        elif line == last_boundary:
            # We're done with this multipart envelope
            break

        else:
            buf.append(line)

    if not outer and headers:
        yield _current_part()


class MultipartWriter(object):

    def __init__(self, fileobj, headers=None, subtype='mixed', boundary=None):
        self.fileobj = fileobj
        if boundary is None:
            boundary = self._make_boundary()
        self.boundary = boundary
        if headers is None:
            headers = {}
        headers['Content-Type'] = 'multipart/%s; boundary="%s"' % (
            subtype, self.boundary
        )
        self._write_headers(headers)

    def open(self, headers=None, subtype='mixed', boundary=None):
        self.fileobj.write('--')
        self.fileobj.write(self.boundary)
        self.fileobj.write(EOL)
        return MultipartWriter(self.fileobj, headers=headers, subtype=subtype,
                               boundary=boundary)

    def add(self, mimetype, content, headers=None):
        self.fileobj.write('--')
        self.fileobj.write(self.boundary)
        self.fileobj.write(EOL)
        if headers is None:
            headers = {}
        headers['Content-Type'] = mimetype
        headers['Content-Length'] = str(len(content))
        self._write_headers(headers)
        if content:
            # XXX: throw an exception if a boundary appears in the content??
            self.fileobj.write(content)
            self.fileobj.write(EOL)

    def close(self):
        self.fileobj.write('--')
        self.fileobj.write(self.boundary)
        self.fileobj.write('--')
        self.fileobj.write(EOL)

    def _make_boundary(self):
        try:
            from uuid import uuid4
            return uuid4().hex
        except ImportError:
            from random import randrange
            token = randrange(sys.maxint)
            format = '%%0%dd' % len(repr(sys.maxint - 1))
            return ('=' * 15) + (fmt % token) + '=='

    def _write_headers(self, headers):
        if headers:
            for name in sorted(headers.keys()):
                self.fileobj.write(name)
                self.fileobj.write(': ')
                self.fileobj.write(headers[name])
                self.fileobj.write(EOL)
        self.fileobj.write(EOL)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def write_multipart(fileobj, subtype='mixed', boundary=None):
    r"""Simple streaming MIME multipart writer.

    This function returns a `MultipartWriter` object that has a few methods to
    control the nested MIME parts. For example, to write a flat multipart
    envelope you call the ``add(mimetype, content, [headers])`` method for
    every part, and finally call the ``close()`` method.

    >>> from StringIO import StringIO

    >>> buf = StringIO()
    >>> envelope = write_multipart(buf, boundary='==123456789==')
    >>> envelope.add('text/plain', 'Just testing')
    >>> envelope.close()
    >>> print buf.getvalue().replace('\r\n', '\n')
    Content-Type: multipart/mixed; boundary="==123456789=="
    <BLANKLINE>
    --==123456789==
    Content-Length: 12
    Content-Type: text/plain
    <BLANKLINE>
    Just testing
    --==123456789==--
    <BLANKLINE>

    Note that an explicit boundary is only specified for testing purposes. If
    the `boundary` parameter is omitted, the multipart writer will generate a
    random string for the boundary.

    To write nested structures, call the ``open([headers])`` method on the
    respective envelope, and finish each envelope using the ``close()`` method:

    >>> buf = StringIO()
    >>> envelope = write_multipart(buf, boundary='==123456789==')
    >>> part = envelope.open(boundary='==abcdefghi==')
    >>> part.add('text/plain', 'Just testing')
    >>> part.close()
    >>> envelope.close()
    >>> print buf.getvalue().replace('\r\n', '\n')
    Content-Type: multipart/mixed; boundary="==123456789=="
    <BLANKLINE>
    --==123456789==
    Content-Type: multipart/mixed; boundary="==abcdefghi=="
    <BLANKLINE>
    --==abcdefghi==
    Content-Length: 12
    Content-Type: text/plain
    <BLANKLINE>
    Just testing
    --==abcdefghi==--
    --==123456789==--
    <BLANKLINE>
    
    :param fileobj: a writable file-like object that the output should get
                    written to
    :param subtype: the subtype of the multipart MIME type (e.g. "mixed")
    :param boundary: the boundary to use to separate the different parts
    :since: 0.6
    """
    return MultipartWriter(fileobj, subtype=subtype, boundary=boundary)
