# Differential synchronisation using diff-match-patch or operational transforms
# An awareness of events (save/connect/disconnect) in streaming
# TODO: Maintain a buffer of the entire document, with a limit for how many
# characters may be removed in an edit
from cgi import escape
from synchrony import log
from synchrony.controllers.auth import auth
from flask import session, request, Response
from socketio import socketio_manage
from socketio.packet import encode, decode
from socketio.namespace import BaseNamespace
from socketio.mixins import RoomsMixin, BroadcastMixin

class DocumentStream(BaseNamespace, RoomsMixin, BroadcastMixin):
    """
     DCC here stands from document content cache.
    """
    dcc = None
    user = None
    censored = None
    socket_type = "document"

    def initialize(self):
        log("init document stream")
#        self.user = None
        self.document = None

    def recv_connect(self):
        self.check_auth()

    def recv_message(self, data):
        self.emit("test", data)
        print "message"
        print data
        print dir(self.socket)
        self.socket.send_packet({"test":"hello"})
        user = auth(self.request)
        if user:
            print user.username

    def recv_json(self, data):
        self.emit("test", data)
        self.emit_to_room("test", data)
        if self.user and self.document:
            log("Received JSON from %s on %s: %s" % (self.user.username, self.document, str(data)))
        else:
            log("Received JSON: %s" % str(data))

    def on_subscribe(self, document):
        user = auth(self.request)
        if user:
            self.user = user
            log('%s has subscribed to the document stream for "%s"' % (self.user.username, document))
        else:
            log('An anonymous user has subscribed to the document stream for "%s"' % document)
        self.document = document
        self.join(document)

    def on_edit(self, update):
        self.check_auth()
        if not self.user:
            log("no user ")
        if self.document and self.user:
            if self.censored:
                update = censor(update)
            log('DocumentStream: %s "%s":%i' % (self.user.username, self.document, len(update)))
            body = {"user":self.user.username,"document":update}
            self.emit_to_room(self.document, "fragment", body)
            # Tell the transmitter their edit is going through
#            self.emit("document", body)

    def recv_disconnect(self):
        if self.user and self.document:
            log('%s has disconnected from document stream "%s"' % (self.user.username, self.document))
        elif self.user:
            log('%s has disconnected from an unspecified document stream.' % self.user.username)

    def check_auth(self):
        if not self.user:
            user = auth(self.request)
            if user:
                log("Received document stream connection from %s" % user.username)
                self.user = user

def censor(data):
    r = "<expletive>"
    words = ['fuck','shit']
    for w in words:
        data = data.replace(w,r)
    return data
