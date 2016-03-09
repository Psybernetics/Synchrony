# set of channels, a contacts list, direct messages, message buffers.
from cgi import escape
from synchrony import app, log, db
from synchrony.controllers.auth import auth
from synchrony.streams.utils import Stream, require_auth

class AnonUser(object):
    created  = None
    username = "Unknown"

# Business logic for the global activity stream
class GlobalStream(Stream):
    socket_type = "global_stream"

    def initialize(self):
        self.buffer  = []
        self.inbox   = None
        self.user    = None
#        Make the channels a set
        self.channel = None
        log("Activity stream init")

    @require_auth
    def recv_connect(self):
        """
        Don't adjust self.user.status here as it permits people to return
        to their appear-offline state.
        """
        log("Received activity stream connection from %s" % self.user.username)

    @require_auth
    def on_poll_friends(self):
        self.emit("friend state", self.user.poll_friends(app.routes))

    @require_auth
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

    @require_auth
    def on_poll(self):
        if self.inbox:
            last_message = self.inbox[-1]
            for key, value in last_message.items():
                if key in self.buffer: continue
                self.buffer.append(key)
                self.emit("message", value)

    @require_auth
    def on_msg(self, msg):
        if self.user and self.channel:
            if self.user.created:
                body = {"u":self.user.username,"m":escape(msg)}
            else:
                body = {"u":self.user.username,"m":escape(msg),"a": True}
            log("Message to %s from %s: %s" % (self.channel, self.user.username, msg))
            self.emit_to_room(self.channel, "privmsg", body)
            self.emit("privmsg", body)
        
#    @require_auth
#    def recv_disconnect(self):
#        pass

