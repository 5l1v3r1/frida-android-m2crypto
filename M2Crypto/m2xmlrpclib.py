"""M2Crypto enhancement to xmlrpclib.

Copyright (c) 1999 Ng Pheng Siong. All rights reserved. """

RCS_id='$Id: m2xmlrpclib.py,v 1.3 2000/12/13 15:41:25 ngps Exp $'

import base64, string, sys

from xmlrpclib import *
import SSL, httpslib, m2urllib

__version__='0.05p2'

class SSL_Transport(Transport):

    user_agent = "xmlrpc_ssl.py/%s - %s" % (__version__, Transport.user_agent)

    def __init__(self, ssl_context=None):
        if ssl_context is None:
            self.ssl_ctx=SSL.Context('sslv23')
        else:
            self.ssl_ctx=ssl_context

    def request(self, host, handler, request_body):
        # Handle username and password.
        user_passwd, host_port = m2urllib.splituser(host)
        _host, _port = m2urllib.splitport(host_port)
        if sys.version[:3] == '2.0':
            h = httpslib.HTTPS(_host, int(_port), ssl_context=self.ssl_ctx)
        elif sys.version[:3] ==  '1.5':
            h = httpslib.HTTPS(self.ssl_ctx, _host, int(_port))
        else:
            raise RuntimeError, 'unsupported Python version'
        h.set_debuglevel(1)

        # What follows is as in xmlrpclib.Transport. (Except the authz bit.)
        h.putrequest("POST", handler)

        # required by HTTP/1.1
        h.putheader("Host", _host)

        # required by XML-RPC
        h.putheader("User-Agent", self.user_agent)
        h.putheader("Content-Type", "text/xml")
        h.putheader("Content-Length", str(len(request_body)))

        # Authorisation.
        if user_passwd is not None:
            auth=string.strip(base64.encodestring(user_passwd))
            h.putheader('Authorization', 'Basic %s' % auth)

        h.endheaders()

        if request_body:
            h.send(request_body)

        errcode, errmsg, headers = h.getreply()

        if errcode != 200:
            raise ProtocolError(
                host + handler,
                errcode, errmsg,
                headers
                )

        return self.parse_response(h.getfile())

