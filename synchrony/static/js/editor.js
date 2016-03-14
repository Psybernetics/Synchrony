/* This is the class for page synchronisation.
 * 
 * var editor = new SynchronyEditor($('.iframe'));
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
 * The protocol appears to want two major message types: "document" and "fragment".
 *
 * Do not consider a map of {channel: SynchronyEditor} pairs.
 * Do consider:
 *      this.patch(subtree)
 *      this.save()
 * $(selector).replaceWith(subtree)
*/
function SynchronyEditor (el) {

    this.el         = el;
   
    // This assumes el is an <iframe>. 
    this.document   = el.contents().get(0);

    // Global hotkeys
    $(this.document).keydown(function(event){
        if (event.keyCode == 27) { toggle_editing(); }
    });

    this.socket     = null;
    
    this.config     = {endpoint: "/documents",
                       channel: "main"}

    this.events     = [];
    this.appendEvent = function(event){
        if (this.events.length >= 10){
            this.events.shift();
        }
        this.events.push(event);
    }

    this.patch = function(subtree){
        var subtrees = $(this.document).find(subtree);
        console.log(subtrees);
    }

    this.connect  = function(endpoint, channel) {
        
        if (endpoint) { this.config.endpoint = endpoint; }
        if (channel)  { this.config.channel  = channel; }

        this.socket = io.connect(this.config.endpoint, {resource: "stream"});
        this.socket.emit('join', this.config.channel);
        
        this.socket.on("fragment", function(data){
            
            // Someone is sending us some DOM nodes as a string,
            // let's instantiate a parser and turn them into DOM node objects.
            console.log(data);
            parser = new DOMParser();
            
            doc    = parser.parseFromString(data.document, "text/xml");
            
            // Lets' clean out errors found by the parser.
            var element = doc.getElementsByTagName("parsererror");
            for (index = element.length - 1; index >= 0; index--) {
                element[index].parentNode.removeChild(element[index]);
            }
            
            console.log(doc);
            this.last_doc = doc;

            // for (p in doc){ console.log(p, doc[p]); }
            // doc.children.attributes.childNodes.nodeValue

            console.log(element);
           
            // TODO: Match childNode attributes: An <a href="..."> should be matched etc.
            // Ie. Given the following DOM fragment, reintregrate it:
            // <span class="sitebit comhead"> (<a href="/request/news.ycombinator.com/from?site=spiegel.de"><span class="sitestr">spie</span></a>)</span>
            //      var selector = $(this.document).find("element[attr*='attr']").get(0);
            // or 
            //      var selector = this.document.querySelectorAll("el.class.class");
            //      var selector = this.document.querySelectorAll("el[attr*='attr']");
            // var original_subtree = $(selector).clone, $(selector).replaceWith(subtree)

            // match attrs of root element
            // match attrs of next child until done.

            // .find("span.sitebit.comhead a[href*='git']").get(0);
            // Notice how this combines first and last element names.

            var doc_text = $(doc).text();
            console.log("doc_text: "+ doc_text);
            var selector   = "";
            var nodes      = [];
            var text_data  = "";
            var class_list = ""
            
            for (var i = 0; i < doc.documentElement.classList.length; i++){
                class_list = class_list + '.' + doc.documentElement.classList[i];
            };
            console.log(class_list);
            //console.log(doc.documentElement.getAttribute("id"));
            
            nodes.push(doc.children[0].nodeName)
            if (doc.children[0].children) {
                nodes.push(doc.children[0].children[0].nodeName);
                if (doc.children[0].children[0].children) {
                    nodes.push(doc.children[0].children[0].children[0].nodeName);
                    text_data = doc.children[0].children[0].children[0].innerHTML
                } else {
                    text_data = doc.children[0].children[0].innerHTML
                }
            } else {
                text_data = doc.children[0].innerHTML
            }
            
            console.log("nodes: ", nodes);
            console.log("text_data: " + text_data);

            selector = nodes[0] + class_list;
            if (nodes.length > 1) { selector = selector + " " + nodes[nodes.length - 1]; }

            console.log("selector: " + selector);
            console.log($(this.document).find(selector).first());

            // This basic algorithm goes on the length of the text data.
            // A smarter way is to match the parent node and other subnodes.
            // IE using up to three parent node, match subtrees on either side of the
            // modified element.
            var length = text_data.length;
            
            // First half
            var subtree = $(this.document).find(nodes.join(" ") + ':contains(' + text_data.slice(0, Math.ceil(length / 2)) + ')').first().get(0);
            console.log("subtree", subtree);
            for (var i = 0; i <= 1; i++) {
                if (subtree.parentNode){
                    subtree = subtree.parentNode
                }
                console.log("subtree", subtree);
            }
            console.log(data.document);
            //this.last_subtree = subtree;
            //if (subtree.length){ subtree.get(0).replaceWith(data.document); }
            // var swapped = $(subtree).html(data.document);
            var swapped = $(subtree).replaceWith(data.document);
            
            console.log("swap attempt 1:");
            console.log(swapped.length);
            console.log(swapped.text());
            
            // Second half
            if (swapped.length != 1) {
                var subtree = $(this.document).find(nodes.join(" ") + ':contains(' + text_data.slice(Math.ceil(length / 2), length) + ')').first();
                for (var i = 0; i <= 1; i++) {
                    if (subtree.parentNode){
                        subtree = subtree.parentNode
                    }
                    console.log("subtree", subtree);
                }
                var swapped = subtree.html(data.document);
                console.log("swap attempt 2:")
                console.log(swapped.length);
                console.log(swapped.text());
            }
        }.bind(this));

        // The majority of editing events.
        $(this.document).on('DOMCharacterDataModified', function(event){

            if (!this.socket) { this.reconnect(); }

            // Traverse up to ... parent nodes and transmit the outerHTML.

            var subtree = event.target;
            for (var i = 0; i <= 1; i++){
                if ("parentNode" in subtree){
                    subtree = subtree.parentNode;
                }
            }
            console.log(subtree);
            console.log(subtree.outerHTML);
            this.socket.emit("edit", subtree.outerHTML);
            this.appendEvent(event);
        }.bind(this));

        // <br />'s inserted when the return key's hit.
        // Also arbitrary subtrees.
        $(this.document).on("DOMNodeInserted", function(event){
            // Iterate to up to three parentNodes.
            //console.log(event);
            this.appendEvent(event);
        }.bind(this));
 
        $(this.document).on("DOMNodeRemoved", function(event){
            //console.log(event);
            this.appendEvent(event);
        }.bind(this));
 
        // Rarely seen in the wild(?)
        $(this.document).on("DOMNodeSubtreeModified", function(event){
            console.log(event);
            this.appendEvent(event);
        }.bind(this));
    }

    // Re-make the socket if asked
    this.reconnect = function () {
        if (this.config.endpoint && this.config.channel) {
            this.connect(this.config.endpoint, this.config.channel);
        }
    }

    this.sync             = function() {}

    // Provide our last revision ID and get the latest copy
    this.save             = function () {}
    this.load             = function () {}
    // undo, redo, insert element etc
    this.commands         = {}
    this.keyBindings      = {}
    this.exec             = function(cmd, toggle, value){
        var mutation = this.document.execCommand(cmd, toggle, value);
        if (cmd == "createLink") { mutation.target = "_blank"; }
        return mutation;
    }
    this.collaborators    = function () {}
}

