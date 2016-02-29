/* This is the class for page synchronisation.
 * 
 * var synch = new Synchrony($('.iframe'));
 * synch.save();
 * Consider a map of {channel: Synchrony} pairs.
 *
 * The current strategy revolves around subscribing to a channel named after
 * the active url, a user addr or shared channel name.
 *
 * DOM nodes are matched up to two parent nodes and changes are then reintegrated
 * where they're found to match. The server stores an array of diffs and an array
 * of reference documents.
 * 
 * This should monitor for changes on the DOM itself via all relevant events.
 *
 * The hardest fragment to match is a single character that's the only inhabitant of
 * its parent element.
 *
 * The protocol appears to want two major message types: "document" and "fragment"
 * where "document" is the entire tree and "fragment" is a subtree.
 *
 * dom.patch(subtree)
*/
function SynchronyEditor (el) {

    this.el         = el;
    
    this.document   = el.contents().get(0);

    this.socket     = null;
    
    this.config     = {endpoint: "/documents",
                       channel: "main"}

    this.last_event = null;

    this.connect  = function(endpoint, channel) {
        
        if (endpoint) { this.config.endpoint = endpoint; }
        if (channel)  { this.config.channel  = channel; }

        var socket  = io.connect(this.config.endpoint, {resource: "stream"});
        this.socket = socket;
        socket.emit('join', this.config.channel);
        
        socket.on("fragment", function(data){
            // Someone is sending us some DOM nodes.
            console.log(data);
            parser = new DOMParser();
            doc = parser.parseFromString(data.document, "text/xml");
            // Clean out errors found by the parser.
            var element = doc.getElementsByTagName("parsererror");
            for (index = element.length - 1; index >= 0; index--) {
                    element[index].parentNode.removeChild(element[index]);
            }
            console.log(doc);
            console.log(element);
            var doc_text = $(doc).text();
            console.log("doc_text: "+ doc_text);
            var nodes = "";
            var text_data = "";
    //        doc.children[0].className
            nodes = nodes + doc.children[0].nodeName
            if (doc.children[0].children) {
                nodes = nodes + ' ' + doc.children[0].children[0].nodeName
                if (doc.children[0].children[0].children) {
                    nodes = nodes + ' ' + doc.children[0].children[0].children[0].nodeName
                    text_data = doc.children[0].children[0].children[0].innerHTML
                } else {
                    text_data = doc.children[0].children[0].innerHTML
                }
            } else {
                text_data = doc.children[0].innerHTML
            }
            console.log("nodes: " + nodes);
            console.log("text_data: " + text_data);
            var length = text_data.length;
            // First half
            var c = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(0,Math.ceil(length / 2)) + ')');
            var swapped = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(0,Math.ceil(length / 2)) + ')').first().html(data.document);
            console.log("swap attempt 1:");
            console.log(swapped.length);
            console.log(swapped.text());
            // Second half
            if (swapped.length != 1) {
                c.push.apply(c, $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(Math.ceil(length / 2), length) + ')'));
                var swapped = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(Math.ceil(length / 2), length) + ')').first().html(data.document);
                console.log("swap attempt 2:")
                console.log(swapped.length);
                console.log(swapped.text());
            }
            console.log("c: " + c.length);
            console.log(c);
            for (var i = 0; i < c.length; i++) {
                console.log($(c[i]).text());
            }
        });

        this.el.contents().find('body').on('DOMCharacterDataModified', function(event){

            if (!socket) { this.reconnect(); }

            // Traverse up to two parent nodes and transmit the outerHTML.
            if (event.target.parentElement) {
                if (event.target.parentElement.parentElement) {
                    edit_data = event.target.parentElement.parentElement.outerHTML;
                } else {
                    edit_data = event.target.parentElement.outerHTML;
                }
            } else {
                console.log("1")
                edit_data = event.target.outerHTML;
            }
            
            socket.emit('edit', edit_data);

            console.log(event);
            this.last_event = event;
        });
    }

    // Re-make the socket if asked
    this.reconnect = function () {
        if (this.config.endpoint && this.config.channel) {
            this.connect(this.config.endpoint, this.config.channel);
        }
    }

    // Provide our last revision ID and get the latest copy
    this.poll             = function () {}
    this.save             = function () {}
    this.load             = function () {}
    // undo, redo, insert element etc
    this.commands         = {}
    this.keyBindings      = {}
    this.exec             = function(cmd, toggle, value){
        this.document.execCommand(cmd, toggle, value);
    }
    this.collaborators    = function () {}
}

