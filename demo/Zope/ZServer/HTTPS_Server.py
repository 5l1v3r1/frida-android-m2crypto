##############################################################################
# 
# Zope Public License (ZPL) Version 1.0
# -------------------------------------
# 
# Copyright (c) Digital Creations.  All rights reserved.
# 
# This license has been certified as Open Source(tm).
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
# 
# 1. Redistributions in source code must retain the above copyright
#    notice, this list of conditions, and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions, and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 
# 3. Digital Creations requests that attribution be given to Zope
#    in any manner possible. Zope includes a "Powered by Zope"
#    button that is installed by default. While it is not a license
#    violation to remove this button, it is requested that the
#    attribution remain. A significant investment has been put
#    into Zope, and this effort will continue if the Zope community
#    continues to grow. This is one way to assure that growth.
# 
# 4. All advertising materials and documentation mentioning
#    features derived from or use of this software must display
#    the following acknowledgement:
# 
#      "This product includes software developed by Digital Creations
#      for use in the Z Object Publishing Environment
#      (http://www.zope.org/)."
# 
#    In the event that the product being advertised includes an
#    intact Zope distribution (with copyright and license included)
#    then this clause is waived.
# 
# 5. Names associated with Zope or Digital Creations must not be used to
#    endorse or promote products derived from this software without
#    prior written permission from Digital Creations.
# 
# 6. Modified redistributions of any form whatsoever must retain
#    the following acknowledgment:
# 
#      "This product includes software developed by Digital Creations
#      for use in the Z Object Publishing Environment
#      (http://www.zope.org/)."
# 
#    Intact (re-)distributions of any official Zope release do not
#    require an external acknowledgement.
# 
# 7. Modifications are encouraged but must be packaged separately as
#    patches to official Zope releases.  Distributions that do not
#    clearly separate the patches from the original work must be clearly
#    labeled as unofficial distributions.  Modifications which do not
#    carry the name Zope may be packaged in any form, as long as they
#    conform to all of the clauses above.
# 
# 
# Disclaimer
# 
#   THIS SOFTWARE IS PROVIDED BY DIGITAL CREATIONS ``AS IS'' AND ANY
#   EXPRESSED OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#   IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#   PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL DIGITAL CREATIONS OR ITS
#   CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#   LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
#   USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#   ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#   OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
#   OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
#   SUCH DAMAGE.
# 
# 
# This software consists of contributions made by Digital Creations and
# many individuals on behalf of Digital Creations.  Specific
# attributions are listed in the accompanying credits file.
# 
##############################################################################

"""
Medusa HTTPS server for Zope

changes from Medusa's http_server:

    Request Threads -- Requests are processed by threads from a thread
    pool.
    
    Output Handling -- Output is pushed directly into the producer
    fifo by the request-handling thread. The HTTP server does not do
    any post-processing such as chunking.

    Pipelineable -- This is needed for protocols such as HTTP/1.1 in
    which mutiple requests come in on the same channel, before
    responses are sent back. When requests are pipelined, the client
    doesn't wait for the response before sending another request. The
    server must ensure that responses are sent back in the same order
    as requests are received.


changes from Zope's HTTP server:

    Well, this is a *HTTPS* server :)

    X.509 certificate-based authentication -- When this is in force,
    zhttps_handler, a subclass of zhttp_handler, is installed.  The 
    https server is configured to _require_ an X.509 certificate 
    from the client. When the request reaches zhttps_handler, it pulls 
    the client's distinguished name (DN) from the certificate, maps 
    that to a Zope user name and sets REMOTE_USER accordingly; if a 
    mapping does not exist, REMOTE_USER is not set. Zope's REMOTE_USER
    machinery takes care of the rest.
    
""" 

import sys, time, types

from PubCore import handle
from medusa import asyncore
from ZServer import CONNECTION_LIMIT, ZOPE_VERSION
from HTTPServer import zhttp_handler
from zLOG import register_subsystem

from M2Crypto import SSL
from medusa.https_server import https_server, https_channel
from medusa.asyncore import dispatcher


ZSERVER_SSL_VERSION='0.06'


register_subsystem('ZServer HTTPS Server')

class zhttps_handler(zhttp_handler):
    "zhttps handler - sets REMOTE_USER to user's X.509 certificate Subject DN"

    def __init__ (self, module, x509_zope_map, uri_base=None, env=None):
        zhttp_handler.__init__(self, module, uri_base, env)
        self.x509_zope = x509_zope_map

    def get_environment(self, request):
        env = zhttp_handler.get_environment(self, request)
        peer = request.channel.get_peer_cert().get_subject()
        try:
            env['REMOTE_USER'] = self.x509_zope[str(peer)]
        except KeyError:
            pass
        return env


class zhttps_channel(https_channel):
    "https channel"

    closed=0
    zombie_timeout=100*60 # 100 minutes
    
    def __init__(self, server, conn, addr):
        https_channel.__init__(self, server, conn, addr)
        self.queue=[]
        self.working=0
        self.peer_found=0
    
    def push(self, producer, send=1):
        # this is thread-safe when send is false
        # note, that strings are not wrapped in 
        # producers by default
        if self.closed:
            return
        self.producer_fifo.push(producer)
        if send: self.initiate_send()
        
    push_with_producer=push

    def work(self):
        "try to handle a request"
        if not self.working:
            if self.queue:
                self.working=1
                try: module_name, request, response=self.queue.pop(0)
                except: return
                handle(module_name, request, response)
        
    def close(self):
        self.closed=1
        while self.queue:
            self.queue.pop()
        if self.current_request is not None:
            self.current_request.channel=None # break circ refs
            self.current_request=None
        while self.producer_fifo:
            p=self.producer_fifo.first()
            if p is not None and type(p) != types.StringType:
                p.more() # free up resources held by producer
            self.producer_fifo.pop()
        self.del_channel()
        self.socket.set_shutdown(SSL.SSL_SENT_SHUTDOWN|SSL.SSL_RECEIVED_SHUTDOWN)
        self.socket.close()

    def done(self):
        "Called when a publishing request is finished"
        self.working=0
        self.work()

    def kill_zombies(self):
        now = int (time.time())
        for channel in asyncore.socket_map.values():
            if channel.__class__ == self.__class__:
                if (now - channel.creation_time) > channel.zombie_timeout:
                    channel.close()


class zhttps_server(https_server):    
    "https server"
    
    SERVER_IDENT='Zope/%s ZServerSSL/%s' % (ZOPE_VERSION,ZSERVER_SSL_VERSION)
    
    channel_class = zhttps_channel
    shutup = 0

    def __init__(self, ip, port, ssl_ctx, resolver=None, logger_object=None):
        https_server.__init__(self, ip, port, ssl_ctx, resolver, logger_object)
        self.ssl_ctx = ssl_ctx
        
    def log_info(self, message, type='info'):
        if self.shutup: return
        dispatcher.log_info(self, message, type)

    def readable(self):
        return self.accepting and \
                len(asyncore.socket_map) < CONNECTION_LIMIT

    def listen(self, num):
        # override asyncore limits for nt's listen queue size
        self.accepting = 1
        return self.socket.listen (num)

