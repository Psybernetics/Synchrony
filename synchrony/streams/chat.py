"""
Channels, a contacts list, direct messages, message buffers.
Should loosely base this on IRC with user modes and channel modes, possibly...

Consider also WebRTC session initiation.
"""
from cgi import escape
from synchrony import app, log
from synchrony.controllers.auth import auth
from flask import session, request, Response
from socketio import socketio_manage
from socketio.packet import encode, decode
from socketio.namespace import BaseNamespace
from socketio.mixins import RoomsMixin, BroadcastMixin

class AnonUser(object):
    username = "Unknown"
    created = False

# Business logic for chat
class ChatStream(BaseNamespace, RoomsMixin, BroadcastMixin):
    socket_type = "chat"

    def initialize(self):
        self.user    = None
#        Access to app.routes for
#        admin users to access via /eval
        self.routes  = app.routes
#        TODO: Make the channels a set
        self.channel = None

        # This lets us cycle through stream connections on
        # the httpd and easily determine the session type.
        self.socket.socket_type       = "chat"
        self.socket.appearing_offline = False
        log("init chat stream")

    def recv_connect(self):
        user = auth(self.request)
        if not user:
            self.request_reconnect()
#            self.user = AnonUser()
        else:
            log("Received chat connection from %s" % user.username)
            self.user = user
#            if not can(user.username, "chat"):
#                body = {"message":"Your user group doesn't have permission to chat"}
#                self.emit("disconnect", body)
#                self.send("disconnect")
#                log("%s isn't permitted to chat." % user.username)

    def request_reconnect(self):
        """
        Shortcut for asking a client to reconnect.
        """
        log("Received chat connection before authentication. Requesting client reconnects.")
        self.emit("reconnect", {"m":"Reconnecting.."})

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
        if self.user and self.user.username:
#            if can(self.user.username, "chat"):
            log("%s joined %s" % (self.user.username, channel))
            self.channel = channel
            self.join(channel)
#            else:
#                log("%s tried to join %s" % (self.user.username, channel))

    def on_appear_offline(self, state):
        """
         Flip the boolean self.socket.appearing_offline
         so we're omitted from emit_to_room events on other users.
        """
        if state:
            self.socket.appearing_offline = True
            self.emit("appear_offline",True)
        else:
            self.socket.appearing_offline = False
            self.emit("appear_offline",False)
   
    def emit_to_room(self, room, event, *args):
        """This is sent to all in the room (in this particular Namespace)"""
        pkt = dict(type="event",
                    name=event,
                    args=args,
                    endpoint=self.ns_name)
        room_name = self._get_room_name(room)
        for sessid, socket in self.socket.server.sockets.iteritems():
            if 'rooms' not in socket.session:
                continue
            if room_name in socket.session['rooms'] and self.socket != socket \
            and not socket.appearing_offline:
                socket.send_packet(pkt)

                
    def on_msg(self, msg):
        if self.user and self.channel:
            if self.user.created:
                body = {"u":self.user.username,"m":escape(msg)}
            else:
                body = {"u":self.user.username,"m":escape(msg),"a": True}
            log("Message to %s from %s: %s" % (self.channel, self.user.username, msg))
            self.emit_to_room(self.channel, "privmsg", body)
            self.emit("privmsg", body)
        else:
            self.request_reconnect()

    def on_cmd(self, command):
        if self.user and self.channel:
            if command == "help":
                body = '<strong>Hello and welcome to the help system.</strong>'
                self.emit("response", {"r": body})
            elif command == "usage":
                import resource
                rusage_denom = 1024
                rusage_denom = rusage_denom * rusage_denom
                mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rusage_denom
                body = "<em>Synchrony is currently using <strong>%iMb</strong> of memory.</em>" % mem
                self.emit("response", {"r":body})

            elif ' ' in command:
                cmd, params = command.split(' ',1)
                if cmd == "eval" and self.user.can("eval"):
                    self.emit("response", {"r":"<em>" + escape(str(eval(params))) + "</em>"})
                else:
                    self.emit("response", {"r":"Unknown command <em>%s.</em>" % escape(str(cmd))})
            else:
                self.emit("response", {"r":"Unknown command <em>%s.</em>" % escape(str(command))})

#            if self.user.created:
#                body = {"u":self.user.username,"r":escape(command)}
#            else:
#                body = {"u":self.user.username,"r":escape(command),"a": True}
#            log("Command from %s: %s" % (self.user.username, command))
#            self.emit("response", body)
        else:
            self.request_reconnect()

    def recv_disconnect(self):
#        print "received disconnect"
        pass
