$(document).ready(function() {
  var socket = io();
  var total_bytes;
  var download_link;
  var downloading;
  var parse_button = $('#parse > input[type=submit]');

  var emptyInfo = function() {
    ids_to_empty = ['video_info', 'audio_formats', 'video_formats', 'download'];
    ids_to_empty.forEach(function(id) {
      $('#'+id).empty();
    });
  }
  parse_button.working = function() {
    this.val('')
  };
  parse_button.reset = function() {
    this.val('Parse')
  };


  socket.on('reconnect', function(msg) {
    emptyInfo();
  });

  socket.on('disconnect', function(msg) {
    emptyInfo();
    $('#download').append('<div class="error message">Connection to server lost</div>')
    if( downloading ) {
      $('#download').append('<div class="info message">Download may still complete.'+
        'Check <a href="'+download_link+'">this link</a> in ten minutes.</div>')
    }
  });

  // the server's best guess at the final location, in case connection is interrupted
  socket.on('filename', function(name){
    download_link = name;
  });


  $("#parse").submit( function(event) {
    emptyInfo();
    var dl_url = $(this).children(":text").val()
    socket.emit('parse', dl_url);
    return false;
  });

  socket.on('parsing', function(_){
    parse_button.working()
  });


  // total bytes will come as an event if more than one file is selected
  socket.on('total_bytes', function(bytes){
    total_bytes = bytes;
  });

  // format and display a json object full of audio and video formats
  socket.on('video_info', function(info) {
    info = $.parseJSON(info);
    parse_button.reset()

    $('#download').html('<form id=start-download><button type=submit>Start Download</button></form>');

    var default_formatter = function(x) { return x; }
    var params = [{
      name: 'title'
    },{
      name: 'uploader'
    },{
      name: 'duration',
      formatter: function(param) {
        s = (param % 60).toString();
        while( (param = Math.floor(param / 60)) > 0 ) {
          s = (param % 60).toString() + ':' + s
        }
        return s;
      }
    //},{
    //  name: 'description'
    }]

    // populate the  general info
    var div = $('#video_info');
    div.append('<h2>video info</h2>')
    params.forEach( function(param) {
      div.append($('<p>').append('<h3>'+param.name+':</h3> ', (param.formatter || default_formatter)(info[param.name])));
    });


    // audio and video need to be displayed differently, but the page elements
    // are created the same way, give each a function that formats it properly
    var formats = [{
      name:'audio_formats',
      descriptor: 'bitrate, compression, filesize',
      formatter: function(format) {
        return format.abr+'k, '+format.acodec+', '+filesize(format.filesize)
      }
    }, {
      name:'video_formats',
      descriptor: 'resolution, compression, filesize',
      formatter: function(format) {
        return format.width+'x'+format.height+'@'+format.fps+'fps, '+format.vcodec+', '+filesize(format.filesize)
      }
    }]

    // fill the dl_info divs with checkboxes for each format
    formats.forEach(function(category) {
      div = $("#"+category.name);
      form = $("<form />");
      label = $('<label />');
      div.append('<h2>'+category.name.replace('_', ' ')+'</h2>', form);
      form.append(label);
      label.append('<input type=radio name='+category.name+' value=0 checked>').append('None');
      info[category.name].forEach(function(format) {
        if(format.vcodec.startsWith('avc'))
          format.vcodec = 'x264';
        if(format.acodec.startsWith('mp4'))
          format.acodec = 'mp4';
        form.append(
          $('<label />').append(
            $('<input type=radio name='+category.name+' value='+format['format_id']+' />')).append(
            category.formatter(format)
          )
        )
      });
      delete info[category.name];
    });


    $('#start-download').submit(function(event) {
      downloading = true;
      socket.emit('start_dl',
        $("input:radio[name=video_formats]:checked").val()+'+'+
        $("input:radio[name=audio_formats]:checked").val()
      );
      var progressbar = $('<progress value="0" max="100" />')
      $('#download').empty().append(progressbar);

      var previous_bytes = 0;
      socket.on('progress', function(progress) {
        progress = $.parseJSON(progress);
        var percent = ((previous_bytes + progress.downloaded_bytes) / (total_bytes || progress.total_bytes)) * 100;
        progressbar.val(percent);
        if( progress.status == "finished" ) {
          previous_bytes += progress.downloaded_bytes;
        }
      });
      return false;
    });

    socket.on('finished', function(link) {
      ['video_info', 'audio_formats', 'video_formats', 'download']
      .forEach(function(id) {
        $('#'+id).empty();
      });
      $('#download').append('<a id=download-file href="'+link+'">Download file</a>')
      downloading = false;
      $('#parse > input[type=submit]').val('Parse')
    });
  });
});
