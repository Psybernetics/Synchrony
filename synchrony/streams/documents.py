# Differential synchronisation using diff-match-patch or operational transforms
# An awareness of events (save/connect/disconnect) in streaming
#
# Think of allocations here in terms of dom fragments.
import time
import copy
from synchrony import app, log
from synchrony.controllers.auth import auth
from flask import session, request, Response

from socketio import socketio_manage
from socketio.packet import encode, decode
from socketio.namespace import BaseNamespace

class DocumentStream(BaseNamespace):
    """
    Manages the lifetime of a connection in relation to channels a user is
    interested in.

    Here a channel is a URL, a user ID or a shared string.

    Channels look like this:

        self.session = {'channels': set(['/documents_main'])}
    
    "/documents" is stored in self.ns_name and corresponds to the
    io.connect("/documents", {"resource":"stream"}); part of your client-side
    code and "main" is the channel name.

    self.join("somesite.net/page") introduces "/documents_somesite.net/page"
    to the set.
    """
    user        = None
    socket_type = "document"
    channel     = () # Available types: url, addr, name.
                     # Eg. ("addr", "alpha/1252322141974278745698082250347869678457931551015/f50068d167fc6")
                     # This type implies we should synchronise with the local
                     # or remote user when they navigate.

    def initialize(self):
        """
        Individual connections have timestamped versions of documents meaning
        they're garbage collected when people disconnect and remaining users
        are left with the official history.
        """
        log("Document stream init")
        self.fragments = []
        self.documents = []
        if 'channels' not in self.session:
            self.session['channels'] = set()

    def broadcast(self, channel, event, *args):
        pkt = dict(type="event",
                   name=event,
                   args=args,
                   endpoint=self.ns_name)
        channel_name = self.get_channel_name(channel)
        for sessid, socket in self.socket.server.sockets.iteritems():
            if 'channels' not in socket.session:
                continue
            if channel_name in socket.session['channels'] \
            and self.socket != socket:
                socket.send_packet(pkt)

    def recv_connect(self):
        self.check_auth()

    def join(self, channel, type="name"):
        self.session['channels'].add(self.get_channel_name(channel))
        self.channel = (type, channel)
        
    def leave(self, channel):
        self.session['channels'].remove(self.get_channel_name(channel))

    def get_channel_name(self, channel):
        return self.ns_name + '_' + channel

    def on_join(self, channel):
        user = auth(self.request)
        if user:
            self.user = user
            log('%s has subscribed to the document stream for "%s"' % \
            (self.user.username, channel))
        else:
            log('An anonymous user has subscribed to the document stream for "%s"' % \
            channel)
        self.join(channel)

    def on_names(self, channel):
        self.check_auth()
        response = []
        channel_name = self.get_channel_name(channel)
        for session_id, socket in self.socket.server.sockets.iteritems():
            if not "rooms" in socket.session:
                continue
            if room_name in socket.session["channels"] \
            and socket != self.socket and socket.user:
                response.append(socket.user.jsonify())
        self.emit({"names": response})

    def on_part(self, channel):
        self.check_auth()
        self.leave(channel)
        self.broadcast(self.channel[1], "part", self.user.jsonify())

    def on_edit(self, update):
        self.check_auth()
        if not self.user:
            log("no user ")
        if self.channel and self.user:
            log('DocumentStream: %s "%s":%i' % \
            (self.user.username, self.channel, len(update)))
            
            body = {"user":self.user.username,"document":update}
            self.broadcast(self.channel[1], "fragment", body)
            
            record = {"time":     time.time(), 
                      "channel":  copy.deepcopy(self.channel),
                      "fragment": update}

            self.emit(self.channel[1], body)

    def recv_disconnect(self):
        if self.user and self.channel:
            log('%s has disconnected from channel %s' % \
            (self.user.username, str(self.channel)))
        elif self.user:
            log('%s has disconnected from an unspecified document stream.' % \
            self.user.username)

    def check_auth(self):
        if not self.user:
            user = auth(self.request)
            if user:
                log("Received document stream connection from %s" % \
                user.username)
                self.user = user

    @property
    def itersockets(self):
        """
        Return other active connections in this same namespace. 
        """
        _ = []
        for c in self.socket.server.sockets.values():
            if c.connected:
                for ns in c.active_ns.values():
                    if ns != self and ns.ns_name == self.ns_name:
                        _.append(ns)
        return _
