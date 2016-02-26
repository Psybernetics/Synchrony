# set of channels, a contacts list, direct messages, message buffers.
from cgi import escape
from synchrony import log
from synchrony.controllers.auth import auth
from flask import session, request, Response
from socketio import socketio_manage
from socketio.packet import encode, decode
from socketio.namespace import BaseNamespace
from socketio.mixins import RoomsMixin, BroadcastMixin

class AnonUser(object):
    username = "Unknown"
    created = False

# Business logic for the global activity stream
class GlobalStream(BaseNamespace, RoomsMixin, BroadcastMixin):
    socket_type = "global_stream"

    def initialize(self):
        self.buffer = []
        self.inbox = None
        self.user = None
#        Make the channels a set
        self.channel = None
        log("Activity stream init")

    def recv_connect(self):
        user = auth(self.request)
        if user:
            log("Received activity stream connection from %s" % user.username)
            self.user = user
#            if not can(user.username, "chat"):
#                body = {"message":"Your user group doesn't have permission to chat"}
#                self.emit("disconnect", body)
#                self.send("disconnect")
#                log("%s isn't permitted to chat." % user.username)
#        else:
        self.user = AnonUser()

    def recv_message(self, data):
        log(data)
        self.emit("test", data)
        self.socket.send_packet({"test":"hello"})

    def recv_json(self, data):
        self.emit("test", data)
        self.emit_to_room("test", data)
        if self.user:
            log("Received JSON from %s: %s" % (self.user.username, str(data)))
        else:
            log("Received JSON: %s" % str(data))

    def on_join(self, channel):
        # Keep everyone on the same stream generally.
        channel = "public"
        if self.user:
#            if can(self.user.username, "rx_stream"):
            log('%s joined activity stream "%s"' % (self.user.username, channel))
            self.channel = channel
            self.join(channel)
#            else:
#                log("%s tried to join %s" % (self.user.username, channel))

    def on_poll(self):
        if self.inbox:
            last_message = self.inbox[-1]
            for key, value in last_message.items():
                if key in self.buffer: continue
                self.buffer.append(key)
                self.emit("message", value)

    def on_msg(self, msg):
        if self.user and self.channel:
            if self.user.created:
                body = {"u":self.user.username,"m":escape(msg)}
            else:
                body = {"u":self.user.username,"m":escape(msg),"a": True}
            log("Message to %s from %s: %s" % (self.channel, self.user.username, msg))
            self.emit_to_room(self.channel, "privmsg", body)
            self.emit("privmsg", body)
        

    def recv_disconnect(self):
#        print "received disconnect"
        pass
