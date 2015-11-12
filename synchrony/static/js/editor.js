/* RealTime Wiki 0.0.1
   A soft-realtime collaborative wiki.
   Copyright RedFlag Alert 2015

  Editor.js Edit contenteditable divs and stream the contents.
*/

function Editor(config){
	/* The config should contain an el attribute
	   that defines an element to attach to,
       a page attribute denoting the document title,
       and an output attribute defining where the document
       is rendered

       var editor = new Editor({   
           page: title,
           el: '.editor',
           output: '#md-doc',
           view: App.Views.wikipage
       });

       Handle transmit and receive if the view object has a socket attached
       Sync between localStorage and the server on .save(), .load() and .close()
    */

	this.config = config;
	var self = this;
	console.log(config)

	this.edit = function(data) {
		console.log(data);
		var s = data.replace(/<br\s*[\/]?>/gi, "\n");
		$(self.config.output).html(
			App.markdown.makeHtml(s)
		);
	}

// Network Tx/Rx
	if (this.config.view.socket) {
		console.log("Detected a socket on the input view")
		this.config.view.socket.on('document', function(data){
			console.log(data)
		});

//		Naive method of transmitting edits: send the whole document..
		$(this.config.el).keyup(function(){
			self.config.view.socket.emit('edit', $(self.config.el).html());
		});
	}

	this.load = function(){}
	this.save = function(){}
	this.close = function(){}
}
